import json

from tests.conftest import load_sample
from tests.test_scenarios import submit


# Unsupported / missing sourceVersion
def test_unsupported_schema_version_rejected(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    payload["sourceVersion"] = "2.0"
    r = submit(client, auth_headers, payload, "schema-1")
    assert r.status_code == 400
    codes = [d["code"] for d in r.json()["details"]]
    assert "UNSUPPORTED_SCHEMA_VERSION" in codes


# Calendar edge case: 2025-02-30 matches the YYYY-MM-DD regex but isn't a
# real date — this is exactly the case a regex-only check would miss.
def test_invalid_calendar_date_rejected(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    payload["invoice"]["issueDate"] = "2025-02-30"
    r = submit(client, auth_headers, payload, "date-1")
    assert r.status_code == 400
    details = r.json()["details"]
    assert any(d["field"] == "invoice.issueDate" for d in details)


# Request size limit — body larger than MAX_CONTENT_LENGTH_BYTES is
# rejected before JSON parsing, based on the Content-Length header alone.
def test_request_too_large_rejected(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    payload["invoice"]["lines"][0]["description"] = "x" * (2 * 1024 * 1024)  # 2MB > 1MB default
    body = json.dumps(payload).encode()
    headers = dict(auth_headers)
    headers["Content-Type"] = "application/json"
    r = client.post("/api/v1/invoices", content=body, headers=headers)
    assert r.status_code == 413
    assert r.json()["error"] == "PAYLOAD_TOO_LARGE"


# Correlation ID: caller-supplied X-Correlation-ID is echoed back rather
# than replaced with a freshly generated one.
def test_correlation_id_echoed(client, auth_headers):
    headers = dict(auth_headers)
    headers["X-Correlation-ID"] = "my-custom-trace-id"
    r = client.get("/api/v1/documents/does-not-exist/status", headers=headers)
    assert r.headers["X-Correlation-ID"] == "my-custom-trace-id"


# Audit log: a successful submission produces a retrievable audit trail
# entry for that document, distinct from debug-level logs.
def test_audit_log_records_document_creation(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    r = submit(client, auth_headers, payload, "audit-1")
    assert r.status_code == 202
    doc_id = r.json()["documentId"]

    audit = client.get(f"/api/v1/audit?document_id={doc_id}", headers=auth_headers)
    assert audit.status_code == 200
    events = [entry["event_type"] for entry in audit.json()["audit"]]
    assert "DOCUMENT_CREATED" in events


def test_health_check(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
