#!/usr/bin/env bash
# PreToolUse hook: require every surfaced finding to be fixed, tracked, or escalated.

set -eo pipefail

payload=$(cat)

HOOK_PAYLOAD="$payload" python3 - <<'PY'
import json
import os
import re
import sys

try:
    data = json.loads(os.environ.get("HOOK_PAYLOAD", "{}"))
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
if tool not in {"Write", "Edit", "Bash"}:
    sys.exit(0)

tool_input = data.get("tool_input") or {}
if tool == "Bash":
    text = "\n---\n".join([tool_input.get("command", ""), tool_input.get("description", "")])
    target = "Bash payload"
else:
    target = tool_input.get("file_path", "edited content")
    lowered = target.lower()
    if not (
        lowered.endswith(".md")
        or "report" in lowered
        or "audit" in lowered
        or "finding" in lowered
        or "qa" in lowered
        or "security" in lowered
        or "compliance" in lowered
        or "/output/" in lowered
    ):
        sys.exit(0)
    text = tool_input.get("content") or tool_input.get("new_string") or ""

if not text:
    sys.exit(0)

patterns = [
    r"pre-existing.*not.*(block|blocker|blocking)",
    r"pre-existing.*(drift|finding|issue|error)",
    r"not.*caused.*by.*this (release|change|pr)",
    r"deferred.*to.*follow-?up",
    r"known issue.*leaving as-is",
    r"long-standing.*drift",
    r"will fix later",
    r"accepted risk",
    r"not a regression from",
    r"leaving as-is",
    r"(unrelated to|out of scope for) (this|the current) (release|pr|change|task)",
    r"skip.*because.*pre-existing",
    r"(ignore|ignoring).*pre-existing",
]

matches = [pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE | re.DOTALL)]
if not matches:
    sys.exit(0)

marker = re.search(r"\b(FIXED NOW|TRACKED|ESCALATED)\b|#\d+|github\.com/.+/issues/", text)
if marker:
    print(
        "[enforce-fix-findings] Dismissive language detected, but a mitigation marker is present. "
        "Verify each finding has FIXED NOW, TRACKED with owner/acceptance criteria/deadline, or ESCALATED.",
        file=sys.stderr,
    )
    sys.exit(0)

print(f"[enforce-fix-findings] BLOCKED: {target} dismisses findings without mitigation.", file=sys.stderr)
print("Matched patterns:", file=sys.stderr)
for pattern in matches:
    print(f"  - {pattern}", file=sys.stderr)
print("Every finding must be FIXED NOW, TRACKED with owner/acceptance criteria/deadline, or ESCALATED.", file=sys.stderr)
sys.exit(2)
PY
