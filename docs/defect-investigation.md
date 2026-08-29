# Defect Investigation: Duplicate Document IDs on Retry

**Reported symptom (verbatim):**
> "We submitted invoice INV-2025-1001 twice after a timeout. We received two
> different document IDs, and one request later failed because the tax
> total did not match."

**Status: unconfirmed.** Treated as a reported symptom to investigate, not
a confirmed product defect, per the assignment's instruction. The
reproduction and analysis below are based on how this prototype's
idempotency and validation logic behave today (`src/persistence.py`,
`src/main.py`, `src/validation.py`) — not on customer-side logs, which we
don't have yet.

## Clarifying questions

1. Was the **same `Idempotency-Key`** sent on both attempts, or a new key is        generated for the second attempt?

2. If no `Idempotency-Key` header was sent at all, was **any field in
   `sourceName`, `invoice.invoiceNo`, or `invoice.issueDate`** different
   between the two attempts (even whitespace, or a different envelope
   `sourceName`)?
3. What was the **exact timeout** the customer observed, a client-side
   timeout with no response received, or a response that did arrive but
   arrived late/was itself dropped? 
4. Was the **request body identical** between the two attempts, byte for
   byte, or did the ERP recompute `totals` before
   resubmitting.
   
   e.g. did it apply a rounding fix, a tax-rate correction,
   or repull data from source in between?
5. What were the **two document IDs** and the **two HTTP status codes**
   received? 
6. Did the tax mismatch happen on the second submission, or on a later retry?

7. What time gap was there between the two submissions? Near-simultaneous
   (sub-second, suggesting a race) vs. minutes apart (suggesting a
   deliberate manual retry after the customer noticed the timeout) point
   at different causes.
8. Is there a **retry/queue layer on the ERP side** (e.g. a middleware
   product, an RPA bot, a message queue with at-least-once delivery) sitting
   between `desert-star-erp` and our API that could itself be generating
   the duplicate, independent of anything our API did?
