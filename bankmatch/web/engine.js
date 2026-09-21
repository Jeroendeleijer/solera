/* bankmatch — browser engine.
 * A direct port of the Python in ../bankmatch/. The two must agree, so the
 * constants, weights and thresholds below are copied verbatim rather than
 * re-tuned, and selftest.js checks them against the same cases the Python
 * unit tests use.
 * Everything here runs on the client. No network calls, no uploads.
 */
(function (global) {
  'use strict';

  const AUTO_THRESHOLD = 0.80;
  const REVIEW_THRESHOLD = 0.50;
  const MAX_DAYS_AFTER = 120;
  const MAX_DAYS_BEFORE = 10;

  // ---------- amounts -----------------------------------------------------
  function parseAmount(raw) {
    let s = String(raw == null ? '' : raw).replace(/ /g, ' ').replace(/\s/g, '');
    const hadContent = s.length > 0;
    s = s.replace(/[−–—]/g, '-');          // U+2212 minus, en/em dash
    let neg = false;
    if (s.startsWith('(') && s.endsWith(')')) { neg = true; s = s.slice(1, -1); }
    if (s.startsWith('-') || s.endsWith('-')) neg = true;
    s = s.replace(/[^\d.,]/g, '');                         // drop EUR, €, $, letters
    if (!s) {
      if (hadContent && /\S/.test(String(raw))) throw new Error('Cannot read amount: ' + raw);
      return 0;
    }
    const lastComma = s.lastIndexOf(','), lastDot = s.lastIndexOf('.');
    if (lastComma > lastDot) s = s.replace(/\./g, '').replace(',', '.');
    else s = s.replace(/,/g, '');
    const v = parseFloat(s);
    if (isNaN(v)) throw new Error('Cannot read amount: ' + raw);
    return neg ? -v : v;
  }

  // ---------- dates -------------------------------------------------------
  const MONTHS = {jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11,
                  mrt:2,mei:4,okt:9};
  function parseDate(raw) {
    if (raw instanceof Date && !isNaN(raw)) return new Date(raw.getFullYear(), raw.getMonth(), raw.getDate());
    const s = String(raw == null ? '' : raw).trim();
    let m;
    if ((m = s.match(/^(\d{4})(\d{2})(\d{2})$/)))                       // 20180102
      return new Date(+m[1], +m[2] - 1, +m[3]);
    if ((m = s.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{4})$/)))       // 02-01-2018
      return new Date(+m[3], +m[2] - 1, +m[1]);
    if ((m = s.match(/^(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})$/)))       // 2018-01-02
      return new Date(+m[1], +m[2] - 1, +m[3]);
    if ((m = s.match(/^([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$/i))) { // Sep 1, 2024
      const mo = MONTHS[m[1].toLowerCase()];
      if (mo !== undefined) return new Date(+m[3], mo, +m[2]);
    }
    if ((m = s.match(/^(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})$/i))) {
      const mo = MONTHS[m[2].toLowerCase()];
      if (mo !== undefined) return new Date(+m[3], mo, +m[1]);
    }
    throw new Error('Cannot read date: ' + raw);
  }
  // format from local parts: toISOString() converts to UTC first, which
  // shifts a local-midnight date back a day east of Greenwich
  const iso = d => d ? d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0') : '';
  const daysBetween = (a, b) => Math.round((a - b) / 86400000);

  // ---------- IBAN --------------------------------------------------------
  const IBAN_RE = /\b([A-Z]{2}\d{2}(?: ?[A-Z0-9]){10,30})\b/g;
  function ibanChecksumOk(candidate) {
    const s = String(candidate || '').toUpperCase().replace(/\s/g, '');
    if (s.length < 15 || s.length > 34) return false;
    if (!/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(s)) return false;
    const re = s.slice(4) + s.slice(0, 4);
    let digits = '';
    for (const ch of re) {
      if (ch >= '0' && ch <= '9') digits += ch;
      else digits += (ch.charCodeAt(0) - 55).toString();
    }
    // mod 97 in chunks — the number is far beyond Number.MAX_SAFE_INTEGER
    let rem = 0;
    for (const d of digits) rem = (rem * 10 + (+d)) % 97;
    return rem === 1;
  }
  function findIban(text) {
    const up = String(text || '').toUpperCase();
    IBAN_RE.lastIndex = 0;
    let m;
    while ((m = IBAN_RE.exec(up))) {
      const raw = m[1].replace(/ /g, '');
      for (let end = raw.length; end > 14; end--) {
        if (ibanChecksumOk(raw.slice(0, end))) return raw.slice(0, end);
      }
    }
    return '';
  }

  // ---------- invoice field extraction -----------------------------------
  const TOTAL_LABELS = ['total\\s*(?:amount)?\\s*(?:due|to\\s*pay)?', 'grand\\s*total',
    'amount\\s*due', 'totaal(?:bedrag)?', 'te\\s*betalen', 'totaal\\s*incl',
    'incl\\.?\\s*btw', 'total\\s*factura', 'importe\\s*total', 'a\\s*pagar', 'gesamtbetrag'];
  const TOTAL_RE = new RegExp('\\b(?:' + TOTAL_LABELS.join('|') + ')\\b[^\\d\\n]{0,25}?(\\d[\\d.,\\s]{1,18}\\d)', 'gi');
  const INVOICE_RE = /(?:invoice|factuur|factura|rechnung|inv)\s*(?:no\.?|nr\.?|number|nummer|n[ºo]\.?|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/\.]{2,24})/gi;

  function findTotal(text) {
    let best = null;
    TOTAL_RE.lastIndex = 0;
    let m;
    while ((m = TOTAL_RE.exec(text))) {
      let v;
      try { v = Math.abs(parseAmount(m[1])); } catch (e) { continue; }
      if (v > 0 && (best === null || v > best)) best = v;
    }
    return best;
  }
  function findInvoiceNumber(text) {
    INVOICE_RE.lastIndex = 0;
    let m;
    while ((m = INVOICE_RE.exec(text))) {
      const c = m[1].replace(/^[.\-\/]+|[.\-\/]+$/g, '');
      if (/\d/.test(c) && c.length >= 3) return c;
    }
    return '';
  }
  function findDate(text) {
    let m = String(text).match(/\b(\d{1,2})[-\/.](\d{1,2})[-\/.](20\d{2})\b/);
    if (m) { const d = new Date(+m[3], +m[2] - 1, +m[1]); if (!isNaN(d)) return d; }
    m = String(text).match(/\b(20\d{2})[-\/.](\d{1,2})[-\/.](\d{1,2})\b/);
    if (m) { const d = new Date(+m[1], +m[2] - 1, +m[3]); if (!isNaN(d)) return d; }
    return null;
  }

  // ---------- similarity --------------------------------------------------
  const NOISE = new Set(['bv','b','v','nv','sl','sa','ltd','gmbh','the','de','van','der',
    'den','het','een','and','en','invoice','factuur','factura','inc','co','com','www','nl','es']);
  function tokens(t) {
    const out = new Set();
    for (const w of String(t || '').toLowerCase().match(/[a-z0-9]+/g) || [])
      if (w.length > 2 && !NOISE.has(w)) out.add(w);
    return out;
  }
  function nameSimilarity(a, b) {
    const ta = tokens(a), tb = tokens(b);
    if (!ta.size || !tb.size) return 0;
    let shared = 0;
    for (const w of ta) if (tb.has(w)) shared++;
    return shared / Math.min(ta.size, tb.size);
  }
  const normRef = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  function referenceHit(invoiceNumber, haystack) {
    const ref = normRef(invoiceNumber);
    if (ref.length < 4) return false;
    return normRef(haystack).includes(ref);
  }

  // ---------- scoring -----------------------------------------------------
  function score(txn, doc) {
    let s = 0; const reasons = [];
    const hay = (txn.counterparty + ' ' + txn.description).trim();

    if (doc.total != null) {
      const diff = Math.abs(doc.total - txn.amount);
      if (diff < 0.005) { s += 0.45; reasons.push('Amount matches exactly (' + fmt(txn.amount) + ').'); }
      else if (diff <= 0.02) { s += 0.40; reasons.push('Amount matches to the cent.'); }
      else if (txn.amount && diff / txn.amount <= 0.01) { s += 0.22; reasons.push('Amount within 1%.'); }
      else { s -= 0.25; reasons.push('Amounts differ: ' + fmt(txn.amount) + ' vs ' + fmt(doc.total) + '.'); }
    } else {
      reasons.push('No total could be read from the document.');
    }

    if (doc.invoiceNumber && referenceHit(doc.invoiceNumber, hay)) {
      s += 0.40; reasons.push('Invoice number ' + doc.invoiceNumber + ' appears in the payment description.');
    }

    const sim = Math.max(nameSimilarity(doc.supplier, hay), nameSimilarity(doc.emailFrom, hay));
    if (sim >= 0.8) { s += 0.25; reasons.push('Supplier name matches the counterparty (' + Math.round(sim * 100) + '%).'); }
    else if (sim >= 0.4) { s += 0.12; reasons.push('Supplier name partly matches (' + Math.round(sim * 100) + '%).'); }

    if (doc.iban && txn.counterpartyIban && doc.iban === txn.counterpartyIban) {
      s += 0.30; reasons.push('IBAN on the invoice matches the counterparty account.');
    }

    const d = doc.docDate || doc.emailDate;
    if (d) {
      const gap = daysBetween(txn.date, d);
      if (gap >= -MAX_DAYS_BEFORE && gap <= MAX_DAYS_AFTER) {
        s += 0.15 * Math.max(0, 1 - Math.max(0, gap) / MAX_DAYS_AFTER);
        reasons.push(gap >= 0 ? 'Paid ' + gap + ' days after the document date.'
                              : 'Paid ' + (-gap) + ' days before the document date.');
      } else if (gap < -MAX_DAYS_BEFORE) {
        return { score: 0, reasons: ['Document is dated ' + (-gap) + ' days after the payment — it cannot explain it.'] };
      } else {
        s -= 0.30; reasons.push('Document is ' + gap + ' days older than the payment — outside the window.');
      }
    }

    if (txn.direction === 'out') s += 0.02;
    return { score: Math.max(0, Math.min(1, s)), reasons };
  }

  function match(txns, docs, autoThreshold) {
    autoThreshold = autoThreshold == null ? AUTO_THRESHOLD : autoThreshold;
    const cands = [];
    txns.forEach((t, ti) => docs.forEach((d, di) => {
      const r = score(t, d);
      if (r.score >= REVIEW_THRESHOLD) cands.push({ s: r.score, ti, di, why: r.reasons });
    }));
    cands.sort((a, b) => b.s - a.s);
    const takenT = new Set(), takenD = new Set(), res = {};
    for (const c of cands) {
      if (takenT.has(c.ti) || takenD.has(c.di)) continue;
      takenT.add(c.ti); takenD.add(c.di);
      res[c.ti] = { transaction: txns[c.ti], document: docs[c.di], score: Math.round(c.s * 1000) / 1000,
                    confidence: c.s >= autoThreshold ? 'matched' : 'review', reasons: c.why };
    }
    const out = txns.map((t, i) => res[i] || { transaction: t, document: null, score: 0,
      confidence: 'none', reasons: ['No document provided explains this payment.'] });
    const usedDocs = new Set(Object.values(res).map(m => m.document));
    return { matches: out, leftover: docs.filter(d => !usedDocs.has(d)) };
  }

  const fmt = n => (n == null ? '' : Number(n).toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

  global.BankMatch = { parseAmount, parseDate, iso, ibanChecksumOk, findIban, findTotal,
    findInvoiceNumber, findDate, nameSimilarity, referenceHit, score, match, fmt,
    AUTO_THRESHOLD, REVIEW_THRESHOLD };
})(window);
