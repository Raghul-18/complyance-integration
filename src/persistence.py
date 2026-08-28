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
            row = conn.execute(
                "SELECT * FROM documents WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if row is None:
                raise IdempotencyConflict("idempotency_key present but record unreadable")
            existing = DocumentRecord.from_row(row)
            if existing.payload_hash != payload_hash:
                raise IdempotencyConflict(
                    f"idempotency_key {idempotency_key!r} reused with a different payload"
                )
            return existing


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
