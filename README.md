# Certificate Agent

Watches a Gmail inbox for emails whose subject contains a keyword (e.g.
"ขอใบ Cer") with an `.xlsx` roster attached, generates one PDF of
certificates (one page per person), and emails it to a fixed destination
address. Runs unattended on a schedule — no server to patch or babysit.

## How it works

```
Cloud Scheduler (every 5 min, cron)
        │  HTTP POST + X-Trigger-Secret header
        ▼
Cloud Run service (scales to zero between runs)
        │
        ├─ 1. IMAP: search UNSEEN emails, subject contains SUBJECT_KEYWORD
        ├─ 2. Download the .xlsx attachment
        ├─ 3. certificate_pipeline.generate_certificates(...)
        │        - parse names + date out of the xlsx
        │        - apply "คุณ" honorific rule
        │        - render each name via PIL+RAQM (Thai-safe shaping)
        │        - stamp name/date/signatures onto the template PDF
        ├─ 4. SMTP: send the resulting PDF to DESTINATION_EMAIL
        └─ 5. Mark the source email as read (only after a successful send)
```

Nothing runs continuously — each Cloud Scheduler tick spins up the
container, does one pass, and it scales back to zero. You only pay for the
seconds it's actually running (a few seconds per tick when the inbox is
empty).

## One-time setup (~15–20 minutes)

### 1. Gmail App Password
On the Gmail account you want the agent to watch:
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
   (app name: "Certificate Agent"). Copy the 16-character password.

> If this is a Google Workspace account and an admin has disabled App
> Passwords, use a dedicated free personal Gmail account instead for the
> "watcher" mailbox — much simpler than setting up OAuth for this use case.

### 2. Google Cloud project
1. Create a project (or reuse one): https://console.cloud.google.com
2. Enable **Cloud Run** and **Cloud Scheduler** APIs.
3. Install the `gcloud` CLI and run `gcloud init` to log in and select the project.

### 3. Deploy to Cloud Run
From this project folder:

```bash
gcloud run deploy certificate-agent \
  --source . \
  --region asia-southeast1 \
  --no-allow-unauthenticated \
  --set-env-vars GMAIL_ADDRESS=your-watcher@gmail.com \
  --set-env-vars GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx \
  --set-env-vars SUBJECT_KEYWORD="ขอใบ Cer" \
  --set-env-vars DESTINATION_EMAIL=hr@yourcompany.com \
  --set-env-vars TRIGGER_SECRET=$(openssl rand -hex 16)
```

`gcloud` will build the Docker image and deploy it automatically — no need
to build/push manually. Note the **Service URL** it prints at the end, and
keep the `TRIGGER_SECRET` value; you'll need both for the next step.

### 4. Schedule it (Cloud Scheduler)
```bash
gcloud scheduler jobs create http certificate-agent-trigger \
  --location asia-southeast1 \
  --schedule "*/5 * * * *" \
  --uri "<SERVICE_URL_FROM_STEP_3>" \
  --http-method POST \
  --headers "X-Trigger-Secret=<TRIGGER_SECRET_FROM_STEP_3>" \
  --oidc-service-account-email <PROJECT_NUMBER>-compute@developer.gserviceaccount.com
```
This calls the service every 5 minutes. Adjust the cron schedule as you like
(e.g. `*/15 * * * *` for every 15 min).

### 5. Test it
Send yourself an email with subject `ขอใบ Cer - test` and an `.xlsx` roster
attached. Within 5 minutes (or however you scheduled it) you should get a
reply at `DESTINATION_EMAIL` with the generated PDF.

You can also trigger a run manually to test without waiting:
```bash
curl -X POST "<SERVICE_URL>" -H "X-Trigger-Secret: <TRIGGER_SECRET>"
```

## Configuration reference (environment variables)

| Variable | Required | Description |
|---|---|---|
| `GMAIL_ADDRESS` | yes | The watcher mailbox's Gmail address |
| `GMAIL_APP_PASSWORD` | yes | 16-character App Password (not the real account password) |
| `SUBJECT_KEYWORD` | yes | Only emails whose subject contains this string are processed |
| `DESTINATION_EMAIL` | yes | Fixed address the finished certificates are sent to |
| `TRIGGER_SECRET` | recommended | Shared secret Cloud Scheduler must send; prevents random requests from triggering a run |

## xlsx format expectations

`certificate_pipeline.load_roster()` tries to be flexible, but for
reliable results your source file should have:

- A header row with a column containing "ชื่อ" or "Name" (the name column).
- Optionally a column containing "โรงงาน" / "Factory" / "Company" — any row
  where this equals `เฉลย` (an answer-key row from a quiz export) is
  automatically skipped.
- **The date**, found via (in priority order):
  1. Sheet name matching a pattern like `15Jun26`
  2. Any literal date value in row 1
  - If neither is present, the agent defaults to *today's date* and marks
    the email subject `[CHECK DATE] ...` plus adds a warning in the email
    body — **it will never silently guess wrong**, but it also won't halt.
    Best practice: always include a dated sheet name (`DDMonYY`) in
    source files feeding this agent.

Duplicate names (same person appearing more than once, e.g. multiple quiz
attempts) are automatically de-duplicated to one certificate per person.

## Known pitfalls this code specifically works around

These are documented so nobody "cleans up" the code and reintroduces a bug
that took real trial-and-error to find:

1. **Thai combining marks render in the wrong position with reportlab's
   native `drawString`** (e.g. the tone mark in "ปลื้ม" floats free /
   detaches from the base character). Fix: every name is rasterized via
   Pillow + libraqm (`name_render.py`, `layout_engine=ImageFont.Layout.RAQM`)
   and embedded as an image instead of drawn as vector text.
2. **A white "cover" rectangle sized/positioned even slightly too large
   clips the descenders (g, p, y) of the line above it.** The date
   cover-rect in particular sits just below an italic line — its
   dimensions were derived by pixel-measuring the real gap on the
   template, not guessed.
3. **A signature image scaled to fill its full bounding box can grow a
   long diagonal tail that overlaps the printed name/title text below
   it.** Fix: signatures are anchored to the *top* of their box with a
   capped max height (`fitted_box_top_anchored`), never stretched to fill.
4. **Draw order matters.** All "erase old content" white rectangles are
   drawn first, in one batch, *before* any new text/images are drawn. If a
   later rectangle is drawn after some new content that overlaps it
   spatially, it will silently erase part of that new content (this
   happened to the leading digit of a date once — "13 August" rendered as
   "3 August").

## Local testing (without deploying)

```bash
pip install -r requirements.txt
python3 -c "
from certificate_pipeline import generate_certificates
pdf_path, names, date_str, note = generate_certificates('path/to/roster.xlsx', 'out_dir')
print(pdf_path, date_str, len(names), note)
"
```

To test the Gmail parts without waiting for Cloud Scheduler, run the Flask
app locally (`python3 main.py`) and `curl` it as shown in step 5 above —
just make sure `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` are set in your shell
environment first.

## Customizing signatories / template

Edit `config.py` — `DEFAULT_SIGNATORIES` holds the left/right name, title,
division text and signature image path. Swap in different signature PNGs
under `assets/`, or point `TEMPLATE_PATH` at a different certificate PDF
(you'll need to re-measure the layout constants at the top of `config.py`
if the new template's layout differs — see the docstring there for how
those numbers were derived).
