"""Local web server for the PhotoSort premium UI (stdlib only, 127.0.0.1)."""
from __future__ import annotations

import io
import json
import os
import socket
import threading
import time
import urllib.parse
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, exif, organizer
from .geocode import Geocoder

WEB_DIR = Path(__file__).parent / "web"
THUMB_SIZE = 260
MAX_LOG = 400


class Cancelled(Exception):
    pass


class Job:
    """Single global job: scan -> plan -> run, with progress + log ring."""

    def __init__(self):
        self.lock = threading.Lock()
        self.reset("empty")
        self.thumb_cache: dict[int, bytes] = {}

    def reset(self, state: str):
        self.state = state
        self.records: list[organizer.PhotoRecord] = []
        self.src: Path | None = None
        self.dst: Path | None = None
        self.mode = organizer.MODE_DATE_LOCATION
        self.move = False
        self.network = True
        self.logq: deque[str] = deque(maxlen=MAX_LOG)
        self.prog = {"phase": "", "done": 0, "total": 0}
        self.result: dict | None = None
        self.error: str | None = None
        self.cancel = False
        self.thread: threading.Thread | None = None
        self.map_points: list[dict] = []
        self.months: list[dict] = []
        self.years: list[str] = []
        self.tree: dict | None = None
        self.stats: dict = {}

    def log(self, msg: str):
        self.logq.append(str(msg))

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


JOB = Job()


# ---------------------------------------------------------------- job steps
def _check_cancel(job: Job):
    if job.cancel:
        raise Cancelled()


def _scan_job(job: Job, src: Path, lang: str = "uk"):
    try:
        job.log(f"Скануємо: {src}")
        files = list(organizer.iter_photos(src))
        job.prog = {"phase": "scan", "done": 0, "total": len(files)}
        recs: list[organizer.PhotoRecord] = []
        for i, path in enumerate(files):
            _check_cancel(job)
            info = exif.get_photo_info(path)
            recs.append(organizer.PhotoRecord(path=path, **info))
            job.prog["done"] = i + 1
            if (i + 1) % 250 == 0 or i + 1 == len(files):
                job.log(f"  Прочитано {i + 1}/{len(files)}")
        job.records = recs
        job.stats = {
            "total": len(recs),
            "geo": sum(1 for r in recs if r.lat is not None),
            "dated": sum(1 for r in recs if r.date),
        }
        if job.network:
            _geocode_job(job, lang)
        _build_geo_aggregates(job)
        _build_month_aggregates(job)
        _pick_thumbs(job)
        job.state = "ready"
        job.log(f"Готово: {len(recs)} фото, {job.stats['geo']} з геотегом")
    except Cancelled:
        job.reset("empty")
        job.log("Сканування скасовано.")
    except Exception as exc:
        job.state, job.error = "error", str(exc)
        job.log(f"Помилка сканування: {exc}")


def _geocode_job(job: Job, lang: str):
    geo_recs = [r for r in job.records if r.lat is not None and r.lon is not None]
    uniq: dict[str, list] = {}
    for r in geo_recs:
        uniq.setdefault(Geocoder._key(r.lat, r.lon), []).append(r)
    if not uniq:
        return
    job.log(f"Геокодинг: {len(uniq)} унікальних точок")
    geocoder = Geocoder(lang=lang, log=job.log)
    done = 0
    for key, group in uniq.items():
        _check_cancel(job)
        r = group[0]
        name = geocoder.reverse(r.lat, r.lon)
        place = organizer.sanitize(name) if name else organizer.UNKNOWN_PLACE
        for g in group:
            g.place = place
        done += 1
        job.prog = {"phase": "geo", "done": done, "total": len(uniq)}
        if name:
            job.log(f"  [{done}/{len(uniq)}] {r.lat:.4f}, {r.lon:.4f} → {place}")
    if geocoder.new_hits:
        geocoder.save_cache()


def _plan_job(job: Job, mode: str):
    try:
        job.mode = mode
        organizer.build_layout(job.records, mode)
        job.tree = _build_tree(job)
        job.state = "planned"
        job.log("План побудовано.")
    except Cancelled:
        job.log("Планування скасовано.")
        job.state = "ready"
    except Exception as exc:
        job.state, job.error = "error", str(exc)
        job.log(f"Помилка планування: {exc}")


