<p align="center">
  <img src="static/logo.png" width="80" height="80" alt="MetaScope logo">
</p>

<h1 align="center">MetaScope</h1>

<p align="center">Metadata extractor for images and videos with a web GUI</p>

<p align="center">
  <strong>Developed by Ritche Gerona</strong><br>
  <a href="https://github.com/ritchegerona/MetaScope">GitHub</a>
</p>

---

## Overview

MetaScope extracts metadata from uploaded images and videos and displays it in a clean, searchable web interface. It supports EXIF, IPTC, XMP, and GPS data from images, plus codec, resolution, duration, and container tags from videos. Results can be viewed in the browser and exported to five formats.

## Features

- **Image metadata** -- format, mode, dimensions, EXIF, IPTC, XMP, GPS via ExifTool (with Pillow EXIF fallback)
- **Video metadata** -- codec, resolution, audio, duration via ffprobe, plus ExifTool container tags
- **HEIC/AVIF support** -- iPhone and modern camera formats via pillow-heif
- **Web GUI** -- drag-and-drop upload, Details and Raw JSON tabs, 6 color themes (light, dark, ocean, forest, sunset, mono)
- **Export** -- download results as TXT, Markdown, CSV, JSON, or PDF
- **JSON API** -- programmatic access via `POST /api/metadata`
- **Health check** -- `GET /api/health` reports which tools are installed

## Requirements

| Dependency | Purpose | Required? |
|---|---|---|
| Python 3.9+ | Runtime | Yes |
| Flask | Web framework | Yes (in requirements.txt) |
| Pillow | Image processing | Yes (in requirements.txt) |
| pillow-heif | HEIC/AVIF support | Yes (in requirements.txt) |
| ffmpeg / ffprobe | Video metadata extraction | Optional -- images work without it |
| ExifTool | Rich EXIF/IPTC/XMP extraction | Optional -- Pillow EXIF is used as fallback |

## Installation

### 1. Clone the repository

```sh
git clone https://github.com/ritchegerona/MetaScope.git
cd MetaScope
```

### 2. Create and activate a virtual environment

```sh
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```sh
pip install -r requirements.txt
```

### 4. Install optional system tools

```sh
# macOS (Homebrew)
brew install ffmpeg exiftool

# Ubuntu / Debian
sudo apt install ffmpeg libimage-exiftool-perl

# Windows (Chocolatey or winget)
choco install ffmpeg exiftool
```

## Configuration

MetaScope uses sensible defaults. Override them by editing `app.py` before running.

| Setting | Default | Description |
|---|---|---|
| Port | `8000` | Port 5000 is reserved by macOS AirPlay Receiver |
| Debug mode | `True` | Set to `False` in production |
| Max upload | 100 MB | Controlled by `MAX_CONTENT_LENGTH` |
| Theme | Light | Saved in browser localStorage |

## Running

```sh
python app.py
```

Open **http://127.0.0.1:8000** in your browser.

> If you open the HTML file directly (via `file://`), you will see a warning telling you to start the server first.

## Usage -- Web GUI

1. **Upload** -- drag and drop a file or click the upload zone to browse
2. **Extract** -- click the **Extract metadata** button
3. **View results** -- switch between **Details** (grouped key-value cards) and **Raw JSON** tabs
4. **Export** -- click **TXT**, **Markdown**, **CSV**, **JSON**, or **PDF** to download the results
5. **Switch theme** -- click any swatch in the header (saved to localStorage)

### Supported file types

**Images:** `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.webp` `.tiff` `.tif` `.heic` `.heif` `.heics` `.heifs` `.avif` `.avifs`

**Videos:** `.mp4` `.mov` `.avi` `.mkv` `.webm` `.m4v` `.mpg` `.mpeg` `.wmv` `.flv` `.ts` `.mts` `.m2ts` `.3gp` `.mxf`

## Exports

All exports are named after the uploaded file (e.g. `IMG_8373.md`). Group prefixes are stripped from keys for readability (`exif.Aperture` becomes `Aperture`).

| Format | Description |
|---|---|
| **TXT** | Plain text, one key-value pair per line |
| **Markdown** | Table with Key and Value columns |
| **CSV** | RFC-compliant escaped CSV with header row |
| **JSON** | Pretty-printed full API response |
| **PDF** | Formatted document with bold keys (uses jsPDF CDN) |

## API

### Health check

```
GET /api/health
```

Returns available tool status:

```json
{
  "status": "ok",
  "exiftool": true,
  "ffprobe": true
}
```

### Extract metadata

```
POST /api/metadata
```

Accepts a multipart form upload with a file field named `file`. Returns JSON with filename, detected type, file size, and extracted metadata.

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `filename` | string | Original filename |
| `type` | string | `image`, `video`, or `unknown` |
| `size` | integer | File size in bytes |
| `metadata` | object | Extracted metadata (structure depends on file type) |

**Image metadata fields** (from ExifTool or Pillow fallback):

- `format`, `mode`, `dimensions`, `ext`
- `exif` -- camera settings, GPS, lens info, timestamps
- `iptc` -- captions, keywords, copyright
- `xmp` -- creator tool, dates, custom properties

**Video metadata fields** (from ffprobe + ExifTool):

- `codec`, `resolution`, `audio_codec`, `audio_sample_rate`, `duration`
- `tags` -- container-level metadata (make, model, encoder, etc.)
- `raw` -- full ffprobe JSON dump (format + streams)

**Error case** (unsupported file type):

```json
{
  "filename": "readme.txt",
  "type": "unknown",
  "size": 1234,
  "metadata": { "error": "Unsupported file type" }
}
```

**Example:**

```sh
curl -F "file=@photo.jpg" http://127.0.0.1:8000/api/metadata
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
static/
  index.html         Web UI (upload, themes, tabs, export)
  logo.png           MetaScope brand mark
tests/
  test_metadata.py   pytest test suite
requirements.txt     Python dependencies
README.md            This file
LICENSE              MIT license
```

## License

MIT -- Copyright (c) 2026 Ritche Gerona
