"""Core types.

Money is Decimal everywhere. A cent of drift is a mismatch, and a mismatch
is exactly what this tool exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class Direction(Enum):
    OUT = "out"   # money left the account — pairs with a purchase invoice
    IN = "in"     # money arrived — pairs with a sales invoice


@dataclass(frozen=True)
class Transaction:
    """One line of a bank statement, normalised across export formats."""
    date: date
    amount: Decimal              # always positive; direction carries the sign
    direction: Direction
    counterparty: str = ""       # name as the bank recorded it
    counterparty_iban: str = ""
    description: str = ""        # free text; invoice references usually hide here
    account_iban: str = ""
    source_row: int = 0

    @property
    def signed(self) -> Decimal:
        return self.amount if self.direction is Direction.IN else -self.amount

    @property
    def haystack(self) -> str:
        return f"{self.counterparty} {self.description}".strip()


@dataclass(frozen=True)
class Document:
    """An invoice or receipt found as an email attachment."""
    path: str                       # where the file was saved
    filename: str
    supplier: str = ""
    invoice_number: str = ""
    total: Optional[Decimal] = None
    doc_date: Optional[date] = None
    iban: str = ""
    email_subject: str = ""
    email_from: str = ""
    email_date: Optional[date] = None
    text_len: int = 0               # 0 means nothing could be read out of it

    @property
    def best_date(self) -> Optional[date]:
        return self.doc_date or self.email_date


class Confidence(Enum):
    MATCHED = "matched"   # safe to hand over
    REVIEW = "review"     # plausible, a human should confirm
    NONE = "none"


@dataclass
class Match:
    transaction: Transaction
    document: Optional[Document]
    score: float
    confidence: Confidence
    reasons: list[str] = field(default_factory=list)
