# Google Drive Setup

CaggyID Backup uses the **official Google Drive API v3** with **OAuth 2.0**.
Your Google password is never seen or stored by this tool.

## Step 1 - Create a Google Cloud project

1. Open https://console.cloud.google.com/
2. Click the project dropdown → **New Project** → name it (e.g. `caggyid-backup`) → **Create**.

## Step 2 - Enable the Drive API

1. In the project, go to **APIs & Services → Library**.
2. Search for **Google Drive API** and click **Enable**.

## Step 3 - Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**.
2. Choose **Internal** (Google Workspace) or **External** (personal Gmail).
3. Fill in the app name (`CaggyID Backup`) and your contact email.
4. Add the scope `https://www.googleapis.com/auth/drive.file`.
5. If the app is in *Testing* mode, add your Google account under **Test users**.

## Step 4 - Create the OAuth Client (Desktop app)

1. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Download the JSON file.

## Step 5 - Install credentials.json

Copy the downloaded file to the configured path (default):

```bash
sudo cp ~/Downloads/client_secret_xxx.json /etc/caggy-backup/credentials.json
sudo chmod 600 /etc/caggy-backup/credentials.json
```

The path can be changed in `config.yaml`:

```yaml
google_drive:
  credentials_file: /etc/caggy-backup/credentials.json
  token_file: /etc/caggy-backup/token.json
```

## Step 6 - Authenticate

```bash
caggy-backup test-drive
```

The first run opens a browser (use `ssh -L 8080:localhost:8080` on a
headless VPS, or run the command once on a desktop and copy
`token.json` to the server). After consent, the token is saved to
`token.json` with `0600` permissions and refreshed automatically.

## How Drive is organized

```text
Google Drive
└── CaggyID-Backups
    └── <hostname>
        └── 2026
            └── 09
                ├── backup.tar.zst
                ├── checksum.sha256
                └── metadata.json
```

The folder name is configurable:

```yaml
google_drive:
  folder_name: CaggyID-Backups
```

The tool creates any missing folders automatically. The `drive.file`
scope means the app only sees files it created - it cannot read the rest
of your Drive.
