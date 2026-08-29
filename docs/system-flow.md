# System Flow

This reflects what `src/main.py` actually does, not an idealized future architecture.
```mermaid
flowchart TD
    A["Customer ERP<br/>Desert Star Trading LLC"] -->|"POST /api/v1/invoices<br/>+ API Key + Idempotency-Key"| B["Integration Service"]

    B --> C{"Authentication<br/>& Correlation ID"}
    C -->|Invalid| E["Structured Error Response<br/>401 / 403"]
    C -->|Valid| D["Validation & Mapping"]

    D -->|Invalid| F["Structured Validation Error<br/>400 + field paths"]
    D -->|Valid| G["Idempotency Check"]

    G -->|Duplicate| H["Return existing documentId<br/>202"]
    G -->|New| I["Generate documentId<br/>Persist record"]

    I --> J[("Document Storage<br/>SQLite / DB")]
    I --> K["Return 202 Accepted<br/>status=PROCESSING"]

    J --> L["Async Processing<br/>Timer / Rule / Manual"]
    L -->|Success| M["Status = ACCEPTED"]
    L -->|Failure| N["Status = REJECTED<br/>+ errors"]

    O["GET /api/v1/documents/{id}/status"] --> B
    B --> J
    J --> P["Status Response"]

    Q["Monitoring & Support<br/>Logs, Alerts, Correlation ID"] -.-> B
    Q -.-> J
    Q -.-> L
```

## Component view

```mermaid
flowchart LR
    subgraph Customer["Customer ERP"]
        ERP[desert-star-erp]
    end

    subgraph Service["Integration service (FastAPI)"]
        direction TB
        MW["Middleware:<br/>size limit + correlation ID"]
        Auth["Auth<br/>(X-API-Key, constant-time)"]
        VM["Validation & Mapping<br/>(validation.py → mapping.py)"]
        BG["Async processing<br/>(background thread,<br/>deterministic decision)"]
        MW --> Auth --> VM
        VM --> BG
    end

    subgraph Storage["Document storage (SQLite)"]
        Docs[("documents<br/>UNIQUE(idempotency_key)")]
        Audit[("audit_log<br/>append-only")]
    end

    subgraph Ops["Monitoring & support"]
        Logs["Structured JSON logs<br/>(stdout, correlation-id tagged,<br/>field-redacted)"]
        AuditAPI["GET /api/v1/audit<br/>support/debug endpoint"]
        Health["GET /health"]
    end

    ERP -->|"POST /api/v1/invoices"| MW
    VM --> Docs
    BG --> Docs
    VM -.write.-> Audit
    BG -.write.-> Audit
    ERP -->|"GET /status"| Auth
    Auth --> Docs
    Docs --> AuditAPI
    Audit --> AuditAPI
    Service -.-> Logs
```