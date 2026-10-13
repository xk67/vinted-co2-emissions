import threading
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from cities import Cities
from config import load_config
from pipeline import run_pipeline
from vinted_client import AuthError

app = Flask(__name__)
CONFIG = load_config()

print("Loading German cities dataset…")
CITIES = Cities.load(
    CONFIG["cities_dataset"],
    CONFIG["geonames_germany_url"],
    CONFIG["geonames_admin1_url"],
    on_progress=print,
)
print(f"Loaded {len(CITIES)} cities.")

_job_lock = threading.Lock()  # one calculation at a time
_state_lock = threading.Lock()  # protects JOBS
JOBS = {}


def _update(job_id, **fields):
    with _state_lock:
        JOBS[job_id].update(fields)


def _progress_callback(job_id):
    def callback(message, current=None, total=None):
        with _state_lock:
            JOBS[job_id]["progress"] = {
                "message": message,
                "current": current or 0,
                "total": total or 0,
            }

    return callback


def _worker(job_id, fixed_location, fixed_point):
    try:
        payload = run_pipeline(
            fixed_location,
            config=CONFIG,
            on_progress=_progress_callback(job_id),
            fixed_point=fixed_point,
        )
        _update(job_id, status="done", result=payload)
    except AuthError as error:
        _update(job_id, status="error", error=str(error))
    except Exception as error:  # noqa: BLE001 - surface any failure to the page
        _update(job_id, status="error", error=str(error))
    finally:
        _job_lock.release()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/cities")
def cities():
    query = (request.args.get("q") or "").strip()
    matches = CITIES.search(query, limit=20)
    return jsonify(
        {
            "cities": [
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "state": entry["state"],
                    "lat": entry["lat"],
                    "lon": entry["lon"],
                    "population": entry["population"],
                }
                for entry in matches
            ]
        }
    )


@app.post("/api/calculate")
def calculate():
    data = request.get_json(silent=True) or {}
    city_id = data.get("city_id")
    if city_id is None:
        return jsonify({"error": "Please choose a city from the list."}), 400

    try:
        city_id = int(city_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Please choose a city from the list."}), 400

    city = CITIES.get(city_id)
    if city is None:
        return jsonify({"error": "Unknown city. Please choose from the list."}), 400

    display_name = f"{city['name']}, {city['state']}" if city["state"] else city["name"]
    fixed_point = {
        "lat": city["lat"],
        "lon": city["lon"],
        "display_name": display_name,
        "query": city["name"],
    }

    if not _job_lock.acquire(blocking=False):
        return jsonify({"error": "A calculation is already running. Please wait."}), 409

    job_id = uuid.uuid4().hex
    with _state_lock:
        JOBS[job_id] = {
            "status": "running",
            "fixed_location": display_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "progress": {"message": "Starting...", "current": 0, "total": 0},
            "result": None,
            "error": None,
        }

    thread = threading.Thread(
        target=_worker, args=(job_id, display_name, fixed_point), daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id}), 202


@app.get("/api/status/<job_id>")
def status(job_id):
    with _state_lock:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "unknown job"}), 404
        job = dict(job)
        job["progress"] = dict(job["progress"])

    response = {"status": job["status"], "progress": job["progress"]}
    if job["status"] == "done":
        payload = job["result"]
        response.update(
            {
                "generated_at": payload["generated_at"],
                "fixed_location": payload["fixed_location"],
                "totals": payload["totals"],
                "equivalents": payload.get("equivalents", []),
                "orders": payload["orders"],
            }
        )
    elif job["status"] == "error":
        response["error"] = job["error"]
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True, debug=False)
