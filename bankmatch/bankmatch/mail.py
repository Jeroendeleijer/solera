"""Fetching invoice attachments over IMAP.

Credentials are read from the environment only — never passed on the command
line (they would land in your shell history) and never typed into a chat.
Put them in a .env file that is gitignored; see .env.example.

IMAP with an app-specific password works for Gmail, Outlook/Microsoft 365,
Fastmail and most hosts, which is why it is the first adapter.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path
from typing import Iterator, Optional

ATTACHMENT_TYPES = {'.pdf', '.png', '.jpg', '.jpeg'}
SAFE = re.compile(r'[^A-Za-z0-9._-]+')


class MailConfigError(RuntimeError):
    pass


def _cfg(key: str, default: Optional[str] = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise MailConfigError(
            f"{key} is not set. Copy .env.example to .env and fill it in, then "
            f"run with:  set -a; source .env; set +a")
    return val


def load_dotenv(path: str | Path = '.env') -> None:
    """Minimal .env loader so no dependency is needed for the common case."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or '')))
    except Exception:
        return str(value or '')


def fetch_attachments(out_dir: str | Path, since: date, until: Optional[date] = None,
                      folder: str = 'INBOX', limit: int = 500) -> list[dict]:
    """Download invoice-shaped attachments in a date range.

    Returns metadata dicts; nothing is deleted, moved or marked read.
    """
    host = _cfg('IMAP_HOST')
    user = _cfg('IMAP_USER')
    password = _cfg('IMAP_PASSWORD')
    port = int(os.environ.get('IMAP_PORT', '993'))

    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    found: list[dict] = []

    with imaplib.IMAP4_SSL(host, port) as M:
        M.login(user, password)
        M.select(folder, readonly=True)          # readonly: we never change your mailbox
        crit = ['SINCE', since.strftime('%d-%b-%Y')]
        if until:
            crit += ['BEFORE', (until + timedelta(days=1)).strftime('%d-%b-%Y')]
        typ, data = M.search(None, *crit)
        ids = data[0].split()[-limit:]
        for num in ids:
            typ, msgdata = M.fetch(num, '(RFC822)')
            if typ != 'OK' or not msgdata or not msgdata[0]:
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            subject = _decode(msg.get('Subject'))
            sender = _decode(msg.get('From'))
            try:
                mdate = email.utils.parsedate_to_datetime(msg.get('Date')).date()
            except Exception:
                mdate = None
            for part in msg.walk():
                fn = part.get_filename()
                if not fn:
                    continue
                fn = _decode(fn)
                if Path(fn).suffix.lower() not in ATTACHMENT_TYPES:
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                safe = SAFE.sub('_', fn)[:120]
                target = out_dir / f"{num.decode()}_{safe}"
                target.write_bytes(payload)
                found.append({'path': str(target), 'filename': fn, 'subject': subject,
                              'from': sender, 'date': mdate})
    return found
