from caggy_backup.database import BackupDatabase, BackupRecord


def _rec(rid, status="SUCCESS"):
    return BackupRecord(
        id=rid, created_at="2026-09-02T20:30:00Z", hostname="h", servers="a,b",
        size=123, checksum="abc", gdrive_file_id="file-1", status=status,
        duration_sec=1.5, error_message="", local_path="/tmp/x", compression="gzip",
    )


def test_insert_get_roundtrip(tmp_path):
    db = BackupDatabase(tmp_path / "db.db")
    db.insert(_rec("b1"))
    record = db.get("b1")
    assert record is not None
    assert record.hostname == "h"
    assert record.size == 123
    assert record.status == "SUCCESS"
    db.close()


def test_update(tmp_path):
    db = BackupDatabase(tmp_path / "db.db")
    db.insert(_rec("b1", status="PENDING"))
    db.update("b1", status="SUCCESS", size=999)
    record = db.get("b1")
    assert record.status == "SUCCESS"
    assert record.size == 999
    db.close()


def test_list_order_and_delete(tmp_path):
    db = BackupDatabase(tmp_path / "db.db")
    db.insert(_rec("b1"))
    db.insert(_rec("b2", status="FAILED"))
    records = db.list_all()
    assert len(records) == 2
    assert records[0].id in ("b1", "b2")
    success = db.list_success()
    assert [r.id for r in success] == ["b1"]
    db.delete("b1")
    assert db.get("b1") is None
    db.close()
