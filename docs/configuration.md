# Configuration

Configuration is loaded from, in priority order:

1. `--config /path/to/config.yaml` (CLI flag)
2. `CAGGY_CONFIG` environment variable
3. `/etc/caggy-backup/config.yaml`
4. `~/.caggy-backup/config.yaml`
5. `./config.yaml`

Environment variables starting with `CAGGY_` override YAML values (see
`.env.example`).

## Full reference

```yaml
backup:
  source:
    - /var/lib/pterodactyl/volumes   # one or more directories
  exclude: []                        # names to skip, e.g. ["logs", "*.log"]
  temp_directory: /tmp/caggy-backup  # working dir for archives
  stop_servers: false                # tool never stops servers by default
  compression:
    type: zstd                       # zstd | gzip
    level: 3                         # 1-19

google_drive:
  folder_name: CaggyID-Backups
  credentials_file: /etc/caggy-backup/credentials.json
  token_file: /etc/caggy-backup/token.json

retention:
  enabled: true
  keep_last: 7
  keep_daily: 7
  keep_weekly: 4
  keep_monthly: 6

schedule:
  enabled: false
  cron: "0 */6 * * *"

logging:
  level: INFO                        # INFO | WARNING | ERROR | DEBUG
  directory: /var/log/caggy-backup
```

## Environment overrides

| Variable | Overrides |
|----------|-----------|
| `CAGGY_CONFIG` | Config file path |
| `CAGGY_BACKUP_SOURCES` | `backup.source` (comma separated) |
| `CAGGY_CREDENTIALS_FILE` | `google_drive.credentials_file` |
| `CAGGY_TOKEN_FILE` | `google_drive.token_file` |
| `CAGGY_GDRIVE_FOLDER` | `google_drive.folder_name` |
| `CAGGY_LOG_DIRECTORY` | `logging.directory` |
| `CAGGY_LOG_LEVEL` | `logging.level` |

## Notes

- Invalid configuration always exits with code `2`.
- File permissions: keep `/etc/caggy-backup` at `0700` and its files at
  `0600`. The tool creates them restrictive by default.
- Never commit `.env`, `credentials.json`, or `token.json`.
