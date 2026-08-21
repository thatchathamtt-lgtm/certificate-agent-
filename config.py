"""
All the calibrated layout numbers below were measured directly off the
certificate template (Certificate_Template.pdf, landscape 780x540pt) by
inspecting text/image bounding boxes with pdfplumber. If you ever swap in a
different template, these will need to be re-measured.
"""
import os

# ---------------------------------------------------------------------------
# Paths (bundled inside the container image, see Dockerfile)
# ---------------------------------------------------------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
TEMPLATE_PATH = os.path.join(ASSETS_DIR, "Certificate_Template.pdf")
NAME_FONT_PATH = os.path.join(ASSETS_DIR, "angsa.ttf")

PAGE_W, PAGE_H = 780.009448818898, 540  # pt, landscape

# ---------------------------------------------------------------------------
# Name + date placement
# CENTER_X is the certificate's true visual center line, derived from the
# "Certificate of Training" title and "Awarded to:" bounding boxes -- NOT
# simply page_width / 2, because the printed layout is not perfectly
# symmetrical on the page.
# ---------------------------------------------------------------------------
CENTER_X = 393.3

NAME_FONT_SIZE = 28
NAME_BASELINE_Y = 303.449
NAME_COVER_RECT = (150, 282, 480, 50)       # x, y, w, h (pdf bottom-up)

DATE_FONT = "Helvetica"
DATE_FONT_SIZE = 14.003
DATE_BASELINE_Y = 184.45
DATE_COVER_RECT = (290, 180, 220, 16)

# ---------------------------------------------------------------------------
# Thai honorific rule
#   - Thai-script name -> prefix "คุณ" unless it already carries a Thai
#     honorific (นาย / นาง / นางสาว / น.ส. / คุณ)
#   - Non-Thai (English) name -> used as-is, no prefix
# ---------------------------------------------------------------------------
THAI_HONORIFICS = ("นางสาว", "น.ส.", "นาย", "นาง", "คุณ")


def is_thai(text: str) -> bool:
    return any("\u0e00" <= ch <= "\u0e7f" for ch in text)


def apply_honorific(name: str) -> str:
    if is_thai(name) and not name.startswith(THAI_HONORIFICS):
        return f"คุณ{name}"
    return name


# ---------------------------------------------------------------------------
# Signatory blocks. FOOTER_FONT is a standard Latin font (Helvetica) since
# these lines are always Latin-script job titles / English names.
#
# Each signature is drawn "top-anchored" (pinned to the top of its box, with
# a capped max height) rather than stretched to fill the box, because a long
# signature tail scaled to fill height can dip down and visually collide
# with the printed name/title line below it.
# ---------------------------------------------------------------------------
FOOTER_FONT = "Helvetica"
FOOTER_NAME_SIZE = 9.01
FOOTER_SUB_SIZE = 10.01

LEFT_COVER_RECT = (145, 115, 205, 80)     # covers old signature + 3 text lines
RIGHT_COVER_RECT = (508, 115, 197, 80)    # covers old signature + 3 text lines

LEFT_SIG_BOX = (150.009, 150.888, 105.222, 41.414)   # x, y, w, h (pdf bottom-up)
RIGHT_SIG_BOX = (514.431, 144.057, 90.539, 41.414)

LEFT_X0 = 157.436
RIGHT_X0 = 514.403

DEFAULT_SIGNATORIES = {
    "left": {
        "lines": [
            ("Chayanun Suankaew", FOOTER_NAME_SIZE, 145.276),
            ("Entomologist", FOOTER_SUB_SIZE, 133.824),
            ("Pest Elimination Service Ecolab Ltd.", FOOTER_SUB_SIZE, 122.202),
        ],
        "signature_image": os.path.join(ASSETS_DIR, "Sig_Chayanan.png"),
        "max_height": 36,
    },
    "right": {
        "lines": [
            ("Nuch Laokhom", FOOTER_NAME_SIZE, 137.112),
            ("Field Sales & Services Manager", FOOTER_SUB_SIZE, 127.672),
            ("Ecolab Pest Elimination Services Division", FOOTER_SUB_SIZE, 118.063),
        ],
        "signature_image": os.path.join(ASSETS_DIR, "Sig_Nuch.png"),
        "max_height": 37,
    },
}

