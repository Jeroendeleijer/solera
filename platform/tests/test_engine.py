"""Engine tests.

The first two cases are deliberately the same figures the public calculator on
the website shows, so the two can be cross-checked by hand.
"""
import unittest
from datetime import date
from decimal import Decimal

from solera import (
    Owner, Property, Ownership, RentalPeriod, IncomeType,
    compute_imputed, compute_rental, days_in_year, days_held, get_rules,
)
from solera.rules import UnknownTaxYear


def prop(value="150000", revision_year=2020):
    return Property(
        cadastral_reference="1234567AB1234C0001XY",
        cadastral_value=Decimal(value),
        municipality="Denia", province="Alicante",
        revision_year=revision_year,
    )


NL = Owner(nif="X1234567L", name="Owner NL", country_iso2="NL")
GB = Owner(nif="Y7654321M", name="Owner GB", country_iso2="GB")


class ImputedIncome(unittest.TestCase):
    def test_matches_website_eu_half_share_revised(self):
        # 150,000 x 1.1% = 1,650 ; x 50% = 825.00 ; x 19% = 156.75
        f = compute_imputed(Ownership(NL, prop(), Decimal("50")), 2025)
        self.assertEqual(f.taxable_base, Decimal("825.00"))
        self.assertEqual(f.rate_percent, Decimal("19"))
        self.assertEqual(f.tax_due, Decimal("156.75"))

    def test_matches_website_non_eu_full_share_unrevised(self):
        # 150,000 x 2% = 3,000.00 ; x 24% = 720.00
        f = compute_imputed(Ownership(GB, prop(revision_year=None), Decimal("100")), 2025)
        self.assertEqual(f.taxable_base, Decimal("3000.00"))
        self.assertEqual(f.rate_percent, Decimal("24"))
        self.assertEqual(f.tax_due, Decimal("720.00"))

    def test_unknown_revision_year_uses_higher_pct_and_says_so(self):
        f = compute_imputed(Ownership(NL, prop(revision_year=None), Decimal("100")), 2025)
        self.assertEqual(f.taxable_base, Decimal("3000.00"))
        self.assertTrue(any("higher 2%" in n for n in f.notes))

    def test_revision_outside_ten_year_window_uses_two_percent(self):
        # revised in 2010, tax year 2025 -> 15 years ago, window is 10
        f = compute_imputed(Ownership(NL, prop(revision_year=2010), Decimal("100")), 2025)
        self.assertEqual(f.taxable_base, Decimal("3000.00"))

    def test_revision_exactly_on_window_edge_still_counts(self):
        f = compute_imputed(Ownership(NL, prop(revision_year=2015), Decimal("100")), 2025)
        self.assertEqual(f.taxable_base, Decimal("1650.00"))

    def test_part_year_is_prorated_by_days_held(self):
        own = Ownership(NL, prop(), Decimal("100"), start=date(2025, 7, 2))
        f = compute_imputed(own, 2025)
        # 2 July to 31 December inclusive = 183 days of 365
        self.assertEqual(days_held(own, 2025), 183)
        self.assertEqual(f.taxable_base, Decimal("827.26"))

    def test_leap_year_prorates_over_366_days(self):
        self.assertEqual(days_in_year(2024), 366)
        self.assertEqual(days_in_year(2025), 365)
        own = Ownership(NL, prop(), Decimal("100"), start=date(2024, 1, 1), end=date(2024, 6, 30))
        f = compute_imputed(own, 2024)
        self.assertEqual(days_held(own, 2024), 182)          # includes 29 February
        self.assertEqual(f.taxable_base, Decimal("820.49"))  # 1650 x 182/366

    def test_full_year_is_not_prorated(self):
        f = compute_imputed(Ownership(NL, prop(), Decimal("100")), 2025)
        self.assertEqual(f.taxable_base, Decimal("1650.00"))
        self.assertEqual(f.notes, [])

    def test_ownership_ending_before_the_year_yields_zero(self):
        own = Ownership(NL, prop(), Decimal("100"), end=date(2024, 12, 31))
        f = compute_imputed(own, 2025)
        self.assertEqual(days_held(own, 2025), 0)
        self.assertEqual(f.tax_due, Decimal("0.00"))

    def test_rounding_is_half_up_at_the_cent(self):
        # 100,001 x 1.1% = 1,100.011 -> base 1,100.01 ; x 19% = 209.0019 -> 209.00
        f = compute_imputed(Ownership(NL, prop("100001"), Decimal("100")), 2025)
        self.assertEqual(f.taxable_base, Decimal("1100.01"))
        self.assertEqual(f.tax_due, Decimal("209.00"))


