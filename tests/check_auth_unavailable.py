"""Read-only requests against a temporary app configured with unavailable MongoDB."""

import json
import time
import urllib.error
import urllib.request

base = "http://127.0.0.1:8001"
for path, payload in [("/api/auth/csrf", None), ("/api/auth/me", None),
                      ("/api/auth/login", {"username": "qa_unavailable", "password": "QaOnlyUnavailable2026!"})]:
    request = urllib.request.Request(base + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Origin": base, "Content-Type": "application/json", "X-CSRF-Token": "invalid"})
    start = time.perf_counter()
    try:
        response = urllib.request.urlopen(request, timeout=12)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read().decode()
        body = json.loads(raw)
        assert response.status == 503 and body["code"] == "database_unavailable", body
        assert all(secret not in raw for secret in ["mongodb://", "27019", "QaOnly", "Traceback"])
    elapsed = time.perf_counter() - start
    assert elapsed < 8, elapsed
    print(f"PASS {path}: sanitized HTTP 503 in {elapsed:.3f}s")
assert urllib.request.urlopen(base + "/api/health/live", timeout=3).status == 200
assert urllib.request.urlopen(base + "/", timeout=3).status == 200
print("PASS backend and page remain available")
