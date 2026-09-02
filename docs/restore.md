# Restore

## List available backups

```bash
caggy-backup list
```

```text
BACKUP ID              SIZE       STATUS       DATE
--------------------------------------------------------------------
2026-09-02_203000      2.41 GB    SUCCESS      02 Sep 2026 20:35
2026-09-01_203000      2.37 GB    SUCCESS      01 Sep 2026 20:32
```

## Dry run (verify only)

```bash
caggy-backup restore 2026-09-02_203000 --dry-run
```

Downloads (if needed), verifies the SHA-256 checksum, and reports how
many entries would be extracted - without touching any files.

## Restore

```bash
caggy-backup restore 2026-09-02_203000 --target /var/lib/pterodactyl/volumes
```

Safety flow:

```text
WARNING:
Restoring this backup may overwrite existing server data.

Backup:
2026-09-02_203000

Continue? [y/N]
```

For automation add `--yes` (only when you are certain).

## Safety mechanisms

- The archive's SHA-256 checksum is verified against the stored
  `checksum.sha256` before extraction. A mismatch aborts the restore.
- Extraction rejects path-traversal members (`../../`) - the tool never
  writes outside the target directory.
- Existing files are only overwritten inside the target directory you
  pass; nothing is deleted automatically.
- If the local archive is gone, it is downloaded from Google Drive
  automatically (requires valid OAuth tokens).

## Recommended practice

Restore into a temporary directory first, compare, then move into
place. This avoids overwriting live server data during inspection.
