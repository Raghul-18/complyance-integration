"""
Validation for the synthetic ERP invoice payload.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Tuple

from src.config import settings

ALLOWED_DOCUMENT_TYPES = {"INVOICE", "CREDIT_NOTE"}
ALLOWED_TAX_CATEGORIES = {"STANDARD", "ZERO_RATED", "EXEMPT", "OUT_OF_SCOPE"}
STANDARD_TAX_RATE = Decimal("5")
NON_STANDARD_TAX_RATE = Decimal("0")
TRN_RE = re.compile(r"^\d{15}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationIssue:
    __slots__ = ("field", "code", "message")

    def __init__(self, field: str, code: str, message: str):
        self.field = field
        self.code = code
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _is_valid_calendar_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# Pluggable currency rules.
CURRENCY_VALIDATORS = {
    "AED": lambda _payload: None,  
}


def validate_structure(body: Any) -> List[ValidationIssue]:
    """Checking payload structure"""
    issues: List[ValidationIssue] = []
    if not isinstance(body, dict):
        issues.append(ValidationIssue("$", "INVALID_BODY", "Request body must be a JSON object."))
        return issues
    for key in ("sourceName", "sourceVersion", "invoice"):
        if key not in body:
            issues.append(ValidationIssue(key, "MISSING_FIELD", f"'{key}' is required."))
    if "invoice" in body and not isinstance(body["invoice"], dict):
        issues.append(ValidationIssue("invoice", "INVALID_TYPE", "'invoice' must be an object."))
    return issues


def _validate_party(party: Any, path: str, require_trn: bool) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not isinstance(party, dict):
        issues.append(ValidationIssue(path, "MISSING_FIELD", f"'{path}' is required."))
        return issues

    legal_name = party.get("legalName")
    if not isinstance(legal_name, str) or not legal_name.strip():
        issues.append(ValidationIssue(f"{path}.legalName", "REQUIRED", "legalName must not be empty."))

    if require_trn:
        trn = party.get("trn")
        if not isinstance(trn, str) or not TRN_RE.match(trn):
            issues.append(
                ValidationIssue(
                    f"{path}.trn", "INVALID_FORMAT", "TRN must be exactly 15 numeric digits."
                )
            )

    addr = party.get("addressLine1")
    if not isinstance(addr, str) or not addr.strip():
        issues.append(ValidationIssue(f"{path}.addressLine1", "REQUIRED", "addressLine1 must not be empty."))

    country = party.get("country")
    if not isinstance(country, str) or not COUNTRY_RE.match(country):
        issues.append(
            ValidationIssue(f"{path}.country", "INVALID_FORMAT", "country must be a 2-letter uppercase code.")
        )

    return issues


def _validate_lines(lines: Any) -> Tuple[List[ValidationIssue], List[Dict[str, Decimal]]]:
    """Returns (issues, computed_lines) where computed_lines carries the per-line Decimal net/tax"""
    issues: List[ValidationIssue] = []
    computed: List[Dict[str, Decimal]] = []

    if not isinstance(lines, list) or len(lines) == 0:
        issues.append(ValidationIssue("invoice.lines", "REQUIRED", "At least one invoice line is required."))
        return issues, computed

    for idx, line in enumerate(lines):
        path = f"invoice.lines[{idx}]"
        if not isinstance(line, dict):
            issues.append(ValidationIssue(path, "INVALID_TYPE", "Each line must be an object."))
            continue

        line_id = line.get("lineId")
        if line_id is None or str(line_id).strip() == "":
            issues.append(ValidationIssue(f"{path}.lineId", "REQUIRED", "lineId must not be empty."))

        description = line.get("description")
        if not isinstance(description, str) or not description.strip():
            issues.append(ValidationIssue(f"{path}.description", "REQUIRED", "description must not be empty."))

        quantity = _to_decimal(line.get("quantity"))
        if quantity is None or quantity <= 0:
            issues.append(ValidationIssue(f"{path}.quantity", "INVALID_VALUE", "quantity must be greater than zero."))

        unit_price = _to_decimal(line.get("unitPrice"))
        if unit_price is None or unit_price < 0:
            issues.append(ValidationIssue(f"{path}.unitPrice", "INVALID_VALUE", "unitPrice must not be negative."))

        category = line.get("taxCategory")
        if category not in ALLOWED_TAX_CATEGORIES:
            issues.append(
                ValidationIssue(
                    f"{path}.taxCategory",
                    "INVALID_VALUE",
                    f"taxCategory must be one of {sorted(ALLOWED_TAX_CATEGORIES)}.",
                )
            )
            expected_rate = None
        else:
            expected_rate = STANDARD_TAX_RATE if category == "STANDARD" else NON_STANDARD_TAX_RATE

        submitted_rate = _to_decimal(line.get("taxRate"))
        if expected_rate is not None and submitted_rate is not None and submitted_rate != expected_rate:
            issues.append(
                ValidationIssue(
                    f"{path}.taxRate",
                    "TAX_RATE_MISMATCH",
                    f"taxRate for {category} must be {expected_rate}, got {submitted_rate}.",
                )
            )

        if quantity is not None and unit_price is not None and expected_rate is not None:
            line_net = _round2(quantity * unit_price)
            line_tax = _round2(line_net * expected_rate / Decimal("100"))
            computed.append({"net": line_net, "tax": line_tax})

    return issues, computed


def validate_invoice(body: Dict[str, Any]) -> List[ValidationIssue]:
    """Full field-level and cross-field validation"""
    issues: List[ValidationIssue] = list(validate_structure(body))
    if issues:
        return issues  
    source_version = body.get("sourceVersion")
    if source_version not in settings.supported_source_versions:
        issues.append(
            ValidationIssue(
                "sourceVersion",
                "UNSUPPORTED_SCHEMA_VERSION",
                f"sourceVersion {source_version!r} is not supported. "
                f"Supported: {sorted(settings.supported_source_versions)}.",
            )
        )

    invoice = body["invoice"]

    invoice_no = invoice.get("invoiceNo")
    if not isinstance(invoice_no, str) or not invoice_no.strip():
        issues.append(ValidationIssue("invoice.invoiceNo", "REQUIRED", "invoiceNo must not be empty."))

    issue_date = invoice.get("issueDate")
    if not isinstance(issue_date, str) or not _is_valid_calendar_date(issue_date):
        issues.append(
            ValidationIssue(
                "invoice.issueDate", "INVALID_FORMAT", "issueDate must be a real calendar date in YYYY-MM-DD format."
            )
        )

    doc_type = invoice.get("documentType")
    if doc_type not in ALLOWED_DOCUMENT_TYPES:
        issues.append(
            ValidationIssue(
                "invoice.documentType", "INVALID_VALUE", f"documentType must be one of {sorted(ALLOWED_DOCUMENT_TYPES)}."
            )
        )

    currency = invoice.get("currency")
    if currency not in CURRENCY_VALIDATORS:
        issues.append(
            ValidationIssue(
                "invoice.currency", "UNSUPPORTED_CURRENCY", f"currency must be one of {sorted(CURRENCY_VALIDATORS)}."
            )
        )
    else:
        CURRENCY_VALIDATORS[currency](invoice)

    issues.extend(_validate_party(invoice.get("seller"), "invoice.seller", require_trn=True))
    issues.extend(_validate_party(invoice.get("buyer"), "invoice.buyer", require_trn=False))

    if doc_type == "CREDIT_NOTE":
        original_no = invoice.get("originalInvoiceNo")
        if not isinstance(original_no, str) or not original_no.strip():
            issues.append(
                ValidationIssue(
                    "invoice.originalInvoiceNo",
                    "REQUIRED",
                    "originalInvoiceNo is required for a CREDIT_NOTE.",
                )
            )

    line_issues, computed_lines = _validate_lines(invoice.get("lines"))
    issues.extend(line_issues)

    lines_raw = invoice.get("lines")
    if not line_issues and isinstance(lines_raw, list) and len(computed_lines) == len(lines_raw):
        computed_net = sum((l["net"] for l in computed_lines), Decimal("0"))
        computed_tax = sum((l["tax"] for l in computed_lines), Decimal("0"))
        computed_gross = computed_net + computed_tax

        totals = invoice.get("totals")
        if not isinstance(totals, dict):
            issues.append(ValidationIssue("invoice.totals", "REQUIRED", "totals is required."))
        else:
            submitted_net = _to_decimal(totals.get("netAmount"))
            submitted_tax = _to_decimal(totals.get("taxAmount"))
            submitted_gross = _to_decimal(totals.get("grossAmount"))

            if submitted_net is None or _round2(submitted_net) != computed_net:
                issues.append(
                    ValidationIssue(
                        "invoice.totals.netAmount",
                        "MISMATCH",
                        f"Expected {computed_net}, got {totals.get('netAmount')}.",
                    )
                )
            if submitted_tax is None or _round2(submitted_tax) != computed_tax:
                issues.append(
                    ValidationIssue(
                        "invoice.totals.taxAmount",
                        "MISMATCH",
                        f"Expected {computed_tax}, got {totals.get('taxAmount')}.",
                    )
                )
            if submitted_gross is None or _round2(submitted_gross) != computed_gross:
                issues.append(
                    ValidationIssue(
                        "invoice.totals.grossAmount",
                        "MISMATCH",
                        f"Expected {computed_gross}, got {totals.get('grossAmount')}.",
                    )
                )

    return issues
