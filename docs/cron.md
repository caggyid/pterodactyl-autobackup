# Cron Setup

## Install the schedule

```bash
sudo caggy-backup cron install
```

You will be asked to pick a schedule (every 6/12 hours, daily, weekly,
or a custom cron expression). The entry uses the absolute binary path
and does not depend on an interactive shell.

Non-interactive presets:

```bash
sudo caggy-backup cron install --schedule every-6-hours
sudo caggy-backup cron install --schedule daily
sudo caggy-backup cron install --schedule "30 4 * * *"   # raw cron
```

## Idempotency

The crontab entry is wrapped in `# CAGGY-BACKUP:BEGIN` / `:END` markers.
Running `cron install` repeatedly replaces the marked block instead of
duplicating it.

## Status / remove

```bash
caggy-backup cron status
sudo caggy-backup cron remove
```

## Headless helper

`scripts/setup-cron.sh` performs the same operation without prompts:

```bash
sudo bash scripts/setup-cron.sh every-6-hours
```

## Systemd alternative

A oneshot service unit is provided at `systemd/caggy-backup.service` for
sites that prefer systemd timers over cron. Pair it with a timer unit:

```ini
# /etc/systemd/system/caggy-backup.timer
[Timer]
OnCalendar=00/6:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Behavior under cron

- The scheduled command runs `caggy-backup backup --non-interactive`,
  which never prompts and returns non-zero on failure.
- Output is appended to `/var/log/caggy-backup/cron.log`.
- Retention cleanup runs as part of the configured policy via
  `caggy-backup cleanup` (run it in the same cron block or rely on the
  manual confirmation flow interactively).
