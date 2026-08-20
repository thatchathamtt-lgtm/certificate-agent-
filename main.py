"""
HTTP entrypoint for Cloud Run. Cloud Scheduler calls this endpoint every
N minutes (e.g. every 5 min via a cron expression) with a shared-secret
header; each call does exactly one "check inbox, process, send" pass, then
exits. There is no long-running background loop -- this is what makes it a
true zero-maintenance serverless setup (scales to zero between runs, you
are only billed for the seconds it actually executes).
"""
import os
import logging
import tempfile
import traceback

from flask import Flask, request, jsonify

import config
import gmail_client
from certificate_pipeline import generate_certificates

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/", methods=["POST", "GET"])
def run_once():
    # Shared-secret check so random internet traffic can't trigger this.
    secret = request.headers.get("X-Trigger-Secret", "")
    if config.TRIGGER_SECRET and secret != config.TRIGGER_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    processed = []
    errors = []

    try:
        matches = gmail_client.fetch_matching_emails(config.SUBJECT_KEYWORD)
    except Exception:
        log.exception("Failed to fetch emails")
        return jsonify({"error": "gmail_fetch_failed", "trace": traceback.format_exc()}), 500

    log.info("Found %d matching email(s)", len(matches))

    for item in matches:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                xlsx_path = os.path.join(tmp, item["xlsx_name"] or "roster.xlsx")
                with open(xlsx_path, "wb") as f:
                    f.write(item["xlsx_bytes"])

                pdf_path, names, date_str, date_flag_note = generate_certificates(xlsx_path, tmp)

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
            processed.append({"subject": item["subject"], "count": len(names), "date": date_str})

        except Exception:
            log.exception("Failed to process email: %s", item.get("subject"))
            errors.append({"subject": item.get("subject"), "trace": traceback.format_exc()})
            # Deliberately do NOT mark_seen on failure, so it gets retried
            # on the next scheduled run instead of being silently dropped.

    return jsonify({"processed": processed, "errors": errors})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
