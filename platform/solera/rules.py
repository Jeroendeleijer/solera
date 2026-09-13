"""Tax rules, versioned per tax year.

Part 3 requires the rules engine to be "versioned per tax year, unit-tested".
Everything that can change by year lives here as data, so a future change is a
new TaxYearRules row and a test, never an edit to the calculation code.

Sources (see the concept note appendix, and verify against AEAT before use):
  - Orden EHA/3316/2010 - Modelo 210 and filing conditions.
  - Orden HAC/623/2026 (BOE 23 June 2026) - new 210 form from 1 January 2027:
    expense annex, days and ownership-share boxes, imputed window moves to
    1 April - 31 December, rental income annual 1-20 April.
  - Rates unchanged: 19% EU/EEA residents, 24% others.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .model import Residency


@dataclass(frozen=True)
class TaxYearRules:
    tax_year: int

    # Imputed income: percentage applied to the cadastral value.
    imputed_pct_revised: Decimal      # municipality revised within the window
    imputed_pct_default: Decimal      # everyone else
    revision_window_years: int        # how recent a revision must be

    # Rates by regime.
    rate_eu_eea: Decimal
    rate_other: Decimal

    # Rental income: only EU/EEA residents may deduct expenses. Non-EU/EEA
    # residents are taxed on gross rent.
    expenses_deductible_eu_eea: bool
    expenses_deductible_other: bool

    # From the 2027 form onwards the rental return carries an expense annex
    # and the form has explicit days/share boxes.
    has_expense_annex: bool
    has_days_and_share_boxes: bool
    form_version: str

    def imputed_pct(self, revised_recently: bool) -> Decimal:
        return self.imputed_pct_revised if revised_recently else self.imputed_pct_default

    def rate_for(self, residency: Residency) -> Decimal:
        return self.rate_eu_eea if residency is Residency.EU_EEA else self.rate_other

    def expenses_deductible(self, residency: Residency) -> bool:
        return (self.expenses_deductible_eu_eea if residency is Residency.EU_EEA
                else self.expenses_deductible_other)


def _legacy(year: int) -> TaxYearRules:
    """Tax years filed on the pre-2027 form."""
    return TaxYearRules(
        tax_year=year,
        imputed_pct_revised=Decimal("1.1"),
        imputed_pct_default=Decimal("2.0"),
        revision_window_years=10,
        rate_eu_eea=Decimal("19"),
        rate_other=Decimal("24"),
        expenses_deductible_eu_eea=True,
        expenses_deductible_other=False,
        has_expense_annex=False,
        has_days_and_share_boxes=False,
        form_version="210-pre2027",
    )


def _modern(year: int) -> TaxYearRules:
    """Tax years filed on the form introduced by Orden HAC/623/2026."""
    return TaxYearRules(
        tax_year=year,
        imputed_pct_revised=Decimal("1.1"),
        imputed_pct_default=Decimal("2.0"),
        revision_window_years=10,
        rate_eu_eea=Decimal("19"),
        rate_other=Decimal("24"),
        expenses_deductible_eu_eea=True,
        expenses_deductible_other=False,
        has_expense_annex=True,
        has_days_and_share_boxes=True,
        form_version="210-2027",
    )


# Tax year -> rules. A tax year absent from this table is refused rather than
# guessed: filing a year whose rules nobody has confirmed is how surcharges happen.
RULES: dict[int, TaxYearRules] = {
    2022: _legacy(2022),
    2023: _legacy(2023),
    2024: _legacy(2024),
    2025: _legacy(2025),
    2026: _modern(2026),
    2027: _modern(2027),
}


class UnknownTaxYear(LookupError):
    """Raised for a tax year with no confirmed rule set."""


def get_rules(tax_year: int) -> TaxYearRules:
    try:
        return RULES[tax_year]
    except KeyError:
        known = ", ".join(str(y) for y in sorted(RULES))
        raise UnknownTaxYear(
            f"No confirmed rules for tax year {tax_year}. Known years: {known}. "
            f"Add a TaxYearRules entry and a test before filing this year."
        ) from None
