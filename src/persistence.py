"""
SQLite persistence.
Uses a single SQLite file for DB
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    invoice_no TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    normalized_payload TEXT NOT NULL,
    status TEXT NOT NULL,
    errors TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    correlation_id TEXT,
    document_id TEXT,
    invoice_no TEXT,
    idempotency_key TEXT,
    status TEXT,
    details TEXT,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(settings.db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(SCHEMA)
        # Enforce ERP invoice-number uniqueness as its own index (rather than
        # inline on the column) so it also applies to a database created
        # before this constraint existed.
        # Assumption: uniqueness is scoped globally across all documents in
        # this single-tenant prototype, not per sourceName. A multi-ERP
        # production deployment would likely need a composite
        # (source_name, invoice_no) constraint instead -- open question for
        # the customer's IT team.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_invoice_no ON documents(invoice_no)"
        )
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentRecord:
    document_id: str
    invoice_no: str
    idempotency_key: str
    payload_hash: str
    normalized_payload: Dict[str, Any]
    status: str
    errors: List[Dict[str, str]]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DocumentRecord":
        return cls(
            document_id=row["document_id"],
            invoice_no=row["invoice_no"],
            idempotency_key=row["idempotency_key"],
            payload_hash=row["payload_hash"],
            normalized_payload=json.loads(row["normalized_payload"]),
            status=row["status"],
            errors=json.loads(row["errors"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class IdempotencyConflict(Exception):
    """Raised when the idempotency key exists with a DIFFERENT payload hash."""


class DuplicateInvoiceNumberError(Exception):
    """
    Raised when invoice_no already belongs to a different document (i.e. a
    different idempotency key). This is NOT a safe retry of the same
    request -- it means the same ERP invoice number is being submitted as
    what looks like a brand-new document.
    """

    def __init__(self, message: str, existing_document_id: str):
        super().__init__(message)
        self.existing_document_id = existing_document_id


def insert_new_document(
    document_id: str,
    invoice_no: str,
    idempotency_key: str,
    payload_hash: str,
    normalized_payload: Dict[str, Any],
    status: str,
    errors: List[Dict[str, str]],
) -> DocumentRecord:
    """
    Attempts to insert a brand-new document row.

    Returns the existing record instead of inserting if the same key +
    same payload hash already exists (idempotent replay). Raises
    IdempotencyConflict if the key exists with a DIFFERENT payload hash.
    Raises DuplicateInvoiceNumberError if invoice_no already belongs to a
    different document under a different idempotency key.
    """
    now = _now()
    with _lock, _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO documents
                    (document_id, invoice_no, idempotency_key, payload_hash,
                     normalized_payload, status, errors, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    invoice_no,
                    idempotency_key,
                    payload_hash,
                    json.dumps(normalized_payload),
                    status,
                    json.dumps(errors),
                    now,
                    now,
                ),
            )
            conn.commit()
            return DocumentRecord(
                document_id, invoice_no, idempotency_key, payload_hash,
                normalized_payload, status, errors, now, now,
            )
        except sqlite3.IntegrityError:
            # First check whether this is a safe retry: the same
            # idempotency_key was used before. If so, the retry semantics
            # (same payload -> return existing, different payload -> raise
            # IdempotencyConflict) take priority over the invoice_no check,
            # since it's the same logical request.
            row = conn.execute(
                "SELECT * FROM documents WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if row is not None:
                existing = DocumentRecord.from_row(row)
                if existing.payload_hash != payload_hash:
                    raise IdempotencyConflict(
                        f"idempotency_key {idempotency_key!r} reused with a different payload"
                    )
                return existing

            # Not an idempotency-key collision -- check whether invoice_no
            # itself already belongs to a different document. This is a
            # genuine duplicate submission (e.g. a client that doesn't
            # reuse Idempotency-Key on retry, or the same invoice sent
            # twice by mistake), not a safe retry.
            dup_row = conn.execute(
                "SELECT * FROM documents WHERE invoice_no = ?", (invoice_no,)
            ).fetchone()
            if dup_row is not None:
                existing = DocumentRecord.from_row(dup_row)
                raise DuplicateInvoiceNumberError(
                    f"invoice_no {invoice_no!r} already exists as document {existing.document_id!r}",
                    existing_document_id=existing.document_id,
                )

            # Some other integrity error we don't have a specific handler
            # for -- surface it rather than mask it.
            raise


def get_by_document_id(document_id: str) -> Optional[DocumentRecord]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        return DocumentRecord.from_row(row) if row else None


def update_status(document_id: str, status: str, errors: List[Dict[str, str]]) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE documents SET status = ?, errors = ?, updated_at = ? WHERE document_id = ?",
            (status, json.dumps(errors), _now(), document_id),
        )
        conn.commit()


def write_audit_log(
    event_type: str,
    correlation_id: Optional[str] = None,
    document_id: Optional[str] = None,
    invoice_no: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    status: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
                (event_type, correlation_id, document_id, invoice_no,
                 idempotency_key, status, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type, correlation_id, document_id, invoice_no,
                idempotency_key, status, json.dumps(details) if details else None, _now(),
            ),
        )
        conn.commit()


def get_audit_log(document_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        if document_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE document_id = ? ORDER BY id DESC LIMIT ?",
                (document_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]