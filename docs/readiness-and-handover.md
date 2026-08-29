# Delivery Readiness and Handover Checklist

Written against this specific prototype (`src/`, SQLite persistence,
single shared API key). Items are marked [done] where the current
codebase already satisfies them, [gap] where it's a known, documented
limitation rather than an oversight, and [open] where it's a pending or
engagement-specific follow-up rather than a code limitation; see the
README's "Known limitations" section and `discovery-and-design.md` for
the reasoning behind each gap. [done] claims below were verified against
the running service (live requests, not just a source read), not assumed
correct.

## UAT readiness

- [open] **Approved requirements and mapping**: `docs/mapping.md` needs
  sign-off on one open item it flags: buyer TRN handling. The buyer's
  `trn` is accepted in the source payload but neither validated nor
  carried into the normalized output (`mapping.py`, `include_trn=False`
  for the buyer). Confirm with the customer whether that's the intended
  behavior before UAT starts, not discovered during it.
  (`payment.method` is already enforced as required by `validation.py`;
  see "Known issues" note below on why it isn't itself an open item.)
- [done] **Environment and connectivity**: runs locally via
  `uvicorn src.main:app` per the README; no external network calls are
  made (mapping and validation are pure functions, persistence is a local
  SQLite file).
- [done] **Credentials and access**: a single `TRAINING_API_KEY`,
  provisioned via `.env` (never committed; see `.gitignore`), read
  through `settings.require_api_key()`. **Verified:** this is *not*
  checked at process startup; the app starts and `/health` returns
  `200` even with the variable unset. The check only runs on the first
  request that hits `require_api_key()` (i.e. `POST /invoices`,
  `GET /status`, or `GET /api/v1/audit`), and it fails as an unhandled exception surfaced to the
  caller as a generic `500 INTERNAL_ERROR` with a `correlationId`. The
  actual `RuntimeError: TRAINING_API_KEY is not set...` message only
  appears in server-side structured logs, not the response body. Worth
  adding an explicit startup-time check before go-live so a missing key
  fails loudly and immediately rather than surfacing as a 500 on first
  use.
- [done] **Synthetic/approved test data**: `samples/valid-invoice.json`
  and `samples/invalid-invoices/*.json` are all synthetic, matching
  Section 4 of the assignment; no real customer data anywhere in the repo.
- [done] **Positive and negative scenarios**: all 10 scenarios the
  assignment requires are implemented as automated tests
  (`tests/test_scenarios.py`) plus 6 additional edge cases
  (`tests/test_additional_scenarios.py`); 16/16 passing as of this
  writing (`python3 -m pytest tests/ -v`).
- [open] **Defect ownership and severity**: no formal severity scale defined
  yet for this engagement; recommend adopting the customer's standard
  (e.g. P1 to P4) before UAT so defects raised during testing have a
  consistent triage path.
- [done] **Evidence and exit criteria**: the audit log
  (`GET /api/v1/audit`) gives a queryable, append-only trail of every
  submission/status-check/validation-failure event, usable as UAT evidence
  without needing to grep raw logs.

## Go-live readiness

- [gap] **Production configuration and environment separation**:
  this prototype has no environment-specific config beyond env vars; there
  is no distinct "UAT settings" vs "prod settings" profile, and
  `MAX_CONTENT_LENGTH_BYTES`/`PROCESSING_DELAY_SECONDS`/
  `SUPPORTED_SOURCE_VERSIONS` would all need real-world values chosen
  before go-live, not left at prototype defaults (2 second processing
  delay, 1 MB body limit).
- [gap] **Secure credential provisioning**: the API key is a
  single shared secret read from a bare environment variable. Production
  needs per-customer keys, individually revocable, ideally sourced from a
  secrets manager rather than a `.env` file. Not implemented; documented
  as a known limitation, not a decision to leave as-is.
- [gap] **Mapping/version alignment**: `sourceVersion` is gated against
  `SUPPORTED_SOURCE_VERSIONS` (`UNSUPPORTED_SCHEMA_VERSION` on mismatch),
  but there is only one mapping function for one version; no
  versioned-mapping dispatch exists yet. Confirm with the customer
  whether a `desert-star-erp` schema change is anywhere on their roadmap
  before go-live.
- [done] **Smoke tests**: `GET /health` returns `{"status": "ok"}`;
  `tests/test_additional_scenarios.py::test_health_check` covers it. A
  minimal smoke check, sufficient for liveness but not for confirming the
  full submit to status pipeline is healthy end-to-end.
- [gap] **Monitoring**: beyond `/health` and structured stdout
  logs, there's no metrics/alerting layer (no dashboards, no paging on
  elevated error rates or stuck `PROCESSING` documents). Needs a real
  observability stack before production traffic.
- [done] **Retry and duplicate controls**: the `UNIQUE(idempotency_key)`
  constraint at the database level, with a documented deterministic
  fallback key when the caller omits `Idempotency-Key`. This is the
  concrete fix underlying the scenario investigated in
  `docs/defect-investigation.md`.
- [gap] **Reconciliation**: no reconciliation job exists to
  compare what the ERP believes it sent against what this system recorded
  (e.g. detecting a submission the ERP made that never reached us due to a
  network failure with no retry). Recommend building this before go-live
  if the customer needs a guarantee beyond "the ERP got a `202`."
- [gap] **Rollback or fallback plan**: not defined for this
  prototype. At minimum, production needs a documented "how do we pause
  ingestion without losing in-flight ERP submissions" plan before go-live.
- [open] **Support ownership and escalation contacts**: to be filled in with
  the actual on-call rotation/contact list for this engagement; not
  something the prototype itself can define.

## Hypercare and support handover

