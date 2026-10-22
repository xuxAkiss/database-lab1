"""MongoDB-backed opaque sessions and reusable authentication dependencies."""

import hashlib
import os
import re
import secrets
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pymongo
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/api/auth", tags=["auth"])
hasher = PasswordHasher()  # Argon2id, library-maintained safe defaults and random salts.
dummy_hash = hasher.hash(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class AuthSettings:
    origin: str
    secure: bool
    session_seconds: int

    @property
    def cookie_name(self):
        return "__Host-work1_session" if self.secure else "work1_session"


def read_auth_settings():
    origin = os.getenv("AUTH_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    value = os.getenv("SESSION_COOKIE_SECURE", "false").lower()
    if value not in {"true", "false"}:
        raise ValueError("SESSION_COOKIE_SECURE must be true or false.")
    secure = value == "true"
    seconds = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("AUTH_ORIGIN must be an exact HTTP(S) origin.")
    if parsed.scheme == "https" and not secure:
        raise ValueError("HTTPS requires SESSION_COOKIE_SECURE=true.")
    if parsed.scheme == "http" and (secure or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("Unsecured cookies are allowed only for loopback HTTP development.")
    if not 1 <= seconds <= 604800:
        raise ValueError("SESSION_TTL_SECONDS must be between 1 and 604800.")
    return AuthSettings(origin, secure, seconds)


def utcnow():
    return datetime.now(timezone.utc)


def digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def fail(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: StrictStr = Field(min_length=1, max_length=128)
    password: StrictStr = Field(min_length=12, max_length=128, repr=False)

    @field_validator("username")
    @classmethod
    def canonical_username(cls, value):
        value = unicodedata.normalize("NFKC", value).strip().casefold()
        if not re.fullmatch(r"[a-z0-9_]{3,32}", value):
            raise ValueError("Username must contain 3-32 ASCII letters, digits or underscores.")
        return value


class AuthStore:
    def __init__(self, database, timeout_ms):
        self.db = database
        self.timeout_ms = timeout_ms
        self.ready = False
        self.lock = threading.Lock()

    def ensure_indexes(self):
        if self.ready:
            return
        with self.lock:
            if not self.ready:
                with pymongo.timeout(self.timeout_ms / 1000):
                    self.db.users.create_index("username", unique=True, name="username_unique")
                    self.db.sessions.create_index("expires_at", expireAfterSeconds=0, name="expires_ttl")
                self.ready = True


def get_auth_store(request: Request):
    store = request.app.state.auth_store
    if store is None:
        fail(503, "database_unavailable", "数据库暂不可用，请稍后重试。")
    store.ensure_indexes()
    return store


def read_session(request: Request, store: AuthStore):
    token = request.cookies.get(request.app.state.auth_settings.cookie_name, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    # TTL deletion is asynchronous; authentication always checks the actual deadline.
    return store.db.sessions.find_one({"_id": digest(token), "expires_at": {"$gt": utcnow()}})


def check_origin(request: Request):
    if request.headers.get("origin") != request.app.state.auth_settings.origin:
        fail(403, "csrf_rejected", "请求来源不受信任，请从本站页面操作。")
    if request.headers.get("sec-fetch-site") == "cross-site":
        fail(403, "csrf_rejected", "不允许跨站修改请求。")


def require_csrf(request: Request, store: AuthStore = Depends(get_auth_store)):
    check_origin(request)
    session = read_session(request, store)
    token = request.headers.get("x-csrf-token", "")
    if not session or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token) or not secrets.compare_digest(token, session["csrf_token"]):
        fail(403, "csrf_rejected", "安全令牌已失效，请刷新页面后重试。")
    return session


def user_for_session(session, store):
    if not session or session.get("user_id") is None:
        fail(401, "authentication_required", "请先登录。")
    user = store.db.users.find_one({"_id": session["user_id"]}, {"password_hash": 0})
    if user is None:
        fail(401, "authentication_required", "登录已失效，请重新登录。")
    return user


def require_user(request: Request, store: AuthStore = Depends(get_auth_store)):
    """Reuse with Depends(require_user); never accept a caller-supplied userId."""
    return user_for_session(read_session(request, store), store)


def require_mutating_user(session=Depends(require_csrf), store: AuthStore = Depends(get_auth_store)):
    """Authenticated write endpoints must depend on this to enforce both identity and CSRF."""
    return user_for_session(session, store)


def public_user(user):
    return {"id": str(user["_id"]), "username": user["username"],
            "created_at": user["created_at"].isoformat()}


def new_session(request, response, store, user_id=None):
    settings = request.app.state.auth_settings
    seconds = settings.session_seconds if user_id is not None else 1200
    token = secrets.token_urlsafe(32)
    session = {"_id": digest(token), "user_id": user_id,
               "csrf_token": secrets.token_urlsafe(32), "created_at": utcnow(),
               "expires_at": utcnow() + timedelta(seconds=seconds)}
    store.db.sessions.insert_one(session)
    response.set_cookie(settings.cookie_name, token, httponly=True, secure=settings.secure,
                        samesite="lax", path="/", max_age=seconds)
    return session


@router.get("/csrf")
def csrf(request: Request, response: Response, store: AuthStore = Depends(get_auth_store)):
    origin = request.headers.get("origin")
    if (origin and origin != request.app.state.auth_settings.origin) or request.headers.get("sec-fetch-site") == "cross-site":
        fail(403, "csrf_rejected", "不允许跨站获取安全令牌。")
    session = read_session(request, store)
    if session is None:
        session = new_session(request, response, store)
    return {"csrf_token": session["csrf_token"]}


@router.post("/register", status_code=201)
def register(body: Credentials, session=Depends(require_csrf), store: AuthStore = Depends(get_auth_store)):
    user = {"username": body.username, "password_hash": hasher.hash(body.password), "created_at": utcnow()}
    try:
        store.db.users.insert_one(user)
    except DuplicateKeyError:
        fail(409, "username_taken", "该用户名已被注册，请换一个。")
    # Registration does not log the caller in; the page directs them to login.
    return {"message": "注册成功，请登录。", "user": public_user(user)}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response,
          session=Depends(require_csrf), store: AuthStore = Depends(get_auth_store)):
    user = store.db.users.find_one({"username": body.username})
    try:
        hasher.verify(user["password_hash"] if user else dummy_hash, body.password)
    except (VerificationError, InvalidHashError):
        fail(401, "invalid_credentials", "用户名或密码错误。")
    if user is None:
        fail(401, "invalid_credentials", "用户名或密码错误。")
    if hasher.check_needs_rehash(user["password_hash"]):
        store.db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hasher.hash(body.password)}})
    # Consume the old session before issuing a new identity-bound token (fixation protection).
    consumed = store.db.sessions.find_one_and_delete({"_id": session["_id"], "expires_at": {"$gt": utcnow()}})
    if consumed is None:
        fail(403, "csrf_rejected", "会话已变化，请刷新页面后重试。")
    fresh = new_session(request, response, store, user["_id"])
    return {"user": public_user(user), "csrf_token": fresh["csrf_token"]}


@router.get("/me")
def me(user=Depends(require_user)):
    return {"user": public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response, session=Depends(require_csrf),
           user=Depends(require_mutating_user), store: AuthStore = Depends(get_auth_store)):
    store.db.sessions.delete_one({"_id": session["_id"]})
    settings = request.app.state.auth_settings
    response.delete_cookie(settings.cookie_name, path="/", httponly=True,
                           secure=settings.secure, samesite="lax")
    return {"message": "已退出登录。"}
