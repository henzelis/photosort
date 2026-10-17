"""Basic tests: run `python -m pytest` or just `python tests/test_basic.py`."""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from photosort import organizer  # noqa: E402
from photosort.geocode import _name_from_address  # noqa: E402


def test_sanitize():
    assert organizer.sanitize('Київ/:*?"<>|') == "Київ"
    assert organizer.sanitize("  hello   world  ") == "hello world"
    assert organizer.sanitize("con") == "_con"
    assert organizer.sanitize("") == "Unknown"
    assert organizer.sanitize("x" * 200) == "x" * 80


def test_name_from_address():
    assert _name_from_address({"city": "Київ", "country": "Україна"}) == "Київ"
    assert _name_from_address({"village": "Софіївка", "county": "Херсон"}) == "Софіївка"
    assert _name_from_address({"country": "Україна"}) == "Україна"
    assert _name_from_address({"display_name": "Львів, Україна, Europe"}) == "Львів"
    assert _name_from_address({}) is None


def _make_records():
    return [
        organizer.PhotoRecord(Path("a.jpg"), dt.datetime(2024, 7, 15), 50.45, 30.52, "Київ"),
        organizer.PhotoRecord(Path("b.jpg"), dt.datetime(2024, 7, 16), 50.45, 30.52, "Київ"),
        organizer.PhotoRecord(Path("c.jpg"), dt.datetime(2023, 5, 1), None, None, None),
        organizer.PhotoRecord(Path("d.jpg"), None, 46.48, 30.72, "Одеса"),
        organizer.PhotoRecord(Path("e.png"), None, None, None, None),
    ]


def test_layout_default():
    recs = _make_records()
    organizer.build_layout(recs, organizer.MODE_DATE_LOCATION)
    assert recs[0].rel_target == Path("2024/07/Київ")
    assert recs[2].rel_target == Path("2023/05/Невідоме місце")
    assert recs[3].rel_target == Path("Без дати/Одеса")
    assert recs[4].rel_target == Path("Без дати")


def test_layout_date_only():
    recs = _make_records()
    organizer.build_layout(recs, organizer.MODE_DATE)
    assert recs[0].rel_target == Path("2024/07")
    assert recs[4].rel_target == Path("Без дати")


def test_layout_location_only():
    recs = _make_records()
    organizer.build_layout(recs, organizer.MODE_LOCATION)
    assert recs[0].rel_target == Path("Київ/2024")
    assert recs[4].rel_target == Path("Невідоме місце/Без дати")


def test_end_to_end_copy():
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "src", Path(td) / "dst"
        (src / "sub").mkdir(parents=True)
        # tiny real JPEG with no EXIF — should land in "Без дати"
        from PIL import Image
        Image.new("RGB", (8, 8), (200, 30, 30)).save(src / "sub" / "x.jpg")
        Image.new("RGB", (8, 8), (30, 200, 30)).save(src / "x.jpg")  # same basename
        stats = organizer.run(src, dst, network=False)
        assert stats["copied"] == 2 and stats["errors"] == 0
        names = sorted(p.name for p in dst.rglob("*.jpg"))
        assert names == ["x (1).jpg", "x.jpg"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if fails else 0)
