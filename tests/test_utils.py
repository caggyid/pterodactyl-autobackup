import pytest

from caggy_backup.utils import (
    EXIT_BACKUP,
    check_disk_space,
    human_size,
    make_backup_id,
    safe_extract_target,
    sha256_file,
    validate_source_path,
)


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(1024) == "1.00 KB"
    assert human_size(1024 ** 3) == "1.00 GB"


def test_make_backup_id_format():
    backup_id = make_backup_id()
    assert len(backup_id) == len("2026-09-02_203000")
    assert backup_id[10] == "_"


def test_sha256_file(tmp_path):
    f = tmp_path / "file.bin"
    f.write_bytes(b"hello world")
    assert sha256_file(f) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_check_disk_space(tmp_path):
    assert check_disk_space(tmp_path, 1)
    assert not check_disk_space(tmp_path, 10 ** 30)


def test_validate_source_path(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    assert validate_source_path(str(d)) == d.resolve()
    with pytest.raises(ValueError):
        validate_source_path(str(tmp_path / "missing"))
    with pytest.raises(ValueError):
        validate_source_path("   ")
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValueError):
        validate_source_path(str(f))


def test_safe_extract_target_rejects_traversal(tmp_path):
    base = tmp_path / "target"
    base.mkdir()
    safe = safe_extract_target(base, "world/level.dat")
    assert str(safe).startswith(str(base))
    with pytest.raises(ValueError):
        safe_extract_target(base, "../../etc/passwd")


def test_exit_codes():
    from caggy_backup.utils import EXIT_CONFIG, EXIT_AUTH, EXIT_GENERAL, EXIT_OK, EXIT_UPLOAD

    assert (EXIT_OK, EXIT_GENERAL, EXIT_CONFIG, EXIT_AUTH, EXIT_BACKUP, EXIT_UPLOAD) == (0, 1, 2, 3, 4, 5)
