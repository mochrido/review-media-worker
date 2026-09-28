import pytest
from worker.naming import image_filename, safe_username, video_filename


@pytest.mark.parametrize("raw,expected", [
    ("tari.hutagalung", "tari.hutagalung"),
    ("@megasyana", "megasyana"),
    ("cinta-sikumbang.turki", "cinta-sikumbang.turki"),
    ("a b/c", "abc"),
    ("../../etc/passwd", "etcpasswd"),
])
def test_safe_username(raw, expected):
    assert safe_username(raw) == expected


def test_safe_username_never_empty_for_nonempty_input():
    assert safe_username("@@@") == "user"


def test_video_filename_is_always_mp4():
    assert video_filename("tari.hutagalung") == "tari.hutagalung.mp4"


def test_image_filename_keeps_extension_from_url():
    url = "https://assets.example.com/uploads/images/reviews/abc.jpeg"
    assert image_filename("tari.hutagalung", url) == "tari.hutagalung.jpeg"


def test_image_filename_strips_query_and_hash():
    url = "https://x.test/a.png?width=10#frag"
    assert image_filename("bob", url) == "bob.png"


def test_image_filename_defaults_when_no_extension():
    assert image_filename("bob", "https://x.test/noext") == "bob.jpg"


def test_safe_username_caps_length():
    # Drive and ext4 cap a name at 255 bytes; a very long username must not
    # produce a filename the upload will reject.
    out = safe_username("a" * 500)
    assert len(out) == 200
    assert len(video_filename("a" * 500)) <= 255


def test_image_filename_keeps_a_sane_extension_for_long_stems():
    url = "https://x.test/a.jpeg"
    out = image_filename("a" * 500, url)
    assert out.endswith(".jpeg")
    assert len(out) <= 255
