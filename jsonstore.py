import json
import os
import tempfile
from pathlib import Path


def load(path, default):
    """Load JSON from path, returning default if missing or corrupt.

    A corrupt file is moved aside (``*.corrupt``) so the pipeline can recover
    instead of crashing on a partially written cache.
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        try:
            path.replace(path.with_name(path.name + ".corrupt"))
        except OSError:
            pass
        return default


def save(path, data):
    """Atomically write JSON to path (temp file + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
