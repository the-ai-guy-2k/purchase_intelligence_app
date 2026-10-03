"""Local web application for receipt intake and evidence preservation."""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, Settings, load_settings, size_limit_message
from app.receipt_extraction.errors import EvidenceNotFound
from app.receipt_extraction.repository import init_extraction_db
from app.receipt_extraction.service import extract_preserved_receipt, read_extraction
from app.receipt_intake.errors import IntakeRejected
from app.receipt_intake.models import parse_evidence_id
from app.receipt_intake.repository import get_evidence, init_db
from app.receipt_intake.service import preserve_upload
from app.receipt_intake.validation import declared_body_too_large, read_limited_upload

logger = logging.getLogger("purchase_intelligence.receipt_intake")
extraction_logger = logging.getLogger("purchase_intelligence.receipt_extraction")

_GENERIC_FAILURE = "The upload could not be processed."


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    init_extraction_db(settings)

    app = FastAPI(
        title="Purchase Intelligence",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def reject_malformed_request(request: Request, exc: RequestValidationError):
        return _rejected(
            "The upload could not be processed. Choose a receipt image and try again."
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return template.replace("__MAX_MB__", str(settings.max_upload_megabytes))

    @app.post("/api/receipts")
    async def intake_receipt(
        request: Request,
        file: UploadFile | None = File(default=None),
    ) -> JSONResponse:
        if declared_body_too_large(request.headers.get("content-length"), settings.max_upload_bytes):
            logger.info("receipt rejected reason=declared_size")
            return _rejected(size_limit_message(settings.max_upload_bytes))
        if file is None:
            logger.info("receipt rejected reason=missing_file")
            return _rejected("No file was provided.")
        try:
            content = await read_limited_upload(file, settings.max_upload_bytes)
            record = preserve_upload(content, file.filename, settings)
        except IntakeRejected as exc:
            logger.info("receipt rejected reason=%s", exc.reason)
            return _rejected(exc.reason)
        except Exception:
            logger.exception("receipt intake failed")
            return _rejected(_GENERIC_FAILURE, status_code=500)

        logger.info(
            "receipt accepted evidence_id=%s mime_type=%s byte_size=%s",
            record.evidence_id,
            record.mime_type,
            record.byte_size,
        )
        return JSONResponse(status_code=201, content=record.to_public_dict())

    @app.post("/api/receipts/{evidence_id}/extraction")
    async def extract_receipt(evidence_id: str) -> JSONResponse:
        try:
            record = await extract_preserved_receipt(settings, evidence_id)
        except EvidenceNotFound:
            extraction_logger.info("extraction rejected reason=evidence_not_found")
            return _not_found()
        except Exception:
            extraction_logger.exception("extraction failed")
            return JSONResponse(
                status_code=500,
                content={"status": "failed", "reason": "The receipt could not be read."},
            )
        extraction_logger.info(
            "extraction finished evidence_id=%s status=%s line_count=%s",
            record.evidence_id,
            record.extraction_status,
            len(record.lines),
        )
        status_code = 422 if record.extraction_status == "failed" else 200
        return JSONResponse(status_code=status_code, content=record.to_public_dict())

    @app.get("/api/receipts/{evidence_id}/extraction")
    def read_saved_extraction(evidence_id: str) -> JSONResponse:
        try:
            record = read_extraction(settings, evidence_id)
        except EvidenceNotFound:
            return _not_found()
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "reason": "No extraction exists for this receipt."},
            )
        return JSONResponse(status_code=200, content=record.to_public_dict())

    @app.get("/api/receipts/{evidence_id}")
    def read_receipt(evidence_id: str) -> JSONResponse:
        canonical = parse_evidence_id(evidence_id)
        if canonical is None:
            return _not_found()
        record = get_evidence(settings, canonical)
        if record is None:
            return _not_found()
        return JSONResponse(status_code=200, content=record.to_public_dict())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _rejected(reason: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "rejected", "reason": reason})


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"status": "not_found", "reason": "Receipt evidence was not found."},
    )


app = create_app()
