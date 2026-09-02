import pytest

from caggy_backup.scheduler import (
    MARKER_BEGIN,
    MARKER_END,
    CronStatus,
    SchedulerError,
    build_entry,
)


def test_build_entry_format():
    entry = build_entry("0 */6 * * *", "/usr/local/bin/caggy-backup")
    assert entry.startswith(MARKER_BEGIN)
    assert entry.endswith(MARKER_END)
    assert "0 */6 * * * /usr/local/bin/caggy-backup" in entry


def test_build_entry_rejects_relative_binary():
    with pytest.raises(SchedulerError):
        build_entry("0 * * * *", "caggy-backup")


def test_build_entry_rejects_bad_schedule():
    with pytest.raises(SchedulerError):
        build_entry("not a cron", "/usr/bin/caggy-backup")
    with pytest.raises(SchedulerError):
        build_entry("* * * * * *", "/usr/bin/caggy-backup")  # 6 fields


def test_status_dataclass():
    st = CronStatus(installed=False, entry=None, crontab="")
    assert not st.installed
