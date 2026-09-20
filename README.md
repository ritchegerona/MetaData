# MetaData — metadata collector for images and videos with a web GUI

## Features

- Image metadata extraction via Pillow: format, mode, dimensions, and EXIF data
- Rich EXIF/IPTC/XMP extraction via ExifTool when installed (GPS, camera settings, captions); Pillow EXIF used as fallback
- Video metadata extraction via ffprobe: codecs, resolution, duration, and raw container probe, plus ExifTool container tags
- Web UI at `/` for upload and metadata display
- JSON API at `POST /api/metadata` for programmatic access

## Requirements

- Python 3.9+
- System `ffmpeg`/`ffprobe` installed for video metadata support (images work without it)
- System `exiftool` installed for rich EXIF/IPTC/XMP extraction (optional; Pillow EXIF is used as fallback)

## Installation

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
  # optional: for video support
  brew install ffmpeg
  # optional: for rich EXIF/IPTC/XMP support
  brew install exiftool
  ```

## Usage

Run the app and open the browser:

```sh
python app.py
```

Then visit `http://127.0.0.1:5000` and upload a file. The app runs with `debug=True`.

## API

### `GET /api/health`

Health check. Returns:

```json
{"status": "ok", "exiftool": true, "ffprobe": true}
```

`exiftool`/`ffprobe` report whether those optional binaries are available.

### `POST /api/metadata`

Accepts a multipart form upload with a file field named `file`. Returns:

```json
{
  "filename": "photo.jpg",
  "type": "image",
  "size": 12345,
  "metadata": { ... }
}
```

`type` is `"image"`, `"video"`, or `"unknown"`. The `metadata` object contents depend on the file type. Example:

```sh
curl -F "file=@photo.jpg" http://127.0.0.1:5000/api/metadata
```

Files are limited to 100 MB.

## Testing

Run the test suite (ffmpeg must be installed for the video test):

```sh
.venv/bin/python -m pytest -q
```

## Project Structure

```
app.py               Flask application and metadata extraction
static/index.html    Web UI upload form
tests/               pytest test suite
requirements.txt     Python dependencies
README.md            This file
```

## License

MIT