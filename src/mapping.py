"""
Data transformation: source (desert-star-erp) payload -> normalized invoice structure.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

def _party(party: Optional[Dict[str, Any]], include_trn: bool) -> Dict[str, Any]:
    party = party or {}
    out = {
        "legalName": party.get("legalName"),
        "address": {
            "line1": party.get("addressLine1"),
            "city": party.get("city"),
            "emirate": party.get("emirate"),
            "country": party.get("country"),
        },
    }
    if include_trn:
        out["trn"] = party.get("trn")
    return out


def map_to_normalized(source_payload: Dict[str, Any]) -> Dict[str, Any]:
    invoice = source_payload.get("invoice", {}) or {}
    lines = invoice.get("lines", []) or []
    totals = invoice.get("totals", {}) or {}
    payment = invoice.get("payment", {}) or {}

    normalized_lines = []
    for line in lines:
        normalized_lines.append(
            {
                "lineId": line.get("lineId"),
                "sku": line.get("sku"),  
                "description": line.get("description"),
                "quantity": line.get("quantity"),
                "unitPrice": line.get("unitPrice"),
                "taxCategory": line.get("taxCategory"),
                "taxRate": line.get("taxRate"),
            }
        )

    return {
        "source": {
            "name": source_payload.get("sourceName"),
            "version": source_payload.get("sourceVersion"),
        },
        "invoiceNo": invoice.get("invoiceNo"),
        "issueDate": invoice.get("issueDate"),
        "documentType": invoice.get("documentType"),
        "currency": invoice.get("currency"),
        "seller": _party(invoice.get("seller"), include_trn=True),
        "buyer": _party(invoice.get("buyer"), include_trn=False),
        "lines": normalized_lines,
        "totals": {
            "netAmount": totals.get("netAmount"),
            "taxAmount": totals.get("taxAmount"),
            "grossAmount": totals.get("grossAmount"),
            "prepaidAmount": totals.get("prepaidAmount", 0),
            "amountDue": totals.get("amountDue"),
        },
        "payment": {
            "method": payment.get("method"),
            "terms": payment.get("terms"),
        },
        "originalInvoiceNo": invoice.get("originalInvoiceNo"),
    }
