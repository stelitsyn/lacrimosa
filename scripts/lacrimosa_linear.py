"""Lacrimosa Linear API client — posts as Lacrimosa, not as the human operator.

Uses Lacrimosa's own API key from ~/.claude/lacrimosa/linear-api-key
so all comments, status updates, and issue changes show as "Lacrimosa"
in Linear's activity feed.

For reads (issue queries, comment fetching), either identity works fine.
For writes (comments, status changes), use these functions to post as Lacrimosa.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from scripts import lacrimosa_config

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

logger = logging.getLogger(__name__)

API_KEY_PATH = Path.home() / ".claude" / "lacrimosa" / "linear-api-key"
GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"

# Team member IDs for @mentions in Linear comments.
# Linear markdown supports @[Name](user-uuid) for tagging.
TEAM_MEMBERS = {
    m["key"]: {"id": m["id"], "name": m["name"]}
    for m in lacrimosa_config.get("linear.team_members")
}


def mention(name: str) -> str:
    """Generate a Linear @mention for a team member.

    Usage in comment bodies:
        f"Hey {mention('some_user')}, this needs your review."

    Args:
        name: Team member key from config (e.g. lacrimosa).

    Returns:
        Linear mention markdown, e.g. @Team Member
    """
    member = TEAM_MEMBERS.get(name.lower())
    if not member:
        return f"@{name}"
    return f"@{member['name']}"


def _load_api_key() -> str:
    """Load Lacrimosa's Linear API key from disk."""
    if not API_KEY_PATH.exists():
        raise FileNotFoundError(
            f"Lacrimosa Linear API key not found at {API_KEY_PATH}. "
            "Create the key at linear.app/settings/api as the Lacrimosa user."
        )
    key = API_KEY_PATH.read_text().strip()
    if not key:
        raise ValueError("Lacrimosa Linear API key file is empty")
    return key


