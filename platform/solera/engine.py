"""The calculation engine.

One filing per owner per property per tax year per income type. The engine
computes the taxable base and the tax due; it does not decide whether a filing
is required, and it does not file anything.

All arithmetic is Decimal, rounded half-up to the cent only at the points where
AEAT expects a rounded figure (the base and the tax), never mid-calculation.
"""
from __future__ import annotations

import calendar as _pycal
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .model import (
    CENT, Filing, FilingStatus, IncomeType, Ownership, RentalPeriod,
)
from .rules import TaxYearRules, get_rules

HUNDRED = Decimal("100")


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def days_in_year(year: int) -> int:
    """366 in a leap year.

    Worth stating plainly: prorating a part-year holding by a hard-coded 365
    overstates the base in a leap year. 2024 and 2028 are leap years.
    """
    return 366 if _pycal.isleap(year) else 365


def days_held(ownership: Ownership, tax_year: int) -> int:
    """Days the stake was held inside the tax year, inclusive of both ends."""
    year_start, year_end = date(tax_year, 1, 1), date(tax_year, 12, 31)
    start = max(ownership.start or year_start, year_start)
    end = min(ownership.end or year_end, year_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _prorate(amount: Decimal, ownership: Ownership, tax_year: int) -> tuple[Decimal, int, int]:
    """Apply ownership share and days held. Returns (amount, days, year_days)."""
    year_days = days_in_year(tax_year)
    held = days_held(ownership, tax_year)
    share = ownership.share_percent / HUNDRED
    return amount * share * (Decimal(held) / Decimal(year_days)), held, year_days


def compute_imputed(ownership: Ownership, tax_year: int,
                    rules: Optional[TaxYearRules] = None) -> Filing:
    """Imputed (notional) income on a property in personal use or empty.

    base = cadastral value x 1.1% (municipality revised within the window)
           or 2% otherwise, prorated by share and days held.
    """
    rules = rules or get_rules(tax_year)
    prop, owner = ownership.property, ownership.owner
    notes: list[str] = []

    revised = prop.revised_recently(tax_year, rules.revision_window_years)
    pct = rules.imputed_pct(revised)
    if prop.revision_year is None:
        notes.append(
            "Revision year unknown, so the higher 2% was applied. Check the "
            "municipality against the list AEAT publishes each year before filing."
        )

    full_base = prop.cadastral_value * (pct / HUNDRED)
    base, held, year_days = _prorate(full_base, ownership, tax_year)
    base = _round(base)

    rate = rules.rate_for(owner.residency)
    tax = _round(base * (rate / HUNDRED))

    if held != year_days:
        notes.append(f"Prorated for {held} of {year_days} days held.")
    if year_days == 366:
        notes.append(f"{tax_year} is a leap year: prorated over 366 days.")

    return Filing(
        owner=owner, property=prop, tax_year=tax_year,
        income_type=IncomeType.IMPUTED,
        taxable_base=base, rate_percent=rate, tax_due=tax,
        status=FilingStatus.CALCULATED, notes=notes,
    )


def compute_rental(ownership: Ownership, period: RentalPeriod, tax_year: int,
                   rules: Optional[TaxYearRules] = None) -> Filing:
    """Tax on rent actually received.

    EU/EEA residents are taxed at 19% on rent net of allowable expenses.
    Everyone else is taxed at 24% on the gross rent, with no deduction - the
    single most expensive difference between the two regimes.
    """
    rules = rules or get_rules(tax_year)
    owner = ownership.owner
    notes: list[str] = []

    deductible = rules.expenses_deductible(owner.residency)
    if deductible:
        net = period.gross_income - period.expenses
        if net < 0:
            net = Decimal("0")
            notes.append("Expenses exceeded rent; the base is floored at zero, "
                         "not carried as a loss by this engine.")
    else:
        net = period.gross_income
        if period.expenses > 0:
            notes.append(
                f"Expenses of {period.expenses} were recorded but are not "
                f"deductible outside the EU/EEA; taxed on gross rent."
            )

    # Rent is prorated by ownership share only. Unlike imputed income it is not
    # spread across the year: the days that matter are the days actually let,
    # which are already reflected in the rent received.
    share = ownership.share_percent / HUNDRED
    base = _round(net * share)

    rate = rules.rate_for(owner.residency)
    tax = _round(base * (rate / HUNDRED))

    if rules.has_expense_annex and deductible:
        notes.append("Expenses must be itemised in the expense annex of the 2027 form.")

    return Filing(
        owner=owner, property=ownership.property, tax_year=tax_year,
        income_type=IncomeType.RENTAL,
        taxable_base=base, rate_percent=rate, tax_due=tax,
        status=FilingStatus.CALCULATED, notes=notes,
    )
