# Complyance E-Invoicing Integration Prototype

Submission for the Associate Integration Engineer take-home: a small
FastAPI service that accepts a synthetic `desert-star-erp` invoice, validates
and maps it to a normalized structure, prevents duplicate processing, and
exposes an async status endpoint — plus the accompanying discovery,
mapping, testing, defect-investigation, and handover documentation.
Scenario and rules are fictional/synthetic per the assignment brief.

## Tasks

| Task | Deliverable |
|---|---|
| A — Technical discovery and integration design | [`docs/discovery-and-design.md`](docs/discovery-and-design.md), [`docs/system-flow.md`](docs/system-flow.md) |
| B — Integration prototype | [`src/`](src/) — see "Setup" and "Running the service" below |
| C — ERP-to-normalized mapping | [`docs/mapping.md`](docs/mapping.md), [`samples/normalized-invoice.json`](samples/normalized-invoice.json) |
| D — Testing | [`tests/`](tests/), [`postman/`](postman/) — see "Running the tests" below |
| E — Defect investigation | [`docs/defect-investigation.md`](docs/defect-investigation.md) |
| F — Delivery readiness and handover | [`docs/readiness-and-handover.md`](docs/readiness-and-handover.md) |

## Requirements

- Python 3.10+ (developed and tested on 3.12.3)
- pip

## Setup

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Windows (Command Prompt):**

```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
```

**Windows (PowerShell):**

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

> PowerShell may block the activation script the first time, with an
> error about execution policies. If so, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that
> same PowerShell window and try activating again.

Edit `.env` and set `TRAINING_API_KEY` to any value you like — this is a
local training key, not a real credential. Never commit `.env` itself
(already covered by `.gitignore`).

