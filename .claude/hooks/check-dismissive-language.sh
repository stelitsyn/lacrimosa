#!/usr/bin/env bash
# Stop hook: scan the last assistant message for dismissive findings language.

set -eo pipefail

payload=$(cat)

HOOK_PAYLOAD="$payload" python3 - <<'PY'
import json
import os
import re
import sys

try:
    payload = json.loads(os.environ.get("HOOK_PAYLOAD", "{}"))
except Exception:
    sys.exit(0)

transcript_path = payload.get("transcript_path", "")
if not transcript_path:
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
            content = message.get("content")
            if content is None:
                content = (message.get("message") or {}).get("content")
            parts = []
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
            if parts:
                last_text = "\n".join(parts)
except OSError:
    sys.exit(0)

patterns = [
    r"pre-existing.*not.*(block|blocker|blocking)",
    r"pre-existing.*(drift|finding|issue|error)",
    r"not.*caused.*by.*this (release|change|pr)",
    r"deferred.*to.*follow-?up",
    r"long-standing.*drift",
    r"will fix later",
    r"accepted risk",
    r"not a regression from",
    r"leaving as-is",
    r"(unrelated to|out of scope for) (this|the current) (release|pr|change|task)",
    r"skip.*because.*pre-existing",
]
matches = [pattern for pattern in patterns if re.search(pattern, last_text, re.IGNORECASE | re.DOTALL)]
if not matches:
    sys.exit(0)

has_marker = re.search(r"\b(FIXED NOW|TRACKED|ESCALATED)\b|#\d+|github\.com/.+/issues/", last_text)
if has_marker:
    sys.exit(0)

message = (
    "Fix-findings rule violation: the last assistant message dismissed a finding as unrelated, "
    "pre-existing, or deferred without mitigation. Every finding must be FIXED NOW, TRACKED "
    "with owner plus acceptance criteria plus deadline, or ESCALATED with the exact user decision needed."
)
print(json.dumps({"systemMessage": message}))
PY
