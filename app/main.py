"""Local web application for receipt intake and evidence preservation."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, Settings, load_settings, size_limit_message
from app.purchase_confirmation.confidence import assess_extraction
from app.purchase_memory.errors import MemoryNotFound, MemoryRejected, PurchaseNotFound
from app.purchase_memory.repository import init_memory_db
from app.purchase_memory.service import (
    correct_classification,
    read_memory,
    read_memory_list,
    remember_from_request,
    remember_purchase,
)
from app.purchase_confirmation.errors import AlreadyConfirmed, ConfirmationRejected, ExtractionNotFound
from app.purchase_confirmation.repository import get_purchase_for_extraction, init_confirmed_db
from app.purchase_confirmation.service import confirm_purchase, read_purchase
from app.receipt_extraction.errors import EvidenceNotFound
from app.receipt_extraction.models import ExtractionRecord
from app.receipt_extraction.repository import init_extraction_db
from app.receipt_extraction.service import extract_preserved_receipt, read_extraction
from app.receipt_intake.errors import IntakeRejected
from app.receipt_intake.models import parse_evidence_id
from app.receipt_intake.repository import get_evidence, init_db
from app.receipt_intake.service import preserve_upload
from app.receipt_intake.validation import declared_body_too_large, read_limited_upload

logger = logging.getLogger("purchase_intelligence.receipt_intake")
extraction_logger = logging.getLogger("purchase_intelligence.receipt_extraction")
confirmation_logger = logging.getLogger("purchase_intelligence.confirmation")
memory_logger = logging.getLogger("purchase_intelligence.memory")

_GENERIC_FAILURE = "The upload could not be processed."


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    init_extraction_db(settings)
    init_confirmed_db(settings)
    init_memory_db(settings)

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
        return JSONResponse(status_code=status_code, content=_reviewed_extraction(settings, record))

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
        return JSONResponse(status_code=200, content=_reviewed_extraction(settings, record))

    @app.post("/api/purchases")
    async def confirm_reviewed_purchase(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return _confirmation_rejected("The confirmation could not be read.")
        try:
            purchase = confirm_purchase(settings, payload)
        except EvidenceNotFound:
            confirmation_logger.info("confirmation rejected reason=evidence_not_found")
            return _not_found()
        except ExtractionNotFound:
            confirmation_logger.info("confirmation rejected reason=extraction_not_found")
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "reason": "The extraction was not found."},
            )
        except AlreadyConfirmed as exc:
            confirmation_logger.info("confirmation rejected reason=already_confirmed")
            return JSONResponse(
                status_code=409,
                content={
                    "status": "rejected",
                    "reason": "This extraction is already confirmed.",
                    "purchase_id": exc.purchase_id,
                },
            )
        except ConfirmationRejected as exc:
            confirmation_logger.info("confirmation rejected")
            return _confirmation_rejected(exc.reason)
        except Exception:
            confirmation_logger.exception("confirmation failed")
            return _confirmation_rejected("The purchase could not be confirmed.", status_code=500)
        confirmation_logger.info(
            "purchase confirmed purchase_id=%s evidence_id=%s item_count=%s",
            purchase.purchase_id,
            purchase.evidence_id,
            len(purchase.items),
        )
        try:
            memory, _created = remember_purchase(settings, purchase.purchase_id)
        except Exception:
            confirmation_logger.exception("purchase history was not saved")
            return _confirmation_rejected(
                "The purchase was confirmed, but purchase history could not be saved.",
                status_code=500,
            )
        payload = purchase.to_public_dict()
        payload["memory_id"] = memory.memory_id
        return JSONResponse(status_code=201, content=payload)

    @app.get("/api/purchases/{purchase_id}")
    def read_confirmed_purchase(purchase_id: str) -> JSONResponse:
        purchase = read_purchase(settings, purchase_id)
        if purchase is None:
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "reason": "The confirmed purchase was not found."},
            )
        return JSONResponse(status_code=200, content=purchase.to_public_dict())

    @app.get("/memory", response_class=HTMLResponse)
    def purchase_history() -> str:
        return (STATIC_DIR / "memory.html").read_text(encoding="utf-8")

    @app.post("/api/memory")
    async def remember_confirmed_purchase(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return _memory_rejected("The memory request could not be read.")
        try:
            memory, created = remember_from_request(settings, payload)
        except PurchaseNotFound:
            memory_logger.info("memory rejected reason=purchase_not_found")
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "reason": "The confirmed purchase was not found."},
            )
        except MemoryRejected as exc:
            memory_logger.info("memory rejected")
            return _memory_rejected(exc.reason)
        except Exception:
            memory_logger.exception("memory creation failed")
            return _memory_rejected("The purchase could not be remembered.", status_code=500)
        memory_logger.info(
            "memory %s memory_id=%s purchase_id=%s item_count=%s",
            "created" if created else "reused",
            memory.memory_id,
            memory.purchase_id,
            len(memory.items),
        )
        return JSONResponse(status_code=201 if created else 200, content=memory.to_public_dict())

    @app.get("/api/memory")
    def list_purchase_history(filter: str | None = None) -> JSONResponse:
        try:
            entries = read_memory_list(settings, filter)
        except MemoryRejected as exc:
            return _memory_rejected(exc.reason)
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "purchases": [entry.to_summary_dict() for entry in entries]},
        )

    @app.get("/api/memory/{memory_id}")
    def read_remembered_purchase(memory_id: str) -> JSONResponse:
        memory = read_memory(settings, memory_id)
        if memory is None:
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "reason": "The remembered purchase was not found."},
            )
        return JSONResponse(status_code=200, content=memory.to_public_dict())

    @app.patch("/api/memory/{memory_id}/items/{memory_item_id}")
    async def correct_item_classification(
        memory_id: str,
        memory_item_id: str,
        request: Request,
    ) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return _memory_rejected("The classification could not be read.")
        try:
            memory = correct_classification(settings, memory_id, memory_item_id, payload)
        except MemoryNotFound:
            memory_logger.info("classification rejected reason=memory_not_found")
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "reason": "The remembered purchase was not found."},
            )
        except MemoryRejected as exc:
            memory_logger.info("classification rejected")
            return _memory_rejected(exc.reason)
        except Exception:
            memory_logger.exception("classification update failed")
            return _memory_rejected("The classification could not be saved.", status_code=500)
        return JSONResponse(status_code=200, content=memory.to_public_dict())

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


def _reviewed_extraction(settings: Settings, record: ExtractionRecord) -> dict[str, object]:
    payload = record.to_public_dict()
    payload["confidence"] = assess_extraction(record)
    existing = get_purchase_for_extraction(settings, record.extraction_id)
    payload["confirmation_state"] = "confirmed" if existing else "unconfirmed"
    payload["purchase_id"] = existing.purchase_id if existing else None
    return payload


def _memory_rejected(reason: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "rejected", "reason": reason})


def _confirmation_rejected(reason: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "rejected", "reason": reason})


def _rejected(reason: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "rejected", "reason": reason})


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"status": "not_found", "reason": "Receipt evidence was not found."},
    )


app = create_app()
