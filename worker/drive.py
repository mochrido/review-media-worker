"""Google Drive access: folder URLs and uploads.

Every Drive call passes supportsAllDrives — the destination folders live on
shared drives, and without it the API answers 404 for a folder that exists.
"""

import io
import re

_FOLDER = re.compile(r"/folders/([-\w]{20,})")
_OPEN_ID = re.compile(r"[?&]id=([-\w]{20,})")
_FILE = re.compile(r"/file/d/([-\w]{20,})")


def folder_id_from_url(url: str) -> str:
    """Extract a folder ID from a Drive folder URL.

    Raises ValueError for anything that is not a folder link — including a
    FILE link, which would otherwise be silently accepted by the ?id= pattern.
    """
    if not url:
        raise ValueError("empty folder URL")
    text = str(url).strip()
    if _FILE.search(text):
        raise ValueError("URL points to a file, not a folder")
    match = _FOLDER.search(text)
    if match:
        return match.group(1)
    match = _OPEN_ID.search(text)
    if match:
        return match.group(1)
    raise ValueError("could not read a folder ID from this URL")


def find_existing(service, folder_id: str, name: str):
    """Return the ID of an existing file with this name, or None.

    Used so a retry does not upload a second copy of a file that already
    landed before the other media type failed.
    """
    query = (
        f"'{folder_id}' in parents and name = '{name.replace(chr(39), chr(92) + chr(39))}'"
        " and trashed = false"
    )
    result = service.files().list(
        q=query, fields="files(id)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def upload(service, folder_id: str, filename: str, data: bytes, mime: str) -> str:
    """Upload bytes as `filename` into `folder_id`. Returns the new file ID."""
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    created = service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media, fields="id", supportsAllDrives=True,
    ).execute()
    return created["id"]
