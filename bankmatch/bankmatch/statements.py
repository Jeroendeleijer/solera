"""Readers for bank exports.

Formats differ per bank and per decade, so the approach is: sniff the header,
pick a column mapping, normalise everything into Transaction. Anything it
cannot map raises rather than guessing — a silently mis-parsed amount is worse
than a refusal.
"""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

from dataclasses import dataclass, field as _field

from .model import Direction, Transaction


@dataclass
class StatementRead:
    """Parsed rows plus the ones that could not be parsed.

    Bank exports carry subtotal and balance lines that are not transactions.
    Those are skipped, but they are reported: a reconciliation tool that
    quietly loses rows is worse than one that refuses to run.
    """
    transactions: list = _field(default_factory=list)
    skipped: list = _field(default_factory=list)   # (row_no, reason, snippet)
    fmt: str = ""

    def __len__(self): return len(self.transactions)
    def __iter__(self): return iter(self.transactions)

# IBANs appear both solid (NL69TEST0000000001) and spaced in groups of four.
IBAN_RE = re.compile(r'\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,30})\b')


class UnknownStatementFormat(ValueError):
    pass


def parse_amount(raw: str) -> Decimal:
    """Handle 1.234,56 (European) and 1,234.56 (Anglo) without guessing wrong.

    The rule: whichever separator appears last is the decimal separator.
    """
    s = str(raw).strip().replace(' ', ' ').replace(' ', '')
    s = re.sub(r'[^\d.,()\u2212\u2013\u2014+-]', '', s)   # drop EUR, €, $, letters
    # real exports use U+2212 minus, en/em dashes, and accounting parentheses
    for ch in ('\u2212', '\u2013', '\u2014'):
        s = s.replace(ch, '-')
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg, s = True, s[1:-1]
    if s.startswith('-') or s.endswith('-'):
        neg = True
    s = s.strip('-')
    if not s:
        # an empty cell is genuinely zero; a non-empty cell that contained no
        # digits ('n/a', 'pending') is not, and must not become 0 silently
        if str(raw).strip():
            raise UnknownStatementFormat(f"Cannot read amount: {raw!r}")
        return Decimal('0')
    last_comma, last_dot = s.rfind(','), s.rfind('.')
    if last_comma > last_dot:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        val = Decimal(s)
    except InvalidOperation:
        raise UnknownStatementFormat(f"Cannot read amount: {raw!r}")
    return -val if neg else val


def parse_date(raw) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    for fmt in ('%Y%m%d', '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%y',
                '%d.%m.%Y', '%b %d, %Y', '%d %b %Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise UnknownStatementFormat(f"Cannot read date: {raw!r}")


def iban_checksum_ok(candidate: str) -> bool:
    """ISO 13616 mod-97 check.

    An IBAN carries its own checksum, so a candidate can be verified rather
    than trusted. This is what stops 'NL69TEST0000000001 TNV' being read as an
    IBAN with TNV glued on the end.
    """
    s = (candidate or '').upper().replace(' ', '')
    if not (15 <= len(s) <= 34) or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    rearranged = s[4:] + s[:4]
    digits = ''
    for ch in rearranged:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch) - 55)
        else:
            return False
    return int(digits) % 97 == 1


def _iban(text: str) -> str:
    """Return the first candidate that actually passes the checksum."""
    up = (text or '').upper()
    for m in IBAN_RE.finditer(up):
        raw = m.group(1).replace(' ', '')
        # the regex is greedy, so walk the tail back to a length that validates
        for end in range(len(raw), 14, -1):
            if iban_checksum_ok(raw[:end]):
                return raw[:end]
    return ''


# --- column mappings -------------------------------------------------------
# Each entry: required header tokens -> field names. Matching is lowercase and
# order-independent so a bank reordering its columns does not break the reader.
MAPPINGS = [
    {   # ING Netherlands
        'name': 'ING (NL)',
        'need': {'datum', 'naam / omschrijving', 'bedrag (eur)', 'af bij'},
        'fields': {'date': 'datum', 'counterparty': 'naam / omschrijving',
                   'amount': 'bedrag (eur)', 'dirflag': 'af bij',
                   'description': 'mededelingen', 'account': 'rekening',
                   'counter_iban': 'tegenrekening'},
        'debit_values': {'af'},
    },
    {   # generic: a single signed amount column
        'name': 'generic signed',
        'need': {'date', 'description'},
        'fields': {'date': 'date', 'counterparty': 'description',
                   'amount': 'amount (eur)', 'description': 'description'},
        'debit_values': set(),
    },
]


