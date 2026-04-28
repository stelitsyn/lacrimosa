#!/usr/bin/env bash
# Stop hook: challenge easy-fix deferrals disguised as scope control.

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

patterns = [
    r"\bscope creep\b",
    r"\bout of scope\b",
    r"\bseparate (pr|pull request|ticket|issue)\b",
    r"\bfollow-?up (pr|pull request|ticket|issue)\b",
    r"\banother session\b",
    r"\bstick to the original task\b",
    r"\bdefer(red)?\b.*\b(later|follow-?up|separate)\b",
]
if not any(re.search(pattern, last_text, re.IGNORECASE) for pattern in patterns):
    sys.exit(0)
if re.search(r"\b(FIXED NOW|TRACKED|ESCALATED)\b|#\d+|github\.com/.+/issues/", last_text):
    sys.exit(0)

message = (
    "Scope-dismissal detected: when an adjacent finding is easy to fix, fix it in the same change. "
    "Only defer genuinely broad, destructive, product-decision, or cross-service work, and then mark it "
    "TRACKED with owner/acceptance criteria/deadline or ESCALATED with the user decision needed."
)
print(json.dumps({"systemMessage": message}))
PY
