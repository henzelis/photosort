"""Reverse geocoding via Nominatim (OpenStreetMap) with local cache + 1 req/s rate limit."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "photosort/1.0 (+https://github.com/henzelis/photosort)"
_CACHE_TTL_S = 60 * 60 * 24 * 365  # place names rarely change; cache a year

# Preferred address fields, from specific to general
_ADDR_KEYS = ("city", "town", "village", "municipality", "county", "island", "state", "country")


def app_config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(__import__("os").environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(__import__("os").environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    d = base / "photosort"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _name_from_address(addr: dict) -> str | None:
    for key in _ADDR_KEYS:
        val = addr.get(key)
        if val:
            return str(val).strip()
    # last resort: first line of display_name
    dn = addr.get("display_name") or ""
    return dn.split(",")[0].strip() or None


class Geocoder:
    def __init__(self, lang: str = "uk", zoom: int = 12, cache_path: Path | None = None,
                 log=print, timeout: float = 15.0):
        self.lang = lang or "en"
        self.zoom = zoom
        self.log = log
        self.timeout = timeout
        self.cache_path = cache_path or (app_config_dir() / "geo_cache.json")
        self.cache: dict[str, dict] = {}
        self.new_hits = 0
        self.cached_hits = 0
        self.failures = 0
        self._last_request = 0.0
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.cache = data
        except Exception:
            pass

    def save_cache(self) -> None:
        try:
            self.cache_path.write_text(
                json.dumps(self.cache, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            self.log(f"  ! Не вдалось зберегти кеш геокодингу: {exc}")

    @staticmethod
    def _key(lat: float, lon: float) -> str:
        return f"{lat:.4f},{lon:.4f}"

    def reverse(self, lat: float, lon: float) -> str | None:
        """Return place name for coordinates, or None if unavailable."""
        key = self._key(lat, lon)
        entry = self.cache.get(key)
        if entry and entry.get("name"):
            self.cached_hits += 1
            return entry["name"]

        # Nominatim usage policy: max 1 request/second
        wait = 1.1 - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        params = urllib.parse.urlencode({
            "format": "jsonv2",
            "lat": f"{lat:.6f}",
            "lon": f"{lon:.6f}",
            "zoom": self.zoom,
            "accept-language": self.lang,
        })
        req = urllib.request.Request(
            f"{NOMINATIM_URL}?{params}",
            headers={"User-Agent": USER_AGENT, "Accept-Language": self.lang},
        )
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.failures += 1
            self.log(f"  ! Геокодинг недоступний ({exc}) — використаю «Невідоме місце»")
            return None

        name = _name_from_address(data) if isinstance(data, dict) else None
        if name:
            self.cache[key] = {"name": name, "ts": int(time.time())}
            self.new_hits += 1
        return name
