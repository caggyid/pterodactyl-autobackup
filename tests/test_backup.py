import json
import tarfile
from pathlib import Path

import pytest

from caggy_backup.backup import discover_servers, estimate_source_size, run_backup
from caggy_backup.config import Config, CompressionConfig
from caggy_backup.database import BackupDatabase
from caggy_backup.utils import sha256_file


@pytest.fixture
def node_env(tmp_path, monkeypatch):
    volumes = tmp_path / "volumes"
    for server in ("server-a", "server-b"):
        d = volumes / server
        d.mkdir(parents=True)
        (d / "data.bin").write_bytes(b"x" * 4096)
        (d / "config.txt").write_text("key=value", encoding="utf-8")

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    db_path = tmp_path / "history.db"

    monkeypatch.setenv("CAGGY_BACKUP_SOURCES", str(volumes))
    monkeypatch.setenv("CAGGY_LOG_DIRECTORY", str(log_dir))

    cfg = Config.load(None)
    cfg.temp_directory = temp_dir
    cfg.compression = CompressionConfig(type="gzip", level=1)
    return cfg, volumes, db_path


def test_discover_servers(node_env):
    cfg, volumes, _ = node_env
    servers = discover_servers(cfg.sources)
    assert servers == ["server-a", "server-b"]


def test_estimate_source_size(node_env):
    cfg, _, _ = node_env
    total = estimate_source_size(cfg.sources, cfg.exclude)
    assert total >= 8192


def test_run_backup_local_no_upload(node_env):
    cfg, _, db_path = node_env
    db = BackupDatabase(db_path)
    result = run_backup(cfg, backup_id="test-backup-1", upload=False, db=db)

    assert result.backup_id == "test-backup-1"
    assert result.archive_size > 0
    assert result.checksum == sha256_file(result.archive_path)
    assert result.compression == "gzip"
    assert not result.uploaded

    record = db.get("test-backup-1")
    assert record is not None
    assert record.status == "SUCCESS"
    assert record.checksum == result.checksum
    assert record.size == result.archive_size
    assert "server-a" in record.servers

    # metadata + checksum artifacts exist
    meta = json.loads((result.archive_path.parent / "metadata.json").read_text(encoding="utf-8"))
    assert meta["project"] == "CaggyID Pterodactyl Backup"
    assert meta["checksum"] == result.checksum
    cs = (result.archive_path.parent / "checksum.sha256").read_text(encoding="utf-8")
    assert result.checksum in cs

    # archive content includes server files
    with tarfile.open(result.archive_path, "r:gz") as tar:
        names = " ".join(tar.getnames())
    assert "data.bin" in names

    db.close()


def test_run_backup_selected_server(node_env):
    cfg, _, db_path = node_env
    db = BackupDatabase(db_path)
    result = run_backup(cfg, backup_id="test-backup-2", selected_servers=["server-a"], upload=False, db=db)
    with tarfile.open(result.archive_path, "r:gz") as tar:
        names = " ".join(tar.getnames())
    assert "config.txt" in names
    assert "server-b" not in names
    db.close()


def test_run_backup_missing_server_fails(node_env):
    cfg, _, db_path = node_env
    db = BackupDatabase(db_path)
    from caggy_backup.backup import BackupError

    with pytest.raises(BackupError):
        run_backup(cfg, backup_id="test-backup-3", selected_servers=["ghost"], upload=False, db=db)
    record = db.get("test-backup-3")
    assert record.status == "FAILED"
    db.close()


def test_run_backup_failed_record_on_db_error_path(node_env):
    cfg, _, db_path = node_env
    db = BackupDatabase(db_path)
    # Force an archive failure by pointing temp dir to a file path.
    cfg.temp_directory = cfg.temp_directory / "impossible" / "\x00bad"
    from caggy_backup.backup import BackupError

    with pytest.raises(BackupError):
        run_backup(cfg, backup_id="test-backup-4", upload=False, db=db)
    db.close()
