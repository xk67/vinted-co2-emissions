import io
import zipfile
from pathlib import Path
from unicodedata import combining, normalize

import requests

import jsonstore

# Populated-place feature codes kept as "cities" (sections/abandoned excluded).
KEEP_CODES = {
    "PPL",
    "PPLA",
    "PPLA2",
    "PPLA3",
    "PPLA4",
    "PPLA5",
    "PPLC",
    "PPLF",
    "PPLG",
    "PPLH",
    "PPLL",
    "PPLR",
    "PPLS",
    "PPLW",
    "PPLCH",
}


def _fold(text):
    return "".join(
        char for char in normalize("NFKD", text) if not combining(char)
    ).lower()


def build_dataset(dest, germany_url, admin1_url, on_progress=None):
    """Download GeoNames data for Germany and write the cities dataset."""
    dest = Path(dest)
    if on_progress:
        on_progress("Downloading German place data (GeoNames)…")

    response = requests.get(germany_url, timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        raw = archive.read("DE.txt").decode("utf-8")

    states = {}
    admin_response = requests.get(admin1_url, timeout=60)
    if admin_response.ok:
        for line in admin_response.text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0] != "DE":
                states[parts[0]] = parts[1]

    entries = []
    for line in raw.splitlines():
        fields = line.split("\t")
        if len(fields) < 15 or fields[6] != "P" or fields[7] not in KEEP_CODES:
            continue
        code = fields[10]
        entries.append(
            {
                "id": int(fields[0]),
                "name": fields[1],
                "asciiname": fields[2],
                "lat": float(fields[4]),
                "lon": float(fields[5]),
                "population": int(fields[14] or 0),
                "state": states.get(f"DE.{code}", ""),
            }
        )

    entries.sort(key=lambda entry: entry["population"], reverse=True)

    if on_progress:
        on_progress(f"Writing {len(entries)} cities to {dest}")
    jsonstore.save(dest, entries)
    return entries


class Cities:
    def __init__(self, entries):
        self.entries = entries
        self._index = {entry["id"]: entry for entry in entries}
        self._keys = [_fold(entry["name"]) for entry in entries]

    @classmethod
    def load(cls, path, germany_url, admin1_url, on_progress=None):
        path = Path(path)
        entries = jsonstore.load(path, None)
        if entries is None:
            entries = build_dataset(path, germany_url, admin1_url, on_progress)
        return cls(entries)

    def search(self, query, limit=20):
        needle = _fold(query.strip())
        if not needle:
            return []
        matches = [
            entry
            for entry, key in zip(self.entries, self._keys)
            if key.startswith(needle)
        ]
        return matches[:limit]

    def get(self, city_id):
        return self._index.get(city_id)

    def __len__(self):
        return len(self.entries)


if __name__ == "__main__":
    import argparse

    from config import load_config

    parser = argparse.ArgumentParser(description="Build the German cities dataset.")
    parser.parse_args()
    config = load_config()
    cities = Cities.load(
        config["cities_dataset"],
        config["geonames_germany_url"],
        config["geonames_admin1_url"],
        on_progress=print,
    )
    print(f"Dataset ready with {len(cities)} cities.")
