"""Entry point.

Reads the sheet, processes each eligible row, writes statuses. One bad row
never aborts the run.
"""

import argparse
import json
import os
import sys
import tempfile

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

from worker import config, drive, images, naming, sheets, videos
from worker.status import error_status, row_status

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _cell(row, index):
    return str(row[index]).strip() if len(row) > index and row[index] is not None else ""


def row_plan(rows, mapping) -> list[dict]:
    """Turn sheet rows into work items, filling folder cells down.

    A blank folder cell inherits the nearest non-empty value above it, which
    is how a spreadsheet user reads a merged-looking column.
    """
    if not rows:
        return []
    username_i = config.col_to_index(mapping["username_col"])
    image_i = config.col_to_index(mapping["image_url_col"])
    video_i = config.col_to_index(mapping["video_url_col"])
    image_folder_i = config.col_to_index(mapping["image_folder_col"])
    video_folder_i = config.col_to_index(mapping["video_folder_col"])
    status_i = config.col_to_index(mapping["status_col"])

    plan = []
    last_image_folder = ""
    last_video_folder = ""
    for offset, row in enumerate(rows[1:], start=2):  # row 1 is the header
        username = _cell(row, username_i)
        if not username:
            continue
        status = _cell(row, status_i).upper()
        if status == "DONE":
            continue

        image_folder = _cell(row, image_folder_i) or last_image_folder
        video_folder = _cell(row, video_folder_i) or last_video_folder
        last_image_folder = image_folder or last_image_folder
        last_video_folder = video_folder or last_video_folder

        image_url = _cell(row, image_i)
        video_url = _cell(row, video_i)
        plan.append({
            "row_index": offset,
            "username": username,
            "image_url": image_url,
            "video_url": video_url,
            "image_folder": image_folder,
            "video_folder": video_folder,
            "has_image": bool(image_url),
            "has_video": bool(video_url),
        })
    return plan


def _service():
    """Sheets + Drive clients from the service-account key in the environment."""
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return (build("sheets", "v4", credentials=credentials),
            build("drive", "v3", credentials=credentials))


def bootstrap(sheets_service, tab: str, mapping: dict):
    """Ensure _config and any mapped columns exist, with headers.

    Returns True when something was created, which means the operator must
    look at it before a real run — the worker never guesses a mapping.
    """
    created = False
    if not sheets.read_config(sheets_service):
        sheets.create_config_tab(sheets_service, tab, mapping)
        created = True
    header = sheets.read_header(sheets_service, tab)
    sheets.ensure_columns(sheets_service, tab, header, mapping)
    return created


def process_row(item, drive_service, session, workdir):
    """Do the row's work. Returns (image_error, video_error); either may be None."""
    image_error = video_error = None
    if item["has_image"]:
        try:
            data, mime = images.fetch_image(item["image_url"], session)
            folder = drive.folder_id_from_url(item["image_folder"])
            name = naming.image_filename(item["username"], item["image_url"])
            if not drive.find_existing(drive_service, folder, name):
                drive.upload(drive_service, folder, name, data, mime)
        except Exception as exc:
            image_error = error_status(exc)
    if item["has_video"]:
        try:
            path = videos.download_video(item["video_url"], workdir)
            if not videos.has_audio(path):
                raise videos.VideoError(error_status("downloaded file has no audio"))
            folder = drive.folder_id_from_url(item["video_folder"])
            name = naming.video_filename(item["username"])
            if not drive.find_existing(drive_service, folder, name):
                with open(path, "rb") as handle:
                    drive.upload(drive_service, folder, name, handle.read(), "video/mp4")
        except videos.VideoError as exc:
            video_error = exc.status
        except Exception as exc:
            video_error = error_status(exc)
    return image_error, video_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="report the plan without downloading anything")
    args = parser.parse_args()

    sheets_service, drive_service = _service()
    mapping = config.parse_mapping(sheets.read_config(sheets_service))
    tab = mapping["data_tab"]

    if bootstrap(sheets_service, tab, mapping):
        print("provisioned _config and/or missing columns with headers")
        print("review the _config tab, then run again")
        return 0

    rows = sheets.read_rows(sheets_service, tab)
    plan = row_plan(rows, mapping)
    print(f"rows to process: {len(plan)}")  # counts only, never contents

    if args.dry_run:
        for item in plan:
            print(f"  row {item['row_index']}: image={item['has_image']} video={item['has_video']}")
        return 0

    session = requests.Session()
    updates = {}
    for item in plan:
        with tempfile.TemporaryDirectory() as workdir:
            image_error, video_error = process_row(item, drive_service, session, workdir)
        status = row_status(item["has_image"], item["has_video"], image_error, video_error)
        updates[item["row_index"]] = status
        # log the row number and the status word only — never the URL or username
        print(f"  row {item['row_index']}: {status.split(':')[0]}")

    sheets.write_statuses(sheets_service, tab, config.col_to_index(mapping["status_col"]), updates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
