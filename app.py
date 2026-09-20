import json
import os
import subprocess
import tempfile

from flask import Flask, jsonify, request
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

try:  # optional: enables HEIC/HEIF (e.g. iPhone photos)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
              ".heic", ".heif", ".heics", ".heifs", ".avif", ".avifs"}
GPS_IFD_TAG = 0x8825
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg",
              ".wmv", ".flv", ".ts", ".mts", ".m2ts", ".3gp", ".mxf"}


def _file_type(ext):
    """Return 'image', 'video', or 'unknown' for a file extension."""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def _json_response(filename, filetype, metadata, size):
    """Build a normalized response body."""
    return {
        "filename": os.path.basename(filename),
        "type": filetype,
        "size": size,
        "metadata": metadata,
    }


def _clean_exif_value(value):
    """Convert an EXIF value to something JSON-safe; None means skip."""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", "strict").strip().strip("\x00")
        except UnicodeDecodeError:
            return None  # binary blob (e.g. MakerNote), not displayable
    if isinstance(value, str):
        value = value.strip().strip("\x00")
        if value and not any(c.isprintable() for c in value):
            return None  # control-char junk (e.g. raw GPS version bytes)
        return value
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            c = _clean_exif_value(v)
            if c is not None:
                cleaned[k] = c
        return cleaned
    if isinstance(value, (tuple, list)):
        cleaned = []
        for v in value:
            c = _clean_exif_value(v)
            if c is not None:
                cleaned.append(c)
        return cleaned
    if value is None or isinstance(value, (bool, int, float)):
        return value
    try:
        return float(value)  # IFDRational and other rationals
    except (TypeError, ValueError):
        return str(value)


def extract_image(path, filename):
    """Extract EXIF and format metadata from an image via Pillow."""
    md = {}
    try:
        img = Image.open(path)
    except Exception as e:  # noqa: BLE001
        md["error"] = f"Could not open image: {e}"
        return md

    md["format"] = (img.format or "unknown").upper()
    md["mode"] = img.mode
    md["dimensions"] = list(img.size)
    md["ext"] = os.path.splitext(filename)[1].lower()

    try:
        exif = img.getexif()
        if exif:
            exif_dict = {}
            for tag_id, value in exif.items():
                if tag_id == GPS_IFD_TAG:
                    try:
                        gps_ifd = exif.get_ifd(GPS_IFD_TAG)
                    except Exception:  # noqa: BLE001
                        continue
                    gps = {}
                    for gid, gval in gps_ifd.items():
                        gval = _clean_exif_value(gval)
                        if gval is None:
                            continue
                        gps[GPSTAGS.get(gid, gid)] = gval
                    if gps:
                        exif_dict["GPSInfo"] = gps
                    continue
                tag_name = TAGS.get(tag_id, tag_id)
                value = _clean_exif_value(value)
                if value is None:
                    continue
                exif_dict[tag_name] = value
            if exif_dict:
                md["exif"] = exif_dict
    except Exception as e:  # noqa: BLE001
        md["exif_error"] = str(e)
    return md


def extract_video(path):
    """Extract container/probe metadata from a video via ffprobe."""
    try:
        probe = _ffprobe(path)
    except FileNotFoundError:
        return {"error": "ffprobe not installed"}
    if "error" in probe:
        return {"error": probe["error"]}

    md = {"raw": probe}
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            md.setdefault("codec", stream.get("codec_name"))
            md.setdefault("resolution",
                          [stream.get("width"), stream.get("height")])
        elif stream.get("codec_type") == "audio":
            md.setdefault("audio_codec", stream.get("codec_name"))
            md.setdefault("audio_sample_rate", stream.get("sample_rate"))
    md.setdefault("duration", probe.get("format", {}).get("duration"))
    return md


def _ffprobe(path):
    """Run ffprobe and return parsed JSON."""
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format",
           "-of", "json", path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"error": proc.stderr}
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        return {"error": str(e)}


def _save(file, ext):
    """Save an uploaded file to a temp path and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    file.save(tmp.name)
    tmp.close()
    return tmp.name


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/metadata", methods=["POST"])
def metadata():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No selected file"}), 400

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    filetype = _file_type(ext)

    if filetype == "unknown":
        size = len(file.read())
        body = _json_response(filename, "unknown",
                              {"error": "Unsupported file type"}, size)
        return jsonify(body), 200

    tmp = _save(file, ext)
    try:
        if filetype == "image":
            md = extract_image(tmp, filename)
        else:
            md = extract_video(tmp)
        body = _json_response(filename, filetype, md, os.stat(tmp).st_size)
        return jsonify(body), 200
    finally:
        os.unlink(tmp)


@app.route("/", methods=["GET"])
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(debug=True)