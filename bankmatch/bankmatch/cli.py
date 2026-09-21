"""Command line entry point.

  python3 -m bankmatch.cli --statement bank.xlsx --since 2026-01-01 --out out/
  python3 -m bankmatch.cli --statement bank.csv --docs ~/invoices --no-mail

Nothing is sent anywhere. The mailbox is opened read-only; attachments are
copied out, and your mail is never modified.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import extract, matching, report
from .mail import load_dotenv
from .model import Confidence
from .statements import read_statement, UnknownStatementFormat


def _d(s: str) -> date:
    return datetime.strptime(s, '%Y-%m-%d').date()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='bankmatch', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--statement', required=True, help='bank export (.xlsx or .csv)')
    ap.add_argument('--out', default='out', help='output directory (default: out)')
    ap.add_argument('--since', type=_d, help='only fetch mail from this date (YYYY-MM-DD)')
    ap.add_argument('--until', type=_d, help='only fetch mail up to this date')
    ap.add_argument('--folder', default='INBOX', help='mailbox folder to search')
    ap.add_argument('--docs', help='use a local folder of invoices instead of mail')
    ap.add_argument('--no-mail', action='store_true', help='skip the mailbox entirely')
    ap.add_argument('--threshold', type=float, default=matching.AUTO_THRESHOLD,
                    help=f'auto-match above this score (default {matching.AUTO_THRESHOLD})')
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    try:
        stmt = read_statement(a.statement)
    except UnknownStatementFormat as e:
        print(f"Could not read the statement: {e}", file=sys.stderr)
        return 2
    print(f"Statement  : {len(stmt.transactions)} transactions read ({stmt.fmt})")
    if stmt.skipped:
        print(f"             {len(stmt.skipped)} rows skipped — listed in the report")

    docs = []
    if a.docs:
        folder = Path(a.docs)
        files = [p for p in folder.rglob('*') if p.suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg')]
        docs = [extract.build_document(p) for p in files]
        print(f"Documents  : {len(docs)} files from {folder}")
    elif not a.no_mail:
        load_dotenv()
        from .mail import fetch_attachments, MailConfigError
        since = a.since or min((t.date for t in stmt.transactions), default=date.today())
        try:
            found = fetch_attachments(out / 'attachments', since=since, until=a.until,
                                      folder=a.folder)
        except MailConfigError as e:
            print(f"\nMailbox not configured.\n{e}\n", file=sys.stderr)
            return 3
        docs = [extract.build_document(f['path'], email_subject=f['subject'],
                                       email_from=f['from'], email_date=f['date'])
                for f in found]
        print(f"Mailbox    : {len(docs)} attachments since {since}")

    unreadable = sum(1 for d in docs if d.text_len < 40)
    if unreadable:
        print(f"             {unreadable} had no readable text layer (scans) — listed separately")

    matches = matching.match(stmt.transactions, docs, auto_threshold=a.threshold)
    leftover = matching.unmatched_documents(docs, matches)

    path = out / 'for-accountant.xlsx'
    counts = report.write_report(path, matches, leftover,
                                 skipped_rows=stmt.skipped,
                                 copy_docs_to=out / 'documents')
    print()
    for k, v in counts.items():
        print(f"  {k:30s} {v}")
    print(f"\nWrote {path}")
    print(f"Documents copied to {out / 'documents'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
