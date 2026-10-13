import re
import time
from pathlib import Path

import http_client
import jsonstore

_COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_RETRY_STATUSES = {403, 429, 500, 502, 503}


class Geocoder:
    """Keyless geocoder backed by Nominatim (OpenStreetMap), with a disk cache."""

    def __init__(self, config):
        self.base_url = config["nominatim_base_url"].rstrip("/")
        self.headers = {"User-Agent": config["nominatim_user_agent"]}
        self.min_interval = config.get("geocode_min_interval_seconds", 1.1)
        self._last_call = 0.0
        self.cache_path = Path(config["cache_dir"]) / "geocode.json"
        self.cache = jsonstore.load(self.cache_path, {})

    def _throttle(self):
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request(self, query):
        """Call the search endpoint with backoff; raise HttpError on failure."""
        attempts = 4
        for attempt in range(attempts):
            self._throttle()
            try:
                status, results = http_client.get_json(
                    self.base_url + "/search",
                    params={"q": query, "format": "json", "limit": 1},
                    headers=self.headers,
                    timeout=30,
                )
            except http_client.HttpError:
                if attempt == attempts - 1:
                    raise
                time.sleep(2**attempt)
                continue

            self._last_call = time.monotonic()
            if status in _RETRY_STATUSES:
                if attempt == attempts - 1:
                    raise http_client.HttpError(
                        f"Nominatim returned HTTP {status} for {query!r}"
                    )
                time.sleep(2**attempt)
                continue
            if status >= 400:
                raise http_client.HttpError(
                    f"Nominatim returned HTTP {status} for {query!r}"
                )
            return results
        return []

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

        results = self._request(query)
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
        jsonstore.save(self.cache_path, self.cache)
