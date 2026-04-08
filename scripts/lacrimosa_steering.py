"""Lacrimosa Linear steering — parse and execute steering commands from Linear comments.

Enables users to steer Lacrimosa by tagging it in Linear issue comments.
Supported commands: rework, reconsider, pause, resume, prioritize, deprioritize, cancel.

The conductor cycle calls these pure functions; Linear API calls (polling comments,
posting acknowledgments) happen at the conductor level via MCP tools.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from scripts.lacrimosa_types import SteeringCommand, SteeringCommandType

# -- Constants ---------------------------------------------------------------

# Regex to detect Lacrimosa mentions (but not inside URLs)
_MENTION_PATTERN = re.compile(
    r"(?<![/\w])@?lacrimosa\b",
    re.IGNORECASE,
)

# URL pattern to exclude false-positive mentions inside URLs
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

# Command keyword → SteeringCommandType mapping
# Order matters: first match wins, so put aliases before they could be
# shadowed by shorter patterns.
_COMMAND_KEYWORDS: list[tuple[re.Pattern[str], SteeringCommandType]] = [
    (re.compile(r"\b(?:rework|redo)\b", re.IGNORECASE), SteeringCommandType.REWORK),
    (re.compile(r"\breconsider\b", re.IGNORECASE), SteeringCommandType.RECONSIDER),
    (re.compile(r"\b(?:unpause|resume)\b", re.IGNORECASE), SteeringCommandType.RESUME),
    (re.compile(r"\b(?:pause|stop|hold)\b", re.IGNORECASE), SteeringCommandType.PAUSE),
    (re.compile(r"\b(?:prioritize|urgent)\b", re.IGNORECASE), SteeringCommandType.PRIORITIZE),
    (re.compile(r"\bdeprioritize\b", re.IGNORECASE), SteeringCommandType.DEPRIORITIZE),
    (re.compile(r"\bcancel\b", re.IGNORECASE), SteeringCommandType.CANCEL),
]


# -- Detection ---------------------------------------------------------------


def is_steering_comment(body: str) -> bool:
    """Check if a comment body mentions Lacrimosa (not inside a URL)."""
    # Strip URLs first to avoid false positives
    text_without_urls = _URL_PATTERN.sub("", body)
    return bool(_MENTION_PATTERN.search(text_without_urls))


def should_process_comment(comment_id: str, processed_ids: set[str]) -> bool:
    """Check if a comment should be processed (not empty, not already processed)."""
    if not comment_id:
        return False
    return comment_id not in processed_ids


# -- Parsing -----------------------------------------------------------------


def parse_steering_command(
    body: str,
    issue_id: str,
    comment_id: str,
) -> SteeringCommand | None:
    """Parse a Linear comment body for a steering command.

    Returns SteeringCommand if a recognized command is found, None otherwise.
    The comment must mention Lacrimosa AND contain a recognized command keyword.
    """
    if not is_steering_comment(body):
        return None

    # Search for command keywords
    for pattern, command_type in _COMMAND_KEYWORDS:
        if pattern.search(body):
            context = _extract_context(body, pattern)
            return SteeringCommand(
                command_type=command_type,
                issue_id=issue_id,
                comment_id=comment_id,
                context=context,
            )

    return None


def _extract_context(body: str, command_pattern: re.Pattern[str]) -> str:
    """Extract context from a steering comment (text after the command keyword).

    Strips the @lacrimosa mention and command keyword, returning the rest as context.
    """
    # Remove @lacrimosa mention
    text = _MENTION_PATTERN.sub("", body).strip()
    # Remove the command keyword
    text = command_pattern.sub("", text).strip()
    # Remove leading punctuation/dashes
    text = re.sub(r"^[\s,\-—:]+", "", text).strip()
    return text


# -- Execution ---------------------------------------------------------------


def execute_command(
    cmd: SteeringCommand,
    state: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Execute a steering command against the current state.

    Returns (new_state, action_description). Does NOT mutate the input state.
    """
    state = copy.deepcopy(state)
    issues = state.get("issues", {})

    if cmd.issue_id not in issues:
        return state, f"Issue {cmd.issue_id} not found in tracked issues"

    issue = issues[cmd.issue_id]

    match cmd.command_type:
        case SteeringCommandType.REWORK:
            issue["state"] = "RetryQueued"
            issue["retry_count"] = 0
            issue["steering_context"] = cmd.context
            _remove_active_worker(state, cmd.issue_id)
            action = f"Issue {cmd.issue_id} queued for rework from scratch"

        case SteeringCommandType.RECONSIDER:
            issue["state"] = "Identified"
            issue["steering_context"] = cmd.context
            _remove_active_worker(state, cmd.issue_id)
            action = f"Issue {cmd.issue_id} sent back to research/architecture phase"

        case SteeringCommandType.PAUSE:
            current_state = issue.get("state", "")
            if current_state == "Paused":
                action = f"Issue {cmd.issue_id} is already paused"
            else:
                issue["paused_from"] = current_state
                issue["state"] = "Paused"
                action = f"Issue {cmd.issue_id} paused (was: {current_state})"

        case SteeringCommandType.RESUME:
            if issue.get("state") != "Paused":
                action = f"Issue {cmd.issue_id} is not paused — no action taken"
            else:
                resumed_state = issue.pop("paused_from", "Implementation")
                issue["state"] = resumed_state
                action = f"Issue {cmd.issue_id} resumed to {resumed_state}"

        case SteeringCommandType.PRIORITIZE:
            old_priority = issue.get("priority", 3)
            issue["priority"] = 1
            action = f"Issue {cmd.issue_id} priority changed from {old_priority} to 1 (Urgent)"

        case SteeringCommandType.DEPRIORITIZE:
            old_priority = issue.get("priority", 3)
            issue["priority"] = 4
            action = f"Issue {cmd.issue_id} priority changed from {old_priority} to 4 (Low)"

        case SteeringCommandType.CANCEL:
            issue["state"] = "Cancelled"
            _remove_active_worker(state, cmd.issue_id)
            action = f"Issue {cmd.issue_id} cancelled"

        case _:
            action = f"Unknown command type: {cmd.command_type}"

    state["issues"][cmd.issue_id] = issue
    return state, action


def _remove_active_worker(state: dict[str, Any], issue_id: str) -> None:
    """Remove an active worker for the given issue (in-place)."""
    state.get("pipeline", {}).get("active_workers", {}).pop(issue_id, None)


# -- Acknowledgment ----------------------------------------------------------


def build_acknowledgment(cmd: SteeringCommand, action_taken: str) -> str:
    """Build a markdown acknowledgment message to post on the Linear issue."""
    emoji_map = {
        SteeringCommandType.REWORK: "🔄",
        SteeringCommandType.RECONSIDER: "🤔",
        SteeringCommandType.PAUSE: "⏸️",
        SteeringCommandType.RESUME: "▶️",
        SteeringCommandType.PRIORITIZE: "🔥",
        SteeringCommandType.DEPRIORITIZE: "📉",
        SteeringCommandType.CANCEL: "🚫",
    }
    emoji = emoji_map.get(cmd.command_type, "📋")

    parts = [
        f"{emoji} **Lacrimosa Steering — {cmd.command_type.value.title()}**",
        "",
        f"**Issue:** {cmd.issue_id}",
        f"**Command:** `{cmd.command_type.value}`",
        f"**Action:** {action_taken}",
    ]

    if cmd.context:
        parts.extend(["", f"**Context:** {cmd.context}"])

    parts.extend(["", "---", "*Processed by Lacrimosa conductor steering*"])

    return "\n".join(parts)
