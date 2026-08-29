# Discovery and Integration Design

Scope: the Desert Star Trading LLC ERP → e-invoicing integration prototype
(Task B). This note captures what I'd need confirmed before treating this
prototype as a real implementation plan, plus the assumptions, dependencies,
and risks I carried instead of blocking on them.

See [`system-flow.md`](./system-flow.md) for the accompanying diagram.

## 1. Ten questions for the customer's ERP, IT, and Finance teams

- What ERP system and version are you using, and how will invoices be sent to the integration service through a direct API, middleware, scheduled job, or another mechanism?

- Does the ERP provide a stable, unique invoice number and a unique request or idempotency key? If so, does it remain unchanged when a submission is retried?

- If the ERP receives a timeout or server error, does it automatically retry? If so, how does it handle the idempotency key during retries?

- What authentication method does the ERP support for outbound API calls, and are there any firewall, proxy, VPN, or IP allow list requirements?

- What is the expected invoice volume per day, and are there periods when invoices will be submitted in large batches?

- How should credit notes be handled, and must the referenced original invoice already exist in the e invoicing system?

- Are there any Finance specific requirements around payment terms, prepaid amounts, partial payments, tax treatment, or reporting?

- Is AED the only currency required for the initial implementation, and if additional currencies are required later, which system will provide the exchange rate?

- Who owns the mapping between ERP fields and the normalized invoice structure, and how will mapping changes be reviewed, approved, and versioned?

- What monitoring and reconciliation process does Finance or IT currently use to track submitted, accepted, rejected, and failed invoices, and who owns escalation when an invoice remains in processing?

## 2. Key assumptions, dependencies, and risks

### Assumptions

- The customer's ERP can send invoice data through an API using JSON, as described in the provided scenario.

- The supplied ERP payload is representative of the data available from the customer's ERP, subject to confirmation during discovery.

- AED is the required currency for the initial implementation, with support for additional currencies considered as a future extension.

- The customer will provide the required business rules for fields or scenarios that are not defined in the assessment.

- Invoice processing may be asynchronous, with the customer retrieving the final status through the status endpoint.

- Only synthetic test data will be used during development and UAT.

### Dependencies

- Access to a suitable ERP test environment or representative test payloads.

- Agreement with the customer on the source to normalized field mapping and validation rules.

- Customer confirmation of authentication, network connectivity, and security requirements.

- Availability of ERP, IT, and Finance stakeholders for discovery, UAT, and issue resolution.

- Availability of the downstream e invoicing or validation service required for production processing.

### Risks

- **Unclear ERP field semantics:** Differences between the customer's actual ERP payload and the supplied sample could result in mapping or validation gaps.

- **Duplicate submissions:** If the ERP does not provide a stable idempotency key or reuse it during retries, a timeout could result in the same invoice being submitted more than once.

- **Credit note dependencies:** Credit notes may reference invoices that were issued outside the integration, so the expected handling of such references needs to be confirmed.

- **TRN validation:** The assessment defines a 15 digit format for the seller TRN but does not define registry level validation. Whether external validation is required should be confirmed before go live.

- **Unexpected invoice volume:** Higher than expected submission volumes or batch bursts may require queue based processing, rate limiting, and additional capacity.

- **Mapping changes:** Changes to ERP fields or the normalized schema after UAT could create inconsistencies unless mapping versions and change approval are defined.

- **Status and reconciliation:** If the customer does not regularly retrieve processing status or reconcile accepted and rejected documents, failed submissions may not be identified promptly.


## 3. System-flow diagram

See [`system-flow.md`](./system-flow.md).


## 4. API vs. file-based vs. manual-upload: operational differences

| | **API (this prototype)** | **File-based (SFTP/batch)** | **Manual upload (portal)** |
|---|---|---|---|
| **Trigger** | ERP calls `POST /api/v1/invoices` for each invoice and receives an immediate acknowledgment. | ERP exports a file or batch of files that are picked up on a schedule or through an event trigger. | A user logs in and selects a file or enters invoice data manually. |
| **Acknowledgment** | Immediate `202` response with a `documentId`, while processing continues asynchronously. | Delayed until the file is detected and processed. | The upload can be acknowledged immediately, but processing depends on user action. |
| **Idempotency** | Uses an `Idempotency-Key` per request, with a documented fallback when the header is not provided. | Requires file or invoice level duplicate detection, such as a filename, checksum, or invoice ID. | Requires duplicate detection while also allowing intentional resubmission of corrected files. |
| **Validation feedback** | Immediate, structured, field level validation errors that the ERP can process programmatically. | Usually delayed and returned through a batch result or error report. | Errors need to be presented through a user friendly interface. |
| **Partial failures** | Each invoice is processed independently, so one failed invoice does not block other submissions. | Requires an explicit model for identifying successful and failed records within a batch. | Depends on whether the portal supports multiple invoices per upload. |
| **Authentication** | API credentials such as an API key are supplied with each request. | Typically uses SFTP credentials or a service account. | Uses user authentication and should maintain an audit trail of uploads. |
| **Monitoring** | Monitor requests, responses, processing status, errors, and correlation IDs. | Monitor file arrival, pickup, processing, and failures as separate stages. | Monitor upload activity, processing status, and user reported failures. |