# Task C: ERP to Normalized Mapping

This document defines how fields from the `desert-star-erp` payload are mapped to the normalized invoice structure.

> **Verification note:** every row below was cross-checked against the actual `validate_invoice` logic in `src/validation.py`, not just against the assessment's plain-language rules. Two rows (seller/buyer `city`, and buyer `emirate`) originally stated a validation the code doesn't actually enforce; those rows have been corrected to reflect current behavior and flagged as open questions rather than left silently wrong.

## 1. Source name and source version

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `sourceName` | `source.name` | Required | Passed through as-is | Must be present | Should source names be restricted to approved values? |
| `sourceVersion` | `source.version` | Required | Passed through as-is | Must be a supported version | How should future ERP schema versions be handled? |

## 2. Core invoice information

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.invoiceNo` | `invoiceNo` | Required | Passed through as-is | Must not be empty | Should invoice numbers be unique across all ERP instances? |
| `invoice.issueDate` | `issueDate` | Required | Passed through as-is | Must be a valid `YYYY-MM-DD` date | Should future issue dates be allowed? |
| `invoice.documentType` | `documentType` | Required | Passed through as-is | Must be `INVOICE` or `CREDIT_NOTE` | Are other document types required? |
| `invoice.currency` | `currency` | Required | Passed through as-is | Currently only `AED` is supported | Which currencies should be supported later? |

## 3. Seller information

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.seller.legalName` | `seller.legalName` | Required | Passed through as-is | Must not be empty | — |
| `invoice.seller.trn` | `seller.trn` | Required | Passed through as-is | Must contain exactly 15 numeric digits | Is registry level TRN validation required? |
| `invoice.seller.addressLine1` | `seller.address.line1` | Required | Passed through as-is | Must not be empty | — |
| `invoice.seller.city` | `seller.address.city` | Optional (per current code) | Passed through as-is | **Not validated** — `validate_invoice` never checks `city` for emptiness | Should city be a required, validated field? (Currently accepted even if blank/missing.) |
| `invoice.seller.emirate` | `seller.address.emirate` | Required | Passed through as-is | Must not be empty | Should emirate be checked against a fixed list? |
| `invoice.seller.country` | `seller.address.country` | Required | Passed through as-is | Must be a two letter uppercase country code | — |

## 4. Buyer information

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.buyer.legalName` | `buyer.legalName` | Required | Passed through as-is | Must not be empty | — |
| `invoice.buyer.trn` | Not mapped | Optional / not required | Not included in normalized output | Not validated | Should buyer TRN be included in the normalized structure? |
| `invoice.buyer.addressLine1` | `buyer.address.line1` | Required | Passed through as-is | Must not be empty | — |
| `invoice.buyer.city` | `buyer.address.city` | Optional (per current code) | Passed through as-is | **Not validated** — same gap as seller city | Should city be a required, validated field? |
| `invoice.buyer.emirate` | `buyer.address.emirate` | Optional (per current code) | Passed through as-is | **Not validated** — `_validate_party` is called for the buyer with `require_emirate` left at its default of `False`, unlike the seller | Is this an intentional asymmetry (only sellers must be in a UAE emirate) or a gap? Should buyer emirate be validated the same way as seller emirate? |
| `invoice.buyer.country` | `buyer.address.country` | Required | Passed through as-is | Must be a two letter uppercase country code | — |

## 5. Lines and tax information

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.lines[]` | `lines[]` | At least one required | Each source line is mapped to one normalized line | Must contain at least one line | — |
| `invoice.lines[].lineId` | `lines[].lineId` | Required | Passed through as-is | Must not be empty | — |
| `invoice.lines[].sku` | `lines[].sku` | Optional | Passed through as-is | No validation | Is SKU required for all lines? |
| `invoice.lines[].description` | `lines[].description` | Required | Passed through as-is | Must not be empty | — |
| `invoice.lines[].quantity` | `lines[].quantity` | Required | Passed through as-is | Must be greater than zero | — |
| `invoice.lines[].unitPrice` | `lines[].unitPrice` | Required | Passed through as-is | Must not be negative | — |
| `invoice.lines[].taxCategory` | `lines[].taxCategory` | Required | Passed through as-is | Must be a supported tax category | Are these the complete set of tax categories? |
| `invoice.lines[].taxRate` | `lines[].taxRate` | Required | Passed through as-is | Must match the expected rate for the tax category | Should tax rates be centrally configured? |

## 6. Totals

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.totals.netAmount` | `totals.netAmount` | Required | Passed through as-is | Compared with calculated line net amount | — |
| `invoice.totals.taxAmount` | `totals.taxAmount` | Required | Passed through as-is | Compared with calculated line tax | — |
| `invoice.totals.grossAmount` | `totals.grossAmount` | Required | Passed through as-is | Must equal calculated net amount + tax | — |
| `invoice.totals.prepaidAmount` | `totals.prepaidAmount` | Optional | Defaults to `0` if missing | Used when checking `amountDue` | Should it be range checked? |
| `invoice.totals.amountDue` | `totals.amountDue` | Required | Passed through as-is | Must equal `grossAmount - prepaidAmount` | Should this remain the final business rule? |

## 7. Payment information

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.payment.method` | `payment.method` | Required | Passed through as-is | Must be a non empty string | Should payment methods be restricted to an approved list? |
| `invoice.payment.terms` | `payment.terms` | Optional | Passed through as-is | No validation | Should payment terms use a fixed format? |

## 8. Credit note reference

| Source field | Target field | Required/conditional | Transformation/default | Validation | Open question |
|---|---|---|---|---|---|
| `invoice.originalInvoiceNo` | `originalInvoiceNo` | Required for `CREDIT_NOTE` | Passed through as-is; `null` for normal invoices | Required and non empty for credit notes | Must the original invoice already exist in the system? |

## 9. Normalized JSON example

```json
{
  "source": {
    "name": "desert-star-erp",
    "version": "1.0"
  },
  "invoiceNo": "INV-2025-1001",
  "issueDate": "2025-02-15",
  "documentType": "INVOICE",
  "currency": "AED",
  "seller": {
    "legalName": "Desert Star Trading LLC",
    "address": {
      "line1": "100 Training Street",
      "city": "Dubai",
      "emirate": "Dubai",
      "country": "AE"
    },
    "trn": "100000000000003"
  },
  "buyer": {
    "legalName": "Oasis Retail LLC",
    "address": {
      "line1": "200 Example Road",
      "city": "Abu Dhabi",
      "emirate": "Abu Dhabi",
      "country": "AE"
    }
  },
  "lines": [
    {
      "lineId": "1",
      "sku": "CONSULT-001",
      "description": "Implementation consulting",
      "quantity": 2,
      "unitPrice": 1000.0,
      "taxCategory": "STANDARD",
      "taxRate": 5
    },
    {
      "lineId": "2",
      "sku": "TRAIN-001",
      "description": "User training",
      "quantity": 1,
      "unitPrice": 500.0,
      "taxCategory": "STANDARD",
      "taxRate": 5
    }
  ],
  "totals": {
    "netAmount": 2500.0,
    "taxAmount": 125.0,
    "grossAmount": 2625.0,
    "prepaidAmount": 0.0,
    "amountDue": 2625.0
  },
  "payment": {
    "method": "BANK_TRANSFER",
    "terms": "Pay within 30 days"
  },
  "originalInvoiceNo": null
}