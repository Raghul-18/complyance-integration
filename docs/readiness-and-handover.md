# Delivery Readiness and Handover Checklist

Written against this specific prototype (`src/`, SQLite persistence,
single shared API key). Items are marked **[done]** where the current
codebase already satisfies them, and **[gap]** where it's a known,
documented limitation rather than an oversight — see the README's "Known
limitations" section and `discovery-and-design.md` for the reasoning
behind each.

## UAT readiness

- [ ] **Approved requirements and mapping** — `docs/mapping.md` needs
  sign-off, specifically the two open items it flags: `payment.method` is
  listed as required source information but is not currently validated,
  and buyer TRN handling (captured or dropped) is unresolved. Both should
  be confirmed before UAT starts, not discovered during it.
- **[done] Environment and connectivity** — runs locally via
  `uvicorn src.main:app` per the README; no external network calls are
  made (mapping and validation are pure functions, persistence is a local
  SQLite file).
- **[done] Credentials and access** — a single `TRAINING_API_KEY`,
  provisioned via `.env` (never committed — see `.gitignore`), read
  through `settings.require_api_key()`, which fails loudly at startup if
  unset rather than silently accepting a blank key.
- **[done] Synthetic/approved test data** — `samples/valid-invoice.json`
  and `samples/invalid-invoices/*.json` are all synthetic, matching
  Section 4 of the assignment; no real customer data anywhere in the repo.
- **[done] Positive and negative scenarios** — all 10 scenarios the
  assignment requires are implemented as automated tests
  (`tests/test_scenarios.py`) plus 6 additional edge cases
  (`tests/test_additional_scenarios.py`); 16/16 passing as of this
  writing (`python3 -m pytest tests/ -v`).
- [ ] **Defect ownership and severity** — no formal severity scale defined
  yet for this engagement; recommend adopting the customer's standard
  (e.g. P1–P4) before UAT so defects raised during testing have a
  consistent triage path.
- **[done] Evidence and exit criteria** — the audit log
  (`GET /api/v1/audit`) gives a queryable, append-only trail of every
  submission/status-check/validation-failure event, usable as UAT evidence
  without needing to grep raw logs.

## Go-live readiness

- [ ] **Production configuration and environment separation** — **[gap]**
  this prototype has no environment-specific config beyond env vars; there
  is no distinct "UAT settings" vs "prod settings" profile, and
  `MAX_CONTENT_LENGTH_BYTES`/`PROCESSING_DELAY_SECONDS`/
  `SUPPORTED_SOURCE_VERSIONS` would all need real-world values chosen
  before go-live, not left at prototype defaults (2-second processing
  delay, 1 MB body limit).
- [ ] **Secure credential provisioning** — **[gap]** the API key is a
  single shared secret read from a bare environment variable. Production
  needs per-customer keys, individually revocable, ideally sourced from a
  secrets manager rather than a `.env` file. Not implemented; documented
  as a known limitation, not a decision to leave as-is.
- [ ] **Mapping/version alignment** — `sourceVersion` is gated against
  `SUPPORTED_SOURCE_VERSIONS` (`UNSUPPORTED_SCHEMA_VERSION` on mismatch),
  but there is only one mapping function for one version. **[gap]**: no
  versioned-mapping dispatch exists yet — confirm with the customer
  whether a `desert-star-erp` schema change is anywhere on their roadmap
  before go-live.
- **[done] Smoke tests** — `GET /health` returns `{"status": "ok"}`;
  `tests/test_additional_scenarios.py::test_health_check` covers it. A
  minimal smoke check, sufficient for liveness but not for confirming the
  full submit → status pipeline is healthy end-to-end.
- [ ] **Monitoring** — **[gap]** beyond `/health` and structured stdout
  logs, there's no metrics/alerting layer (no dashboards, no paging on
  elevated error rates or stuck `PROCESSING` documents). Needs a real
  observability stack before production traffic.
- **[done] Retry and duplicate controls** — the `UNIQUE(idempotency_key)`
  constraint at the database level, with a documented deterministic
  fallback key when the caller omits `Idempotency-Key`. This is the
  concrete fix underlying the scenario investigated in
  `docs/defect-investigation.md`.
- [ ] **Reconciliation** — **[gap]** no reconciliation job exists to
  compare what the ERP believes it sent against what this system recorded
  (e.g. detecting a submission the ERP made that never reached us due to a
  network failure with no retry). Recommend building this before go-live
  if the customer needs a guarantee beyond "the ERP got a `202`."
- [ ] **Rollback or fallback plan** — **[gap]** not defined for this
  prototype. At minimum, production needs a documented "how do we pause
  ingestion without losing in-flight ERP submissions" plan before go-live.
- [ ] **Support ownership and escalation contacts** — to be filled in with
  the actual on-call rotation/contact list for this engagement; not
  something the prototype itself can define.

## Hypercare and support handover

- **Known issues** (carried into hypercare, not fixed pre-launch — see
  README "Known limitations" and `discovery-and-design.md` for the full
  list):
  - Single shared API key, not per-customer.
  - `payment.method` listed as required by the assessment rules but not
    currently validated (see `mapping.md`).
  - `amountDue` and `prepaidAmount` are captured but not reconciled
    against the other totals fields.
  - No TRN registry check — format only.
  - No existence check on `originalInvoiceNo` for credit notes.
  - Single local SQLite file — no multi-instance write support.
  - No rate limiting. (Request **size** limiting *is* implemented —
    `MAX_CONTENT_LENGTH_BYTES`, tested — this is a narrower control than
    rate limiting and shouldn't be conflated with it.)
  - No idempotency-key TTL — keys and their documents are retained
    indefinitely; no data-retention policy defined.
- [ ] **Monitoring and alerts** — to be stood up for the real environment;
  not present in the prototype (see "Monitoring" above).
- **Runbook and troubleshooting guide** (minimum viable version, based on
  what this system actually exposes):
  - A submission returning `400 VALIDATION_FAILED` → check the `details[]`
    array's `field`/`code`/`message`; each maps directly to a rule in
    `docs/mapping.md`'s Validation column.
  - A submission returning `409 IDEMPOTENCY_KEY_REUSE_MISMATCH` → the
    caller reused an `Idempotency-Key` with a different payload; see
    `docs/defect-investigation.md` for the investigation pattern.
  - A document stuck in `PROCESSING` past `PROCESSING_DELAY_SECONDS` →
    check application logs for the correlation ID from the original
    `202` response; the background thread
    (`src/main.py::_finalize_processing`) should have updated status
    within that window under normal operation.
  - Any `500 INTERNAL_ERROR` → the response includes only a
    `correlationId`, deliberately no stack trace; use that ID to find the
    full server-side exception in structured logs (never in the response
    body, by design).
- [ ] **Open actions** — to be tracked in whatever the customer's ticketing
  system is; the items under "Known issues" above are a reasonable
  starting backlog.
- [ ] **Customer and internal support contacts** — to be filled in per
  engagement.
- [ ] **Exit criteria from hypercare** — recommend basing this on: zero
  unexplained `IDEMPOTENCY_KEY_REUSE_MISMATCH` or duplicate-`documentId`
  reports for a defined window (directly addressing the Task E scenario),
  plus no `500 INTERNAL_ERROR` spikes correlated with any specific
  `sourceVersion` or payload shape. Concrete thresholds (how many, how
  long) need customer agreement, not just internal judgment.
