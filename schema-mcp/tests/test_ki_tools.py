"""Tests for Knowledge Index (KI) atomic operations."""

import threading
from pathlib import Path

import pytest
from schema_mcp.tools.ki_tools import ki_get, ki_list, ki_mget, ki_set

SAMPLE_KI_CONTENT = """# Knowledge: Test

> Dense key-value facts for agent lookup. Source-linked.

## Section A

```yaml
entries:
  - key: test.alpha
    value: first-value
    source: "file.py:L1"
    verified: "2026-03-09"
  - key: test.beta
    value: second-value
    extra_field: extra
    source: "file.py:L2"
    verified: "2026-03-09"
```

## Section B

```yaml
entries:
  - key: test.gamma
    value: third-value
    source: "file.py:L3"
    verified: "2026-03-09"
```
"""


@pytest.fixture()
def ki_dir(tmp_path: Path) -> Path:
    """Create a temp schemas dir with a KI file."""
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    ki_file = schemas / "KI_INFRA_SCHEMA.md"
    ki_file.write_text(SAMPLE_KI_CONTENT, encoding="utf-8")
    return schemas


class TestKiGet:
    def test_exact_match(self, ki_dir: Path) -> None:
        result = ki_get("db.alpha", str(ki_dir), fuzzy=True)
        # "db" prefix routes to KI_INFRA_SCHEMA — but our test file has "test.*" keys
        # so this should not find an exact match
        assert result["found"] is False

    def test_exact_match_real_key(self, ki_dir: Path) -> None:
        # Create a file with db.* keys to match the prefix routing
        content = """# KI Infra
```yaml
entries:
  - key: db.us.instance
    value: example-db-us
    source: "config.md:L8"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_get("db.us.instance", str(ki_dir))
        assert result["found"] is True
        assert result["entry"]["value"] == "example-db-us"
        assert result["file"] == "KI_INFRA_SCHEMA.md"

    def test_fuzzy_match(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.us.prod.instance
    value: example-db-us
    source: "config.md:L8"
    verified: "2026-03-09"
  - key: db.eu.prod.instance
    value: example-db-eu
    source: "config.md:L9"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_get("db.us", str(ki_dir), fuzzy=True)
        assert result["found"] is True
        assert "us" in result["entry"]["key"]

    def test_not_found_returns_similar(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.us.instance
    value: val
    source: "x"
    verified: "2026-03-09"
  - key: db.eu.instance
    value: val2
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_get("db.nonexistent", str(ki_dir))
        assert result["found"] is False
        assert "similar_keys" in result
        assert "db.us.instance" in result["similar_keys"]

    def test_unknown_prefix_falls_back_to_scan(self, ki_dir: Path) -> None:
        # "unknown" prefix has no mapping — should still scan all KI files
        result = ki_get("unknown.key", str(ki_dir))
        assert result["found"] is False


class TestKiSet:
    def test_update_existing_key(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.us.instance
    value: old-value
    source: "old.py:L1"
    verified: "2026-01-01"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_set(
            "db.us.instance", "new-value", "new.py:L5", str(ki_dir), verified="2026-03-09"
        )
        assert result["success"] is True
        assert result["operation"] == "updated"

        # Verify the file was written correctly
        verify = ki_get("db.us.instance", str(ki_dir))
        assert verify["found"] is True
        assert verify["entry"]["value"] == "new-value"
        assert verify["entry"]["source"] == "new.py:L5"

    def test_append_new_key(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.existing
    value: existing-val
    source: "x:L1"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_set("db.new.key", "brand-new", "y:L2", str(ki_dir))
        assert result["success"] is True
        assert result["operation"] == "appended"

        # Verify both entries exist
        verify_old = ki_get("db.existing", str(ki_dir))
        assert verify_old["found"] is True
        verify_new = ki_get("db.new.key", str(ki_dir))
        assert verify_new["found"] is True
        assert verify_new["entry"]["value"] == "brand-new"

    def test_extra_fields_preserved(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.placeholder
    value: x
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_set(
            "db.with.extras",
            "value",
            "src.py:L1",
            str(ki_dir),
            extra_fields={"region": "us-central1", "url": "https://example.com"},
        )
        assert result["success"] is True

        verify = ki_get("db.with.extras", str(ki_dir))
        assert verify["found"] is True
        assert verify["entry"]["region"] == "us-central1"
        assert verify["entry"]["url"] == "https://example.com"

    def test_unknown_prefix_returns_error(self, ki_dir: Path) -> None:
        result = ki_set("zzz.unknown", "val", "src", str(ki_dir))
        assert result["success"] is False
        assert "No KI file mapping" in result["error"]

    def test_missing_file_returns_error(self, ki_dir: Path) -> None:
        # Remove the file
        (ki_dir / "KI_INFRA_SCHEMA.md").unlink()
        result = ki_set("db.test", "val", "src", str(ki_dir))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_section_hint_targets_correct_block(self, ki_dir: Path) -> None:
        content = """# KI Infra

