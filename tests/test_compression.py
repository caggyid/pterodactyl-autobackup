import gzip
import tarfile
from pathlib import Path

import pytest

from caggy_backup.compression import (
    _matches_exclude,
    archive_suffix,
    create_archive,
    resolve_compression_type,
    verify_archive,
)


@pytest.fixture
def sample_tree(tmp_path):
    src = tmp_path / "volumes" / "server-a"
    (src / "world").mkdir(parents=True)
    (src / "server.properties").write_text("motd=hello", encoding="utf-8")
    (src / "world" / "level.dat").write_bytes(b"\x00" * 2048)
    (src / "logs").mkdir()
    (src / "logs" / "latest.log").write_text("log line\n" * 100, encoding="utf-8")
    return src


def test_suffix_mapping():
    assert archive_suffix("zstd") == ".tar.zst"
    assert archive_suffix("gzip") == ".tar.gz"


def test_resolve_compression_fallback():
    # On systems without zstd the resolver must return gzip, never fail.
    resolved = resolve_compression_type("zstd")
    assert resolved in ("zstd", "gzip")


def test_create_archive_gzip_roundtrip(tmp_path, sample_tree):
    out = tmp_path / "out" / "backup.tar.gz"
    create_archive([sample_tree], out, "gzip", 3, excludes=None)
    assert out.exists() and out.stat().st_size > 0
    assert verify_archive(out, "gzip")

    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert any("server.properties" in n for n in names)
    assert any("level.dat" in n for n in names)


def test_create_archive_respects_excludes(tmp_path, sample_tree):
    out = tmp_path / "out" / "backup.tar.gz"
    create_archive([sample_tree.parent], out, "gzip", 3, excludes=["logs"])
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert not any("latest.log" in n for n in names)
    assert any("server.properties" in n for n in names)


def test_exclude_patterns():
    assert _matches_exclude("logs/latest.log", ["logs", "logs/latest.log"])
    assert _matches_exclude("world/level.dat", ["*.dat"])
    assert not _matches_exclude("world/region/r.0.mca", ["logs"])


def test_verify_archive_detects_corruption(tmp_path, sample_tree):
    out = tmp_path / "out" / "backup.tar.gz"
    create_archive([sample_tree], out, "gzip", 3, excludes=None)
    corrupted = tmp_path / "out" / "corrupt.tar.gz"
    raw = gzip.compress(b"this is not a tar archive")
    corrupted.write_bytes(raw)
    assert not verify_archive(corrupted, "gzip")
