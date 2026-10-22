"""Real HTTP + MongoDB auth checks. Adds labeled QA accounts; never clears data."""

import hashlib
import http.cookiejar
import json
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from bson import ObjectId
from pymongo import MongoClient
from backend.config import read_settings

BASE = "http://127.0.0.1:8000"
RUN = "qa_auth_" + datetime.now().strftime("%Y%m%d") + "_" + uuid4().hex[:6]
PASSWORD = secrets.token_urlsafe(24)
settings = read_settings()
mongo = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000, tz_aware=True)
db = mongo[settings.mongodb_db]


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def call(self, path, body=None, headers=None):
        hs = {"Origin": BASE}
        if body is not None:
            hs.update({"Content-Type": "application/json", "X-CSRF-Token": self.csrf or ""})
        hs.update(headers or {})
        request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers=hs)
        try:
            response = self.opener.open(request, timeout=12)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            text = response.read().decode()
            assert PASSWORD not in text and "password_hash" not in text and "mongodb://" not in text
            return response.status, json.loads(text), response.headers

    def bootstrap(self):
        status, body, headers = self.call("/api/auth/csrf")
        assert status == 200
        self.csrf = body["csrf_token"]
        return headers

    def token(self):
        return next(c.value for c in self.jar if c.name == "work1_session")


def expect(client, path, code, body=None, headers=None):
    actual, result, response_headers = client.call(path, body, headers)
    assert actual == code, (path, actual, result)
    return result, response_headers


def raw_token_me(token):
    # Use a client with no cookie jar state other than the explicitly supplied old token.
    return Client().call("/api/auth/me", headers={"Cookie": "work1_session=" + token})[0]


users = []
try:
    a, b = Client(), Client()
    expect(a, "/api/auth/me", 401)
    print("PASS unauthenticated protected request rejected")
    cookie_headers = a.bootstrap()
    cookie = cookie_headers.get("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie and "Secure" not in cookie
    assert cookie_headers["Cache-Control"] == "no-store"
    b.bootstrap()
    credentials_a = {"username": RUN + "_a", "password": PASSWORD}
    credentials_b = {"username": RUN + "_b", "password": PASSWORD}
    expect(a, "/api/auth/register", 403, credentials_a, {"X-CSRF-Token": ""})
    expect(a, "/api/auth/register", 403, credentials_a, {"Origin": "https://foreign.invalid"})
    expect(a, "/api/auth/register", 403, credentials_a, {"Origin": ""})
    print("PASS CSRF missing-token, cross-origin and missing-origin rejected")
    expect(a, "/api/auth/register", 422, {**credentials_a, "userId": "untrusted"})
    expect(a, "/api/auth/register", 422, {"username": "x", "password": PASSWORD})
    expect(a, "/api/auth/register", 422, {"username": RUN, "password": "short"})
    print("PASS server validation and no password echo")

    for client, credentials in [(a, credentials_a), (b, credentials_b)]:
        created, _ = expect(client, "/api/auth/register", 201, credentials)
        user_id = ObjectId(created["user"]["id"])
        users.append(user_id)
        db.users.update_one({"_id": user_id, "username": credentials["username"]},
                            {"$set": {"test_run_id": RUN, "test_purpose": "automated authentication verification"}})
        stored = db.users.find_one({"_id": user_id})
        assert stored["password_hash"].startswith("$argon2id$")
        assert PasswordHasher().verify(stored["password_hash"], PASSWORD)
        assert "password" not in stored and PASSWORD not in json.dumps(stored, default=str)
    expect(a, "/api/auth/register", 409, {"username": "  " + credentials_a["username"].upper() + "  ", "password": PASSWORD})
    print("PASS two registrations, normalized uniqueness and Argon2id storage")

    bad = {**credentials_a, "password": secrets.token_urlsafe(24)}
    expect(a, "/api/auth/login", 401, bad)
    expect(a, "/api/auth/login", 401, {"username": RUN + "_none", "password": PASSWORD})
    old_anonymous = a.token()
    for client, credentials in [(a, credentials_a), (b, credentials_b)]:
        logged_in, _ = expect(client, "/api/auth/login", 200, credentials)
        client.csrf = logged_in["csrf_token"]
        current, _ = expect(client, "/api/auth/me", 200)
        assert current["user"]["username"] == credentials["username"]
        assert set(current["user"]) == {"id", "username", "created_at"}
        token = client.token()
        stored_session = db.sessions.find_one({"_id": hashlib.sha256(token.encode()).hexdigest()})
        assert stored_session and stored_session["user_id"] == ObjectId(current["user"]["id"])
        assert token not in json.dumps(stored_session, default=str)
    assert a.token() != old_anonymous and raw_token_me(old_anonymous) == 401
    current, _ = expect(a, "/api/auth/me?userId=" + str(users[1]), 200)
    assert current["user"]["id"] == str(users[0])
    print("PASS correct/wrong passwords, two isolated identities, rotation and ignored userId")

    live_a = a.token()
    expect(a, "/api/auth/logout", 403, {}, {"X-CSRF-Token": "wrong"})
    expect(a, "/api/auth/me", 200)
    expect(a, "/api/auth/logout", 200, {})
    expect(a, "/api/auth/me", 401)
    assert raw_token_me(live_a) == 401
    assert db.sessions.find_one({"_id": hashlib.sha256(live_a.encode()).hexdigest()}) is None
    expect(b, "/api/auth/me", 200)
    print("PASS logout deletes only caller session; old cookie rejected, other account remains logged in")

    # Only change this run's own session, not server clock or arbitrary user's data.
    session_b = hashlib.sha256(b.token().encode()).hexdigest()
    result = db.sessions.update_one({"_id": session_b, "user_id": users[1]},
                                    {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert result.matched_count == 1
    expect(b, "/api/auth/me", 401)
    print("PASS explicitly expired QA session rejected without waiting for TTL cleanup")
    expect(a, "/api/health/live", 200)
    expect(a, "/api/health/database", 200)
    indexes = db.users.index_information()
    assert indexes["username_unique"]["unique"] is True
    assert db.sessions.index_information()["expires_ttl"]["expireAfterSeconds"] == 0
    print("PASS health regressions and user/session indexes")
    print("TEST_RUN=" + RUN)
    print("Retained labeled QA accounts: " + ", ".join([credentials_a["username"], credentials_b["username"]]))
finally:
    if users:
        db.sessions.update_many({"user_id": {"$in": users}},
                                {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    mongo.close()