def _run_job(job: Job, dst: Path, move: bool):
    import shutil
    try:
        if job.tree is None:
            organizer.build_layout(job.records, job.mode)
            job.tree = _build_tree(job)
        job.dst, job.move = dst, move
        job.log(f"{'Переміщуємо' if move else 'Копіюємо'} → {dst}")
        copied = moved = errors = 0
        total = len(job.records)
        job.prog = {"phase": "copy", "done": 0, "total": total}
        for i, r in enumerate(job.records):
            _check_cancel(job)
            try:
                out_dir = dst / r.rel_target
                out_dir.mkdir(parents=True, exist_ok=True)
                dest = out_dir / r.path.name
                if move:
                    shutil.move(str(r.path), str(organizer._unique_copy_dest(dest)))
                    moved += 1
                else:
                    shutil.copy2(str(r.path), str(organizer._unique_copy_dest(dest)))
                    copied += 1
            except (OSError, shutil.Error) as exc:
                errors += 1
                job.log(f"  ! {r.path}: {exc}")
            job.prog["done"] = i + 1
            if (i + 1) % 100 == 0 or i + 1 == total:
                job.log(f"  {i + 1}/{total}")
        job.result = {"copied": copied, "moved": moved, "errors": errors, "total": total}
        job.state = "done"
        job.log(f"Готово ✓ {'переміщено' if move else 'скопійовано'} {copied + moved}, помилок {errors}")
    except Cancelled:
        job.state = "ready"
        job.log("Сортування скасовано.")
    except Exception as exc:
        job.state, job.error = "error", str(exc)
        job.log(f"Помилка: {exc}")


# ------------------------------------------------------------ aggregates
def _build_geo_aggregates(job: Job):
    groups: dict[str, dict] = {}
    for r in job.records:
        if r.lat is None or r.lon is None:
            continue
        key = f"{r.lat:.3f},{r.lon:.3f}"
        g = groups.setdefault(key, {"lat": round(r.lat, 5), "lon": round(r.lon, 5),
                                    "count": 0, "name": r.place or ""})
        g["count"] += 1
        if r.place and not g["name"]:
            g["name"] = r.place
    job.map_points = sorted(groups.values(), key=lambda g: -g["count"])[:300]
    places: dict[str, int] = {}
    for r in job.records:
        if r.place:
            places[r.place] = places.get(r.place, 0) + 1
    job.stats["places"] = len(places)
    job.top_places = sorted(places.items(), key=lambda kv: -kv[1])[:14]


def _build_month_aggregates(job: Job):
    months: dict[str, int] = {}
    years: set[str] = set()
    for r in job.records:
        if r.date:
            months.setdefault(f"{r.date.year:04d}-{r.date.month:02d}", 0)
            months[f"{r.date.year:04d}-{r.date.month:02d}"] += 1
            years.add(f"{r.date.year:04d}")
    job.months = [{"m": m, "n": months[m]} for m in sorted(months)]
    job.years = sorted(years)


def _pick_thumbs(job: Job):
    n = min(24, len(job.records))
    if not n:
        job.thumb_idx = []
        return
    step = max(1, len(job.records) // n)
    job.thumb_idx = [i for i in range(0, len(job.records), step)][:24]


def _build_tree(job: Job) -> dict:
    root = {"name": str(job.dst or ""), "dirs": {}, "files": 0}
    for r in job.records:
        node = root
        for part in r.rel_target.parts:
            node["files"] += 1
            node = node["dirs"].setdefault(part, {"name": part, "dirs": {}, "files": 0})
        node["files"] += 1

    def to_list(node, depth=0):
        out = {"name": node["name"], "files": node["files"], "depth": depth, "children": []}
        if depth < 4:
            kids = sorted(node["dirs"].items(), key=lambda kv: kv[0])
            for name, kid in kids[:40]:
                out["children"].append(to_list(kid, depth + 1))
            if len(kids) > 40:
                out["children"].append({"name": f"… +{len(kids) - 40}", "files": 0, "children": []})
        return out
    return to_list(root)


def _thumb_bytes(rec: organizer.PhotoRecord) -> bytes | None:
    from PIL import Image, ImageOps

    try:
        with Image.open(rec.path) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=72)
            return buf.getvalue()
    except Exception:
        return None


# --------------------------------------------------------------- browse
def browse_dir(path_str: str) -> dict:
    if path_str:
        p = Path(os.path.expanduser(path_str))
    elif os.name == "nt":
        drives = [f"{c}:\\" for c in "CDEFGHIJKLMNOPQRSTUVWXYZ"
                  if os.path.exists(f"{c}:\\")]
        return {"path": "", "parent": None,
                "dirs": [{"name": d, "path": d} for d in drives]}
    else:
        p = Path.home()
    try:
        p = p.resolve()
        if p.is_file():
            p = p.parent
        dirs = []
        for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
            try:
                if entry.is_dir() and not entry.name.startswith("."):
                    dirs.append({"name": entry.name, "path": str(entry)})
            except OSError:
                continue
        parent = str(p.parent) if p.parent != p else (None if os.name != "nt" else "")
        return {"path": str(p), "parent": parent, "dirs": dirs}
    except OSError as exc:
        return {"path": str(p), "parent": None, "dirs": [], "error": str(exc)}


