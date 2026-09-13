"""Filing window tests - the 2027 form moved these, so they are pinned."""
import unittest
from datetime import date

from solera import IncomeType, filing_window
from solera.rules import UnknownTaxYear


class Windows(unittest.TestCase):
    def test_imputed_pre_2027_runs_the_whole_following_year(self):
        w = filing_window(2025, IncomeType.IMPUTED)
        self.assertEqual((w.opens, w.closes), (date(2026, 1, 1), date(2026, 12, 31)))
        self.assertEqual(w.form_version, "210-pre2027")

    def test_imputed_from_2026_opens_in_april(self):
        w = filing_window(2026, IncomeType.IMPUTED)
        self.assertEqual((w.opens, w.closes), (date(2027, 4, 1), date(2027, 12, 31)))
        self.assertEqual(w.form_version, "210-2027")

    def test_rental_is_annual_first_twenty_days_of_april(self):
        w = filing_window(2026, IncomeType.RENTAL)
        self.assertEqual((w.opens, w.closes), (date(2027, 4, 1), date(2027, 4, 20)))

    def test_is_open_on_boundaries(self):
        w = filing_window(2026, IncomeType.RENTAL)
        self.assertTrue(w.is_open_on(date(2027, 4, 1)))
        self.assertTrue(w.is_open_on(date(2027, 4, 20)))
        self.assertFalse(w.is_open_on(date(2027, 4, 21)))
        self.assertFalse(w.is_open_on(date(2027, 3, 31)))

    def test_unknown_year_is_refused(self):
        with self.assertRaises(UnknownTaxYear):
            filing_window(2031, IncomeType.IMPUTED)


if __name__ == "__main__":
    unittest.main()
