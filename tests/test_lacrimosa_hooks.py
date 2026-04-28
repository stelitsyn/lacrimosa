from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_hook(name: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(REPO_ROOT / ".claude" / "hooks" / name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_enforce_fix_findings_blocks_unrelated_without_marker():
    result = _run_hook(
        "enforce-fix-findings.sh",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "REPORT.md",
                "content": "The failing tests are unrelated to this change, so leaving as-is.",
            },
        },
    )

    assert result.returncode == 2
    assert "BLOCKED" in result.stderr


def test_enforce_fix_findings_allows_tracked_marker():
    result = _run_hook(
        "enforce-fix-findings.sh",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "REPORT.md",
                "content": "This is unrelated to this change. TRACKED: owner, acceptance criteria, deadline.",
            },
        },
    )

    assert result.returncode == 0


def test_stop_hook_emits_system_message_for_unrelated_dismissal(tmp_path: Path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"role": "assistant", "content": "One failure is pre-existing and not blocking."}) + "\n"
    )

    result = _run_hook("check-dismissive-language.sh", {"transcript_path": str(transcript)})

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "systemMessage" in payload
    assert "FIXED NOW" in payload["systemMessage"]


def test_handoff_hook_challenges_reflex_pause(tmp_path: Path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(json.dumps({"role": "assistant", "content": "Should I proceed?"}) + "\n")

    result = _run_hook("challenge-handoff.sh", {"transcript_path": str(transcript)})

    assert result.returncode == 0
    assert "systemMessage" in json.loads(result.stdout)


def test_scope_hook_challenges_follow_up_deferral(tmp_path: Path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"role": "assistant", "content": "That is scope creep, so I will handle it in a follow-up ticket."}) + "\n"
    )

    result = _run_hook("challenge-scope-creep-dismissal.sh", {"transcript_path": str(transcript)})

    assert result.returncode == 0
    assert "systemMessage" in json.loads(result.stdout)