def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against Linear API as Lacrimosa."""
    api_key = _load_api_key()
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_ENDPOINT,
        data=data,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("Linear API error %d: %s", exc.code, body[:500])
        raise
    except urllib.error.URLError as exc:
        logger.error("Linear API connection error: %s", exc.reason)
        raise

    if "errors" in result:
        error_msgs = "; ".join(e.get("message", "") for e in result["errors"])
        logger.error("Linear GraphQL errors: %s", error_msgs)
        raise RuntimeError(f"Linear GraphQL errors: {error_msgs}")

    return result.get("data", {})


# -- Public API: Write operations (as Lacrimosa) ----------------------------


def create_comment(issue_id: str, body: str) -> dict[str, Any]:
    """Post a comment on a Linear issue as Lacrimosa.

    Args:
        issue_id: The Linear issue UUID (not the short identifier).
        body: Markdown comment body.

    Returns:
        Comment data dict with id, createdAt.
    """
    query = """
    mutation($issueId: String!, $body: String!) {
        commentCreate(input: { issueId: $issueId, body: $body }) {
            success
            comment { id createdAt }
        }
    }
    """
    result = _graphql(query, {"issueId": issue_id, "body": body})
    return result.get("commentCreate", {}).get("comment", {})


def update_issue_state(issue_id: str, state_id: str) -> bool:
    """Update an issue's state (status) as Lacrimosa.

    Args:
        issue_id: The Linear issue UUID.
        state_id: The target state UUID (e.g., Todo, In Progress, Done).

    Returns:
        True if successful.
    """
    query = """
    mutation($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
        }
    }
    """
    result = _graphql(query, {"id": issue_id, "stateId": state_id})
    return result.get("issueUpdate", {}).get("success", False)


def update_issue_priority(issue_id: str, priority: int) -> bool:
    """Update an issue's priority as Lacrimosa.

    Args:
        issue_id: The Linear issue UUID.
        priority: Priority level (0=None, 1=Urgent, 2=High, 3=Normal, 4=Low).

    Returns:
        True if successful.
    """
    query = """
    mutation($id: String!, $priority: Int!) {
        issueUpdate(id: $id, input: { priority: $priority }) {
            success
        }
    }
    """
    result = _graphql(query, {"id": issue_id, "priority": priority})
    return result.get("issueUpdate", {}).get("success", False)


def update_issue_project(issue_id: str, project_id: str) -> bool:
    """Assign an issue to a project as Lacrimosa.

    Args:
        issue_id: The Linear issue UUID.
        project_id: The project UUID.

    Returns:
        True if successful.
    """
    query = """
    mutation($id: String!, $projectId: String!) {
        issueUpdate(id: $id, input: { projectId: $projectId }) {
            success
        }
    }
    """
    result = _graphql(query, {"id": issue_id, "projectId": project_id})
    return result.get("issueUpdate", {}).get("success", False)


def update_issue_assignee(issue_id: str, assignee_id: str) -> bool:
    """Assign an issue to a user as Lacrimosa.

    Args:
        issue_id: The Linear issue UUID.
        assignee_id: The user UUID to assign to.

    Returns:
        True if successful.
    """
    query = """
    mutation($id: String!, $assigneeId: String!) {
        issueUpdate(id: $id, input: { assigneeId: $assigneeId }) {
            success
        }
    }
    """
    result = _graphql(query, {"id": issue_id, "assigneeId": assignee_id})
    return result.get("issueUpdate", {}).get("success", False)


def assign_to_lacrimosa(issue_id: str) -> bool:
    """Assign an issue to the Lacrimosa bot user."""
    return update_issue_assignee(issue_id, TEAM_MEMBERS["lacrimosa"]["id"])


# -- Public API: Read operations (as Lacrimosa) -----------------------------


def get_issue_by_number(number: int) -> dict[str, Any] | None:
    """Look up a Linear issue by KAL number. Returns issue data or None."""
    query = """
    query($number: Float!) {
        issues(filter: { number: { eq: $number } }) {
            nodes { id identifier title state { id name } priority }
        }
    }
    """
    result = _graphql(query, {"number": number})
    nodes = result.get("issues", {}).get("nodes", [])
    return nodes[0] if nodes else None


def get_issue_comments(issue_id: str, first: int = 20) -> list[dict[str, Any]]:
    """Get recent comments on an issue.

    Args:
        issue_id: The Linear issue UUID.
        first: Max number of comments to return.

    Returns:
        List of comment dicts with id, body, user.name, createdAt.
    """
    query = """
    query($issueId: String!, $first: Int!) {
        issue(id: $issueId) {
            comments(first: $first, orderBy: createdAt) {
                nodes {
                    id
                    body
                    user { id name }
                    createdAt
                }
            }
        }
    }
    """
    result = _graphql(query, {"issueId": issue_id, "first": first})
    return result.get("issue", {}).get("comments", {}).get("nodes", [])


def create_issue(
    title: str,
    team_id: str,
    description: str = "",
    priority: int = 3,
    state_id: str | None = None,
    assignee_id: str | None = None,
    label_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new Linear issue as Lacrimosa.

    Returns:
        Issue data dict with id, identifier, url.
    """
    variables: dict[str, Any] = {
        "title": title,
        "teamId": team_id,
        "description": description,
        "priority": priority,
    }
    input_fields = [
        "title: $title",
        "teamId: $teamId",
        "description: $description",
        "priority: $priority",
    ]
    var_decls = [
        "$title: String!",
        "$teamId: String!",
        "$description: String!",
        "$priority: Int!",
    ]

    if state_id:
        variables["stateId"] = state_id
        input_fields.append("stateId: $stateId")
        var_decls.append("$stateId: String!")
    if assignee_id:
        variables["assigneeId"] = assignee_id
        input_fields.append("assigneeId: $assigneeId")
        var_decls.append("$assigneeId: String!")
    if label_ids:
        variables["labelIds"] = label_ids
        input_fields.append("labelIds: $labelIds")
        var_decls.append("$labelIds: [String!]!")

    query = f"""
    mutation({', '.join(var_decls)}) {{
        issueCreate(input: {{ {', '.join(input_fields)} }}) {{
            success
            issue {{ id identifier url }}
        }}
    }}
    """
    result = _graphql(query, variables)
    return result.get("issueCreate", {}).get("issue", {})


