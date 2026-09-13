"""Filing windows and deadlines, per tax year and income type.

The 2027 form moved the imputed-income window and made rental income annual.
Getting this wrong means a late filing and a surcharge, so the windows are
data and are tested, exactly like the rates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .model import IncomeType
from .rules import get_rules


@dataclass(frozen=True)
class FilingWindow:
    opens: date
    closes: date
    form_version: str
    note: str = ""

    def is_open_on(self, day: date) -> bool:
        return self.opens <= day <= self.closes


def filing_window(tax_year: int, income_type: IncomeType) -> FilingWindow:
    """Return the window in which a return for `tax_year` must be filed."""
    rules = get_rules(tax_year)          # refuses unknown years
    following = tax_year + 1

    if income_type is IncomeType.IMPUTED:
        if rules.has_days_and_share_boxes:
            # Orden HAC/623/2026: 1 April - 31 December of the following year.
            return FilingWindow(
                opens=date(following, 4, 1),
                closes=date(following, 12, 31),
                form_version=rules.form_version,
                note="Imputed income, new form: 1 April - 31 December of the following year.",
            )
        # Pre-2027: the whole of the following calendar year.
        return FilingWindow(
            opens=date(following, 1, 1),
            closes=date(following, 12, 31),
            form_version=rules.form_version,
            note="Imputed income, pre-2027 form: calendar year following the tax year.",
        )

    # Rental income: annual, in the first twenty days of April.
    return FilingWindow(
        opens=date(following, 4, 1),
        closes=date(following, 4, 20),
        form_version=rules.form_version,
        note="Rental income: annual return, 1-20 April of the following year.",
    )
