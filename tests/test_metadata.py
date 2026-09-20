import io
import json
import os
import struct
import tempfile

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _upload(client, filename: str, data: bytes, content_type: str = "application/octet-stream"):
    return client.post(
        "/api/metadata",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


# ── Image metadata ──────────────────────────────────────────────

def _make_tiny_png() -> bytes:
    """Create a valid minimal 1x1 white PNG."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buf, format="PNG")
    return buf.getvalue()


def _make_jpg_with_exif() -> bytes:
    """Create a 1x1 JPEG with EXIF data."""
    from PIL import Image
    from PIL.ExifTags import Base as ExifBase

    img = Image.new("RGB", (1, 1), "red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_no_file_returns_400(client):
    r = client.post("/api/metadata", data={}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_root_serves_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<html" in r.data.lower()


def test_png_returns_metadata(client):
    png = _make_tiny_png()
    r = _upload(client, "test.png", png)
    assert r.status_code == 200
    body = r.get_json()
    assert body["filename"] == "test.png"
    assert body["type"] == "image"
    assert body["size"] == len(png)
    assert "format" in body["metadata"]
    assert body["metadata"]["dimensions"] == [1, 1]


def test_jpg_returns_metadata(client):
    jpg = _make_jpg_with_exif()
    r = _upload(client, "photo.jpg", jpg)
    assert r.status_code == 200
    body = r.get_json()
    assert body["type"] == "image"
    assert body["metadata"]["format"] == "JPEG"
    assert body["size"] == len(jpg)


# ── Video metadata ──────────────────────────────────────────────

def _make_tiny_mp4() -> bytes:
    """Create a minimal MP4 via ffprobe-testable structure."""
    # Use ffmpeg to make a 1-frame MP4
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        tmppath = f.name
    try:
        os.system(
            f"ffmpeg -y -f lavfi -i color=c=black:s=2x2:d=0.04 "
            f"-c:v libx264 -pix_fmt yuv420p {tmppath} 2>/dev/null"
        )
        with open(tmppath, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmppath)


def test_mp4_returns_metadata(client):
    mp4 = _make_tiny_mp4()
    r = _upload(client, "video.mp4", mp4)
    assert r.status_code == 200
    body = r.get_json()
    assert body["type"] == "video"
    assert body["size"] == len(mp4)
    assert "duration" in body["metadata"]
    assert "codec" in body["metadata"]
    assert "resolution" in body["metadata"]


def test_unsupported_file_type(client):
    r = _upload(client, "readme.txt", b"hello world")
    assert r.status_code == 200
    body = r.get_json()
    assert body["type"] == "unknown"
    assert body["size"] == len(b"hello world")
    assert "error" in body["metadata"]


def _make_jpg_with_gps_exif() -> bytes:
    """Create a JPEG with decoded GPS EXIF (like a phone photo)."""
    from PIL import Image

    img = Image.new("RGB", (4, 3), "blue")
    exif = img.getexif()
    exif[271] = "TestMake"
    exif.get_ifd(0x8825).update({1: "N", 2: (37, 46, 30), 3: "W", 4: (122, 25, 10)})
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_jpg_gps_exif_is_decoded(client):
    jpg = _make_jpg_with_gps_exif()
    r = _upload(client, "photo.jpg", jpg)
    assert r.status_code == 200
    body = r.get_json()
    gps = body["metadata"]["exif"]["GPSInfo"]
    assert isinstance(gps, dict)
    assert gps["GPSLatitudeRef"] == "N"
    assert list(gps["GPSLatitude"]) == [37, 46, 30]


def test_heic_returns_metadata(client):
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image

    heif = pillow_heif.from_pillow(Image.new("RGB", (8, 6), "green"))
    buf = io.BytesIO()
    heif.save(buf, format="HEIF")
    data = buf.getvalue()
    r = _upload(client, "photo.heic", data)
    assert r.status_code == 200
    body = r.get_json()
    assert body["type"] == "image"
    assert body["size"] == len(data)
    assert body["metadata"]["dimensions"] == [8, 6]
