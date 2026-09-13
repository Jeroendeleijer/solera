"""Solera platform - reference implementation.

Scope: the data model, the per-tax-year rules and the calculation engine.
Deliberately NOT included, and not stubbed:
  - the .210 file generator (blocked on the 2027 record design)
  - the AEAT batch filer (needs colaborador social status and a certificate)
  - authentication and persistence
See README.md.
"""
from .model import (
    Owner, Property, Ownership, RentalPeriod, Filing,
    IncomeType, FilingStatus, Residency, residency_for,
)
from .rules import TaxYearRules, get_rules, RULES, UnknownTaxYear
from .calendar import filing_window, FilingWindow
from .engine import compute_imputed, compute_rental, days_in_year, days_held

__all__ = [
    "Owner", "Property", "Ownership", "RentalPeriod", "Filing",
    "IncomeType", "FilingStatus", "Residency", "residency_for",
    "TaxYearRules", "get_rules", "RULES", "UnknownTaxYear",
    "filing_window", "FilingWindow",
    "compute_imputed", "compute_rental", "days_in_year", "days_held",
]
