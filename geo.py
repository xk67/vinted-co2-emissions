import json
import re
import time
from pathlib import Path

import http_client

_COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class Geocoder:
    """Keyless geocoder backed by Nominatim (OpenStreetMap), with a disk cache."""

    def __init__(self, config):
        self.base_url = config["nominatim_base_url"].rstrip("/")
        self.headers = {"User-Agent": config["nominatim_user_agent"]}
        self.min_interval = config.get("geocode_min_interval_seconds", 1.1)
        self._last_call = 0.0
        self.cache_path = Path(config["cache_dir"]) / "geocode.json"
        self.cache = (
            json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        )

    def _throttle(self):
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def geocode(self, query):
        """Resolve a free-text query to {'lat','lon','display_name'} or None (cached).

        A 'lat,lon' string is accepted directly without a network request.
        """
        key = " ".join(query.lower().split())
        if key in self.cache:
            return self.cache[key]

        match = _COORDINATES.match(query)
        if match:
            result = {
                "lat": float(match.group(1)),
                "lon": float(match.group(2)),
                "display_name": query.strip(),
                "query": query,
            }
            self.cache[key] = result
            self._save()
            return result

        self._throttle()
        status, results = http_client.get_json(
            self.base_url + "/search",
            params={"q": query, "format": "json", "limit": 1},
            headers=self.headers,
            timeout=30,
        )
        self._last_call = time.monotonic()
        if status >= 400:
            raise RuntimeError(f"Nominatim geocoding failed ({status}) for {query!r}")

        if results:
            top = results[0]
            result = {
                "lat": float(top["lat"]),
                "lon": float(top["lon"]),
                "display_name": top.get("display_name"),
                "query": query,
            }
        else:
            result = None

        self.cache[key] = result
        self._save()
        return result

    def _save(self):
        self.cache_path.write_text(
            json.dumps(self.cache, indent=2, ensure_ascii=False)
        )
