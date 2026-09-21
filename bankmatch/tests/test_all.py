import unittest
from datetime import date
from decimal import Decimal

from bankmatch.model import Direction, Document, Transaction, Confidence
from bankmatch.statements import parse_amount, parse_date, UnknownStatementFormat
from bankmatch.extract import find_total, find_invoice_number, find_date, find_iban
from bankmatch import matching


def txn(amount='121.00', d=(2026, 3, 20), cp='Acme Supplies BV', desc='', iban=''):
    return Transaction(date=date(*d), amount=Decimal(amount), direction=Direction.OUT,
                       counterparty=cp, description=desc, counterparty_iban=iban)


def doc(total='121.00', d=(2026, 3, 14), supplier='Acme Supplies BV', inv='INV-2026/0042', iban=''):
    return Document(path='/tmp/x.pdf', filename='x.pdf', supplier=supplier,
                    invoice_number=inv, total=Decimal(total) if total else None,
                    doc_date=date(*d) if d else None, iban=iban, text_len=500)


class Amounts(unittest.TestCase):
    def test_european_and_anglo_formats(self):
        self.assertEqual(parse_amount('1.234,56'), Decimal('1234.56'))
        self.assertEqual(parse_amount('1,234.56'), Decimal('1234.56'))
        self.assertEqual(parse_amount('825,00'), Decimal('825.00'))

    def test_currency_symbols_are_stripped(self):
        self.assertEqual(parse_amount('$1,452.00'), Decimal('1452.00'))
        self.assertEqual(parse_amount('EUR 121,00'), Decimal('121.00'))
        self.assertEqual(parse_amount('€ 99,95'), Decimal('99.95'))

    def test_negatives_in_every_notation_seen_in_the_wild(self):
        self.assertEqual(parse_amount('-50,50'), Decimal('-50.50'))
        self.assertEqual(parse_amount('50,50-'), Decimal('-50.50'))       # trailing minus
        self.assertEqual(parse_amount('−496.50'), Decimal('-496.50'))  # U+2212
        self.assertEqual(parse_amount('(1.234,56)'), Decimal('-1234.56'))   # accounting

    def test_unreadable_amount_raises_rather_than_returning_zero(self):
        with self.assertRaises(UnknownStatementFormat):
            parse_amount('n/a')


class Dates(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_date('20180102'), date(2018, 1, 2))
        self.assertEqual(parse_date('02-01-2018'), date(2018, 1, 2))
        self.assertEqual(parse_date('Sep 1, 2024'), date(2024, 9, 1))

    def test_unreadable_date_raises(self):
        with self.assertRaises(UnknownStatementFormat):
            parse_date('Sep 1 - 11, 2024')


class Extraction(unittest.TestCase):
    def test_subtotal_does_not_win_over_total(self):
        t = 'Subtotaal 100,00\nBTW 21% 21,00\nTotaal incl. btw: EUR 121,00'
        self.assertEqual(find_total(t), Decimal('121.00'))

    def test_spanish_and_english_templates(self):
        self.assertEqual(find_total('Base imponible 250,00\nIMPORTE TOTAL: 302,50'), Decimal('302.50'))
        self.assertEqual(find_total('Subtotal $1,200.00\nTotal Amount Due $1,452.00'), Decimal('1452.00'))

    def test_invoice_number_and_iban(self):
        self.assertEqual(find_invoice_number('Factuur nr: INV-2026/0042'), 'INV-2026/0042')
        self.assertEqual(find_iban('IBAN NL69 TEST 0000 0000 01'), 'NL69TEST0000000001')
        self.assertEqual(find_iban('rekening NL69TEST0000000001 tnv'), 'NL69TEST0000000001')

    def test_no_total_returns_none_rather_than_guessing(self):
        self.assertIsNone(find_total('Thanks for your business. See attached.'))


class Similarity(unittest.TestCase):
    def test_legal_suffixes_are_ignored(self):
        self.assertGreaterEqual(matching.name_similarity('Vodafone Espana SLU', 'VODAFONE ES'), 0.9)

    def test_unrelated_names_score_zero(self):
        self.assertEqual(matching.name_similarity('Acme BV', 'Totally Different Ltd'), 0.0)

    def test_reference_survives_separator_changes(self):
        self.assertTrue(matching.reference_hit('INV-2026/0042', 'betaling inv 2026 0042'))
        self.assertTrue(matching.reference_hit('F-2026-118', 'FACT F2026118 GRACIAS'))

    def test_short_reference_is_not_evidence(self):
        self.assertFalse(matching.reference_hit('42', 'order 42 shipped'))


class Matching(unittest.TestCase):
    def test_strong_pair_is_auto_matched(self):
        m = matching.match([txn(desc='factuur INV-2026/0042')], [doc()])[0]
        self.assertIs(m.confidence, Confidence.MATCHED)
        self.assertGreaterEqual(m.score, 0.80)

    def test_amount_alone_is_not_enough_to_auto_match(self):
        # same amount, unrelated supplier, no reference quoted
        m = matching.match([txn(cp='Unrelated Company', desc='')],
                           [doc(supplier='Acme Supplies BV', inv='')])[0]
        self.assertIsNot(m.confidence, Confidence.MATCHED)

    def test_wrong_amount_blocks_the_match(self):
        m = matching.match([txn(amount='500.00', cp='Acme Supplies BV')], [doc(total='121.00')])[0]
        self.assertIs(m.confidence, Confidence.NONE)

    def test_invoice_dated_after_the_payment_is_rejected(self):
        m = matching.match([txn(d=(2026, 1, 5))], [doc(d=(2026, 6, 1))])[0]
        self.assertIs(m.confidence, Confidence.NONE)

    def test_transaction_with_no_document_is_reported_not_dropped(self):
        ms = matching.match([txn(), txn(amount='9999.00', cp='Nobody')], [doc()])
        self.assertEqual(len(ms), 2)
        self.assertIs(ms[1].confidence, Confidence.NONE)

    def test_one_document_cannot_serve_two_payments(self):
        d = doc()
        ms = matching.match([txn(desc='INV-2026/0042'), txn(desc='INV-2026/0042')], [d])
        used = [m for m in ms if m.document is not None]
        self.assertEqual(len(used), 1, "the same invoice was matched twice")

    def test_best_pair_wins_over_an_earlier_weaker_one(self):
        weak = txn(cp='Acme Supplies BV', desc='')                 # name only
        strong = txn(cp='Acme Supplies BV', desc='INV-2026/0042')  # name + reference
        ms = matching.match([weak, strong], [doc()])
        self.assertIsNone(ms[0].document)
        self.assertIsNotNone(ms[1].document)

    def test_iban_on_the_invoice_supports_the_match(self):
        m = matching.match([txn(cp='X', iban='NL69TEST0000000001')],
                           [doc(supplier='Y', inv='', iban='NL69TEST0000000001')])[0]
        self.assertGreaterEqual(m.score, matching.REVIEW_THRESHOLD)

    def test_every_match_explains_itself(self):
        for m in matching.match([txn(desc='INV-2026/0042')], [doc()]):
            self.assertTrue(m.reasons, "a match with no reasons is unreviewable")

    def test_document_with_no_total_can_still_match_on_reference(self):
        m = matching.match([txn(desc='payment for INV-2026/0042')], [doc(total=None)])[0]
        self.assertIsNot(m.confidence, Confidence.NONE)


if __name__ == '__main__':
    unittest.main()
