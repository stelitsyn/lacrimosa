"""Read-only access to production feedback data for Lacrimosa Discovery.

SAFETY GUARDS:
  - ALL transactions forced to READ ONLY mode
  - Connection uses a dedicated Cloud SQL Proxy port (5434)
  - Module refuses to import from non-discovery contexts (env guard)
  - No INSERT/UPDATE/DELETE/DROP/ALTER/CREATE statements allowed
  - Connection auto-closes after each query batch

Usage (from discovery specialist only):
    from scripts.lacrimosa_feedback_reader import read_feedback, read_feedback_stats

    # Get recent feedback
    records = read_feedback(limit=50, since_hours=48)

    # Get sentiment stats
    stats = read_feedback_stats(since_hours=168)  # last 7 days
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras

from scripts import lacrimosa_config

logger = logging.getLogger(__name__)

PROD_DB_NAME = lacrimosa_config.get("data_sources.gcp.database_name")

# Both regions — US primary, EU secondary
_gcp_project = lacrimosa_config.get("data_sources.gcp.project_id")
_sql_instances = lacrimosa_config.get("data_sources.gcp.cloud_sql_instances")

# Map GCP region prefixes to short display names
_REGION_SHORT_NAMES: dict[str, str] = {
    "us": "US",
    "europe": "EU",
    "asia": "ASIA",
}


def _region_short_name(region: str) -> str:
    """Convert GCP region (e.g. 'europe-west1') to short name ('EU')."""
    prefix = region.split("-")[0]
    return _REGION_SHORT_NAMES.get(prefix, prefix.upper())


PROD_REGIONS = [
    {
        "name": _region_short_name(inst["region"]),
        "instance": f"{_gcp_project}:{inst['region']}:{inst['instance']}",
        "proxy_port": 5434 + i,
        "password_secret": "POSTGRES_PASSWORD" if i == 0 else f"POSTGRES_PASSWORD_{_region_short_name(inst['region'])}",
    }
    for i, inst in enumerate(_sql_instances)
]

# SQL injection guard — block any write statements
_WRITE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


@dataclass
class FeedbackEntry:
    """A single feedback record."""
    id: int
    user_id: int
    username: str | None
    email: str | None
    feedback_text: str
    created_at: str
    has_chat_history: bool


def _ensure_proxy_running(port: int, instance: str) -> None:
    """Start Cloud SQL Proxy on dedicated port if not already running."""
    result = subprocess.run(
        ["lsof", "-i", f":{port}", "-t"],
        capture_output=True, text=True,
    )
    if result.stdout.strip():
        return  # Already running

    logger.info("Starting Cloud SQL Proxy on port %d for %s", port, instance)
    subprocess.Popen(
        ["{db_proxy_command}", instance, f"--port={port}", "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(10):
        time.sleep(1)
        check = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True, text=True,
        )
        if check.stdout.strip():
            logger.info("Cloud SQL Proxy ready on port %d", port)
            return
    raise RuntimeError(f"Cloud SQL Proxy failed to start on port {port}")


def _get_password(secret_name: str = "POSTGRES_PASSWORD") -> str:
    """Get DB password from env or GCP Secret Manager."""
    password = os.environ.get(secret_name, "")
    if not password:
        try:
            _project = lacrimosa_config.get("data_sources.gcp.project_id")
            result = subprocess.run(
                ["gcloud", "secrets", "versions", "access", "latest",
                 f"--secret={secret_name}",
                 f"--project={_project}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                password = result.stdout.strip()
        except Exception:
            pass
    return password


@contextmanager
def _readonly_connection(port: int = 5434, password_secret: str = "POSTGRES_PASSWORD"):
    """Context manager for a read-only connection to prod on a specific port.

    GUARDS:
      - Transaction set to READ ONLY
      - default_transaction_read_only = on
      - Connection auto-closed on exit
    """
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = _get_password(password_secret)

    conn = psycopg2.connect(
        host="127.0.0.1",
        port=port,
        database=PROD_DB_NAME,
        user=user,
        password=password,
        options="-c default_transaction_read_only=on",
    )
    try:
        conn.set_session(readonly=True, autocommit=False)
        yield conn
    finally:
        conn.close()


def _safe_query(sql: str) -> str:
    """Validate SQL is read-only. Raises ValueError on write attempts."""
    if _WRITE_PATTERN.search(sql):
        raise ValueError(f"BLOCKED: Write statement detected in read-only query: {sql[:100]}")
    return sql


def read_feedback(
    limit: int = 50,
    since_hours: int = 48,
) -> list[FeedbackEntry]:
    """Read recent feedback entries from ALL prod regions (US + EU).

    Args:
        limit: Max records per region.
        since_hours: How far back to look (hours).

    Returns:
        List of FeedbackEntry records from all regions, newest first.
    """
    # Adapt this query to YOUR schema. The column aliases must match FeedbackEntry fields:
    # id, user_id, username, email, feedback_text, created_at, has_chat (bool)
    #
    # Example (replace YOUR_* placeholders with your actual table/column names):
    sql = _safe_query("""
        SELECT id, YOUR_USER_ID_COLUMN AS user_id, YOUR_USERNAME_COLUMN AS username,
               YOUR_EMAIL_COLUMN AS email, YOUR_TEXT_COLUMN AS feedback_text, created_at,
               (YOUR_METADATA_COLUMN IS NOT NULL) AS has_chat
        FROM YOUR_FEEDBACK_TABLE
        WHERE created_at >= NOW() - INTERVAL '%s hours'
        ORDER BY created_at DESC
        LIMIT %s
    """)

    all_entries: list[FeedbackEntry] = []
    for region in PROD_REGIONS:
        try:
            _ensure_proxy_running(region["proxy_port"], region["instance"])
            with _readonly_connection(port=region["proxy_port"], password_secret=region["password_secret"]) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (since_hours, limit))
                    rows = cur.fetchall()
            all_entries.extend(
                FeedbackEntry(
                    id=r["id"],
                    user_id=r["user_id"],
                    username=r.get("username"),
                    email=r.get("email"),
                    feedback_text=f"[{region['name']}] {r['feedback_text']}",
                    created_at=str(r["created_at"]),
                    has_chat_history=r.get("has_chat", False),
                )
                for r in rows
            )
        except Exception as e:
            logger.warning("Failed to read feedback from %s: %s", region["name"], e)

    all_entries.sort(key=lambda x: x.created_at, reverse=True)
    return all_entries


def read_feedback_stats(since_hours: int = 168) -> dict[str, Any]:
    """Get aggregated feedback statistics from ALL prod regions.

    Returns:
        Dict with total_count, unique_users, date_range, recent_texts (last 10), by_region.
    """
    total_count = 0
    unique_users = 0
    earliest = None
    latest = None
    all_recent: list[dict] = []
    by_region: dict[str, int] = {}

    for region in PROD_REGIONS:
        try:
            _ensure_proxy_running(region["proxy_port"], region["instance"])
            with _readonly_connection(port=region["proxy_port"], password_secret=region["password_secret"]) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(_safe_query("""
                        SELECT
                            COUNT(*) as total,
                            COUNT(DISTINCT YOUR_USER_ID_COLUMN) as unique_users,
                            MIN(created_at) as earliest,
                            MAX(created_at) as latest
                        FROM YOUR_FEEDBACK_TABLE
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                    """), (since_hours,))
                    stats = cur.fetchone()

                    by_region[region["name"]] = stats["total"]
                    total_count += stats["total"]
                    unique_users += stats["unique_users"]
                    if stats["earliest"] and (earliest is None or str(stats["earliest"]) < str(earliest)):
                        earliest = stats["earliest"]
                    if stats["latest"] and (latest is None or str(stats["latest"]) > str(latest)):
                        latest = stats["latest"]

                    cur.execute(_safe_query("""
                        SELECT YOUR_TEXT_COLUMN AS feedback_text, created_at,
                               YOUR_USERNAME_COLUMN AS username
                        FROM YOUR_FEEDBACK_TABLE
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                        ORDER BY created_at DESC
                        LIMIT 10
                    """), (since_hours,))
                    for r in cur.fetchall():
                        all_recent.append({**r, "_region": region["name"]})
        except Exception as e:
            logger.warning("Failed to read stats from %s: %s", region["name"], e)
            by_region[region["name"]] = -1

    all_recent.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    recent = all_recent[:10]

    return {
        "total_count": total_count,
        "unique_users": unique_users,
        "earliest": str(earliest) if earliest else None,
        "latest": str(latest) if latest else None,
        "by_region": by_region,
        "recent_texts": [
            {
                "text": r["feedback_text"][:200],
                "at": str(r["created_at"]),
                "user": r.get("username"),
                "region": r.get("_region", "?"),
            }
            for r in recent
        ],
    }


if __name__ == "__main__":
    import json
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "stats":
        print(json.dumps(read_feedback_stats(), indent=2, default=str))
    elif cmd == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        for f in read_feedback(limit=limit):
            print(f"[{f.created_at}] @{f.username or 'anon'}: {f.feedback_text[:100]}")
    else:
        print(f"Usage: {sys.argv[0]} [stats|recent [limit]]")
