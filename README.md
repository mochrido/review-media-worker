# Review Media Worker

Downloads each row's review image and Vimeo video from a Google Sheet, uploads them to
per-row Drive folders, and writes a status back to the sheet.

## How it runs

A menu item in the bound Google Sheet calls the GitHub Actions workflow
`process-media.yml`. The runner fetches and muxes the media, so nothing depends on the
operator's network or location.

## One-time setup

### 1. Actions secrets

In **Settings → Secrets and variables → Actions**:

| Secret | What it is |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client id |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | Refresh token for the operator's own Google account |
| `SPREADSHEET_ID` | The ID from the sheet's URL |

The worker acts **as a real user account, not a service account**. A service
account has zero Drive storage quota, so uploading into a folder in someone's
My Drive always fails with *"Service Accounts do not have storage quota"*,
however the folder is shared. The account above needs **write** access to every
destination folder; sharing a parent folder covers its subfolders.

To mint the refresh token with Drive + Sheets scope:

```
uv run --with google-auth-oauthlib python -m google_auth_oauthlib.tools.run_flow \
  --client-secrets client_secret.json --scopes \
  https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets
```

### 2. Apps Script properties

In the bound script: **Project Settings → Script properties**.

| Property | What it is |
|---|---|
| `GITHUB_REPO` | `owner/repo` |
| `GITHUB_TOKEN` | A GitHub token with `actions:write` on the repo |

The token is stored here, never in this repository — and this repository is public.

### 3. Trigger it

Open the sheet, then **Media Manager → ☁️ Run Cloud Downloader**.

Everyday users should read the **INSTRUCTION** tab in the spreadsheet — it is the
operator-facing guide (what each column means, what every status says, how to add
more reviews, and what to do when a row errors). This README is the maintainer's
view: setup, credentials, and the internals.

That runs the workflow for real. To see what it *would* do without downloading
or uploading anything, dispatch the workflow manually from the Actions tab and
tick **dry_run** (equivalently, run the worker with `--dry-run`). A dry run
prints the row count and, per row, whether it has an image and a video, then
stops — so you can confirm the `_config` mapping before spending runner minutes
or Vimeo quota.

## The `_config` tab

The worker does not guess which column is which. It reads `_config` in the sheet:

| Key | Meaning |
|---|---|
| `data_tab` | Tab holding the rows |
| `username_col` | Column with the username |
| `image_url_col` | Column with the image URL |
| `video_url_col` | Column with the Vimeo URL |
| `image_folder_col` | Column with the image's Drive folder link |
| `video_folder_col` | Column with the video's Drive folder link |
| `status_col` | Column the worker writes the status to |

If `_config` is absent the worker creates it from defaults **and stops**, so you can
review the mapping before anything moves. Missing columns are created **with their
header** — a column is never added without one.

## Statuses

| Status | Meaning |
|---|---|
| `DONE` | Everything this row asked for was downloaded and uploaded |
| `NO_MEDIA` | The row has no media URLs |
| `RESTRICTED` | The video is gated on the Vimeo account; retrying will not help |
| `ERROR: <reason>` | Something failed; fix and run again |

A blank media cell is not a failure — it means that media type was not expected. A row
with only an image is `DONE` once the image lands.

Runs are resumable: `DONE` rows are skipped, and a file that already exists is not
uploaded twice.

## Local development

```bash
pip install -r requirements.txt
python -m pytest -q
```

The tests need **ffmpeg** and **ffprobe** on `PATH` — the `has_audio` guard shells out to
`ffprobe`, and its tests generate real fixtures with `ffmpeg` rather than committing
binaries. Install ffmpeg before running the suite.

## Notes

- Never commit a service-account key, token, sheet ID, or folder ID. This repository is
  public and the workflow logs are public.
- Logs contain row numbers and statuses only.
