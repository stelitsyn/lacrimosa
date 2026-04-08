"""Knowledge Index (KI) atomic operations.

Provides atomic get/set/mget for individual KI entries without reading/writing
entire schema files. KI entries are YAML key-value facts stored in KI_*_SCHEMA.md files.

Performance features:
- In-memory cache with mtime invalidation (avoids re-parsing YAML on repeated lookups)
- Batch mget for fetching multiple keys in one call
- File-level locking (fcntl.flock) for concurrent write safety
"""

import fcntl
import re
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Key prefix → KI schema file mapping
_KEY_TO_FILE: dict[str, str] = {
    "db.table": "KI_DB_MAP_SCHEMA",
    "db.stats": "KI_DB_MAP_SCHEMA",
    "db": "KI_INFRA_SCHEMA",
    "cloudrun": "KI_INFRA_SCHEMA",
    "firebase": "KI_INFRA_SCHEMA",
    "url": "KI_INFRA_SCHEMA",
    "secrets": "KI_INFRA_SCHEMA",
    "dev": "KI_INFRA_SCHEMA",
    "gcp": "KI_INFRA_SCHEMA",
    "arch": "KI_ARCHITECTURE_SCHEMA",
    "gotcha": "KI_GOTCHAS_SCHEMA",
    "billing": "KI_BUSINESS_RULES_SCHEMA",
    "plan": "KI_BUSINESS_RULES_SCHEMA",
    "credits": "KI_BUSINESS_RULES_SCHEMA",
    "payments": "KI_BUSINESS_RULES_SCHEMA",
    "convention": "KI_CONVENTIONS_SCHEMA",
    "decision": "KI_DECISIONS_SCHEMA",
    "code": "KI_CODE_MAP_SCHEMA",
    "api": "KI_API_SURFACE_SCHEMA",
    "hierarchy": "KI_SERVICE_HIERARCHY_SCHEMA",
}

# Regex to find ```yaml ... ``` blocks in markdown
_YAML_BLOCK_RE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)

# In-memory cache: file_path_str → (mtime_ns, entries_list)
_entry_cache: dict[str, tuple[int, list[dict[str, Any]]]] = {}


@contextmanager
def _file_lock(file_path: Path, exclusive: bool = True) -> Generator[None, None, None]:
    """Acquire a file lock for safe concurrent access."""
    lock_path = file_path.with_suffix(".md.lock")
    lock_fd = open(lock_path, "w")  # noqa: SIM115
    try:
        lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(lock_fd, lock_type)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def _resolve_file_for_key(key: str) -> str:
    """Resolve which KI schema file a key belongs to."""
    for prefix in sorted(_KEY_TO_FILE, key=len, reverse=True):
        if key.startswith(prefix):
            return _KEY_TO_FILE[prefix]
    raise ValueError(f"No KI file mapping for key prefix: {key.split('.')[0]}")


def _list_ki_files(schemas_dir: str) -> list[Path]:
    """List all KI_* schema files."""
    return sorted(Path(schemas_dir).glob("KI_*_SCHEMA.md"))


