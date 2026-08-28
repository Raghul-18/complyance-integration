"""
Standalone auth debug script -- no pytest, no Postman.

Usage:
    python test_auth.py
    python test_auth.py --api-key "some-other-key"
    python test_auth.py --base-url http://localhost:8000

What it does:
    1. Hits /health (no auth needed) to confirm the server is even reachable.
    2. Hits /api/v1/invoices with NO key -> expect 401.
    3. Hits /api/v1/invoices with a WRONG key -> expect 401.
    4. Hits /api/v1/invoices with the key you provide (or TRAINING_API_KEY
       from the environment / a local .env file) -> expect 202.
    5. Prints the exact key being sent (length + repr) so you can catch
       stray whitespace, quotes, or the wrong variable name.
"""
import argparse
import json
import os
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()  # picks up TRAINING_API_KEY from a local .env, if present
except ImportError:
    pass

VALID_PAYLOAD = {
    "sourceName": "desert-star-erp",
    "sourceVersion": "1.0",
    "invoice": {
        "invoiceNo": "INV-DEBUG-0001",
        "issueDate": "2025-02-15",
        "documentType": "INVOICE",
        "currency": "AED",
        "seller": {
            "legalName": "Desert Star Trading LLC",
            "trn": "100000000000003",
            "addressLine1": "100 Training Street",
            "city": "Dubai",
            "emirate": "Dubai",
            "country": "AE",
        },
        "buyer": {
            "legalName": "Oasis Retail LLC",
            "trn": "200000000000005",
            "addressLine1": "200 Example Road",
            "city": "Abu Dhabi",
            "emirate": "Abu Dhabi",
            "country": "AE",
        },
        "lines": [
            {
                "lineId": "1",
                "sku": "CONSULT-001",
                "description": "Implementation consulting",
                "quantity": 2,
                "unitPrice": 1000.0,
                "taxCategory": "STANDARD",
                "taxRate": 5,
            }
        ],
        "totals": {
            "netAmount": 2000.0,
            "taxAmount": 100.0,
            "grossAmount": 2100.0,
            "prepaidAmount": 0.0,
            "amountDue": 2100.0,
        },
        "payment": {"method": "BANK_TRANSFER", "terms": "Pay within 30 days"},
        "originalInvoiceNo": None,
    },
}


def pretty(resp):
    try:
        return json.dumps(resp.json(), indent=2)
    except ValueError:
        return resp.text


def check(label, resp, expected_status):
    ok = resp.status_code == expected_status
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {label}: expected {expected_status}, got {resp.status_code}")
    print(pretty(resp))
    print("-" * 70)
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("TRAINING_API_KEY"),
        help="Defaults to $TRAINING_API_KEY (or .env, if python-dotenv is installed)",
    )
    args = parser.parse_args()

    print(f"Target server: {args.base_url}")
    print(f"TRAINING_API_KEY as seen by this script: repr={args.api_key!r} len={len(args.api_key) if args.api_key else 0}")
    print("=" * 70)

    all_ok = True

    # 1. Health check -- no auth required
    r = requests.get(f"{args.base_url}/health")
    all_ok &= check("Health check", r, 200)

    # 2. No key at all -> should be 401
    r = requests.post(f"{args.base_url}/api/v1/invoices", json=VALID_PAYLOAD)
    all_ok &= check("No API key", r, 401)

    # 3. Wrong key -> should be 401
    r = requests.post(
        f"{args.base_url}/api/v1/invoices",
        json=VALID_PAYLOAD,
        headers={"X-API-Key": "definitely-not-the-right-key"},
    )
    all_ok &= check("Wrong API key", r, 401)

    # 4. Your key -> should be 202 (or 400 if the payload itself is stale,
    #    which still proves auth passed)
    if not args.api_key:
        print("[FAIL] No API key provided -- pass --api-key or set TRAINING_API_KEY")
        sys.exit(1)

    r = requests.post(
        f"{args.base_url}/api/v1/invoices",
        json=VALID_PAYLOAD,
        headers={
            "X-API-Key": args.api_key,
            "Idempotency-Key": "debug-script-1",
        },
    )
    if r.status_code == 401:
        print("[FAIL] Your API key was rejected -- it does not match the server's TRAINING_API_KEY.")
        all_ok = False
    elif r.status_code in (202, 200, 400):
        print(f"[PASS] Your API key was accepted (auth passed, got {r.status_code} from validation/idempotency layer).")
    else:
        print(f"[?] Unexpected status {r.status_code} -- see body below.")
        all_ok = False
    print(pretty(r))
    print("=" * 70)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()