# ---------------------------------------------------------------------------
# Signatory library -- everyone who might sign a certificate, keyed by a
# short lowercase id. Both the left and right slot can independently be set
# to any of these (see run_once.py: signers are picked by matching these ids
# as substrings of the triggering email's subject line, e.g.
# "ขอใบ Cer | left: chayanun | right: nuch").
#
# NOTE: each entry's "lines" use LEFT-slot baseline y-positions by default
# (145.276 / 133.824 / 122.202). If a person is placed in the RIGHT slot
# instead, the baselines need the right-slot offset (roughly -8 pt higher
# top line, see DEFAULT_SIGNATORIES above for the reference numbers) --
# render_certificate_page() handles this shift automatically based on which
# slot the profile is assigned to, so you only need to fill in "lines_left"
# below and the pipeline derives the right-slot version.
# ---------------------------------------------------------------------------
SIGNATORY_LIBRARY = {
    "chayanun": {
        "display_lines": [
            "Chayanun Suankaew",
            "Entomologist",
            "Pest Elimination Service Ecolab Ltd.",
        ],
        "signature_image": os.path.join(ASSETS_DIR, "Sig_Chayanan.png"),
    },
    "issariya": {
        "display_lines": [
            "Issariya Tanaksaranone",
            "Pest Elimination Division",
            "Operation Manager",
        ],
        "signature_image": os.path.join(ASSETS_DIR, "Sig_Issariya.png"),
    },
    "nuch": {
        "display_lines": [
            "Nuch Laokhom",
            "Field Sales & Services Manager",
            "Ecolab Pest Elimination Services Division",
        ],
        "signature_image": os.path.join(ASSETS_DIR, "Sig_Nuch.png"),
    },
    "yadawan": {
        "display_lines": [
            "Yadawan Praisri",
            "Technical Support",
            "Ecolab Pest Elimination Services Division",
        ],
        "signature_image": os.path.join(ASSETS_DIR, "Sig_Yadawan.png"),
    },
}

# Baseline y-positions for each slot (pdf bottom-up coords). Every profile
# in SIGNATORY_LIBRARY gets stamped into whichever slot it's assigned to
# using these, so signatures aren't tied to a fixed person/slot pairing.
SLOT_BASELINES = {
    "left": {
        "x0": LEFT_X0,
        "box": LEFT_SIG_BOX,
        "max_height": 36,
        "baselines": [145.276, 133.824, 122.202],
    },
    "right": {
        "x0": RIGHT_X0,
        "box": RIGHT_SIG_BOX,
        "max_height": 37,
        "baselines": [137.112, 127.672, 118.063],
    },
}


def build_signatory_slot(profile_id, slot):
    """Look up a SIGNATORY_LIBRARY profile and format it for the given
    slot ('left' or 'right'), using that slot's own baseline positions."""
    profile = SIGNATORY_LIBRARY[profile_id]
    slot_cfg = SLOT_BASELINES[slot]
    sizes = [FOOTER_NAME_SIZE, FOOTER_SUB_SIZE, FOOTER_SUB_SIZE]
    lines = list(zip(profile["display_lines"], sizes, slot_cfg["baselines"]))
    return {
        "lines": lines,
        "signature_image": profile["signature_image"],
        "max_height": slot_cfg["max_height"],
    }

# ---------------------------------------------------------------------------
# Runtime / email settings -- overridable via environment variables so
# nothing sensitive or deployment-specific is hardcoded in source.
# ---------------------------------------------------------------------------
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
SUBJECT_KEYWORD = os.environ.get("SUBJECT_KEYWORD", "ขอใบ Cer")
DESTINATION_EMAIL = os.environ.get("DESTINATION_EMAIL", "")
TRIGGER_SECRET = os.environ.get("TRIGGER_SECRET", "")  # shared secret Cloud Scheduler must send
