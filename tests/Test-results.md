# Task D — Testing

## Scenario results

| # | Scenario | Expected status code | Expected outcome |
|---|---|---|---|
| 1 | Valid standard-rated invoice | 202 | Document created with status `PROCESSING`, a generated `documentId`, and `isTerminal: false`; status endpoint later reports `ACCEPTED`. |
| 2 | Missing required seller TRN | 400 | Validation fails with `INVALID_FORMAT` on field `invoice.seller.trn` — a missing TRN and a malformed TRN hit the same regex check and share this code, there is no separate "required" case; no document is created. |
| 3 | Invalid TRN format | 400 | Validation fails with `INVALID_FORMAT` on `invoice.seller.trn`; no document is created. |
| 4 | Unsupported tax category | 400 | Validation fails with `INVALID_VALUE` on `invoice.lines[0].taxCategory`; no document is created. |
| 5 | Incorrect total or tax calculation | 400 | Validation fails with `MISMATCH` on `invoice.totals.taxAmount` (submitted value doesn't match the calculated line total); no document is created. |
| 6 | Duplicate retry using the same idempotency key | 200 or 202 | No new document is created; the response returns the same `documentId` as the original request. |
| 7 | Reuse of an idempotency key with a different payload | 409 | Request rejected with error `IDEMPOTENCY_KEY_REUSE_MISMATCH`; no new document is created. |
| 8 | Unknown document ID on status retrieval | 404 | Error `DOCUMENT_NOT_FOUND` returned. |
| 9 | Credit note without an original-invoice reference | 400 | Validation fails with a `REQUIRED` issue on `invoice.originalInvoiceNo`. |
| 10 | Unauthorized request | 401 | Error `UNAUTHORIZED` returned, both for a wrong `X-API-Key` and a missing one. |
| 11 | Unsupported schema version | 400 | Validation fails with `UNSUPPORTED_SCHEMA_VERSION` on `sourceVersion`; no document is created. |
| 12 | Invalid calendar date (e.g. `2025-02-30`) | 400 | Validation fails on `invoice.issueDate` — a value that matches the `YYYY-MM-DD` pattern but isn't a real calendar date is still rejected. |
| 13 | Request body exceeds the size limit | 413 | Request rejected with error `PAYLOAD_TOO_LARGE`, based on the `Content-Length` header, before the body is parsed. |
| 14 | Caller-supplied `X-Correlation-ID` | 404 (using an unknown document ID to trigger a response) | The correlation ID supplied in the request header is echoed back unchanged in the response header, rather than being replaced with a generated one. |
| 15 | Audit log records document creation | 202 (submit), 200 (audit lookup) | A successful submission produces a `DOCUMENT_CREATED` entry in the audit log, retrievable by `documentId`. |
| 16 | Health check | 200 | Response body `{"status": "ok"}`. |

## Test-results summary

**Pytest (`tests/`):** 16 of 16 tests passed — all ten required scenarios plus the six additional ones above.

**Postman collection (`postman/collection.json`, run via `newman`):** 17 of 17 requests and 47 of 47 assertions passed, covering the same 16 scenarios (the audit-trail scenario is split across two requests: submit, then look up).

## Scenarios described but not implemented

- **Zero-rated, exempt, and out-of-scope invoices**: submit an invoice with one line per non-standard tax category (`ZERO_RATED`, `EXEMPT`, `OUT_OF_SCOPE`) and confirm each computes at a 0% tax rate; also test an invoice mixing `STANDARD` lines with non-standard lines to confirm totals sum correctly across categories.
- **Multiple currencies and exchange-rate fields**: today only `AED` is accepted (anything else returns `UNSUPPORTED_CURRENCY`). Testing this would mean submitting a non-AED currency and confirming the rejection, then — once exchange-rate support is added — submitting a payload with a currency and rate and confirming totals are computed/rounded correctly in the target currency.
- **Bulk submission of up to 10 invoices**: submit 10 distinct invoices (unique `invoiceNo`/`Idempotency-Key` per invoice) in sequence or via a batch endpoint, and confirm each gets its own `documentId` and is processed independently.
- **Temporary downstream failure and retry**: simulate a transient failure in the asynchronous processing step (e.g. the finalize/decision step throws once), confirm the document remains `PROCESSING` in the interim, and confirm a retry reaches a terminal status without creating a duplicate document.
- **Partial failure in a batch**: submit a batch of several invoices where one is intentionally invalid, and confirm the other invoices in the batch still succeed independently rather than the whole batch failing together.
- **High-volume or performance behavior**: drive concurrent submissions against the submit endpoint and observe behavior under load, particularly around write contention on the persistence layer, to establish a baseline throughput and identify the first bottleneck.
- **File-based and manual-upload validation**: run the same payload through the validation and mapping logic directly (bypassing the HTTP API), to confirm a file-based or manual-upload ingestion path would enforce identical rules without needing its own duplicate validation logic.