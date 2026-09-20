import json
import os
import shutil
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

# ExifTool groups merged into image EXIF output, in ascending priority
# (later groups override earlier ones on tag-name collisions).
EXIF_FAMILY_GROUPS = ("Composite", "EXIF", "IFD0", "ExifIFD", "GPS",
                      "InteropIFD", "SubIFD")
# Groups/tags dropped from ExifTool output: temp-file artifacts and noise.
EXIFTOOL_SKIP_GROUPS = {"ExifTool"}
EXIFTOOL_SKIP_TAGS = {"SourceFile", "FileName", "Directory", "FileModifyDate",
                      "FileAccessDate", "FileInodeChangeDate", "FilePermissions",
                      "ExifToolVersion"}


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


def _has_exiftool():
    """Return True when the exiftool binary is on PATH."""
    return shutil.which("exiftool") is not None


def _exiftool(path):
    """Run exiftool and return its parsed JSON dict for the file.

    Returns {"error": ...} when the binary is missing, times out, or fails.
    Keys use the 'GROUP:Tag' form (via -G -s) for lossless grouping.
    """
    try:
        proc = subprocess.run(["exiftool", "-j", "-G", "-s", path],
                              capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return {"error": "exiftool not installed"}
    except subprocess.TimeoutExpired:
        return {"error": "exiftool timed out"}
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or "exiftool failed"}
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as e:
        return {"error": str(e)}
    if not data:
        return {"error": "exiftool returned no data"}
    return data[0]


def _group_exiftool(raw):
    """Split a flat 'GROUP:Tag' dict into {group: {tag: value}}, sanitized."""
    groups = {}
    for key, value in raw.items():
        group, sep, tag = key.partition(":")
        if not sep:
            group, tag = "", key
        if group in EXIFTOOL_SKIP_GROUPS or tag in EXIFTOOL_SKIP_TAGS:
            continue
        value = _clean_exif_value(value)
        if value is None:
            continue
        groups.setdefault(group, {})[tag] = value
    return groups


def _enrich_image_exif(md, raw):
    """Merge ExifTool EXIF/IPTC/XMP groups into image metadata (in place)."""
    groups = _group_exiftool(raw)
    merged = {}
    for group in EXIF_FAMILY_GROUPS:
        merged.update(groups.get(group, {}))
    if merged:
        md["exif"] = merged
    if groups.get("IPTC"):
        md["iptc"] = groups["IPTC"]
    xmp = {}
    for group in sorted(groups):
        if group == "XMP" or group.startswith("XMP-"):
            xmp.update(groups[group])
    if xmp:
        md["xmp"] = xmp


def extract_image(path, filename):
    """Extract image metadata: Pillow basics + ExifTool EXIF/IPTC/XMP."""
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

    raw = _exiftool(path) if _has_exiftool() else {"error": "exiftool not installed"}
    if "error" not in raw:
        _enrich_image_exif(md, raw)
        return md

    # Fallback when exiftool is unavailable: Pillow EXIF only.
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
    """Extract video metadata: ffprobe streams/format + ExifTool tags."""
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

    if _has_exiftool():
        raw = _exiftool(path)
        if "error" not in raw:
            groups = _group_exiftool(raw)
            tags = {}
            for group in sorted(groups):
                tags.update(groups[group])
            if tags:
                md["tags"] = tags
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
    return jsonify({
        "status": "ok",
        "exiftool": _has_exiftool(),
        "ffprobe": shutil.which("ffprobe") is not None,
    }), 200


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
    app.run(debug=True, port=8000)