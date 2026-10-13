import time
from pathlib import Path

import http_client
import jsonstore


class Router:
    """Keyless road-routing via the public OSRM demo server, with a disk cache."""

    def __init__(self, config):
        self.base_url = config["osrm_base_url"].rstrip("/")
        self.profile = config.get("osrm_profile", "driving")
        self.min_interval = config.get("route_min_interval_seconds", 0.3)
        self._last_call = 0.0
        self.cache_path = Path(config["cache_dir"]) / "routes.json"
        self.cache = jsonstore.load(self.cache_path, {})

    @staticmethod
    def _key(origin, destination):
        return (
            f"{origin['lat']:.5f},{origin['lon']:.5f}"
            f"->{destination['lat']:.5f},{destination['lon']:.5f}"
        )

    def _throttle(self):
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def route(self, origin, destination):
        """Return {'distance_m','duration_s','geometry'} or None (cached).

        The route is computed with the car ('driving') profile; the emission
        factor is applied downstream.
        """
        key = self._key(origin, destination)
        if key in self.cache:
            return self.cache[key]

        coords = (
            f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
        )
        url = f"{self.base_url}/route/v1/{self.profile}/{coords}"
        self._throttle()
        status, data = http_client.get_json(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=60,
        )
        self._last_call = time.monotonic()
        if status >= 400:
            raise RuntimeError(f"OSRM routing failed ({status}) for {key}")

        if data.get("code") == "Ok" and data.get("routes"):
            best = data["routes"][0]
            result = {
                "distance_m": best["distance"],
                "duration_s": best["duration"],
                "geometry": best.get("geometry"),
            }
        else:
            result = None

        self.cache[key] = result
        self._save()
        return result

    def _save(self):
        jsonstore.save(self.cache_path, self.cache)
