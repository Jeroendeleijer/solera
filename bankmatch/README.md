# bankmatch

Pairs bank transactions with the invoices sitting in your mailbox, and produces
one workbook your accountant can work from.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# try it with no mailbox at all
.venv/bin/python -m bankmatch.cli --statement sample/sample-statement.csv --no-mail --out out

# a folder of invoices instead of email
.venv/bin/python -m bankmatch.cli --statement bank.xlsx --docs ~/invoices --out out

# the real thing
cp .env.example .env      # fill it in
set -a; source .env; set +a
.venv/bin/python -m bankmatch.cli --statement bank.xlsx --since 2026-01-01 --out out
```

## Browser version

https://jeroendeleijer.github.io/solera/bankmatch/web/

Drop a bank export and a pile of invoice PDFs in; the matching runs entirely in
the page. **Nothing is uploaded** — you can disconnect from the network and it
still works, which for bank data is the point. Results download as CSV.

It cannot read your mailbox: IMAP needs a server, and a browser has none. For
that, use the command line below.

`web/engine.js` is a port of the Python matcher and is held to the same cases —
open the page and run the checks in `web/selftest.js` from the console.

## What it produces

`out/for-accountant.xlsx`, with a sheet per outcome:

| Sheet | What is in it |
|---|---|
| **Matched** | Score ≥ 0.80. Safe to hand over. |
| **Review** | 0.50–0.79. Plausible, wants a human glance. |
| **No document** | A payment with nothing in the mailbox to explain it. |
| **Documents without a payment** | An invoice that was never paid, or paid from elsewhere. |
| **Rows not read** | Statement lines that could not be parsed, with the reason. |

Plus `out/documents/`, the attachments renamed
`2026-03-14__Acme-Supplies__EUR-121.00__INV-2026-0042.pdf` — so the filename
alone says what the paper is, and the workbook points at it.

## How the matching works

Every pair is scored, and **every match carries the reasons it scored what it
did**, so your accountant can disagree with any single row rather than having
to trust the lot.

| Signal | Weight |
|---|---|
| Amount matches exactly | +0.45 |
| Invoice number quoted in the payment description | +0.40 |
| IBAN on the invoice matches the counterparty account | +0.30 |
| Supplier name matches the counterparty | +0.25 |
| Payment shortly after the invoice date | up to +0.15 |
| Amounts differ | −0.25 |
| Invoice dated *after* the payment | disqualified outright |

One invoice pairs with at most one transaction and vice versa, assigned best
score first — so a strong pair is never stolen by a weaker one seen earlier.

## Decisions worth knowing about

**Nothing is silently dropped.** A statement row that cannot be parsed is
reported in its own sheet, not skipped. An amount cell reading `n/a` raises
rather than becoming `0.00` — silent zeros are how reconciliations go wrong.

**Money is `Decimal`, never `float`.**

**IBANs are checksum-verified**, not regex-guessed. The ISO 13616 mod-97 check
is what stops `NL69TEST0000000001 TNV` being read with `TNV` glued on. On a
real ING export of 118 rows, 111 IBANs were extracted and all 111 validated.

**Amount parsing handles what real exports actually contain**: `1.234,56` and
`1,234.56`, a U+2212 minus, trailing minus, accounting parentheses, and any
currency symbol. Each of these came from a genuine file, not from imagination.

**Your mailbox is opened read-only.** Nothing is deleted, moved, or marked
read. Attachments are copied out; the originals stay put.

**Credentials live in `.env` and nowhere else** — not on the command line
(shell history), not in this repo (`.env` is gitignored), and never typed into
a chat window. Use an app-specific password, not your account password.

## Limits

- A scanned invoice with no text layer yields no amount or number. It is
  listed as `no text layer` rather than guessed at. OCR would be the next step.
- Statement formats: ING (NL) CSV and generic `Date`/`Description`/`Amount`
  layouts, `.csv` and `.xlsx`. Another bank means adding a mapping in
  `statements.py` — about six lines.
- Attachment types: PDF, PNG, JPG. Only PDFs are read for text.
- IMAP only for now. It works for Gmail, Microsoft 365 and most hosts.

## Tests

```bash
python3 -m unittest discover -s tests -t .    # 24 tests, no dependencies needed
```
