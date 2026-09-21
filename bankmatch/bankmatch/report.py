"""The hand-off to the accountant.

One workbook with four sheets, plus a folder of the attachments renamed so the
filename alone says what the document is. The workbook references those names,
so the accountant can open a row and find the paper behind it.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable

from .model import Confidence, Match, Document

SAFE = re.compile(r'[^A-Za-z0-9._-]+')

HEADERS = ['Date', 'Amount', 'Direction', 'Counterparty', 'Description',
           'Document', 'Supplier', 'Invoice no.', 'Doc total', 'Doc date',
           'Score', 'Why']


def _row(m: Match) -> list:
    t, d = m.transaction, m.document
    return [t.date.isoformat(), float(t.amount), t.direction.value, t.counterparty,
            t.description[:180],
            d.filename if d else '', d.supplier if d else '',
            d.invoice_number if d else '',
            float(d.total) if d and d.total is not None else '',
            d.best_date.isoformat() if d and d.best_date else '',
            m.score, ' '.join(m.reasons)[:400]]


def rename_for_accountant(doc: Document, dest_dir: Path) -> str:
    """YYYY-MM-DD__supplier__EUR-123.45__INV-42.pdf — sorts and reads correctly."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    bits = [doc.best_date.isoformat() if doc.best_date else 'nodate',
            SAFE.sub('-', doc.supplier or 'unknown')[:28].strip('-') or 'unknown',
            f"EUR-{doc.total}" if doc.total is not None else 'EUR-unknown',
            SAFE.sub('-', doc.invoice_number)[:20] if doc.invoice_number else 'noref']
    name = '__'.join(bits) + Path(doc.filename).suffix.lower()
    target = dest_dir / name
    n = 2
    while target.exists():
        target = dest_dir / (name.rsplit('.', 1)[0] + f'_{n}.' + name.rsplit('.', 1)[1])
        n += 1
    try:
        shutil.copy2(doc.path, target)
    except Exception:
        return ''
    return target.name


def write_report(path: str | Path, matches: list[Match], leftover_docs: list[Document],
                 skipped_rows: list | None = None, copy_docs_to: str | Path | None = None) -> dict:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
    except ImportError:
        raise RuntimeError("Writing the report needs openpyxl — pip install -r requirements.txt")

    dest = Path(copy_docs_to) if copy_docs_to else None
    renamed = {}
    if dest:
        for m in matches:
            if m.document:
                renamed[id(m.document)] = rename_for_accountant(m.document, dest)
        for d in leftover_docs:
            renamed[id(d)] = rename_for_accountant(d, dest)

    wb = Workbook(); wb.remove(wb.active)
    buckets = {
        'Matched':   [m for m in matches if m.confidence is Confidence.MATCHED],
        'Review':    [m for m in matches if m.confidence is Confidence.REVIEW],
        'No document': [m for m in matches if m.confidence is Confidence.NONE],
    }
    for title, rows in buckets.items():
        ws = wb.create_sheet(title)
        ws.append(HEADERS)
        for c in ws[1]:
            c.font = Font(bold=True)
        for m in rows:
            r = _row(m)
            if dest and m.document:
                r[5] = renamed.get(id(m.document), r[5])
            ws.append(r)
        ws.freeze_panes = 'A2'
        for col, w in zip('ABCDEFGHIJKL', (11, 11, 10, 28, 46, 40, 20, 16, 11, 11, 8, 60)):
            ws.column_dimensions[col].width = w

    ws = wb.create_sheet('Documents without a payment')
    ws.append(['Document', 'Supplier', 'Invoice no.', 'Total', 'Doc date', 'Email subject', 'Readable'])
    for c in ws[1]:
        c.font = Font(bold=True)
    for d in leftover_docs:
        ws.append([renamed.get(id(d), d.filename), d.supplier, d.invoice_number,
                   float(d.total) if d.total is not None else '',
                   d.best_date.isoformat() if d.best_date else '',
                   d.email_subject[:120], 'yes' if d.text_len > 40 else 'no text layer'])
    ws.freeze_panes = 'A2'

    if skipped_rows:
        ws = wb.create_sheet('Rows not read')
        ws.append(['Statement row', 'Reason', 'Content'])
        for c in ws[1]:
            c.font = Font(bold=True)
        for row in skipped_rows:
            ws.append(list(row))

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return {k: len(v) for k, v in buckets.items()} | {'Documents without a payment': len(leftover_docs)}
