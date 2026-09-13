"""Worked example: two co-owners of one Denia property, tax year 2026.

Run:  python3 demo.py
"""
from datetime import date
from decimal import Decimal

from solera import (
    Owner, Property, Ownership, RentalPeriod, IncomeType,
    compute_imputed, compute_rental, filing_window,
)

home = Property(
    cadastral_reference="1234567AB1234C0001XY",
    cadastral_value=Decimal("150000"),
    municipality="Denia", province="Alicante",
    revision_year=2020,
)

anna = Owner(nif="X1234567L", name="Anna de Vries", country_iso2="NL", language="nl")
paul = Owner(nif="Y7654321M", name="Paul Whitfield", country_iso2="GB", language="en")

print("Property:", home.municipality, "- cadastral value", home.cadastral_value)
print("Tax year 2026, two co-owners at 50% each\n")

for owner in (anna, paul):
    own = Ownership(owner, home, Decimal("50"))
    f = compute_imputed(own, 2026)
    print(f"{owner.name} ({owner.country_iso2}, {owner.residency.value})")
    print(f"  imputed base {f.taxable_base}  rate {f.rate_percent}%  tax due {f.tax_due}")
    for n in f.notes:
        print(f"  note: {n}")

print("\nSame two owners, if the property were let for 8,000 with 3,000 of costs:")
for owner in (anna, paul):
    own = Ownership(owner, home, Decimal("50"))
    f = compute_rental(own, RentalPeriod(Decimal("8000"), Decimal("3000"), days_let=60), 2026)
    print(f"  {owner.name}: base {f.taxable_base} rate {f.rate_percent}% tax {f.tax_due}")
    for n in f.notes:
        print(f"    note: {n}")

print("\nFiling windows for tax year 2026:")
for t in IncomeType:
    w = filing_window(2026, t)
    print(f"  {t.value:8s} {w.opens} to {w.closes}  ({w.form_version})")

print("\nSame property, same owners, but nobody has checked the revision year:")
unknown = Property("1234567AB1234C0001XY", Decimal("150000"), "Denia", "Alicante", revision_year=None)
f = compute_imputed(Ownership(anna, unknown, Decimal("50")), 2026)
print(f"  base {f.taxable_base} tax {f.tax_due}  <- 2% applied, not 1.1%")
for n in f.notes:
    print(f"  note: {n}")