- **Known issues** (carried into hypercare, not fixed pre-launch; see
  README "Known limitations" and `discovery-and-design.md` for the full
  list):
  - Single shared API key, not per-customer.
  - No TRN registry check; format only.
  - No existence check on `originalInvoiceNo` for credit notes.
  - Single local SQLite file; no multi-instance write support.
  - No rate limiting. (Request **size** limiting *is* implemented,
    via `MAX_CONTENT_LENGTH_BYTES` and tested; this is a narrower control than
    rate limiting and shouldn't be conflated with it.)
  - No idempotency-key TTL; keys and their documents are retained
    indefinitely, and no data-retention policy is defined.
  - `city` is accepted for both seller and buyer but never validated;
    `validate_invoice` doesn't check it for emptiness (see `docs/mapping.md`
    open question on this).
  - Buyer `emirate` isn't validated, asymmetrically to seller `emirate`.
    `_validate_party` is called for the buyer with `require_emirate` left
    at its default of `False`. Unclear whether this asymmetry (only
    sellers must be in a UAE emirate) is intentional; flagged as an open
    question in `docs/mapping.md`.
  - `invoice_no` uniqueness is enforced at the database level
    (`persistence.py`, `DuplicateInvoiceNumberError`) as an addition beyond
    the assignment's required scenarios; it isn't covered by the ten
    required test scenarios or the six additional ones in
    `tests/test_additional_scenarios.py`.
  - Only `AED` is accepted as `currency`; any other value returns
    `UNSUPPORTED_CURRENCY`. See `docs/discovery-and-design.md` for how
    multi-currency support would be added.
  - The async processing step (`_finalize_processing` in `src/main.py`) is
    a fixed-delay, deterministic threshold rule on `grossAmount` — not a
    real downstream integration. Support staff should know there's no
    actual validation/clearance system behind an `ACCEPTED` or `REJECTED`
    status; it's a stand-in for the exercise.
  - `GET /api/v1/audit` sits behind the same API key as the submit/status
    endpoints; a real deployment would likely put it behind a separate
    support-only role.
  - **Corrected from an earlier draft of this doc:** `payment.method` and
    the `amountDue = grossAmount minus prepaidAmount` reconciliation are
    both already enforced by `validation.py` and confirmed by a live
    request against the running service (`400 VALIDATION_FAILED` /
    `REQUIRED` and `400 VALIDATION_FAILED` / `MISMATCH` respectively);
    neither is an open issue. The one real open item on `payment.method`
    is that the assessment PDF lists it under "Required source
    information" but never states an explicit rule for it the way it
    does for TRN format or the totals formulas, which is worth flagging
    for sign-off, even though the behavior itself is already correct.
- [open] **Monitoring and alerts**: to be stood up for the real environment;
  not present in the prototype (see "Monitoring" above).
- **Runbook and troubleshooting guide** (minimum viable version, based on
  what this system actually exposes):
  - A submission returning `400 VALIDATION_FAILED`: check the `details[]`
    array's `field`/`code`/`message`; each maps directly to a rule in
    `docs/mapping.md`'s Validation column.
  - A submission returning `409 IDEMPOTENCY_KEY_REUSE_MISMATCH`: the
    caller reused an `Idempotency-Key` with a different payload; see
    `docs/defect-investigation.md` for the investigation pattern.
  - A document stuck in `PROCESSING` past `PROCESSING_DELAY_SECONDS`:
    check application logs for the correlation ID from the original
    `202` response; the background thread
    (`src/main.py::_finalize_processing`) should have updated status
    within that window under normal operation.
  - Any `500 INTERNAL_ERROR`: the response includes only a
    `correlationId`, deliberately no stack trace; use that ID to find the
    full server-side exception in structured logs (never in the response
    body, by design).
  - A submission returning `409 DUPLICATE_INVOICE_NUMBER`: distinct from
    `IDEMPOTENCY_KEY_REUSE_MISMATCH` above; the `invoice_no` already
    belongs to a different document under a *different* idempotency key
    (`persistence.py::DuplicateInvoiceNumberError`), not a retry of the
    same request. **Correction:** the response body's `message` does
    *not* include the existing `documentId` — verified directly against
    `src/main.py`, it only names the `invoiceNo`. The existing
    `documentId` is captured in the structured logs
    (`existing_document_id`) and in the audit log entry's `details`
    (`DUPLICATE_INVOICE_NUMBER_REJECTED`), so support staff need to pull
    it from `GET /api/v1/audit` (filtered by `invoice_no` or correlation
    ID) rather than from the API response itself.
  - `401 UNAUTHORIZED`: missing or incorrect `X-API-Key` header; the
    response body deliberately gives no detail beyond that, to avoid
    leaking whether a key format is close to valid.
  - `404 DOCUMENT_NOT_FOUND`: the `documentId` in
    `GET /api/v1/documents/{documentId}/status` doesn't exist in this
    instance's database.
  - `413 PAYLOAD_TOO_LARGE`: request body exceeds
    `MAX_CONTENT_LENGTH_BYTES`, rejected by middleware based on the
    `Content-Length` header before any JSON parsing happens.
- [open] **Open actions**: to be tracked in whatever the customer's ticketing
  system is; the items under "Known issues" above are a reasonable
  starting backlog.
- [open] **Customer and internal support contacts**: to be filled in per
  engagement.
- [open] **Exit criteria from hypercare**: recommend basing this on: zero
  unexplained `IDEMPOTENCY_KEY_REUSE_MISMATCH` or duplicate `documentId`
  reports for a defined window (directly addressing the Task E scenario),
  plus no `500 INTERNAL_ERROR` spikes correlated with any specific
  `sourceVersion` or payload shape. Concrete thresholds (how many, how
  long) need customer agreement, not just internal judgment.