/* Paste into the console on the page, or load it, to check the browser engine
 * against the same cases as the Python unit tests in ../tests/test_all.py.
 * Prints the failures; an empty list means the two implementations agree.
 */
(function () {
  const B = window.BankMatch, fails = [];
  const eq = (g, w, l) => { if (JSON.stringify(g) !== JSON.stringify(w)) fails.push(l + ': got ' + JSON.stringify(g) + ', want ' + JSON.stringify(w)); };
  eq(B.parseAmount('1.234,56'), 1234.56, 'euro'); eq(B.parseAmount('1,234.56'), 1234.56, 'anglo');
  eq(B.parseAmount('$1,452.00'), 1452, 'dollar'); eq(B.parseAmount('50,50-'), -50.5, 'trailing minus');
  eq(B.parseAmount('−496.50'), -496.5, 'U+2212'); eq(B.parseAmount('(1.234,56)'), -1234.56, 'parens');
  try { B.parseAmount('n/a'); fails.push('n/a should throw'); } catch (e) {}
  eq(B.iso(B.parseDate('20180102')), '2018-01-02', 'YYYYMMDD');
  eq(B.iso(B.parseDate('Sep 1, 2024')), '2024-09-01', 'Mon D YYYY');
  eq(B.findTotal('Subtotaal 100,00\nTotaal incl. btw: EUR 121,00'), 121, 'subtotal must lose');
  eq(B.findTotal('Total Amount Due $1,452.00'), 1452, 'english total');
  eq(B.findIban('rekening NL69TEST0000000001 tnv'), 'NL69TEST0000000001', 'iban not over-captured');
  eq(B.ibanChecksumOk('NL69TEST0000000002'), false, 'bad checksum rejected');
  eq(B.referenceHit('INV-2026/0042', 'betaling inv 2026 0042'), true, 'reference across separators');
  eq(B.referenceHit('42', 'order 42'), false, 'short reference is not evidence');
  const T = o => Object.assign({ date: new Date(2026,2,20), amount: 121, direction: 'out', counterparty: 'Acme Supplies BV', description: '', counterpartyIban: '' }, o);
  const D = o => Object.assign({ filename: 'x.pdf', supplier: 'Acme Supplies BV', invoiceNumber: 'INV-2026/0042', total: 121, docDate: new Date(2026,2,14), iban: '', emailFrom: '', textLen: 500 }, o);
  eq(B.match([T({description:'INV-2026/0042'})], [D({})]).matches[0].confidence, 'matched', 'strong pair auto-matches');
  eq(B.match([T({amount:500})], [D({})]).matches[0].confidence, 'none', 'wrong amount blocks');
  eq(B.match([T({date:new Date(2026,0,5)})], [D({docDate:new Date(2026,5,1)})]).matches[0].confidence, 'none', 'document after payment');
  eq(B.match([T({description:'INV-2026/0042'}), T({description:'INV-2026/0042'})], [D({})]).matches.filter(m=>m.document).length, 1, 'one document, one payment');
  console.log(fails.length ? fails : 'all checks passed');
  return fails;
})();
