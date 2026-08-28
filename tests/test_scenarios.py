import time

from tests.conftest import load_sample


def submit(client, headers, payload, idem_key=None):
    h = dict(headers)
    if idem_key:
        h["Idempotency-Key"] = idem_key
    return client.post("/api/v1/invoices", json=payload, headers=h)


# 1. Valid standard-rated invoice
def test_valid_invoice_accepted(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    r = submit(client, auth_headers, payload, "key-1")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "PROCESSING"
    assert body["isTerminal"] is False
    assert "documentId" in body

    time.sleep(0.2)
    status = client.get(f"/api/v1/documents/{body['documentId']}/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["status"] == "ACCEPTED"


# 2. Missing required seller TRN
def test_missing_seller_trn_rejected(client, auth_headers):
    payload = load_sample("missing-seller-trn.json")
    r = submit(client, auth_headers, payload, "key-2")
    assert r.status_code == 400
    codes = [d["field"] for d in r.json()["details"]]
    assert "invoice.seller.trn" in codes


# 3. Invalid TRN format
def test_invalid_trn_format_rejected(client, auth_headers):
    payload = load_sample("invalid-trn-format.json")
    r = submit(client, auth_headers, payload, "key-3")
    assert r.status_code == 400
    details = r.json()["details"]
    assert any(d["field"] == "invoice.seller.trn" and d["code"] == "INVALID_FORMAT" for d in details)


# 4. Unsupported tax category
def test_unsupported_tax_category_rejected(client, auth_headers):
    payload = load_sample("unsupported-tax-category.json")
    r = submit(client, auth_headers, payload, "key-4")
    assert r.status_code == 400
    details = r.json()["details"]
    assert any(d["field"] == "invoice.lines[0].taxCategory" for d in details)


# 5. Incorrect total or tax calculation
def test_incorrect_tax_total_rejected(client, auth_headers):
    payload = load_sample("incorrect-tax-total.json")
    r = submit(client, auth_headers, payload, "key-5")
    assert r.status_code == 400
    details = r.json()["details"]
    assert any(d["field"] == "invoice.totals.taxAmount" and d["code"] == "MISMATCH" for d in details)


# 6. Duplicate retry using the same idempotency key (same payload)
def test_duplicate_retry_same_key_same_payload(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    r1 = submit(client, auth_headers, payload, "key-6")
    r2 = submit(client, auth_headers, payload, "key-6")
    assert r1.status_code == 202
    assert r2.status_code in (200, 202)
    assert r1.json()["documentId"] == r2.json()["documentId"]


# 7. Reuse of an idempotency key with a different payload
def test_idempotency_key_reuse_different_payload_conflict(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    r1 = submit(client, auth_headers, payload, "key-7")
    assert r1.status_code == 202

    payload2 = dict(payload)
    payload2["invoice"] = dict(payload["invoice"])
    payload2["invoice"]["invoiceNo"] = "INV-DIFFERENT"
    r2 = submit(client, auth_headers, payload2, "key-7")
    assert r2.status_code == 409
    assert r2.json()["error"] == "IDEMPOTENCY_KEY_REUSE_MISMATCH"


# 8. Unknown document ID on status retrieval
def test_unknown_document_id_status_404(client, auth_headers):
    r = client.get("/api/v1/documents/does-not-exist/status", headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["error"] == "DOCUMENT_NOT_FOUND"


# 9. Credit note without an original-invoice reference
def test_credit_note_missing_original_ref_rejected(client, auth_headers):
    payload = load_sample("credit-note-missing-original-ref.json")
    r = submit(client, auth_headers, payload, "key-9")
    assert r.status_code == 400
    details = r.json()["details"]
    assert any(d["field"] == "invoice.originalInvoiceNo" for d in details)


# 10. Unauthorized request
def test_unauthorized_request_401(client, auth_headers):
    payload = load_sample("valid-invoice.json")
    r = client.post("/api/v1/invoices", json=payload, headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401
    r_missing = client.post("/api/v1/invoices", json=payload)
    assert r_missing.status_code == 401
