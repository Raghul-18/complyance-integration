"""
Complyance Associate Integration Engineer assessment — Task B prototype.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth import require_api_key
from src.config import settings
from src.logging_config import correlation_id, log_exception, log_info, log_warning, payload_metadata_for_log
from src.mapping import map_to_normalized
from src.persistence import (
    IdempotencyConflict,
    get_audit_log,
    get_by_document_id,
    init_db,
    insert_new_document,
    update_status,
    write_audit_log,
)
from src.validation import validate_invoice


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    log_info("app_startup", max_content_length_bytes=settings.max_content_length_bytes)
    yield


app = FastAPI(title="Complyance Integration Prototype", version="1.0", lifespan=lifespan)

REVIEW_THRESHOLD_GROSS = Decimal("1000000.00")


# ---------------------------------------------------------------------------
# Middleware: reject oversized bodies before parsing anything
# ---------------------------------------------------------------------------
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_content_length_bytes:
            log_warning(
                "request_too_large",
                content_length=content_length,
                max_allowed=settings.max_content_length_bytes,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "error": "PAYLOAD_TOO_LARGE",
                    "details": [{
                        "field": "$",
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Request body exceeds the {settings.max_content_length_bytes}-byte limit.",
                    }],
                },
            )
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware)


# ---------------------------------------------------------------------------
# Correlation ID + request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def correlation_and_logging(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    correlation_id.set(cid)
    request.state.correlation_id = cid
    start = time.monotonic()

    try:
        response = await call_next(request)
    except Exception:
        log_exception("unhandled_error", method=request.method, path=request.url.path)
        write_audit_log("INTERNAL_ERROR", correlation_id=cid, details={"path": str(request.url)})
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        log_info("request", method=request.method, path=request.url.path, status=500, latency_ms=latency_ms)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "correlationId": cid,
            },
            headers={"X-Correlation-ID": cid},
        )

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    response.headers["X-Correlation-ID"] = cid
    log_info("request", method=request.method, path=request.url.path, status=response.status_code, latency_ms=latency_ms)
    return response


# ---------------------------------------------------------------------------
# Background "downstream decision"
# ---------------------------------------------------------------------------
def _finalize_processing(document_id: str, normalized_payload: Dict[str, Any]) -> None:
    time.sleep(settings.processing_delay_seconds)
    try:
        gross = Decimal(str(normalized_payload["totals"]["grossAmount"]))
    except Exception:
        gross = Decimal("0")

    if gross > REVIEW_THRESHOLD_GROSS:
        update_status(
            document_id,
            "REJECTED",
            [{"field": "invoice.totals.grossAmount", "code": "REQUIRES_MANUAL_REVIEW",
              "message": f"Gross amount exceeds the {REVIEW_THRESHOLD_GROSS} review threshold."}],
        )
        write_audit_log("DOCUMENT_REJECTED", document_id=document_id, status="REJECTED")
    else:
        update_status(document_id, "ACCEPTED", [])
        write_audit_log("DOCUMENT_ACCEPTED", document_id=document_id, status="ACCEPTED")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/v1/invoices", status_code=202, dependencies=[Depends(require_api_key)])
async def submit_invoice(request: Request):
    cid = request.state.correlation_id

    raw_body = await request.body()
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={
                "error": "VALIDATION_FAILED",
                "details": [{"field": "$", "code": "INVALID_JSON", "message": "Request body is not valid JSON."}],
            },
        )

    invoice_no = (body.get("invoice") or {}).get("invoiceNo") if isinstance(body, dict) else None
    idempotency_key_header = request.headers.get("Idempotency-Key")

    log_info(
        "invoice_submission_received",
        invoice_no=invoice_no,
        idempotency_key=idempotency_key_header,
        **payload_metadata_for_log(body if isinstance(body, dict) else {}),
    )

    issues = validate_invoice(body)
    if issues:
        log_info("validation_failed", invoice_no=invoice_no, codes=[i.code for i in issues])
        write_audit_log(
            "VALIDATION_FAILED", correlation_id=cid, invoice_no=invoice_no,
            idempotency_key=idempotency_key_header, details={"errorCodes": [i.code for i in issues]},
        )
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_FAILED", "details": [i.to_dict() for i in issues]},
        )

    idempotency_key = idempotency_key_header
    if not idempotency_key:
        invoice = body["invoice"]
        idempotency_key = "auto:" + hashlib.sha256(
            f"{body.get('sourceName')}|{invoice['invoiceNo']}|{invoice['issueDate']}".encode()
        ).hexdigest()

    normalized = map_to_normalized(body)
    payload_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()
    document_id = str(uuid.uuid4())

    try:
        record = insert_new_document(
            document_id=document_id,
            invoice_no=invoice_no,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            normalized_payload=normalized,
            status="PROCESSING",
            errors=[],
        )
    except IdempotencyConflict:
        log_info("idempotency_conflict", invoice_no=invoice_no, idempotency_key=idempotency_key)
        write_audit_log(
            "IDEMPOTENCY_KEY_REUSE_REJECTED", correlation_id=cid, invoice_no=invoice_no,
            idempotency_key=idempotency_key, details={"reason": "payload_hash_mismatch"},
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": "IDEMPOTENCY_KEY_REUSE_MISMATCH",
                "message": "This idempotency key was already used with a different payload.",
            },
        )

    is_new = record.document_id == document_id
    if is_new:
        threading.Thread(target=_finalize_processing, args=(document_id, normalized), daemon=True).start()
        log_info("document_accepted", invoice_no=invoice_no, document_id=document_id, idempotency_key=idempotency_key)
        write_audit_log(
            "DOCUMENT_CREATED", correlation_id=cid, document_id=document_id, invoice_no=invoice_no,
            idempotency_key=idempotency_key, status="PROCESSING",
        )
    else:
        log_info("idempotent_replay", invoice_no=invoice_no, document_id=record.document_id, idempotency_key=idempotency_key)
        write_audit_log(
            "IDEMPOTENT_RETRY", correlation_id=cid, document_id=record.document_id, invoice_no=invoice_no,
            idempotency_key=idempotency_key, status=record.status,
        )

    status_code = 202 if record.status == "PROCESSING" else 200
    return JSONResponse(
        status_code=status_code,
        content={
            "documentId": record.document_id,
            "status": record.status,
            "isTerminal": record.status != "PROCESSING",
            "receivedAt": record.created_at,
        },
    )


@app.get("/api/v1/documents/{document_id}/status", dependencies=[Depends(require_api_key)])
async def get_status(document_id: str, request: Request):
    cid = request.state.correlation_id
    record = get_by_document_id(document_id)
    if record is None:
        write_audit_log("STATUS_NOT_FOUND", correlation_id=cid, document_id=document_id)
        return JSONResponse(
            status_code=404,
            content={"error": "DOCUMENT_NOT_FOUND", "message": f"No document with id {document_id!r}."},
        )
    write_audit_log(
        "STATUS_RETRIEVED", correlation_id=cid, document_id=document_id,
        invoice_no=record.invoice_no, status=record.status,
    )
    return {
        "documentId": record.document_id,
        "status": record.status,
        "isTerminal": record.status != "PROCESSING",
        "errors": record.errors,
    }


@app.get("/api/v1/audit", dependencies=[Depends(require_api_key)])
async def get_audit(document_id: Optional[str] = None, limit: int = 100):
    """Support/debugging tool: recent audit log entries, optionally filtered
    to one document. Behind the same API key as everything else — a real
    deployment would likely put this behind a separate support-only role."""
    return {"audit": get_audit_log(document_id=document_id, limit=min(limit, 500))}


@app.get("/health")
async def health():
    return {"status": "ok"}
