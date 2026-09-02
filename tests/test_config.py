import os

import pytest
import yaml

from caggy_backup.config import Config, ConfigError, CompressionConfig, RetentionConfig


def _write_config(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_missing_explicit_config_raises(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "nope.yaml")


def test_minimal_valid_config(tmp_path, monkeypatch):
    source = tmp_path / "volumes"
    source.mkdir()
    path = _write_config(tmp_path, {"backup": {"source": [str(source)]}})
    monkeypatch.delenv("CAGGY_BACKUP_SOURCES", raising=False)
    cfg = Config.load(path)
    assert cfg.sources == [source]
    assert cfg.compression.type == "zstd"
    assert cfg.retention.keep_last == 7


def test_invalid_compression_type(tmp_path):
    source = tmp_path / "volumes"
    source.mkdir()
    path = _write_config(
        tmp_path,
        {"backup": {"source": [str(source)], "compression": {"type": "bzip2"}}},
    )
    with pytest.raises(ConfigError):
        Config.load(path)


def test_invalid_log_level(tmp_path):
    source = tmp_path / "volumes"
    source.mkdir()
    path = _write_config(tmp_path, {"backup": {"source": [str(source)]}, "logging": {"level": "LOUD"}})
    with pytest.raises(ConfigError):
        Config.load(path)


def test_nonexistent_source_fails_validation(tmp_path):
    path = _write_config(tmp_path, {"backup": {"source": [str(tmp_path / "missing")]}})
    with pytest.raises(ConfigError):
        Config.load(path)


def test_env_overrides(tmp_path, monkeypatch):
    source = tmp_path / "volumes"
    source.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    path = _write_config(tmp_path, {"backup": {"source": [str(source)]}})
    monkeypatch.setenv("CAGGY_BACKUP_SOURCES", str(other))
    cfg = Config.load(path)
    assert cfg.sources == [other]


def test_string_source_accepted(tmp_path, monkeypatch):
    source = tmp_path / "volumes"
    source.mkdir()
    path = _write_config(tmp_path, {"backup": {"source": str(source)}})
    cfg = Config.load(path)
    assert cfg.sources == [source]


def test_no_sources_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("CAGGY_BACKUP_SOURCES", raising=False)
    path = _write_config(tmp_path, {"backup": {"source": []}})
    with pytest.raises(ConfigError):
        Config.load(path)


def test_retention_defaults():
    policy = RetentionConfig.from_dict(None)
    assert policy.keep_last == 7
    assert policy.keep_daily == 7


def test_compression_level_bounds():
    with pytest.raises(ConfigError):
        CompressionConfig.from_dict({"type": "gzip", "level": 25})