## Database

```yaml
entries:
  - key: db.main
    value: main-db
    source: "x"
    verified: "2026-03-09"
```

## Cloud Run

```yaml
entries:
  - key: cloudrun.staging
    value: staging-svc
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_set(
            "db.secondary",
            "secondary-db",
            "src:L1",
            str(ki_dir),
            section_hint="Database",
        )
        assert result["success"] is True
        assert result["operation"] == "appended"

    def test_default_verified_date(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.placeholder
    value: x
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_set("db.auto.date", "val", "src:L1", str(ki_dir))
        assert result["success"] is True

        verify = ki_get("db.auto.date", str(ki_dir))
        assert verify["found"] is True
        assert verify["entry"]["verified"] is not None


class TestKiList:
    def test_list_all(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.one
    value: v1
    source: "x"
    verified: "2026-03-09"
  - key: db.two
    value: v2
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_list(str(ki_dir))
        assert result["total_entries"] == 2
        assert "KI_INFRA_SCHEMA" in result["files"]

    def test_prefix_filter(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.one
    value: v1
    source: "x"
    verified: "2026-03-09"
  - key: cloudrun.one
    value: v2
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_list(str(ki_dir), prefix_filter="db.")
        assert result["total_entries"] == 1
        assert result["files"]["KI_INFRA_SCHEMA"][0]["key"] == "db.one"

    def test_file_filter(self, ki_dir: Path) -> None:
        # Create two KI files
        content1 = """# KI Infra
```yaml
entries:
  - key: db.one
    value: v1
    source: "x"
    verified: "2026-03-09"