def update_profile_status(
    emoji: str,
    label: str,
    description: str | None = None,
) -> bool:
    """Update Lacrimosa's Linear profile status visible to all team members.

    Called every conductor cycle to show current state at a glance.

    Args:
        emoji: Status emoji (e.g., "🟢", "🟡", "🔴", "⏸️").
        label: Short status text (e.g., "Running | 3 active workers").
        description: Optional longer profile description with current dashboard.

    Returns:
        True if successful.
    """
    user_id = TEAM_MEMBERS["lacrimosa"]["id"]
    input_parts = [f'statusEmoji: "{emoji}"', f'statusLabel: "{_escape_gql(label)}"']
    if description is not None:
        input_parts.append(f'description: "{_escape_gql(description)}"')

    query = f"""
    mutation {{
        userUpdate(id: "{user_id}", input: {{ {', '.join(input_parts)} }}) {{
            success
        }}
    }}
    """
    result = _graphql(query)
    return result.get("userUpdate", {}).get("success", False)


def build_profile_description(state: dict[str, Any]) -> str:
    """Build a profile description from current Lacrimosa state.

    Shows a compact dashboard in the profile visible to all Linear users.
    """
    system_state = state.get("system_state", "Unknown")
    throttle = state.get("rate_limits", {}).get("throttle_level", "unknown")
    active_workers = state.get("pipeline", {}).get("active_workers", {})
    worker_count = len(active_workers)

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = state.get("daily_counters", {}).get(today, {})
    dispatched_today = daily.get("workers_spawned", 0)

    lines = [
        f"Autonomous engineering engine for {lacrimosa_config.get('product.name')}.",
        "",
        f"State: {system_state} | Throttle: {throttle.upper()}",
        f"Active workers: {worker_count}",
        f"Dispatched today: {dispatched_today}",
    ]

    if active_workers:
        lines.append("")
        lines.append("Current work:")
        for issue_id, wk in list(active_workers.items())[:5]:
            if not isinstance(wk, dict):
                continue
            phase = wk.get("phase", "?")
            lines.append(f"  {issue_id}: {phase}")

    last_poll = state.get("last_poll") or state.get("steering", {}).get("last_poll")
    if last_poll:
        lines.extend(["", f"Last cycle: {last_poll}"])

    return "\n".join(lines)


def build_profile_status_emoji(state: dict[str, Any]) -> str:
    """Pick the right status emoji based on system state."""
    system_state = state.get("system_state", "Stopped")
    throttle = state.get("rate_limits", {}).get("throttle_level", "green")

    if system_state != "Running":
        return "⏹️"
    if throttle == "red":
        return "🔴"
    if throttle == "yellow":
        return "🟡"
    return "🟢"


def build_profile_status_label(state: dict[str, Any]) -> str:
    """Build a short status label from state."""
    system_state = state.get("system_state", "Stopped")
    if system_state != "Running":
        return f"{system_state}"

    worker_count = len(state.get("pipeline", {}).get("active_workers", {}))
    throttle = state.get("rate_limits", {}).get("throttle_level", "green")
    return f"Running | {worker_count} workers | {throttle.upper()}"


def _escape_gql(s: str) -> str:
    """Escape a string for inline GraphQL."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def whoami() -> dict[str, Any]:
    """Check Lacrimosa's identity. Returns viewer data."""
    result = _graphql("{ viewer { id name email } }")
    return result.get("viewer", {})
