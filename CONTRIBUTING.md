# Contributing to CaggyID Pterodactyl Backup

Thank you for your interest in contributing!

## Development setup

```bash
git clone https://github.com/CaggyID/caggyid-pterodactyl-backup.git
cd caggyid-pterodactyl-backup

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

Tests never touch production data; they operate entirely on temporary
directories.

## Code style

- Python 3.10+ compatible code only.
- Type hints on all public functions.
- No `shell=True` subprocess calls.
- Never log or commit credentials, tokens, or secrets.
- Keep the CLI output clean and automation-friendly (no animations).

## Submitting changes

1. Fork the repository and create a feature branch.
2. Make your changes with tests.
3. Update documentation (`README.md`, `docs/`) when behavior changes.
4. Open a pull request using the provided template.

## Reporting bugs

Use the bug report issue template. For security issues, follow
`SECURITY.md`.
