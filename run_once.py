"""
Standalone entrypoint for running one "check inbox -> generate -> send" pass.
Used by GitHub Actions (a scheduled workflow just runs this script directly
and exits) instead of the Cloud Run HTTP version in main.py.

Both main.py (Cloud Run) and this file share the same underlying logic in
certificate_pipeline.py and gmail_client.py -- only the trigger mechanism
differs.
"""
import os
import sys
import logging
import tempfile

import config
import gmail_client
from certificate_pipeline import generate_certificates, parse_signatories_from_subject

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    missing = [k for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "DESTINATION_EMAIL")
               if not getattr(config, k)]
    if missing:
        log.error("Missing required environment variable(s): %s", ", ".join(missing))
        sys.exit(1)

    try:
        matches = gmail_client.fetch_matching_emails(config.SUBJECT_KEYWORD)
    except Exception:
        log.exception("Failed to fetch emails")
        sys.exit(1)

    log.info("Found %d matching email(s)", len(matches))
    had_error = False

    for item in matches:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                xlsx_path = os.path.join(tmp, item["xlsx_name"] or "roster.xlsx")
                with open(xlsx_path, "wb") as f:
                    f.write(item["xlsx_bytes"])

                signatories = parse_signatories_from_subject(item["subject"])
                pdf_path, names, date_str, date_flag_note = generate_certificates(
                    xlsx_path, tmp, signatories=signatories
                )

                dest = config.DESTINATION_EMAIL or item["from"]
                subject = f"Certificates generated - {date_str} ({len(names)} people)"
                body = (
                    f"Attached: {len(names)} certificates dated {date_str}.\n"
                    f"Source file: {item['xlsx_name']}\n"
                    f"From: {item['from']}\n"
                )
                if date_flag_note:
                    subject = "[CHECK DATE] " + subject
                    body += f"\n{date_flag_note}\n"

                gmail_client.send_email_with_attachments(dest, subject, body, [pdf_path])

            gmail_client.mark_seen(item["uid"])
            log.info("Processed '%s' -> %d certificates", item["subject"], len(names))

        except Exception:
            log.exception("Failed to process email: %s", item.get("subject"))
            had_error = True
            # Not marking as seen -> will retry on the next scheduled run.

    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
