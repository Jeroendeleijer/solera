/* bankmatch browser app — file handling, statement parsing, PDF text, UI.
 * All local. The only network requests this page makes are the two CDN
 * script tags and the webfont.
 */
(function () {
  'use strict';
  const BM = window.BankMatch;
  const $ = id => document.getElementById(id);
  if (window.pdfjsLib) {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  }

  let statement = null;     // {transactions, skipped, fmt, name}
  let documents = [];
  let result = null;

  // ---------- statement parsing (mirrors statements.py) -------------------
  const MAPPINGS = [
    { name: 'ING (NL)',
      need: ['datum', 'naam / omschrijving', 'bedrag (eur)', 'af bij'],
      f: { date: 'datum', counterparty: 'naam / omschrijving', amount: 'bedrag (eur)',
           dirflag: 'af bij', description: 'mededelingen', account: 'rekening',
           counterIban: 'tegenrekening' },
      debit: ['af'] },
    { name: 'generic signed',
      need: ['date', 'description'],
      f: { date: 'date', counterparty: 'description', amount: 'amount (eur)', description: 'description' },
      debit: [] },
  ];

  const normHeader = h => String(h == null ? '' : h).trim().replace(/^﻿/, '').replace(/^"|"$/g, '').toLowerCase();

  function pickMapping(headers) {
    const hs = new Set(headers);
    for (const m of MAPPINGS) if (m.need.every(n => hs.has(n))) return m;
    const amountCol = headers.find(h => h.startsWith('amount'));
    if (hs.has('date') && amountCol) {
      const m = JSON.parse(JSON.stringify(MAPPINGS[1]));
      m.f.amount = amountCol;
      return m;
    }
    throw new Error('Unrecognised layout. Columns seen: ' + headers.join(', '));
  }

  function rowsToStatement(rows, sourceName) {
    if (!rows.length) throw new Error('The file has no rows.');
    let headerIdx = -1, mapping = null;
    for (let i = 0; i < Math.min(rows.length, 25); i++) {
      try { mapping = pickMapping(rows[i].map(normHeader)); headerIdx = i; break; } catch (e) {}
    }
    if (headerIdx < 0) throw new Error('No recognisable header row in the first 25 lines.');
    const headers = rows[headerIdx].map(normHeader);
    const txns = [], skipped = [];
    for (let i = headerIdx + 1; i < rows.length; i++) {
      const r = rows[i];
      if (!r.some(c => String(c == null ? '' : c).trim())) continue;
      const cells = {};
      headers.forEach((h, j) => cells[h] = r[j]);
      try {
        const rawDate = cells[mapping.f.date];
        if (!String(rawDate == null ? '' : rawDate).trim()) continue;
        const amount = BM.parseAmount(cells[mapping.f.amount] == null ? '0' : cells[mapping.f.amount]);
        const flag = String(cells[mapping.f.dirflag] == null ? '' : cells[mapping.f.dirflag]).trim().toLowerCase();
        const direction = flag ? (mapping.debit.includes(flag) ? 'out' : 'in') : (amount < 0 ? 'out' : 'in');
        const desc = String(cells[mapping.f.description] == null ? '' : cells[mapping.f.description]);
        txns.push({
          date: BM.parseDate(rawDate),
          amount: Math.abs(amount),
          direction,
          counterparty: String(cells[mapping.f.counterparty] == null ? '' : cells[mapping.f.counterparty]).trim(),
          counterpartyIban: BM.findIban(String(cells[mapping.f.counterIban] == null ? '' : cells[mapping.f.counterIban]) || desc),
          description: desc.trim(),
          row: i + 1,
        });
      } catch (err) {
        skipped.push({ row: i + 1, reason: err.message, content: r.slice(0, 3).join(' | ') });
      }
    }
    return { transactions: txns, skipped, fmt: mapping.name, name: sourceName };
  }

  function parseCsv(text) {
    const delim = (text.split(';').length > text.split(',').length) ? ';' : ',';
    const rows = []; let row = [], cell = '', inQ = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQ) {
        if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else inQ = false; }
        else cell += c;
      } else if (c === '"') inQ = true;
      else if (c === delim) { row.push(cell); cell = ''; }
      else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
      else if (c !== '\r') cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }

  async function readStatement(file) {
    const isXlsx = /\.(xlsx|xlsm)$/i.test(file.name);
    if (isXlsx) {
      if (!window.XLSX) throw new Error('The spreadsheet reader did not load — check your connection and reload.');
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: 'array', cellDates: true });
      const ws = wb.Sheets[wb.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: '' });
      return rowsToStatement(rows, file.name);
    }
    return rowsToStatement(parseCsv(await file.text()), file.name);
  }

  // ---------- documents ---------------------------------------------------
  async function pdfText(file) {
    if (!window.pdfjsLib) return '';
    try {
      const doc = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
      let out = '';
      for (let p = 1; p <= Math.min(doc.numPages, 4); p++) {
        const page = await doc.getPage(p);
        const tc = await page.getTextContent();
        out += tc.items.map(i => i.str).join(' ') + '\n';
      }
      return out;
    } catch (e) { return ''; }
  }

  async function buildDocument(file) {
    const text = /\.pdf$/i.test(file.name) ? await pdfText(file) : '';
    const stem = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
    const combined = text + '\n' + stem;
    return {
      filename: file.name,
      supplier: stem.split(/\s+/).slice(0, 4).join(' '),
      invoiceNumber: BM.findInvoiceNumber(combined),
      total: text ? BM.findTotal(text) : null,
      docDate: text ? BM.findDate(text) : null,
      iban: BM.findIban(text),
      emailFrom: '', emailSubject: '', emailDate: null,
      textLen: text.length,
    };
  }

  // ---------- wiring ------------------------------------------------------
  function wireDrop(dropId, inputId, onFiles) {
    const drop = $(dropId), input = $(inputId);
    drop.addEventListener('click', () => input.click());
    drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    input.addEventListener('change', () => onFiles([...input.files]));
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => onFiles([...e.dataTransfer.files]));
  }

  function setStatus(msg) { $('status').textContent = msg || ''; }

  wireDrop('drop-stmt', 'file-stmt', async files => {
    if (!files.length) return;
    setStatus('Reading the statement…');
    try {
      statement = await readStatement(files[0]);
      $('drop-stmt').classList.add('filled');
      $('stmt-label').textContent = statement.name;
      $('stmt-list').innerHTML = '<li>' + statement.transactions.length + ' transactions · format: ' + statement.fmt +
        (statement.skipped.length ? ' · ' + statement.skipped.length + ' rows not read' : '') + '</li>';
      setStatus('');
    } catch (e) {
      statement = null;
      $('drop-stmt').classList.remove('filled');
      $('stmt-label').textContent = 'Could not read that file';
      $('stmt-list').innerHTML = '<li>' + e.message + '</li>';
      setStatus('');
    }
    $('run').disabled = !statement;
  });

  wireDrop('drop-docs', 'file-docs', async files => {
    const pdfs = files.filter(f => /\.pdf$/i.test(f.name));
    if (!pdfs.length) return;
    setStatus('Reading ' + pdfs.length + ' document(s)…');
    documents = [];
    for (const f of pdfs) documents.push(await buildDocument(f));
    const unreadable = documents.filter(d => d.textLen < 40).length;
    $('drop-docs').classList.add('filled');
    $('docs-label').textContent = documents.length + ' invoice' + (documents.length === 1 ? '' : 's');
    $('docs-list').innerHTML = documents.slice(0, 40).map(d =>
      '<li>' + esc(d.filename) + (d.total != null ? ' — ' + BM.fmt(d.total) : ' — no total found') + '</li>').join('') +
      (unreadable ? '<li><strong>' + unreadable + ' had no text layer</strong></li>' : '');
    setStatus('');
  });

  $('run').addEventListener('click', () => {
    if (!statement) return;
    setStatus('Matching…');
    result = BM.match(statement.transactions, documents);
    const c = { matched: 0, review: 0, none: 0 };
    result.matches.forEach(m => c[m.confidence]++);
    $('t-matched').textContent = c.matched;
    $('t-review').textContent = c.review;
    $('t-none').textContent = c.none;
    $('t-left').textContent = result.leftover.length;
    $('results').hidden = false;
    $('download').disabled = false;
    showTab('matched');
    setStatus('');
  });

  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

  function rowsFor(tab) {
    if (tab === 'left') return result.leftover.map(d => ({ doc: d }));
    if (tab === 'skipped') return statement.skipped.map(s => ({ skip: s }));
    return result.matches.filter(m => m.confidence === tab);
  }

  function showTab(tab) {
    document.querySelectorAll('.tabs button').forEach(b =>
      b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    const rows = rowsFor(tab);
    if (!rows.length) { $('panel').innerHTML = '<p class="empty">Nothing in this list.</p>'; return; }

    if (tab === 'skipped') {
      $('panel').innerHTML = '<table><thead><tr><th>Row</th><th>Reason</th><th>Content</th></tr></thead><tbody>' +
        rows.map(r => '<tr><td class="num">' + r.skip.row + '</td><td>' + esc(r.skip.reason) + '</td><td class="why">' + esc(r.skip.content) + '</td></tr>').join('') +
        '</tbody></table>';
      return;
    }
    if (tab === 'left') {
      $('panel').innerHTML = '<table><thead><tr><th>Document</th><th>Invoice no.</th><th class="num">Total</th><th>Date</th><th>Readable</th></tr></thead><tbody>' +
        rows.map(r => '<tr><td>' + esc(r.doc.filename) + '</td><td>' + esc(r.doc.invoiceNumber) + '</td><td class="num">' +
          (r.doc.total != null ? BM.fmt(r.doc.total) : '—') + '</td><td>' + BM.iso(r.doc.docDate) + '</td><td>' +
          (r.doc.textLen > 40 ? 'yes' : 'no text layer') + '</td></tr>').join('') + '</tbody></table>';
      return;
    }
    $('panel').innerHTML = '<table><thead><tr><th>Date</th><th class="num">Amount</th><th>Counterparty</th><th>Document</th><th class="num">Score</th><th>Why</th></tr></thead><tbody>' +
      rows.map(m => '<tr><td>' + BM.iso(m.transaction.date) + '</td><td class="num">' + BM.fmt(m.transaction.amount) +
        '</td><td>' + esc(m.transaction.counterparty || m.transaction.description.slice(0, 40)) + '</td><td>' +
        (m.document ? esc(m.document.filename) : '—') + '</td><td class="num">' +
        (m.score ? '<span class="pill ' + m.confidence + '">' + m.score.toFixed(2) + '</span>' : '—') +
        '</td><td class="why">' + esc(m.reasons.join(' ')) + '</td></tr>').join('') + '</tbody></table>';
  }

  document.querySelectorAll('.tabs button').forEach(b =>
    b.addEventListener('click', () => showTab(b.dataset.tab)));

  $('download').addEventListener('click', () => {
    const head = ['Status', 'Date', 'Amount', 'Direction', 'Counterparty', 'Description',
                  'Document', 'Invoice no.', 'Doc total', 'Doc date', 'Score', 'Why'];
    const q = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
    const lines = [head.map(q).join(',')];
    result.matches.forEach(m => lines.push([m.confidence, BM.iso(m.transaction.date), m.transaction.amount,
      m.transaction.direction, m.transaction.counterparty, m.transaction.description,
      m.document ? m.document.filename : '', m.document ? m.document.invoiceNumber : '',
      m.document && m.document.total != null ? m.document.total : '',
      m.document ? BM.iso(m.document.docDate) : '', m.score, m.reasons.join(' ')].map(q).join(',')));
    result.leftover.forEach(d => lines.push(['unpaid-invoice', '', '', '', '', '', d.filename,
      d.invoiceNumber, d.total == null ? '' : d.total, BM.iso(d.docDate), '', 'No payment matched this document.'].map(q).join(',')));
    statement.skipped.forEach(s => lines.push(['row-not-read', '', '', '', '', s.content, '', '', '', '', '', s.reason].map(q).join(',')));
    const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'for-accountant.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  });
})();