# ---------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}

    # ---- routes
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path in ("/", "/index.html"):
            return self._static("index.html")
        if u.path in ("/app.css", "/app.js"):
            return self._static(u.path.lstrip("/"))
        if u.path.startswith("/vendor/"):
            return self._static(u.path.lstrip("/"))
        if u.path == "/api/state":
            return self._json(snapshot())
        if u.path == "/api/browse":
            return self._json(browse_dir(q.get("path", "")))
        if u.path == "/api/thumb":
            try:
                i = int(q.get("i", "-1"))
                rec = JOB.records[i]
            except (ValueError, IndexError):
                return self._send(404, b"", "image/jpeg")
            data = JOB.thumb_cache.get(i) or _thumb_bytes(rec)
            if not data:
                return self._send(404, b"", "image/jpeg")
            if len(JOB.thumb_cache) > 400:
                JOB.thumb_cache.clear()
            JOB.thumb_cache[i] = data
            return self._send(200, data, "image/jpeg")
        self._send(404, b"not found", "text/plain")

    def _static(self, rel: str):
        f = (WEB_DIR / rel.lstrip("/")).resolve()
        if not str(f).startswith(str(WEB_DIR.resolve())) or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = ("text/html; charset=utf-8" if f.suffix == ".html" else
                 "text/css; charset=utf-8" if f.suffix == ".css" else
                 "application/javascript; charset=utf-8" if f.suffix == ".js" else
                 "application/octet-stream")
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        body = self._body()
        if u.path == "/api/scan":
            if JOB.busy():
                return self._json({"ok": False, "err": "job busy"})
            src = Path(os.path.expanduser(body.get("src", "")))
            if not src.is_dir():
                return self._json({"ok": False, "err": "invalid src"})
            JOB.reset("scanning")
            JOB.src, JOB.network = src, bool(body.get("network", True))
            JOB.thread = threading.Thread(target=_scan_job, args=(JOB, src,
                                          body.get("lang", "uk")), daemon=True)
            JOB.thread.start()
            return self._json({"ok": True})
        if u.path == "/api/plan":
            if JOB.state not in ("ready", "planned", "error") or JOB.busy():
                return self._json({"ok": False, "err": "busy"})
            JOB.state = "planning"
            JOB.cancel = False
            JOB.thread = threading.Thread(
                target=_plan_job, args=(JOB, body.get("mode", JOB.mode)), daemon=True)
            JOB.thread.start()
            return self._json({"ok": True})
        if u.path == "/api/run":
            if JOB.state not in ("ready", "planned") or JOB.busy():
                return self._json({"ok": False, "err": "busy"})
            if not JOB.records:
                return self._json({"ok": False, "err": "no records"})
            dst = Path(os.path.expanduser(body.get("dst", "")))
            if not str(dst):
                return self._json({"ok": False, "err": "no dst"})
            if JOB.src and dst.resolve() == JOB.src.resolve():
                return self._json({"ok": False, "err": "dst == src"})
            JOB.state = "running"
            JOB.cancel = False
            JOB.move = bool(body.get("move", False))
            JOB.thread = threading.Thread(target=_run_job, args=(JOB, dst, JOB.move),
                                          daemon=True)
            JOB.thread.start()
            return self._json({"ok": True})
        if u.path == "/api/cancel":
            JOB.cancel = True
            return self._json({"ok": True})
        if u.path == "/api/reset":
            if not JOB.busy():
                JOB.reset("empty")
            return self._json({"ok": True})
        self._send(404, b"not found", "text/plain")


def snapshot() -> dict:
    with JOB.lock:
        return {
            "state": JOB.state,
            "version": __version__,
            "busy": JOB.busy(),
            "src": str(JOB.src) if JOB.src else None,
            "dst": str(JOB.dst) if JOB.dst else None,
            "mode": JOB.mode,
            "move": JOB.move,
            "network": JOB.network,
            "prog": JOB.prog,
            "log": list(JOB.logq)[-250:],
            "stats": JOB.stats,
            "years": JOB.years,
            "months": JOB.months,
            "map": JOB.map_points,
            "places": getattr(JOB, "top_places", []),
            "tree": JOB.tree,
            "result": JOB.result,
            "error": JOB.error,
            "thumbs": getattr(JOB, "thumb_idx", []),
            "home": str(Path.home()),
            "win": os.name == "nt",
        }


def find_free_port(start: int, tries: int = 25) -> int:
    for p in range(start, start + tries):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise OSError("Не знайдено вільного порту")


def run_web(open_browser: bool = True, port: int | None = None) -> None:
    port = port or find_free_port(8720)
    url = f"http://127.0.0.1:{port}"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"PhotoSort:  {url}")
    print("Закрий це вікно або натисни Ctrl+C, щоб завершити.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