9. Were both requests sent to the **same environment/base URL**, and by
   the same client/service account? (Ruling out "one hit staging, one hit
   local" type mix-ups.)
10. Does the customer have **their own request/response logs** for both
    attempts (timestamps, headers, status codes, response bodies)? Without
    those, we're limited to what our own audit log captured.

## Reproduction steps

Using this prototype as the reference implementation:

1. Submit `samples/valid-invoice.json` (invoice `INV-2025-1001`) with a
   fixed `Idempotency-Key`, e.g. `repro-1`.
2. Immediately submit the **exact same payload** again with the **same**
   `Idempotency-Key: repro-1`.
   - **Expected (current code):** the second response returns the *same*
     `documentId` as the first — `test_duplicate_retry_same_key_same_payload`
     in `tests/test_scenarios.py` covers exactly this and passes. This is
     the "safe replay" path (`insert_new_document` reads back the winning
     row when the `UNIQUE(idempotency_key)` constraint rejects the second
     `INSERT`).
3. Submit a **modified** payload (e.g. a different `invoiceNo`, to
   simulate "the ERP changed something before retrying") with the **same**
   `Idempotency-Key: repro-1`.
   - **Expected (current code):** `409 IDEMPOTENCY_KEY_REUSE_MISMATCH` —
   `test_idempotency_key_reuse_different_payload_conflict` covers this.
4. Submit the same payload **twice with no `Idempotency-Key` header at
   all**, to exercise the deterministic fallback
   (`sha256(sourceName|invoiceNo|issueDate)`).
   - **Expected (current code):** same behavior as step 2 — same
     `documentId` both times, since the fallback key is identical when
     `sourceName`, `invoiceNo`, and `issueDate` are unchanged.
5. Repeat step 4, but change `issueDate` by one day on the second
   submission (simulating the ERP silently normalizing or correcting a
   date on retry).
   - **Expected (current code):** a **different** fallback key is derived,
     so this produces a genuinely new `documentId` — indistinguishable at
     the API level from two separate, unrelated invoices. This is the
     closest reproduction this prototype's design can offer for "two
     document IDs from what the customer considered one submission."

If the customer's real report matches step 5 rather than step 2 or 3, the
most likely explanation is a field-level difference between the two
requests — not a bug in the idempotency mechanism itself.

## Evidence to collect

- Our own audit log for the time window in question:
  `GET /api/v1/audit?limit=500` (or filtered by either reported
  `documentId`), looking specifically for `DOCUMENT_CREATED`,
  `IDEMPOTENT_RETRY`, and `IDEMPOTENCY_KEY_REUSE_REJECTED` events and their
  `idempotency_key` values.
- The `X-Correlation-ID` returned on both responses, if the customer's
  client captured response headers — lets us pull the exact structured
  log lines for each request from application logs (never the raw
  payload, per the logging redaction rule, but method/path/status/latency
  and the safe payload metadata are there).
- The two `documentId` values and their current `status`/`errors` via
  `GET /api/v1/documents/{id}/status` for each.
- The customer's own timestamps and headers for both attempts, per
  clarifying question 10.
- Whichever request produced "the tax total did not match" — its exact
  `400` response body, which would include `field: invoice.totals.taxAmount,
  code: MISMATCH` per `src/validation.py`'s reconciliation logic, and the
  submitted vs. expected values in the error message.

## Likely causes to investigate (not yet confirmed)

In rough order of likelihood given how this system is built:

1. **Different idempotency keys across the two attempts** (deterministic
   fallback path, with a field difference — most likely if no
   `Idempotency-Key` header is in use). Two genuinely distinct keys will
   always produce two genuinely distinct documents; this is expected
   behavior, not a bug, if the underlying data differed.
2. **A retry/queue layer upstream of the ERP integration** generating a
   second, independently-keyed request without the ERP's own logic being
   aware a retry happened (clarifying question 8).
3. **A pre-fix check-then-insert race condition**, if this report describes
   behavior from a *previous* version of the system rather than this one.
   This prototype's persistence layer (`src/persistence.py`) uses a
   database-level `UNIQUE` constraint on `idempotency_key` specifically to
   close this race — two near-simultaneous `INSERT`s with the same key
   cannot both succeed; the loser reads back the winner's row. If the
   report is about *this* codebase, reproduction step 2 above should be
   used to confirm or rule this out directly, since it's covered by an
   automated test that currently passes.
4. **The "tax total did not match" failure is unrelated to the duplicate
   documentId issue** — i.e., two separate problems bundled into one
   report. Worth explicitly asking the customer (clarifying question 6)
   whether the tax mismatch happened on the same request that produced a
   second `documentId`, or on a distinct, later resubmission.

## Immediate containment / workaround

- Ask the customer to **always send an explicit `Idempotency-Key`** header
  derived from something stable on their side (e.g. their own internal
  transaction ID), rather than relying on the deterministic
  `sourceName + invoiceNo + issueDate` fallback, until the root cause is
  confirmed. This removes any ambiguity introduced by a field changing
  between attempts.
- If the two documents are confirmed duplicates of a single real invoice,
  manually mark the incorrect one for exclusion in downstream reporting
  (there is no `DELETE`/cancel endpoint in this prototype — this is a
  known gap, not an oversight; see `readiness-and-handover.md`).
- Do **not** silently merge or delete either document record without
  customer confirmation of which one is authoritative — the audit log is
  append-only specifically so that both attempts remain traceable while
  this is investigated.

## Recommended permanent controls

- **Already implemented in this codebase**, worth explicitly verifying
  against whatever system the customer actually hit: a `UNIQUE` database
  constraint on `idempotency_key`, not an application-level
  check-then-insert. If the customer's report is against an older or
  different implementation, this is the concrete fix to point to.
- **Recommend the customer's ERP always sends an explicit
  `Idempotency-Key`** rather than relying on any server-side fallback
  derived from mutable fields — removes an entire class of "field changed
  between retries" ambiguity.
- **Add existence-check tooling for the audit trail** so this kind of
  investigation doesn't depend on someone manually cross-referencing two
  `documentId`s — e.g. a lookup by `invoice_no` (not just `document_id`)
  on `GET /api/v1/audit`, since the customer is unlikely to know a
  `documentId` when first reporting the issue.
- **Consider validating `amountDue`** in the same reconciliation pass as
  `netAmount`/`taxAmount`/`grossAmount` (currently unvalidated — see
  `mapping.md`), if "tax total did not match" turns out to trace back to
  an inconsistency in a field that isn't checked today.

## What to escalate, and to whom

- **To the Technical Implementation Consultant / customer's integration
  team:** clarifying questions 1–4 and 8–10 above — we cannot determine
  root cause without the customer's own request logs and confirmation of
  their retry behavior.
- **To Product:** whether the deterministic fallback idempotency key
  (used only when the customer doesn't send `Idempotency-Key`) should be
  deprecated in favor of *requiring* the header for this customer, given
  this incident.
- **To Engineering:** only if reproduction step 2 (same key, same payload)
  is shown to fail against the actual deployed system — that would
  indicate the `UNIQUE` constraint fix isn't present or isn't working in
  that environment, which is a genuine regression worth a P1 ticket. Do
  not open that ticket before confirming reproduction step 2 actually
  fails; today it passes in this codebase's automated test suite.
