"""HTTP API for sharing lecture study results."""

import ipaddress
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.app.schema import LectureValidationError, validate_lecture
from server.app.storage import LimitExceeded, PostgresLectureStore


MAX_BODY_BYTES = 4 * 1024 * 1024
logger = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))


def _clock(milliseconds: int) -> str:
    total = milliseconds // 1000
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


templates.env.filters["clock"] = _clock


def _client_ip(request: Request) -> str:
    if os.getenv("TRUST_RAILWAY_PROXY") == "1":
        candidate = request.headers.get("x-real-ip", "")
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def create_app(store=None) -> FastAPI:
    application = FastAPI(title="YouTube Lecture", docs_url=None, redoc_url=None)
    application.state.store = store
    application.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    def current_store():
        if application.state.store is None:
            application.state.store = PostgresLectureStore(
                os.getenv("DATABASE_URL", ""),
                os.getenv("RATE_LIMIT_SALT", ""),
                int(os.getenv("PER_IP_DAILY_LIMIT", "5")),
                int(os.getenv("GLOBAL_DAILY_LIMIT", "100")),
            )
        return application.state.store

    @application.get("/health")
    def health() -> dict:
        try:
            current_store().check_ready()
        except Exception as error:
            logger.exception("Lecture storage health check failed")
            raise HTTPException(503, "저장소에 연결할 수 없습니다") from error
        return {"status": "ok"}

    @application.post("/api/lectures")
    async def create_lecture(request: Request):
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(415, "JSON 본문이 필요합니다")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                raise HTTPException(413, "JSON이 4 MiB 한도를 넘었습니다")
        try:
            payload = json.loads(body)
            validate_lecture(payload)
        except (json.JSONDecodeError, LectureValidationError, TypeError) as error:
            raise HTTPException(422, f"강의 JSON이 올바르지 않습니다: {error}") from error
        try:
            share_id = current_store().create(payload, _client_ip(request))
        except LimitExceeded as error:
            raise HTTPException(429, str(error), headers={"Retry-After": str(error.retry_after_seconds)}) from error
        except Exception as error:
            logger.exception("Lecture save failed")
            raise HTTPException(503, "강의 결과를 저장하지 못했습니다") from error
        base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
        return JSONResponse(
            {"share_id": share_id, "share_url": f"{base}/lectures/{share_id}"},
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/api/lectures/{share_id}")
    def get_lecture(share_id: str):
        try:
            lecture = current_store().get(share_id)
        except Exception as error:
            logger.exception("Lecture read failed")
            raise HTTPException(503, "강의 결과를 읽지 못했습니다") from error
        if lecture is None:
            raise HTTPException(404, "공유 결과를 찾지 못했습니다")
        return lecture

    @application.get("/lectures/{share_id}")
    def lecture_page(share_id: str, request: Request):
        try:
            lecture = current_store().get(share_id)
        except Exception as error:
            logger.exception("Lecture page read failed")
            raise HTTPException(503, "강의 결과를 읽지 못했습니다") from error
        if lecture is None:
            return templates.TemplateResponse(
                request, "not_found.html", {"share_id": share_id}, status_code=404,
                headers={"X-Robots-Tag": "noindex, nofollow"},
            )
        return templates.TemplateResponse(
            request, "lecture.html", {"lecture": lecture, "share_id": share_id},
            headers={"X-Robots-Tag": "noindex, nofollow"},
        )

    return application


app = create_app()
