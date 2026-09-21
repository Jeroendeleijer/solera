"""Matching a bank transaction to the invoice that explains it.

Design rules:
  - Every match carries the reasons it scored what it did. An accountant must
    be able to see why, and disagree.
  - Nothing is auto-accepted on a weak signal. Below the threshold it goes to
    a review queue rather than into the "done" pile.
  - One document pairs with at most one transaction, and vice versa. Assignment
    is greedy over the global best scores, so a strong pair is not stolen by a
    weaker one seen earlier.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Iterable

from .model import Confidence, Direction, Document, Match, Transaction

AUTO_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50
MAX_DAYS_AFTER = 120      # invoice this long before the payment is still plausible
MAX_DAYS_BEFORE = 10      # payment slightly ahead of the invoice date happens

_WORD = re.compile(r'[a-z0-9]+')
_NOISE = {'bv', 'b', 'v', 'nv', 'sl', 'sa', 'ltd', 'gmbh', 'the', 'de', 'van',
          'der', 'den', 'het', 'een', 'and', 'en', 'invoice', 'factuur',
          'factura', 'inc', 'co', 'com', 'www', 'nl', 'es'}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or '').lower())
            if len(w) > 2 and w not in _NOISE}


def name_similarity(a: str, b: str) -> float:
    """Token overlap, normalised by the smaller name.

    Deliberately not a character-level ratio: 'Vodafone Espana SLU' against
    'VODAFONE ES' should score high, and edit distance would not say so.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _normalise_ref(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def reference_hit(invoice_number: str, haystack: str) -> bool:
    """Is the invoice number actually quoted in the payment description?

    Compared with separators stripped, because 'INV-2026/0042' on the invoice
    arrives at the bank as 'INV20260042' or 'inv 2026 0042'.
    """
    ref = _normalise_ref(invoice_number)
    if len(ref) < 4:            # too short to be evidence
        return False
    return ref in _normalise_ref(haystack)


def score(txn: Transaction, doc: Document) -> tuple[float, list[str]]:
    """Score one candidate pair. Returns (0..1, reasons)."""
    s, reasons = 0.0, []

    # --- amount: the single strongest signal -------------------------------
    if doc.total is not None:
        diff = abs(doc.total - txn.amount)
        if diff == 0:
            s += 0.45; reasons.append(f"Amount matches exactly ({txn.amount}).")
        elif diff <= Decimal('0.02'):
            s += 0.40; reasons.append(f"Amount matches to the cent ({txn.amount} vs {doc.total}).")
        elif txn.amount and diff / txn.amount <= Decimal('0.01'):
            s += 0.22; reasons.append(f"Amount within 1% ({txn.amount} vs {doc.total}).")
        else:
            # a clear mismatch is evidence against, not merely absent evidence
            s -= 0.25; reasons.append(f"Amounts differ: {txn.amount} vs {doc.total}.")
    else:
        reasons.append("No total could be read from the document.")

    # --- invoice number quoted in the payment ------------------------------
    if doc.invoice_number and reference_hit(doc.invoice_number, txn.haystack):
        s += 0.40; reasons.append(f"Invoice number {doc.invoice_number} appears in the payment description.")

    # --- supplier name -----------------------------------------------------
    sim = max(name_similarity(doc.supplier, txn.haystack),
              name_similarity(doc.email_from, txn.haystack))
    if sim >= 0.8:
        s += 0.25; reasons.append(f"Supplier name matches the counterparty ({sim:.0%}).")
    elif sim >= 0.4:
        s += 0.12; reasons.append(f"Supplier name partly matches ({sim:.0%}).")

    # --- IBAN --------------------------------------------------------------
    if doc.iban and txn.counterparty_iban and doc.iban == txn.counterparty_iban:
        s += 0.30; reasons.append(f"IBAN on the invoice matches the counterparty account.")

    # --- dates -------------------------------------------------------------
    d = doc.best_date
    if d:
        gap = (txn.date - d).days
        if -MAX_DAYS_BEFORE <= gap <= MAX_DAYS_AFTER:
            close = max(0.0, 1 - max(0, gap) / MAX_DAYS_AFTER)
            s += 0.15 * close
            reasons.append(f"Paid {gap} days after the document date." if gap >= 0
                           else f"Paid {-gap} days before the document date.")
        elif gap < -MAX_DAYS_BEFORE:
            # the invoice is dated after the money moved: it cannot be the cause
            return 0.0, [f"Document is dated {-gap} days after the payment — it cannot explain it."]
        else:
            s -= 0.30
            reasons.append(f"Document is {gap} days older than the payment — outside the window.")

    # --- direction sanity --------------------------------------------------
    # A purchase invoice should pair with money going out. This is a weak
    # signal because sales invoices legitimately pair with money coming in.
    if txn.direction is Direction.OUT:
        s += 0.02

    return max(0.0, min(1.0, s)), reasons


def match(transactions: Iterable[Transaction],
          documents: Iterable[Document],
          auto_threshold: float = AUTO_THRESHOLD,
          review_threshold: float = REVIEW_THRESHOLD) -> list[Match]:
    """Pair transactions with documents, best global scores first."""
    txns, docs = list(transactions), list(documents)
    candidates = []
    for ti, t in enumerate(txns):
        for di, d in enumerate(docs):
            sc, why = score(t, d)
            if sc >= review_threshold:
                candidates.append((sc, ti, di, why))
    candidates.sort(key=lambda c: -c[0])

    taken_t, taken_d, results = set(), set(), {}
    for sc, ti, di, why in candidates:
        if ti in taken_t or di in taken_d:
            continue
        taken_t.add(ti); taken_d.add(di)
        results[ti] = Match(
            transaction=txns[ti], document=docs[di], score=round(sc, 3),
            confidence=Confidence.MATCHED if sc >= auto_threshold else Confidence.REVIEW,
            reasons=why)

    out = [results.get(i, Match(transaction=t, document=None, score=0.0,
                                confidence=Confidence.NONE,
                                reasons=["No document in the mailbox explains this payment."]))
           for i, t in enumerate(txns)]
    return out


def unmatched_documents(documents: Iterable[Document], matches: Iterable[Match]) -> list[Document]:
    used = {id(m.document) for m in matches if m.document is not None}
    return [d for d in documents if id(d) not in used]
