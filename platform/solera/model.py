"""Data model for the Solera platform.

Mirrors the minimum model in Part 3 of the concept note:
Owner, Property, Ownership, TaxYear rules, Filing, Document.

Money is Decimal throughout. Never float: binary floats cannot represent
tenths exactly, and a tax figure that is off by a cent is a wrong filing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

CENT = Decimal("0.01")


class Residency(Enum):
    """Which of the two Spanish non-resident regimes an owner falls under.

    The distinction drives both the rate and whether expenses are deductible,
    so it is modelled explicitly rather than inferred from a country string.
    """
    EU_EEA = "eu_eea"   # EU member states plus Norway, Iceland, Liechtenstein
    OTHER = "other"     # everyone else, the United Kingdom included since Brexit


# EEA = EU + these three. Kept as data so the list can be corrected in one place.
_EEA_EXTRA = {"NO", "IS", "LI"}
_EU = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
}


def residency_for(country_iso2: str) -> Residency:
    """Map an ISO-3166 alpha-2 country code to a regime.

    Deliberately conservative: anything unrecognised is OTHER, the higher
    rate, so an unknown country can never under-declare.
    """
    code = (country_iso2 or "").strip().upper()
    if code in _EU or code in _EEA_EXTRA:
        return Residency.EU_EEA
    return Residency.OTHER


class IncomeType(Enum):
    IMPUTED = "imputed"   # personal use or empty: notional income
    RENTAL = "rental"     # actual rent received


class FilingStatus(Enum):
    """The pipeline the portal shows to the owner."""
    CONFIRMED = "confirmed"
    CALCULATED = "calculated"
    FILED = "filed"
    PAID = "paid"


@dataclass(frozen=True)
class Owner:
    nif: str                    # NIE or NIF
    name: str
    country_iso2: str           # country of tax residence
    language: str = "nl"

    @property
    def residency(self) -> Residency:
        return residency_for(self.country_iso2)


@dataclass(frozen=True)
class Property:
    """A single cadastral reference.

    A garage or storeroom with its own reference is a separate Property and
    therefore a separate filing, which is why this is keyed on the reference
    rather than on an address.
    """
    cadastral_reference: str
    cadastral_value: Decimal
    municipality: str
    province: str
    # Year of the last collective valuation revision. None means unknown, which
    # is treated as "not recently revised" -> the higher 2% applies.
    revision_year: Optional[int] = None

    def revised_recently(self, tax_year: int, window_years: int) -> bool:
        if self.revision_year is None:
            return False
        return 0 <= (tax_year - self.revision_year) <= window_years


@dataclass(frozen=True)
class Ownership:
    """One owner's stake in one property, for a period.

    Both the share and the days held prorate the taxable base, and the 2027
    form has explicit boxes for each.
    """
    owner: Owner
    property: Property
    share_percent: Decimal
    start: Optional[date] = None   # None = held since before the tax year
    end: Optional[date] = None     # None = still held at year end


@dataclass(frozen=True)
class RentalPeriod:
    """Rent received, and the expenses against it.

    Expenses are recorded whatever the owner's residency; whether they may be
    deducted is a rule decision, not a data one, so the record stays truthful.
    """
    gross_income: Decimal
    expenses: Decimal = Decimal("0")
    days_let: int = 0


@dataclass
class Filing:
    owner: Owner
    property: Property
    tax_year: int
    income_type: IncomeType
    taxable_base: Decimal
    rate_percent: Decimal
    tax_due: Decimal
    status: FilingStatus = FilingStatus.CALCULATED
    receipt_csv: Optional[str] = None
    notes: list[str] = field(default_factory=list)
