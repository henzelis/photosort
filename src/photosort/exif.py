"""EXIF extraction: capture date (DateTimeOriginal) and GPS coordinates."""
from __future__ import annotations

import datetime as dt

from PIL import Image

# HEIC/HEIF support (iPhone photos) — optional, app degrades gracefully without it
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    pass

IMAGE_EXTS = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".tif", ".tiff", ".webp"}
SIDECAR_EXTS = {".aae", ".xmp"}

_DATE_FORMATS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y:%m:%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y:%m:%d",
    "%Y-%m-%d",
)


def _rational(value) -> float:
    try:
        return float(value)  # Fraction / int / float
    except (TypeError, ValueError):
        num, den = value
        return float(num) / float(den) if den else 0.0


def _dms_to_deg(dms, ref) -> float:
    d, m, s = (_rational(v) for v in dms)
    deg = d + m / 60.0 + s / 3600.0
    if str(ref).upper() in ("S", "W"):
        deg = -deg
    return deg


def parse_date(raw) -> dt.datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def get_photo_info(path) -> dict:
    """Return {'date': datetime|None, 'lat': float|None, 'lon': float|None}."""
    info = {"date": None, "lat": None, "lon": None}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
    except Exception:
        return info
    if not exif:
        return info

    # Date: DateTimeOriginal / DateTimeDigitized (Exif IFD), fallback DateTime (IFD0)
    try:
        exif_ifd = exif.get_ifd(0x8769)
    except Exception:
        exif_ifd = {}
    raw = exif_ifd.get(36867) or exif_ifd.get(36868) or exif.get(306)
    info["date"] = parse_date(raw)

    # GPS (GPS IFD): tags 1/2 = lat ref/deg, 3/4 = lon ref/deg
    try:
        gps = exif.get_ifd(0x8825)
    except Exception:
        gps = {}
    try:
        if gps.get(2) and gps.get(4):
            lat = _dms_to_deg(gps[2], gps.get(1, "N"))
            lon = _dms_to_deg(gps[4], gps.get(3, "E"))
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
                info["lat"], info["lon"] = lat, lon
    except Exception:
        pass
    return info
