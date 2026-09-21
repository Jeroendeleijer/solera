"""Pull invoice fields out of an attachment.

Works on the PDF text layer. A scanned invoice with no text layer yields
nothing — that is reported rather than guessed at, and OCR is a later step.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .model import Document
from .statements import IBAN_RE, _iban as _verified_iban, parse_amount

# Totals are labelled differently per country and per template.
TOTAL_LABELS = [
    r'total\s*(?:amount)?\s*(?:due|to\s*pay)?', r'grand\s*total', r'amount\s*due',
    r'totaal(?:bedrag)?', r'te\s*betalen', r'totaal\s*incl', r'incl\.?\s*btw',
    r'total\s*factura', r'importe\s*total', r'a\s*pagar', r'gesamtbetrag',
]

# \b stops 'Subtotaal' matching the 'totaal' label. The filler lets a
# currency word or punctuation sit between label and figure, as in
# 'Totaal incl. btw: EUR 121,00'.
TOTAL_RE = re.compile(
    r'\b(?:' + '|'.join(TOTAL_LABELS) + r')\b[^\d\n]{0,25}?([\d][\d.,\s]{1,18}\d)', re.I)

INVOICE_LABELS = r'(?:invoice|factuur|factura|rechnung|inv)\s*(?:no\.?|nr\.?|number|nummer|n[ºo]\.?|#)?'
INVOICE_RE = re.compile(INVOICE_LABELS + r'\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/\.]{2,24})', re.I)

DATE_PATTERNS = [
    (re.compile(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b'), ('d', 'm', 'Y')),
    (re.compile(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b'), ('Y', 'm', 'd')),
]


def pdf_text(path: str | Path, max_pages: int = 4) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ''
    try:
        r = PdfReader(str(path))
        return '\n'.join((p.extract_text() or '') for p in r.pages[:max_pages])
    except Exception:
        return ''


def find_total(text: str) -> Optional[Decimal]:
    """Largest labelled total wins — templates repeat subtotals above the total."""
    best = None
    for m in TOTAL_RE.finditer(text):
        try:
            v = abs(parse_amount(m.group(1)))
        except Exception:
            continue
        if v > 0 and (best is None or v > best):
            best = v
    return best


def find_invoice_number(text: str) -> str:
    for m in INVOICE_RE.finditer(text):
        cand = m.group(1).strip(' .-/')
        if any(c.isdigit() for c in cand) and len(cand) >= 3:
            return cand
    return ''


def find_date(text: str) -> Optional[date]:
    for rx, order in DATE_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        parts = dict(zip(order, m.groups()))
        try:
            return date(int(parts['Y']), int(parts['m']), int(parts['d']))
        except ValueError:
            continue
    return None


def find_iban(text: str) -> str:
    return _verified_iban(text)


def build_document(path: str | Path, *, email_subject: str = '', email_from: str = '',
                   email_date: Optional[date] = None, supplier_hint: str = '') -> Document:
    p = Path(path)
    text = pdf_text(p) if p.suffix.lower() == '.pdf' else ''
    # the filename and subject often carry the invoice number when the PDF is a scan
    combined = '\n'.join([text, p.stem.replace('_', ' ').replace('-', ' '), email_subject])
    supplier = supplier_hint or (email_from.split('@')[-1].split('.')[0] if '@' in email_from else email_from)
    return Document(
        path=str(p), filename=p.name,
        supplier=supplier,
        invoice_number=find_invoice_number(combined),
        total=find_total(text) if text else None,
        doc_date=find_date(text) if text else None,
        iban=find_iban(text),
        email_subject=email_subject, email_from=email_from, email_date=email_date,
        text_len=len(text),
    )
