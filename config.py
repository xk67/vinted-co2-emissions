import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_config():
    """Load config.json, overlay optional config.local.json and env overrides."""
    config = json.loads((ROOT / "config.json").read_text())

    local_path = ROOT / "config.local.json"
    if local_path.exists():
        config.update(json.loads(local_path.read_text()))

    env_cookie = os.environ.get("VINTED_COOKIE")
    if env_cookie:
        config["cookie"] = env_cookie

    cookie = config.get("cookie", "")
    if not cookie or "PASTE" in cookie:
        raise SystemExit(
            "Missing Vinted cookie. Set VINTED_COOKIE or create config.local.json "
            "(copy config.local.example.json)."
        )

    config["cache_dir"] = ROOT / config["cache_dir"]
    config["data_dir"] = ROOT / config["data_dir"]
    config["cities_dataset"] = ROOT / config["cities_dataset"]
    config["cache_dir"].mkdir(parents=True, exist_ok=True)
    config["data_dir"].mkdir(parents=True, exist_ok=True)
    return config
