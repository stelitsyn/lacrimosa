#!/usr/bin/env bash
# Stop hook: challenge reflex handoffs when the next action is agent-executable.

set -eo pipefail

payload=$(cat)

HOOK_PAYLOAD="$payload" python3 - <<'PY'
import json
import os
import re
import sys

try:
    transcript_path = json.loads(os.environ.get("HOOK_PAYLOAD", "{}")).get("transcript_path", "")
except Exception:
    sys.exit(0)

last_text = ""
try:
    with open(transcript_path, encoding="utf-8", errors="ignore") as transcript:
        for line in transcript:
            try:
                message = json.loads(line)
            except Exception:
                continue
            role = message.get("role") or (message.get("message") or {}).get("role")
            if role != "assistant":
                continue
            content = message.get("content") or (message.get("message") or {}).get("content")
            if isinstance(content, str):
                last_text = content
            elif isinstance(content, list):
                last_text = "\n".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
except OSError:
    sys.exit(0)

handoff_patterns = [
    r"\byour turn\b",
    r"\bover to you\b",
    r"\blet me know (when|if|how|whether)\b",
    r"\bwould you like me to\b",
    r"\bshould i (proceed|continue|run|commit|push|apply|fix|go)\b",
    r"\bshall i (proceed|continue|run|commit|push|apply|fix|go)\b",
    r"\bawaiting your approval\b",
]
allowlist_patterns = [
    r"\bprod(uction)?\s+(deploy|migration|release)\b",
    r"\bbilling\s+(mutation|change|update)\b",
    r"\bforce[-\s]push.*(main|master)\b",
    r"\bsend\s+(email|message)\s+to\b.*(customer|real user)",
    r"\bdestructive\b",
]

if not any(re.search(pattern, last_text, re.IGNORECASE) for pattern in handoff_patterns):
    sys.exit(0)
if any(re.search(pattern, last_text, re.IGNORECASE) for pattern in allowlist_patterns):
    sys.exit(0)

message = (
    "Reflex handoff detected: do not stop with 'should I proceed' or similar when the next action "
    "is safe for the agent to perform. Continue with local edits, tests, docs, and reports unless "
    "the action is destructive, production, billing/customer-facing, or explicitly approval-gated."
)
print(json.dumps({"systemMessage": message}))
PY