class RentalIncome(unittest.TestCase):
    def test_eu_resident_deducts_expenses_at_19(self):
        f = compute_rental(
            Ownership(NL, prop(), Decimal("100")),
            RentalPeriod(gross_income=Decimal("8000"), expenses=Decimal("3000"), days_let=60),
            2026,
        )
        self.assertEqual(f.taxable_base, Decimal("5000.00"))
        self.assertEqual(f.tax_due, Decimal("950.00"))

    def test_non_eu_resident_taxed_on_gross_at_24(self):
        f = compute_rental(
            Ownership(GB, prop(), Decimal("100")),
            RentalPeriod(gross_income=Decimal("8000"), expenses=Decimal("3000"), days_let=60),
            2026,
        )
        self.assertEqual(f.taxable_base, Decimal("8000.00"))   # expenses ignored
        self.assertEqual(f.tax_due, Decimal("1920.00"))
        self.assertTrue(any("not" in n and "deductible" in n for n in f.notes))

    def test_rent_is_split_by_ownership_share(self):
        f = compute_rental(
            Ownership(NL, prop(), Decimal("50")),
            RentalPeriod(gross_income=Decimal("8000"), expenses=Decimal("3000")),
            2026,
        )
        self.assertEqual(f.taxable_base, Decimal("2500.00"))

    def test_expenses_above_rent_floor_at_zero(self):
        f = compute_rental(
            Ownership(NL, prop(), Decimal("100")),
            RentalPeriod(gross_income=Decimal("1000"), expenses=Decimal("4000")),
            2026,
        )
        self.assertEqual(f.taxable_base, Decimal("0.00"))
        self.assertEqual(f.tax_due, Decimal("0.00"))
        self.assertTrue(any("floored at zero" in n for n in f.notes))

    def test_expense_annex_is_flagged_from_the_2027_form(self):
        eu = Ownership(NL, prop(), Decimal("100"))
        period = RentalPeriod(gross_income=Decimal("8000"), expenses=Decimal("3000"))
        self.assertTrue(any("annex" in n for n in compute_rental(eu, period, 2026).notes))
        self.assertFalse(any("annex" in n for n in compute_rental(eu, period, 2025).notes))


class Rules(unittest.TestCase):
    def test_unknown_tax_year_is_refused_not_guessed(self):
        with self.assertRaises(UnknownTaxYear):
            get_rules(2031)
        with self.assertRaises(UnknownTaxYear):
            compute_imputed(Ownership(NL, prop(), Decimal("100")), 2031)

    def test_rates_are_19_and_24_across_every_known_year(self):
        for year in (2022, 2023, 2024, 2025, 2026, 2027):
            r = get_rules(year)
            self.assertEqual(r.rate_eu_eea, Decimal("19"), year)
            self.assertEqual(r.rate_other, Decimal("24"), year)

    def test_only_eu_eea_may_deduct_expenses(self):
        for year in (2025, 2026):
            r = get_rules(year)
            self.assertTrue(r.expenses_deductible_eu_eea)
            self.assertFalse(r.expenses_deductible_other)

    def test_expense_annex_appears_with_the_2027_form(self):
        self.assertFalse(get_rules(2025).has_expense_annex)
        self.assertTrue(get_rules(2026).has_expense_annex)


class ResidencyMapping(unittest.TestCase):
    def test_uk_is_outside_the_eea_since_brexit(self):
        self.assertEqual(GB.residency.value, "other")

    def test_norway_iceland_liechtenstein_are_eea(self):
        for code in ("NO", "IS", "LI"):
            self.assertEqual(Owner("X", "n", code).residency.value, "eu_eea", code)

    def test_switzerland_is_not_eea(self):
        self.assertEqual(Owner("X", "n", "CH").residency.value, "other")

    def test_unknown_country_falls_back_to_the_higher_rate(self):
        self.assertEqual(Owner("X", "n", "").residency.value, "other")
        self.assertEqual(Owner("X", "n", "ZZ").residency.value, "other")


if __name__ == "__main__":
    unittest.main()
