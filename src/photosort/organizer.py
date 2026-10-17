"""Core organizing logic: scan, extract metadata, build folder layout, copy/move."""
from __future__ import annotations

import datetime as dt
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import exif
from .geocode import Geocoder

MODE_DATE = "date"
MODE_LOCATION = "location"
MODE_DATE_LOCATION = "date_location"
MODES = (MODE_DATE, MODE_LOCATION, MODE_DATE_LOCATION)
UNKNOWN_PLACE = "Невідоме місце"
UNKNOWN_DATE = "Без дати"

# Windows-forbidden characters (plus control chars), applied on every OS for portability
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def sanitize(name: str, max_len: int = 80) -> str:
    """Make a filesystem-safe folder name, preserving Unicode (Cyrillic etc.)."""
    name = unicodedata.normalize("NFC", str(name)).strip()
    name = _FORBIDDEN.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "Unknown"
    if name.lower().split(".")[0] in _WINDOWS_RESERVED:
        name = "_" + name
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name or "Unknown"


def slugify(name: str) -> str:
    """Normalize a place name for grouping (case-insensitive, trimmed)."""
    return re.sub(r"\s+", " ", str(name)).strip().casefold()


@dataclass
class PhotoRecord:
    path: Path
    date: dt.datetime | None = None
    lat: float | None = None
    lon: float | None = None
    place: str | None = None
    rel_target: Path | None = None  # folder path relative to output dir


def iter_photos(src: Path):
    """Yield image files from src, recursively."""
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("._") or path.name.startswith("."):
            continue  # macOS resource forks / dotfiles
        if path.suffix.lower() in exif.IMAGE_EXTS:
            yield path


def scan(src: Path, log=print) -> list[PhotoRecord]:
    records: list[PhotoRecord] = []
    for path in iter_photos(src):
        info = exif.get_photo_info(path)
        records.append(PhotoRecord(path=path, **info))
    log(f"Знайдено фото: {len(records)}")
    return records


def resolve_places(records: list[PhotoRecord], geocoder: Geocoder | None, log=print) -> None:
    geo = [r for r in records if r.lat is not None and r.lon is not None]
    if not geo:
        return
    uniq: dict[str, list[PhotoRecord]] = {}
    for r in geo:
        uniq.setdefault(Geocoder._key(r.lat, r.lon), []).append(r)
    log(f"Геотеги: {len(geo)} фото, {len(uniq)} унікальних точок")
    for i, (_key, group) in enumerate(uniq.items(), 1):
        r = group[0]
        name = geocoder.reverse(r.lat, r.lon) if geocoder else None
        place = sanitize(name) if name else UNKNOWN_PLACE
        if name is None and geocoder is None:
            place = UNKNOWN_PLACE
        log(f"  [{i}/{len(uniq)}] {r.lat:.4f}, {r.lon:.4f} -> {place}")
        for g in group:
            g.place = place


def unique_place_map(records: list[PhotoRecord]) -> dict[str, str]:
    """Cluster near-identical raw place names so Kyiv == kyiv == Київ? (case-insensitive only)."""
    seen: dict[str, str] = {}
    for r in records:
        if r.place:
            seen.setdefault(slugify(r.place), r.place)
    return seen


def build_layout(records: list[PhotoRecord], mode: str) -> None:
    """Assign rel_target to every record according to the chosen mode."""
    for r in records:
        year = f"{r.date.year:04d}" if r.date else UNKNOWN_DATE
        month = f"{r.date.month:02d}" if r.date else UNKNOWN_DATE
        place = sanitize(r.place) if r.place else UNKNOWN_PLACE

        if mode == MODE_DATE:
            r.rel_target = Path(year, month) if r.date else Path(UNKNOWN_DATE)
        elif mode == MODE_LOCATION:
            r.rel_target = Path(place, year)
        else:  # MODE_DATE_LOCATION — default: year / month / place
            if r.date:
                r.rel_target = Path(year, month, place)
            elif r.place:
                # avoid silly "Без дати/Без дати" nesting
                r.rel_target = Path(UNKNOWN_DATE, place)
            else:
                r.rel_target = Path(UNKNOWN_DATE)


def _unique_copy_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        cand = dest.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1


def run(src: Path, dst: Path, mode: str = MODE_DATE_LOCATION, move: bool = False,
        lang: str = "uk", network: bool = True, log=print, progress=None) -> dict:
    """Full pipeline. Returns stats dict."""
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        raise FileNotFoundError(f"Вхідна папка не існує: {src}")
    if dst.resolve() == src.resolve():
        raise ValueError("Папка призначення повинна відрізнятися від вхідної.")

    records = scan(src, log=log)
    if not records:
        log("Немає фото для обробки.")
        return {"total": 0, "copied": 0, "moved": 0, "skipped": 0, "errors": 0}

    geocoder = Geocoder(lang=lang, log=log) if network else None
    resolve_places(records, geocoder, log=log)
    if geocoder and geocoder.new_hits:
        geocoder.save_cache()

    build_layout(records, mode)

    copied = moved = skipped = errors = 0
    total = len(records)
    for i, r in enumerate(records, 1):
        try:
            out_dir = dst / r.rel_target
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / r.path.name
            if move:
                shutil.move(str(r.path), str(_unique_copy_dest(dest)))
                moved += 1
            else:
                shutil.copy2(str(r.path), str(_unique_copy_dest(dest)))
                copied += 1
        except (OSError, shutil.Error) as exc:
            errors += 1
            log(f"  ! Помилка {r.path}: {exc}")
        if progress:
            progress(i, total)

    log(f"Готово: {'переміщено' if move else 'скопійовано'} {moved + copied}, "
        f"помилок: {errors}")
    return {"total": total, "copied": copied, "moved": moved, "skipped": skipped, "errors": errors}
