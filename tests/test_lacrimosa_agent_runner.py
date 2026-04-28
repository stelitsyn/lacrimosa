from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import lacrimosa_agent_runner as runner


def test_claude_backend_uses_claude_print(monkeypatch):
    monkeypatch.delenv("LACRIMOSA_AGENT_BACKEND", raising=False)
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"ok": true}',
        stderr="",
    )
    with patch("scripts.lacrimosa_agent_runner.subprocess.run", return_value=completed) as run:
        result = runner.run_agent_prompt("hello", purpose="test", json_mode=True)

    cmd = run.call_args.args[0]
    assert cmd[:2] == ["claude", "--print"]
    assert cmd[-2:] == ["-p", "hello"]
    assert "input" not in run.call_args.kwargs
    assert result.parsed_json == {"ok": True}


def test_codex_backend_uses_stdin_and_never_claude(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LACRIMOSA_AGENT_BACKEND", "codex")
    monkeypatch.setenv("CODEX_MODEL", "gpt-test")
    monkeypatch.setenv("CODEX_REASONING_EFFORT", "low")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")
    with patch("scripts.lacrimosa_agent_runner.subprocess.run", return_value=completed) as run:
        runner.run_agent_prompt("prompt", purpose="test", cwd=tmp_path, dangerous=True)

    cmd = run.call_args.args[0]
    assert cmd[:3] == ["codex", "exec", "-"]
    assert "claude" not in cmd
    assert "--model" in cmd and "gpt-test" in cmd
    assert "model_reasoning_effort=low" in cmd
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert run.call_args.kwargs["input"] == "prompt"


def test_start_codex_worker_writes_prompt_to_stdin(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LACRIMOSA_AGENT_BACKEND", "codex")
    proc = Mock()
    proc.stdin = Mock()
    proc.pid = 123
    with patch("scripts.lacrimosa_agent_runner.subprocess.Popen", return_value=proc) as popen:
        result = runner.start_agent_prompt("worker prompt", purpose="dispatch", cwd=tmp_path)

    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["codex", "exec", "-"]
    proc.stdin.write.assert_called_once_with("worker prompt")
    proc.stdin.close.assert_called_once()
    assert result is proc


def test_start_claude_worker_uses_worktree(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LACRIMOSA_AGENT_BACKEND", "claude")
    proc = Mock(pid=456)
    with patch("scripts.lacrimosa_agent_runner.subprocess.Popen", return_value=proc) as popen:
        runner.start_agent_prompt(
            "worker prompt",
            purpose="dispatch",
            cwd=tmp_path,
            worktree_name="lacrimosa-ISSUE-1",
        )

    cmd = popen.call_args.args[0]
    assert cmd[0] == "claude"
    assert "--worktree" in cmd
    assert "lacrimosa-ISSUE-1" in cmd
