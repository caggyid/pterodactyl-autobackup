# Troubleshooting

Exit codes for automation:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Authentication error |
| 4 | Backup error |
| 5 | Upload error |

## Google Drive authentication failed (exit 3)

```text
[ERROR] Google Drive authentication failed.
```

1. Check that `credentials.json` exists at the configured path and is a
   **Desktop app** OAuth client.
2. Re-authenticate: `caggy-backup test-drive`.
3. Verify the OAuth consent screen includes the `drive.file` scope and
   your account is listed as a Test user (Testing mode).
4. On a headless server, forward the browser callback:
   `ssh -L 8080:localhost:8080 user@node`.

## Upload fails or times out (exit 5)

- Transient 429/5xx errors are retried automatically with exponential
  backoff. Persistent failures usually mean network or quota issues.
- Check Drive storage quota (15 GB free tier).
- Ensure the Drive API is enabled in the Google Cloud project.

## zstd not available / fallback warning

Install it: `sudo apt install zstd`. Until then the tool automatically
falls back to gzip so backups continue to work.

## Not enough disk space (exit 4)

The tool checks free space in `backup.temp_directory` before archiving.
Point it to a bigger volume:

```yaml
backup:
  temp_directory: /var/caggy-tmp
```

## Source directory missing (exit 2)

Validate `backup.source` in the config; the path must exist when the
command runs. Use `caggy-backup status` to see which sources are OK.

## Corrupted archive during restore

Restore aborts on checksum mismatch. Run `caggy-backup verify <id>` for
details, then take a fresh backup. Persistent corruption points to disk
or transfer problems.

## Cron not running

1. `caggy-backup cron status` - is the marked entry present?
2. `systemctl status cron` - is the daemon running?
3. Check `/var/log/caggy-backup/cron.log` and the file log for errors.
4. Cron jobs have a minimal environment; the entry uses absolute paths
   for this reason.

## Permission denied on volumes

If volumes are root-owned, run caggy-backup as root (or via sudo), or
adjust volume ACLs. Never relax permissions on the config directory.

## Where are the logs?

- File log: `/var/log/caggy-backup/caggy-backup.log` (rotating, 10 MB x 5)
- Cron capture: `/var/log/caggy-backup/cron.log`
- OAuth tokens/credentials are never written to logs.