Environment variables (see `.env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `TRAINING_API_KEY` | Required. Value the `X-API-Key` header must match. | *(none — must be set)* |
| `DB_PATH` | SQLite file path. | `invoices.db` |
| `PROCESSING_DELAY_SECONDS` | Simulated async processing delay. | `2` |
| `MAX_CONTENT_LENGTH_BYTES` | Request body size limit. | `1048576` (1 MB) |
| `SUPPORTED_SOURCE_VERSIONS` | Comma-separated accepted `sourceVersion` values. | `1.0` |

## Running the service

```bash
uvicorn src.main:app --reload
```

Runs on `http://127.0.0.1:8000`. `/health` and interactive docs at
`/docs` need no auth; everything under `/api/v1` requires the
`X-API-Key` header.

### Example requests

Submit an invoice (replace `<your-api-key>` with the value you set for
`TRAINING_API_KEY` in `.env`):

**macOS / Linux (curl):**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/invoices" \
  -H "X-API-Key: <your-api-key>" \
  -H "Idempotency-Key: demo-001" \
  -H "Content-Type: application/json" \
  -d @samples/valid-invoice.json
```

**Windows (Command Prompt, curl.exe — bundled with Windows 10+):**

```cmd
curl.exe -X POST "http://127.0.0.1:8000/api/v1/invoices" -H "X-API-Key: <your-api-key>" -H "Idempotency-Key: demo-001" -H "Content-Type: application/json" -d "@samples/valid-invoice.json"
```

**Windows (PowerShell):**

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/invoices" -H "X-API-Key: <your-api-key>" -H "Idempotency-Key: demo-001" -H "Content-Type: application/json" -d "@samples/valid-invoice.json"
```

> On PowerShell, `curl` is often aliased to `Invoke-WebRequest`, which
> doesn't take the same flags. Calling `curl.exe` explicitly (as above)
> bypasses the alias and uses the real curl binary instead.

Check status (use the `documentId` from the response above):

**macOS / Linux:**

```bash
curl "http://127.0.0.1:8000/api/v1/documents/<documentId>/status" \
  -H "X-API-Key: <your-api-key>"
```

**Windows (Command Prompt or PowerShell):**

```cmd
curl.exe "http://127.0.0.1:8000/api/v1/documents/<documentId>/status" -H "X-API-Key: <your-api-key>"
```

This is a **local prototype only** — it never calls any Complyance,
customer, sandbox, or production system.

## Running the tests

```bash
pytest tests/ -v
```

Tests spin up an isolated `TestClient` per test with a temporary SQLite
file (see `tests/conftest.py`), so they don't touch your local `invoices.db`
or require the server to be running separately.

### Running the Postman collection

The `postman/` directory has an alternative black-box test suite that
hits the running service over HTTP instead of using `TestClient` directly.

**Import into Postman (GUI):**

1. Start the service first — the collection makes real HTTP calls to it:
   `uvicorn src.main:app --reload`
2. In Postman, click **Import** and select both:
   - `postman/collection.json`
   - `postman/local-environment.json`
3. In the top-right environment selector, choose the imported
   **local** environment.
4. Open the environment's variables and set `apiKey` (and `baseUrl` if
   it isn't already `http://127.0.0.1:8000`) to match your `.env`'s
   `TRAINING_API_KEY`.
5. Run individual requests, or click the collection's **⋯** menu →
   **Run collection** to execute the whole suite through the Collection
   Runner.

**Run from the command line (newman):**

```bash
npm install -g newman
uvicorn src.main:app --reload &          # start the service in the background
newman run postman/collection.json -e postman/local-environment.json
```

### Test-results summary

**Pytest (`tests/`): 16 of 16 passed**, covering all 10 required Task D
scenarios plus 6 additional ones (unsupported schema version, invalid
calendar date, oversized payload, correlation-ID echo, audit log, health
check). Full scenario-by-scenario expected/actual results are in
[`tests/Test-results.md`](tests/Test-results.md).

Scenarios described but intentionally not implemented (zero-rated/exempt/
out-of-scope mix, multi-currency, bulk submission, transient downstream
failure, partial batch failure, high-volume/performance, file-based/
manual-upload validation) are documented in the same file, per the
assignment's "describe but do not necessarily implement" allowance.

## Repository structure

```
README.md
requirements.txt
.env.example
.gitignore
src/                        # FastAPI app (auth, config, logging, mapping,
                             # persistence, validation, main)
tests/                       # pytest suite (conftest.py, testapi.py,
                             # test_scenarios.py, test_additional_scenarios.py,
                             # Test-results.md)
samples/
  valid-invoice.json
  normalized-invoice.json    # Task C: example mapping output
  invalid-invoices/          # fixtures for the negative test scenarios
docs/
  discovery-and-design.md    # Task A: discovery questions, assumptions,
                             # dependencies, risks, API/file/manual comparison
  system-flow.md             # Task A: system-flow + component diagrams
  mapping.md                 # Task C: ERP-to-normalized field mapping
  defect-investigation.md    # Task E: defect-investigation note
  readiness-and-handover.md  # Task F: UAT/go-live/hypercare checklist
postman/
  collection.json
  local-environment.json
```

## Assumptions and known limitations

*These are implementation-level assumptions and limitations from building
the prototype. For discovery-phase assumptions, dependencies, and risks
about the customer's ERP and process, see
[`docs/discovery-and-design.md` §2](docs/discovery-and-design.md#2-key-assumptions-dependencies-and-risks).*

- Single-tenant prototype: `invoice_no` uniqueness is enforced globally,
  not per `sourceName`. A multi-ERP deployment would likely need a
  composite `(source_name, invoice_no)` constraint instead.
- Only `AED` is accepted as `currency`; anything else returns
  `UNSUPPORTED_CURRENCY`. See `docs/discovery-and-design.md` for how
  multi-currency support would be added.
- `amountDue` is assumed to equal `grossAmount − prepaidAmount`, since the
  assessment rules require the field but don't define its formula.
- The async processing step is a fixed-delay deterministic rule (gross
  amount over a threshold → `REJECTED`, otherwise `ACCEPTED`), not a real
  downstream integration.
- Persistence is a single local SQLite file with a global write lock —
  fine for this exercise, but not something to scale under concurrent
  load as-is.
- `/api/v1/audit` sits behind the same API key as the submit/status
  endpoints; a real deployment would likely put it behind a separate
  support-only role.

## External resources and tools

- [FastAPI](https://fastapi.tiangolo.com/), [Starlette](https://www.starlette.io/),
  [Uvicorn](https://www.uvicorn.org/), [pytest](https://docs.pytest.org/) —
  see `requirements.txt` for pinned versions.
- Standard library only otherwise (`sqlite3`, `hmac`, `hashlib`, `uuid`,
  `decimal`, `contextvars`).
- No copied third-party code beyond the libraries above.

## AI-use disclosure

Generative AI (Claude) was used during this project as follows:
- Reviewing `docs/system-flow.md` against the actual `src/` implementation
  and identifying and fixing discrepancies between the diagram and the
  code's real behavior.
- Assisting in generating code as per the design and flow.
- Drafting this README and other documents.
- Generating synthetic JSON invoices.
- Verifying logic and test scenario


## Approximate time spent

Approximately 8 hours.

## Candidate declaration

- [x] I used only synthetic data.
- [x] I did not include credentials or confidential third-party information.
- [x] I have listed material external resources, reused code, and tools
      (see "External resources and tools" above).
- [x] I have disclosed any use of generative AI in accordance with the
      assignment email (see "AI-use disclosure" above).
- [x] I can explain the submitted design and code during a follow-up
      discussion.