def _parse_entries_from_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse all YAML entries from a KI schema file, with mtime caching."""
    path_str = str(file_path)
    try:
        current_mtime = file_path.stat().st_mtime_ns
    except OSError:
        _entry_cache.pop(path_str, None)
        return []

    cached = _entry_cache.get(path_str)
    if cached and cached[0] == current_mtime:
        return cached[1]

    content = file_path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    for match in _YAML_BLOCK_RE.finditer(content):
        yaml_text = match.group(1)
        try:
            parsed = yaml.safe_load(yaml_text)
            if isinstance(parsed, dict) and "entries" in parsed:
                for entry in parsed["entries"]:
                    if isinstance(entry, dict) and "key" in entry:
                        entries.append(entry)
        except yaml.YAMLError:
            continue

    _entry_cache[path_str] = (current_mtime, entries)
    return entries


def _invalidate_cache(file_path: Path) -> None:
    """Remove a file from the entry cache after writes."""
    _entry_cache.pop(str(file_path), None)


def _search_entries(
    key: str,
    schemas_dir: str,
    fuzzy: bool,
) -> dict[str, Any] | None:
    """Search for a single key across KI files. Returns match or None."""
    # Try prefix-routed file first
    try:
        target_name = _resolve_file_for_key(key)
        target_path = Path(schemas_dir) / f"{target_name}.md"
        if target_path.exists():
            for entry in _parse_entries_from_file(target_path):
                if entry["key"] == key:
                    return {"found": True, "entry": entry, "file": target_path.name}
                if fuzzy and key.lower() in entry["key"].lower():
                    return {"found": True, "entry": entry, "file": target_path.name}
    except ValueError:
        pass

    # Fall back to scanning all KI files
    for ki_file in _list_ki_files(schemas_dir):
        for entry in _parse_entries_from_file(ki_file):
            if entry["key"] == key:
                return {"found": True, "entry": entry, "file": ki_file.name}
            if fuzzy and key.lower() in entry["key"].lower():
                return {"found": True, "entry": entry, "file": ki_file.name}

    return None


def ki_get(
    key: str,
    schemas_dir: str,
    fuzzy: bool = False,
) -> dict[str, Any]:
    """Get a single KI entry by exact key match (cached)."""
    result = _search_entries(key, schemas_dir, fuzzy)
    if result:
        return result

    # Not found — suggest similar keys
    prefix = key.split(".")[0] if "." in key else key
    available = []
    for ki_file in _list_ki_files(schemas_dir):
        for entry in _parse_entries_from_file(ki_file):
            if entry["key"].startswith(prefix):
                available.append(entry["key"])

    return {
        "found": False,
        "error": f"No entry found for key: {key}",
        "similar_keys": available[:10],
    }


def ki_mget(
    keys: list[str],
    schemas_dir: str,
    fuzzy: bool = False,
) -> dict[str, Any]:
    """Get multiple KI entries in one call.

    Returns all found entries plus a list of missing keys. Much more efficient
    than calling ki_get N times — files are parsed once and shared across lookups.
    """
    results: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for key in keys:
        result = _search_entries(key, schemas_dir, fuzzy)
        if result:
            results[key] = result
        else:
            missing.append(key)

    return {
        "found_count": len(results),
        "missing_count": len(missing),
        "entries": results,
        "missing": missing,
    }


def ki_set(
    key: str,
    value: str,
    source: str,
    schemas_dir: str,
    verified: str | None = None,
    extra_fields: dict[str, Any] | None = None,
    section_hint: str | None = None,
) -> dict[str, Any]:
    """Upsert a single KI entry atomically with file locking."""
    if not verified:
        verified = str(date.today())

    new_entry: dict[str, Any] = {"key": key, "value": value}
    if extra_fields:
        new_entry.update(extra_fields)
    new_entry["source"] = source
    new_entry["verified"] = verified

    try:
        target_file_name = _resolve_file_for_key(key)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    target_path = Path(schemas_dir) / f"{target_file_name}.md"
    if not target_path.exists():
        return {"success": False, "error": f"KI file not found: {target_file_name}.md"}

    with _file_lock(target_path, exclusive=True):
        content = target_path.read_text(encoding="utf-8")

        # Try to find and update existing entry
        for match in _YAML_BLOCK_RE.finditer(content):
            yaml_text = match.group(1)
            try:
                parsed = yaml.safe_load(yaml_text)
            except yaml.YAMLError:
                continue

            if not isinstance(parsed, dict) or "entries" not in parsed:
                continue

            for i, entry in enumerate(parsed["entries"]):
                if isinstance(entry, dict) and entry.get("key") == key:
                    parsed["entries"][i] = new_entry
                    new_yaml = yaml.dump(
                        parsed, default_flow_style=False, allow_unicode=True, sort_keys=False
                    )
                    block_start = match.start(1)
                    block_end = match.end(1)
                    content = content[:block_start] + new_yaml + content[block_end:]
                    target_path.write_text(content, encoding="utf-8")
                    _invalidate_cache(target_path)
                    return {
                        "success": True,
                        "operation": "updated",
                        "key": key,
                        "file": target_file_name,
                    }

        # Key not found — append to best YAML block
        best_match = None
        if section_hint:
            section_re = re.compile(
                rf"##\s+{re.escape(section_hint)}.*?```yaml\n(.*?)```",
                re.DOTALL,
            )
            section_match = section_re.search(content)
            if section_match:
                best_match = section_match
        if not best_match:
            matches = list(_YAML_BLOCK_RE.finditer(content))
            if matches:
                best_match = matches[-1]

        if best_match:
            yaml_text = best_match.group(1)
            try:
                parsed = yaml.safe_load(yaml_text)
                if isinstance(parsed, dict) and "entries" in parsed:
                    parsed["entries"].append(new_entry)
                    new_yaml = yaml.dump(
                        parsed,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                    block_start = best_match.start(1)
                    block_end = best_match.end(1)
                    content = content[:block_start] + new_yaml + content[block_end:]
                    target_path.write_text(content, encoding="utf-8")
                    _invalidate_cache(target_path)
                    return {
                        "success": True,
                        "operation": "appended",
                        "key": key,
                        "file": target_file_name,
                    }
            except yaml.YAMLError:
                pass

        return {
            "success": False,
            "error": f"Could not find a valid YAML entries block in {target_file_name}.md",
        }


def ki_list(
    schemas_dir: str,
    file_filter: str | None = None,
    prefix_filter: str | None = None,
) -> dict[str, Any]:
    """List all KI keys with their values (compact format, cached)."""
    ki_files = _list_ki_files(schemas_dir)
    result: dict[str, list[dict[str, str]]] = {}
    total = 0

    for ki_file in ki_files:
        file_name = ki_file.stem
        if file_filter and file_filter.upper() not in file_name:
            continue

        entries = _parse_entries_from_file(ki_file)
        file_entries = []
        for entry in entries:
            key = entry.get("key", "")
            if prefix_filter and not key.startswith(prefix_filter):
                continue
            compact = {"key": key, "value": str(entry.get("value", ""))}
            file_entries.append(compact)

        if file_entries:
            result[file_name] = file_entries
            total += len(file_entries)

    return {"total_entries": total, "files": result}