```
"""
        content2 = """# KI Gotchas
```yaml
entries:
  - key: gotcha.test
    value: v2
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content1, encoding="utf-8")
        (ki_dir / "KI_GOTCHAS_SCHEMA.md").write_text(content2, encoding="utf-8")
        result = ki_list(str(ki_dir), file_filter="GOTCHAS")
        assert result["total_entries"] == 1
        assert "KI_GOTCHAS_SCHEMA" in result["files"]
        assert "KI_INFRA_SCHEMA" not in result["files"]

    def test_long_value_truncated(self, ki_dir: Path) -> None:
        long_val = "x" * 200
        content = f"""# KI Infra
```yaml
entries:
  - key: db.long
    value: "{long_val}"
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_list(str(ki_dir))
        assert result["total_entries"] == 1
        listed_val = result["files"]["KI_INFRA_SCHEMA"][0]["value"]
        assert len(listed_val) == 80
        assert listed_val.endswith("...")

    def test_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = ki_list(str(empty))
        assert result["total_entries"] == 0
        assert result["files"] == {}


class TestFileLocking:
    def test_concurrent_writes_no_data_loss(self, ki_dir: Path) -> None:
        """Verify that concurrent ki_set calls don't lose entries."""
        content = """# KI Infra
```yaml
entries:
  - key: db.seed
    value: seed-value
    source: "seed:L1"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")

        errors: list[str] = []
        results: list[dict] = []

        def write_entry(idx: int) -> None:
            try:
                r = ki_set(f"db.concurrent.{idx}", f"val-{idx}", f"src:L{idx}", str(ki_dir))
                results.append(r)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_entry, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors during concurrent writes: {errors}"
        assert all(r["success"] for r in results)

        # All 5 entries + the seed should be present
        all_entries = ki_list(str(ki_dir), prefix_filter="db.")
        assert all_entries["total_entries"] == 6  # seed + 5 concurrent


class TestKiMget:
    def test_batch_all_found(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.us.instance
    value: example-db-us
    source: "config:L8"
    verified: "2026-03-09"
  - key: db.eu.instance
    value: example-db-eu
    source: "config:L9"
    verified: "2026-03-09"
  - key: cloudrun.staging.us
    value: example-staging-us
    source: "config:L20"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_mget(
            ["db.us.instance", "db.eu.instance", "cloudrun.staging.us"],
            str(ki_dir),
        )
        assert result["found_count"] == 3
        assert result["missing_count"] == 0
        assert result["missing"] == []
        assert "db.us.instance" in result["entries"]
        assert result["entries"]["db.us.instance"]["entry"]["value"] == "example-db-us"

    def test_batch_partial_found(self, ki_dir: Path) -> None:
        content = """# KI Infra
```yaml
entries:
  - key: db.us.instance
    value: example-db-us
    source: "config:L8"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")
        result = ki_mget(
            ["db.us.instance", "db.nonexistent"],
            str(ki_dir),
        )
        assert result["found_count"] == 1
        assert result["missing_count"] == 1
        assert "db.nonexistent" in result["missing"]

    def test_batch_cross_file(self, ki_dir: Path) -> None:
        content1 = """# KI Infra
```yaml
entries:
  - key: db.us.instance
    value: db-us
    source: "x"
    verified: "2026-03-09"
```
"""
        content2 = """# KI Gotchas
```yaml
entries:
  - key: gotcha.cloudflare.timeout
    value: worker-to-worker timeout
    source: "y"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content1, encoding="utf-8")
        (ki_dir / "KI_GOTCHAS_SCHEMA.md").write_text(content2, encoding="utf-8")
        result = ki_mget(
            ["db.us.instance", "gotcha.cloudflare.timeout"],
            str(ki_dir),
        )
        assert result["found_count"] == 2
        assert result["missing_count"] == 0


class TestCaching:
    def test_cache_hit_on_repeated_read(self, ki_dir: Path) -> None:
        """Second ki_get should use cache (same mtime = no re-parse)."""
        content = """# KI Infra
```yaml
entries:
  - key: db.cached
    value: cached-val
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")

        # First call populates cache
        r1 = ki_get("db.cached", str(ki_dir))
        assert r1["found"] is True

        # Second call should hit cache (file unchanged)
        r2 = ki_get("db.cached", str(ki_dir))
        assert r2["found"] is True
        assert r2["entry"]["value"] == "cached-val"

    def test_cache_invalidation_on_write(self, ki_dir: Path) -> None:
        """ki_set should invalidate cache so next read sees new data."""
        content = """# KI Infra
```yaml
entries:
  - key: db.mutable
    value: old
    source: "x"
    verified: "2026-03-09"
```
"""
        (ki_dir / "KI_INFRA_SCHEMA.md").write_text(content, encoding="utf-8")

        # Populate cache
        r1 = ki_get("db.mutable", str(ki_dir))
        assert r1["entry"]["value"] == "old"

        # Write invalidates cache
        ki_set("db.mutable", "new", "y:L1", str(ki_dir))

        # Next read sees updated value
        r2 = ki_get("db.mutable", str(ki_dir))
        assert r2["entry"]["value"] == "new"
