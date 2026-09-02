# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a vulnerability

If you discover a security vulnerability in CaggyID Pterodactyl Backup,
**do not open a public issue**. Instead:

1. Email the details to the CaggyID security contact via https://caggyid.my.id
2. Include reproduction steps, affected versions, and potential impact.
3. Allow up to 90 days for a fix before public disclosure.

## Security design notes

- The tool never stores your Google password. Authentication uses OAuth 2.0
  with an installed-app flow; only a refresh/access token file is stored
  locally with restrictive permissions (0600).
- `credentials.json`, `token.json`, and `.env` must never be committed to
  version control (see `.gitignore`).
- Archive extraction rejects path-traversal members; restore requires
  explicit confirmation or `--yes`.
- All external processes (zstd) are invoked via safe subprocess lists,
  never `shell=True`.
- Logs never include OAuth tokens or credentials.

## Scope

CaggyID Pterodactyl Backup runs with filesystem access to your Pterodactyl
server volumes. Compromise of the host account that runs this tool implies
compromise of the backups. Run it as root only when required by the volume
permissions, and keep the configuration directory (`/etc/caggy-backup`)
readable only by that account (0700).
