"""Google Drive integration using the official Drive API v3.

Authentication uses OAuth 2.0 (InstalledAppFlow) with a user-provided
``credentials.json``. The tool never sees or stores the Google password.
Tokens are refreshed automatically and stored only in the token file.

Uploads use Google's resumable media (chunked MediaFileUpload) with
retry + exponential backoff on transient failures.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

RETRYABLE_STATUS = {500, 502, 503, 504, 429}
MAX_RETRIES = 5


class GoogleDriveError(Exception):
    pass


class GoogleDriveAuthError(GoogleDriveError):
    pass


def _credentials_from_token(token_file: Path) -> Credentials | None:
    if not token_file.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds, token_file)
            return creds
    except Exception:
        return None
    return None


def _save_token(creds: Credentials, token_file: Path) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    with open(token_file, "w", encoding="utf-8") as handle:
        handle.write(creds.to_json())
    if os.name == "posix":
        os.chmod(token_file, 0o600)


def authenticate(credentials_file: Path, token_file: Path) -> Credentials:
    """Authenticate with Google Drive via OAuth 2.0.

    Reuses a valid token when available; otherwise runs the installed-app
    flow (requires a browser on first run only).
    """
    credentials_file = Path(os.path.expanduser(credentials_file))
    token_file = Path(os.path.expanduser(token_file))

    if not credentials_file.exists():
        raise GoogleDriveAuthError(
            f"credentials.json not found at: {credentials_file}\n"
            "Possible solutions:\n"
            "1. Create an OAuth Client ID in Google Cloud Console\n"
            "2. Download credentials.json and place it at the path above\n"
            "3. Run: caggy-backup setup"
        )

    creds = _credentials_from_token(token_file)
    if creds:
        return creds

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
    except Exception as exc:
        raise GoogleDriveAuthError(
            f"Google Drive authentication failed: {exc}\n"
            "Possible solutions:\n"
            "1. Check credentials.json is a valid OAuth Client (Desktop app)\n"
            "2. Re-authenticate Google Drive: caggy-backup setup\n"
            "3. Verify Google Cloud OAuth configuration"
        ) from exc

    _save_token(creds, token_file)
    return creds


def build_service(creds: Credentials):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _is_retryable(error: HttpError) -> bool:
    try:
        return error.status_code in RETRYABLE_STATUS
    except AttributeError:
        return False


def find_or_create_folder(service, name: str, parent_id: str | None = None) -> str:
    """Find a Drive folder by name (creating it when missing)."""
    query_parts = [
        "mimeType='application/vnd.google-apps.folder'",
        "trashed=false",
        f"name='{name}'",
    ]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    response = (
        service.files()
        .list(q=" and ".join(query_parts), fields="files(id, name)", pageSize=10)
        .execute()
    )
    files = response.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    created = service.files().create(body=metadata, fields="id").execute()
    return created["id"]


def get_folder_path(service, path_parts: list[str]) -> str:
    """Resolve or create a nested folder path, returning the leaf id."""
    current = None
    for part in path_parts:
        current = find_or_create_folder(service, part, current)
    return current  # type: ignore[return-value]


def upload_file(
    service,
    local_path: Path,
    drive_name: str,
    parent_folder_id: str,
    chunk_size: int = 8 * 1024 * 1024,
    progress_callback=None,
) -> str:
    """Upload a file using resumable media with retry/backoff.

    Returns the created Google Drive file id.
    """
    import time

    media = MediaFileUpload(
        str(local_path),
        chunksize=chunk_size,
        resumable=True,
        mimetype="application/octet-stream",
    )
    metadata = {"name": drive_name, "parents": [parent_folder_id]}
    request = service.files().create(body=metadata, media_body=media, fields="id")

    response = None
    attempt = 0
    while response is None:
        try:
            status, response = request.next_chunk(num_retries=0)
            if status and progress_callback:
                progress_callback(status.progress())
        except HttpError as exc:
            if _is_retryable(exc) and attempt < MAX_RETRIES:
                attempt += 1
                delay = min(2 ** attempt, 60)
                time.sleep(delay)
                continue
            if isinstance(exc, HttpError) and getattr(exc, "status_code", 0) in (401, 403):
                raise GoogleDriveError(
                    f"Google Drive API permission error: {exc}\n"
                    "Check the Drive API is enabled and the OAuth scope drive.file is granted."
                ) from exc
            raise GoogleDriveError(f"Google Drive upload failed: {exc}") from exc
        except Exception as exc:  # network timeouts etc.
            if attempt < MAX_RETRIES:
                attempt += 1
                delay = min(2 ** attempt, 60)
                time.sleep(delay)
                continue
            raise GoogleDriveError(f"Upload interrupted after retries: {exc}") from exc

    file_id = response.get("id")
    if not file_id:
        raise GoogleDriveError("Google Drive upload did not return a file id")
    return file_id


def download_file(service, file_id: str, destination: Path) -> Path:
    """Download a Drive file by id to the destination path."""
    import io

    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(str(destination), "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                continue
    return destination


def delete_file(service, file_id: str) -> None:
    service.files().delete(fileId=file_id).execute()


def get_file_metadata(service, file_id: str) -> dict:
    return service.files().get(fileId=file_id, fields="id, name, size, mimeType").execute()


def test_connection(service) -> dict:
    """Perform a lightweight Drive API call to verify auth + connectivity."""
    about = service.about().get(fields="user(displayName, emailAddress)").execute()
    return about.get("user", {})
