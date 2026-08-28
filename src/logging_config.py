"""
Structured (JSON) logging with a request-scoped correlation ID.

Rules enforced by convention throughout the codebase 
"""
import json
import logging
import sys
from contextvars import ContextVar
from typing import Any, Dict, Optional

correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)

# Exact field names that are always secret.
_REDACT_EXACT = {"api_key", "x-api-key", "authorization", "password", "secret", "token", "trn"}
# Substring markers for anything else that should never appear in logs.
_REDACT_SUBSTRING_MARKERS = ("password", "secret", "token", "authorization")


def _redact_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if key_lower in _REDACT_EXACT or any(marker in key_lower for marker in _REDACT_SUBSTRING_MARKERS):
        return "***REDACTED***"
    return value


def payload_metadata_for_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    invoice = payload.get("invoice") or {}
    return {
        "sourceName": payload.get("sourceName"),
        "sourceVersion": payload.get("sourceVersion"),
        "invoiceNo": invoice.get("invoiceNo"),
        "documentType": invoice.get("documentType"),
        "lineCount": len(invoice.get("lines") or []),
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        cid = correlation_id.get()
        if cid:
            log_obj["correlationId"] = cid
        extra = getattr(record, "log_extra", None)
        if extra:
            log_obj.update({k: _redact_value(k, v) for k, v in extra.items()})
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


def _configure_root() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


_configure_root()
logger = logging.getLogger("complyance_integration")


def log(level: int, message: str, **extra: Any) -> None:
    logger.log(level, message, extra={"log_extra": extra})


def log_info(message: str, **extra: Any) -> None:
    log(logging.INFO, message, **extra)


def log_warning(message: str, **extra: Any) -> None:
    log(logging.WARNING, message, **extra)


def log_exception(message: str, **extra: Any) -> None:
    logger.error(message, exc_info=True, extra={"log_extra": extra})
