"""Row outcome vocabulary and the decision rule.

One status column covers both media types. A blank cell is not a failure:
it means that media type was never expected for the row.
"""

DONE = "DONE"
NO_MEDIA = "NO_MEDIA"
RESTRICTED = "RESTRICTED"

_MAX_REASON = 180


def error_status(reason: str) -> str:
    """Build an ERROR status. Truncated so a long message cannot be clipped
    mid-cell by the spreadsheet's 50k limit.

    URLs are stripped: a requests/Drive exception message embeds the full URL
    or file ID, and the status cell is the one place that must not carry it.
    """
    import re
    reason = " ".join(str(reason).split())
    reason = re.sub(r"https?://\S+", "<url>", reason)
    if len(reason) > _MAX_REASON:
        reason = reason[:_MAX_REASON] + "..."
    return "ERROR: " + reason


def row_status(image_present: bool, video_present: bool,
               image_error: str | None, video_error: str | None) -> str:
    """Decide a row's status.

    A present-but-failed media type always wins over a success, so a row is
    never reported DONE while something it asked for is missing.
    """
    if not image_present and not video_present:
        return NO_MEDIA
    if video_error:
        return video_error
    if image_error:
        return image_error
    return DONE
