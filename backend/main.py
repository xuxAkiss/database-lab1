"""Authentication, existing read-only health checks, and same-origin static pages."""

import logging
from contextlib import asynccontextmanager
from time import perf_counter

import pymongo
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from backend.config import ROOT, read_settings
from backend.statistics import router as statistics_router
from backend.filling import router as filling_router
from backend.surveys import SurveyStore, router as survey_router
from backend.auth import AuthStore, read_auth_settings, router as auth_router

logger = logging.getLogger("work1.health")
HEADERS = {"Cache-Control": "no-store"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = None
    app.state.database = None
    app.state.timeout_ms = 5000
    app.state.auth_store = None
    app.state.survey_store = None
    try:
        settings = read_settings()
        app.state.timeout_ms = settings.db_check_timeout_ms
        app.state.client = MongoClient(
            settings.mongodb_uri,
            connect=False,
            serverSelectionTimeoutMS=settings.db_check_timeout_ms,
            connectTimeoutMS=min(2000, settings.db_check_timeout_ms),
            socketTimeoutMS=settings.db_check_timeout_ms,
            waitQueueTimeoutMS=settings.db_check_timeout_ms,
            timeoutMS=settings.db_check_timeout_ms,
            tz_aware=True,
        )
        # Selecting a database does not create it. No collections are accessed.
        app.state.database = app.state.client[settings.mongodb_db]
        app.state.auth_store = AuthStore(app.state.database, settings.db_check_timeout_ms)
        app.state.survey_store = SurveyStore(app.state.database)
    except (ValueError, PyMongoError):
        # Never include raw configuration/driver errors: they can contain credentials.
        logger.warning("Database configuration is unavailable or invalid.")
    app.state.auth_settings = read_auth_settings()
    try:
        yield
    finally:
        if app.state.client is not None:
            app.state.client.close()


app = FastAPI(title="问卷系统 · 账号与会话", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(survey_router)
app.include_router(filling_router)
app.include_router(statistics_router)


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def auth_error(request, error):
    detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
    return JSONResponse({"status": "error", **detail}, status_code=error.status_code, headers=HEADERS)


@app.exception_handler(RequestValidationError)
async def invalid_input(request, error):
    if request.url.path.startswith(('/api/surveys', '/api/shared', '/api/fill')):
        errors = [{'field': '.'.join(str(v) for v in e['loc']), 'message': e['msg']}
                  for e in error.errors()]
        return JSONResponse({'status': 'error', 'code': 'invalid_input',
                             'message': '；'.join(e['field'] + ': ' + e['message'] for e in errors),
                             'errors': errors}, status_code=422, headers=HEADERS)
    # FastAPI's default validation response may echo the submitted password. Do not use it.
    return JSONResponse({"status": "error", "code": "invalid_input",
                         "message": "输入不合法：用户名需为 3–32 位字母、数字或下划线，密码需为 12–128 个字符；不接受额外字段。"},
                        status_code=422, headers=HEADERS)


@app.exception_handler(PyMongoError)
async def database_error(request, error):
    return JSONResponse({"status": "error", "code": "database_unavailable",
                         "message": "数据库暂不可用，请稍后重试；本次操作未确认成功。"},
                        status_code=503, headers=HEADERS)


@app.get("/api/health/live")
def liveness():
    return JSONResponse({"status": "ok", "message": "后端运行正常"}, headers=HEADERS)


@app.get("/api/health/database")
def database_health(request: Request):
    state = request.app.state
    if state.database is None:
        return JSONResponse(
            {"status": "error", "code": "database_configuration_error",
             "message": "数据库配置缺失或无效；后端仍可使用。"},
            status_code=503, headers=HEADERS,
        )
    started = perf_counter()
    try:
        # Sync route runs in FastAPI's worker thread pool; DB failure does not block liveness.
        # CSOT bounds the entire operation, in addition to the driver's phase timeouts.
        with pymongo.timeout(state.timeout_ms / 1000):
            result = state.database.command("ping")
        if result.get("ok") != 1:
            raise PyMongoError("Ping did not succeed.")
    except (PyMongoError, TimeoutError):
        return JSONResponse(
            {"status": "error", "code": "database_unavailable",
             "message": "数据库暂不可达或检查超时，请检查本地实例后重试。",
             "elapsed_ms": round((perf_counter() - started) * 1000),
             "timeout_ms": state.timeout_ms},
            status_code=503, headers=HEADERS,
        )
    return JSONResponse(
        {"status": "ok", "message": "MongoDB ping 成功",
         "elapsed_ms": round((perf_counter() - started) * 1000)},
        headers=HEADERS,
    )


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "frontend" / "auth.html", headers=HEADERS)


@app.get("/health", include_in_schema=False)
def health_page():
    return FileResponse(ROOT / "frontend" / "index.html", headers=HEADERS)


@app.get('/manage', include_in_schema=False)
def manage_page():
    return FileResponse(ROOT / 'frontend' / 'surveys.html', headers=HEADERS)


@app.get('/s/{token}', include_in_schema=False)
def shared_page(token: str):
    return FileResponse(ROOT / 'frontend' / 'fill.html', headers=HEADERS)


@app.get("/statistics/{sid}", include_in_schema=False)
def statistics_page(sid: str):
    return FileResponse(ROOT / "frontend" / "statistics.html", headers=HEADERS)


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