def _norm_headers(row: Iterable[str]) -> list[str]:
    return [str(h or '').strip().lstrip('﻿').strip('"').lower() for h in row]


def _pick_mapping(headers: list[str]):
    hs = set(headers)
    for m in MAPPINGS:
        if m['need'] <= hs:
            return m
    # tolerate an amount column under another name
    if 'date' in hs and any(h.startswith('amount') for h in hs):
        m = dict(MAPPINGS[1])
        m['fields'] = dict(m['fields'])
        m['fields']['amount'] = next(h for h in hs if h.startswith('amount'))
        return m
    raise UnknownStatementFormat(
        "Unrecognised statement layout. Columns seen: " + ', '.join(headers))


def _row_to_txn(cells: dict, m: dict, idx: int) -> Optional[Transaction]:
    f = m['fields']
    raw_date = cells.get(f['date'], '')
    if not str(raw_date).strip():
        return None
    amount = parse_amount(cells.get(f.get('amount', ''), '0'))
    dirflag = str(cells.get(f.get('dirflag', ''), '')).strip().lower()
    if dirflag:
        direction = Direction.OUT if dirflag in m['debit_values'] else Direction.IN
    else:
        direction = Direction.OUT if amount < 0 else Direction.IN
    desc = str(cells.get(f.get('description', ''), '') or '')
    counter = str(cells.get(f.get('counterparty', ''), '') or '')
    return Transaction(
        date=parse_date(raw_date),
        amount=abs(amount),
        direction=direction,
        counterparty=counter.strip(),
        counterparty_iban=_iban(str(cells.get(f.get('counter_iban', ''), '')) or desc),
        description=desc.strip(),
        account_iban=_iban(str(cells.get(f.get('account', ''), ''))),
        source_row=idx,
    )


def read_csv(path: str | Path) -> list[Transaction]:
    path = Path(path)
    raw = path.read_text(encoding='utf-8-sig', errors='replace')
    dialect_delim = ';' if raw.count(';') > raw.count(',') else ','
    rows = list(csv.reader(raw.splitlines(), delimiter=dialect_delim))
    if not rows:
        return []
    headers = _norm_headers(rows[0])
    m = _pick_mapping(headers)
    out, skipped = [], []
    for i, r in enumerate(rows[1:], start=2):
        if not any(str(c).strip() for c in r):
            continue
        cells = dict(zip(headers, r))
        try:
            txn = _row_to_txn(cells, m, i)
        except UnknownStatementFormat as e:
            skipped.append((i, str(e), ' | '.join(str(c) for c in r[:3])))
            continue
        if txn:
            out.append(txn)
    return StatementRead(out, skipped, m['name'])


def read_xlsx(path: str | Path) -> list[Transaction]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise UnknownStatementFormat(
            "Reading .xlsx needs openpyxl — run: pip install -r requirements.txt")
    wb = load_workbook(Path(path), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    # the header is not always the first row in a bank export
    header_idx = None
    for i, r in enumerate(rows[:25]):
        hs = set(_norm_headers(r))
        try:
            _pick_mapping(_norm_headers(r))
            header_idx = i
            break
        except UnknownStatementFormat:
            continue
    if header_idx is None:
        raise UnknownStatementFormat(
            "No recognisable header row in the first 25 rows of " + str(path))
    headers = _norm_headers(rows[header_idx])
    m = _pick_mapping(headers)
    out, skipped = [], []
    for i, r in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if not any(str(c).strip() for c in r if c is not None):
            continue
        cells = dict(zip(headers, r))
        try:
            txn = _row_to_txn(cells, m, i)
        except UnknownStatementFormat as e:
            skipped.append((i, str(e), ' | '.join(str(c) for c in r[:3] if c is not None)))
            continue
        if txn:
            out.append(txn)
    return StatementRead(out, skipped, m['name'])


def read_statement(path: str | Path) -> list[Transaction]:
    p = Path(path)
    if p.suffix.lower() in ('.xlsx', '.xlsm'):
        return read_xlsx(p)
    if p.suffix.lower() in ('.csv', '.txt'):
        return read_csv(p)
    raise UnknownStatementFormat(f"Unsupported file type: {p.suffix}")
