"""
Gmail access via plain IMAP (search/download) + SMTP (send). This is the
simplest possible setup: no Google Cloud OAuth consent screen, no
service-account JSON, no token refresh logic to maintain -- just a Gmail
address + a 16-character "App Password".

Setup (one-time, ~2 minutes):
  1. On the Gmail account that should be watched, turn on 2-Step
     Verification: https://myaccount.google.com/security
  2. Create an App Password: https://myaccount.google.com/apppasswords
     (choose "Mail" / "Other" as the app name)
  3. Put the resulting 16-character password in the GMAIL_APP_PASSWORD
     environment variable (never the real account password).

Trade-off vs OAuth: this account can only be a regular Gmail account (not
locked down by an org policy that disables IMAP/App Passwords). If your
Workspace admin disables App Passwords, use OAuth + the Gmail API instead --
happy to provide that version too.
"""
import imaplib
import smtplib
import email
import logging
from email.message import EmailMessage
from email.header import decode_header

import config

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _normalize_charset(enc):
    """Some mail clients label Thai text as 'windows-874', but Python's
    codec registry only recognizes the equivalent name 'cp874' -- map the
    common aliases here so decode_header() doesn't crash on them."""
    if not enc:
        return "utf-8"
    aliases = {
        "windows-874": "cp874",
        "tis-620": "cp874",
        "iso-8859-11": "cp874",
    }
    return aliases.get(enc.lower(), enc)


def _decode(value):
    parts = decode_header(value)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            charset = _normalize_charset(enc)
            try:
                out += text.decode(charset)
            except (LookupError, UnicodeDecodeError):
                out += text.decode(charset, errors="replace")
        else:
            out += text
    return out

def fetch_matching_emails(subject_keyword):
    """Returns a list of dicts: {uid, from, subject, xlsx_bytes, xlsx_name}
    for UNSEEN emails whose subject contains subject_keyword and that have
    an .xlsx attachment. Does NOT mark them as seen (caller does that only
    after successfully processing, so a crash mid-run doesn't lose an
    email)."""
    results = []
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
    imap.select("INBOX")

    status, uids = imap.search(None, "UNSEEN")
    if status != "OK":
        imap.logout()
        return results

    for uid in uids[0].split():
        status, msg_data = imap.fetch(uid, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        subject = _decode(msg.get("Subject", ""))
        if subject_keyword not in subject:
            continue

        xlsx_bytes, xlsx_name = None, None
        for part in msg.walk():
            filename = part.get_filename()
            if filename and filename.lower().endswith(".xlsx"):
                xlsx_bytes = part.get_payload(decode=True)
                xlsx_name = _decode(filename)
                break

        if xlsx_bytes is None:
            log.info("Skipping email %s (subject matched but no .xlsx attachment)", subject)
            continue

        results.append({
            "uid": uid,
            "from": _decode(msg.get("From", "")),
            "subject": subject,
            "xlsx_bytes": xlsx_bytes,
            "xlsx_name": xlsx_name,
        })

    imap.logout()
    return results


def mark_seen(uid):
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
    imap.select("INBOX")
    imap.store(uid, "+FLAGS", "\\Seen")
    imap.logout()


def send_email_with_attachments(to_addr, subject, body, attachment_paths):
    msg = EmailMessage()
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    for path in attachment_paths:
        with open(path, "rb") as f:
            data = f.read()
        maintype = "application"
        subtype = "pdf" if path.lower().endswith(".pdf") else "octet-stream"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.split("/")[-1])

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        smtp.send_message(msg)
    log.info("Sent email to %s with %d attachment(s)", to_addr, len(attachment_paths))
