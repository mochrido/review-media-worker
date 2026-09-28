from worker.status import DONE, NO_MEDIA, RESTRICTED, error_status, row_status


def test_no_media_when_both_absent():
    assert row_status(False, False, None, None) == NO_MEDIA


def test_done_when_image_only_succeeds():
    # a blank video column is not expected, so it must not block DONE
    assert row_status(True, False, None, None) == DONE


def test_done_when_both_succeed():
    assert row_status(True, True, None, None) == DONE


def test_failure_wins_over_success():
    assert row_status(True, True, None, RESTRICTED) == RESTRICTED


def test_restricted_is_distinct_from_error():
    assert RESTRICTED != error_status("boom")
    assert RESTRICTED == "RESTRICTED"


def test_error_status_is_prefixed_and_truncated():
    out = error_status("x" * 500)
    assert out.startswith("ERROR: ")
    assert len(out) <= 200


def test_error_status_strips_urls():
    # a requests/Drive exception message embeds the URL; the status cell must not
    out = error_status("image fetch failed: 404 for url: https://assets.example.com/a/b.jpeg")
    assert "https://" not in out
    assert "<url>" in out
