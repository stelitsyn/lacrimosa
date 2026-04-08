"""Lacrimosa toolchain monitor — Anthropic/Claude Code intelligence.

Crawls 6 sources for toolchain changes, classifies findings via Claude,
evaluates relevance/impact/risk, routes decisions (auto-adopt/human/archive).
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.lacrimosa_external_sensing import crawl_with_fallback
from scripts.lacrimosa_types import (
    FindingClassification,
    FindingDecision,
    ToolchainFinding,
    TOOLCHAIN_LOG_SIZE_WARN_BYTES,
)
from scripts.lacrimosa_validation import sanitize_content

logger = logging.getLogger(__name__)
_UTC = timezone.utc
DEFAULT_LOG = Path.home() / ".claude" / "lacrimosa" / "toolchain_monitor.jsonl"


class ToolchainMonitor:
    """Monitors Anthropic/Claude Code toolchain for changes."""

    def __init__(self, config: dict[str, Any]) -> None:
        tc = config.get("toolchain_monitor", {})
        self._full_config = config
        self._sources = tc.get("sources", {})
        eval_cfg = tc.get("evaluation", {})
        self._adopt_threshold = eval_cfg.get("auto_adopt_threshold", 7)
        self._risk_threshold = eval_cfg.get("human_review_risk_threshold", 7)
        tracking = tc.get("tracking", {})
        self._log_path = Path(tracking.get("file", str(DEFAULT_LOG))).expanduser()
        self._state: dict[str, Any] = {}

    def run(self, crawl_budget: Any = None) -> list[ToolchainFinding]:
        raw = self._detect(crawl_budget)
        findings: list[ToolchainFinding] = []
        for item in raw:
            if self._is_known(item):
                continue
            classified = self._classify(item)
            evaluated = self._evaluate(classified)
            finding = self._decide(evaluated)
            self._persist(finding)
            findings.append(finding)
        return findings

    # -- Detection -----------------------------------------------------------

    def _detect(self, budget: Any) -> list[dict]:
        results: list[dict] = []
        for name, src in self._sources.items():
            try:
                if "method" in src and src["method"].startswith("gh "):
                    results.extend(self._detect_gh_releases(src))
                else:
                    results.extend(self._detect_url_sources(name, src, budget))
            except Exception as exc:
                logger.error("Source %s failed: %s", name, exc)
        return results

    def _detect_gh_releases(self, src: dict) -> list[dict]:
        cmd = src.get("method", "").split()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return []
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("gh CLI error: %s", exc)
            return []
        results: list[dict] = []
        for line in proc.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            results.append(
                {
                    "tag": parts[0] if parts else "",
                    "title": parts[1] if len(parts) > 1 else "",
                    "date": parts[2] if len(parts) > 2 else "",
                    "source": "claude_code_releases",
                    "content": line,
                    "url": "gh release list",
                }
            )
        return results

    def _detect_url_sources(self, name: str, src: dict, budget: Any) -> list[dict]:
        urls = src.get("urls", [])
        if "url" in src:
            urls = [src["url"]]
        results: list[dict] = []
        for url in urls:
            if budget and not budget.can_crawl():
                break
            try:
                if budget:
                    budget.consume()
                content = crawl_with_fallback(url, self._full_config)
                if content:
                    results.append(
                        {
                            "source": name,
                            "url": url,
                            "content": sanitize_content(str(content)[:2000]),
                        }
                    )
            except Exception as exc:
                logger.warning("Crawl failed for %s: %s", url, exc)
        return results

    # -- Classification & evaluation -----------------------------------------

    def _classify(self, raw: dict) -> dict:
        result = self._dispatch_classify(raw.get("content", ""))
        raw.update(result)
        return raw

    def _dispatch_classify(self, content: str) -> dict:
        prompt = (
            "Classify this toolchain change. Output ONLY JSON: "
            '{"classification": "breaking_change|new_feature|pricing_change|'
            'new_model|deprecation|security_advisory", '
            '"title": "short title", "summary": "1-3 sentences"}\n\n'
            f"Content: {content[:2000]}"
        )
        try:
            proc = subprocess.run(
                ["claude", "--print", "-p", prompt], capture_output=True, text=True, timeout=60
            )
            if proc.returncode == 0 and proc.stdout.strip():
                text = proc.stdout.strip()
                s, e = text.find("{"), text.rfind("}")
                if s != -1 and e > s:
                    return json.loads(text[s : e + 1])
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return {"classification": "new_feature", "title": content[:100], "summary": content[:200]}

    def _evaluate(self, finding: dict) -> dict:
        result = self._dispatch_evaluate(finding)
        finding.update(result)
        return finding

    def _dispatch_evaluate(self, finding: dict) -> dict:
        prompt = (
            "Score this toolchain finding. Output ONLY JSON: "
            '{"relevance": 0-10, "impact": 0-10, "risk": 0-10, '
            '"effort": "low|medium|high"}\n\n'
            f"Classification: {finding.get('classification')}\n"
            f"Title: {finding.get('title')}\n"
            f"Summary: {finding.get('summary')}"
        )
        try:
            proc = subprocess.run(
                ["claude", "--print", "-p", prompt], capture_output=True, text=True, timeout=60
            )
            if proc.returncode == 0 and proc.stdout.strip():
                text = proc.stdout.strip()
                s, e = text.find("{"), text.rfind("}")
                if s != -1 and e > s:
                    return json.loads(text[s : e + 1])
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return {"relevance": 5, "impact": 5, "risk": 5, "effort": "medium"}

    # -- Decision (pure function, no LLM) ------------------------------------

    def _decide(self, evaluated: dict) -> ToolchainFinding:
        classification = evaluated.get("classification", "new_feature")
        avg_score = (evaluated.get("relevance", 0) + evaluated.get("impact", 0)) / 2
        risk = evaluated.get("risk", 0)

        if classification in (
            FindingClassification.BREAKING_CHANGE.value,
            FindingClassification.SECURITY_ADVISORY.value,
        ):
            decision = FindingDecision.HUMAN_REVIEW
        elif avg_score >= self._adopt_threshold and risk < self._risk_threshold:
            decision = FindingDecision.AUTO_ADOPT
        elif avg_score >= self._adopt_threshold:
            decision = FindingDecision.HUMAN_REVIEW
        else:
            decision = FindingDecision.ARCHIVE

        return ToolchainFinding(
            id=f"tcf-{uuid.uuid4().hex[:8]}",
            source=evaluated.get("source", ""),
            url=evaluated.get("url", ""),
            timestamp=datetime.now(_UTC).isoformat(),
            classification=classification,
            title=evaluated.get("title", ""),
            summary=evaluated.get("summary", ""),
            raw_content=str(evaluated.get("content", ""))[:2000],
            relevance=float(evaluated.get("relevance", 0)),
            impact=float(evaluated.get("impact", 0)),
            risk=float(evaluated.get("risk", 0)),
            effort_estimate=evaluated.get("effort", "medium"),
            decision=decision.value,
            issue_id=None,
            applied=False,
        )

    # -- Deduplication & persistence -----------------------------------------

    def _is_known(self, raw: dict) -> bool:
        source = raw.get("source", "")
        known = self._state.get("toolchain_monitor", {}).get("known_versions", {})
        source_known = known.get(source, {})
        tag = raw.get("tag")
        if tag and tag in source_known:
            return True
        title = raw.get("title", "")
        if title:
            title_hash = hashlib.md5(title.encode()).hexdigest()[:12]
            return title_hash in source_known
        return False

    def _persist(self, finding: ToolchainFinding) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as f:
            f.write(json.dumps(asdict(finding), default=str) + "\n")
        if (
            self._log_path.exists()
            and self._log_path.stat().st_size > TOOLCHAIN_LOG_SIZE_WARN_BYTES
        ):
            logger.warning("Toolchain log exceeds 512KB")


# -- Top-level entry points --------------------------------------------------


def run_toolchain_monitor(
    config: dict[str, Any],
    state: dict[str, Any],
    state_manager: Any,
) -> list[ToolchainFinding]:
    """Run toolchain monitoring cycle. Conductor calls this on 6h cadence."""
    monitor = ToolchainMonitor(config)
    monitor._state = state
    try:
        return monitor.run()
    except Exception as exc:
        logger.error("Toolchain monitor failed: %s", exc)
        return []


def read_findings_log(path: Path | None = None) -> list[dict[str, Any]]:
    """Read toolchain findings from JSONL file."""
    p = path or DEFAULT_LOG
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
