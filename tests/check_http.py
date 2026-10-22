"""Read-only integration checks against a running server (stdlib only)."""

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--base", default="http://127.0.0.1:8000")
parser.add_argument("--database", choices=["up", "down"], default="up")
args = parser.parse_args()


def get(path):
    start = time.perf_counter()
    try:
        response = urllib.request.urlopen(args.base + path, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.read().decode("utf-8"), time.perf_counter() - start


for path in ["/", "/static/app.js", "/static/styles.css"]:
    status, text, duration = get(path)
    assert status == 200 and text.strip(), (path, status)
    print(f"PASS {path} HTTP {status}")

# Exercise liveness while the real failed database operation is still waiting.
with concurrent.futures.ThreadPoolExecutor() as pool:
    pending_db = pool.submit(get, "/api/health/database")
    time.sleep(0.15)
    status, text, live_seconds = get("/api/health/live")
    assert status == 200 and json.loads(text)["status"] == "ok"
    assert live_seconds < 2, f"Liveness blocked for {live_seconds:.3f}s"
    print(f"PASS liveness HTTP 200 in {live_seconds:.3f}s")
    status, text, db_seconds = pending_db.result()

payload = json.loads(text)
assert "mongodb://" not in text and "Traceback" not in text and "27019" not in text
if args.database == "up":
    assert status == 200 and payload["status"] == "ok", (status, payload)
else:
    assert status == 503 and payload["code"] == "database_unavailable", (status, payload)
    assert db_seconds < 8, f"Database check exceeded bounded test budget: {db_seconds:.3f}s"
    assert payload["timeout_ms"] == 5000
assert get("/api/health/live")[0] == 200
print(f"PASS database={args.database} HTTP {status} in {db_seconds:.3f}s; sanitized response")
