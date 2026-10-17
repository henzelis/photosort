"""Command-line interface. With no arguments it launches the GUI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, organizer


def force_utf8_stdout() -> None:
    """Windows consoles default to cp1252/cp866 — Ukrainian log text would crash print()."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv=None) -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(
        prog="photosort",
        description="Сортування фотографій за датою та місцем (EXIF + GPS + геокодинг).",
    )
    parser.add_argument("src", nargs="?", help="Вхідна папка з фото (рекурсивно)")
    parser.add_argument("dst", nargs="?", help="Папка для відсортованих фото")
    parser.add_argument(
        "--mode", choices=organizer.MODES, default=organizer.MODE_DATE_LOCATION,
        help="date_location (типово): рік/місяць/місце; date: рік/місяць; location: місце/рік",
    )
    parser.add_argument("--move", action="store_true",
                        help="переміщувати файли замість копіювання")
    parser.add_argument("--no-network", action="store_true",
                        help="не звертатись до Nominatim (папки місць матимуть координати/«Невідоме місце»)")
    parser.add_argument("--lang", default="uk", help="мова назв місць (default: uk)")
    parser.add_argument("--dry-run", action="store_true",
                        help="лише показати план, нічого не копіювати")
    parser.add_argument("--version", action="version", version=f"photosort {__version__}")
    args = parser.parse_args(argv)

    if not args.src or not args.dst:
        # GUI mode
        try:
            from .gui import run_gui
        except ImportError:
            print("Для GUI потрібен tkinter. Або вкажіть папки в аргументах (photosort --help).",
                  file=sys.stderr)
            return 2
        run_gui()
        return 0

    src, dst = Path(args.src), Path(args.dst)
    if not src.is_dir():
        print(f"Помилка: вхідна папка не існує: {src}", file=sys.stderr)
        return 2

    if args.dry_run:
        records = organizer.scan(src)
        geocoder = organizer.Geocoder(lang=args.lang) if not args.no_network else None
        organizer.resolve_places(records, geocoder)
        if geocoder and geocoder.new_hits:
            geocoder.save_cache()
        organizer.build_layout(records, args.mode)
        planned: set = set()
        for r in records:
            dest = dst / r.rel_target / r.path.name
            stem, suffix, i = dest.stem, dest.suffix, 1
            while dest in planned:
                dest = dest.with_name(f"{stem} ({i}){suffix}")
                i += 1
            planned.add(dest)
            print(f"{r.path}  ->  {dest}")
        return 0

    organizer.run(src, dst, mode=args.mode, move=args.move,
                  lang=args.lang, network=not args.no_network)
    return 0


if __name__ == "__main__":
    sys.exit(main())
