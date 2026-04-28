"""Backend-neutral agent dispatch helpers for Lacrimosa.

Claude remains the default backend. Operators may select Codex by setting
``LACRIMOSA_AGENT_BACKEND=codex`` and providing the corresponding CLI/runtime
environment.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class AgentRunResult:
    """Completed agent invocation."""

    stdout: str
    stderr: str
    returncode: int
    parsed_json: Any | None = None


def current_backend() -> str:
    """Return the selected agent backend."""
    backend = os.environ.get("LACRIMOSA_AGENT_BACKEND", "claude").strip().lower()
    if backend not in {"claude", "codex"}:
        raise ValueError(f"Unsupported LACRIMOSA_AGENT_BACKEND: {backend!r}")
    return backend


def run_agent_prompt(
    prompt: str,
    *,
    purpose: str,
    timeout: int | float | None = None,
    json_mode: bool = False,
    dangerous: bool = False,
    cwd: str | Path | None = None,
    extra_add_dirs: list[str | Path] | None = None,
) -> AgentRunResult:
    """Run one prompt through the configured agent backend and wait for output."""
    backend = current_backend()
    cwd_path = Path(cwd) if cwd is not None else _project_dir()
    cmd = _build_command(
        backend,
        prompt=prompt,
        json_mode=json_mode,
        dangerous=dangerous,
        cwd=cwd_path,
        extra_add_dirs=extra_add_dirs,
    )
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout or DEFAULT_TIMEOUT_SECONDS,
        "cwd": str(cwd_path),
    }
    if backend == "codex":
        proc = subprocess.run(cmd, input=prompt, **kwargs)
    else:
        proc = subprocess.run(cmd, **kwargs)
    parsed = _parse_json(proc.stdout) if json_mode and proc.returncode == 0 else None
    return AgentRunResult(
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        parsed_json=parsed,
    )


def start_agent_prompt(
    prompt: str,
    *,
    purpose: str,
    json_mode: bool = False,
    dangerous: bool = False,
    cwd: str | Path | None = None,
    extra_add_dirs: list[str | Path] | None = None,
    worktree_name: str | None = None,
) -> subprocess.Popen:
    """Start an asynchronous agent process for long-running worker dispatch."""
    backend = current_backend()
    cwd_path = Path(cwd) if cwd is not None else _project_dir()
    env = os.environ.copy()
    if worktree_name:
        env["LACRIMOSA_WORKTREE_NAME"] = worktree_name
    cmd = _build_command(
        backend,
        prompt=prompt,
        json_mode=json_mode,
        dangerous=dangerous,
        cwd=cwd_path,
        extra_add_dirs=extra_add_dirs,
        worktree_name=worktree_name,
    )
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd_path),
        stdin=subprocess.PIPE if backend == "codex" else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=env,
    )
    if backend == "codex" and proc.stdin is not None:
        proc.stdin.write(prompt)
        proc.stdin.close()
    return proc


def _build_command(
    backend: str,
    *,
    prompt: str,
    json_mode: bool,
    dangerous: bool,
    cwd: Path,
    extra_add_dirs: list[str | Path] | None,
    worktree_name: str | None = None,
) -> list[str]:
    if backend == "claude":
        cmd = ["claude", "--print"]
        if json_mode:
            cmd.extend(["--output-format", "json"])
        if dangerous:
            cmd.append("--dangerously-skip-permissions")
        if worktree_name:
            cmd.extend(["--worktree", worktree_name])
        for add_dir in extra_add_dirs or []:
            cmd.extend(["--add-dir", str(add_dir)])
        cmd.extend(["-p", prompt])
        return cmd

    cmd = [
        "codex",
        "exec",
        "-",
        "--model",
        os.environ.get("CODEX_MODEL", "gpt-5.5"),
        "-c",
        f"model_reasoning_effort={os.environ.get('CODEX_REASONING_EFFORT', 'high')}",
        "--cd",
        str(cwd),
    ]
    if dangerous:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    for add_dir in extra_add_dirs or []:
        cmd.extend(["--add-dir", str(add_dir)])
    if json_mode:
        cmd.extend(["-c", "output_format=json"])
    return cmd


def _project_dir() -> Path:
    return Path(os.environ.get("LACRIMOSA_PROJECT_DIR", Path.cwd())).expanduser()


def _parse_json(raw: str) -> Any | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([idx for idx in (text.find("{"), text.find("[")) if idx != -1], default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
    return None
