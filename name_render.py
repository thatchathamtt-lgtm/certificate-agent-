"""Render text (Thai-safe, via RAQM/HarfBuzz shaping) to a tightly-cropped
RGBA PNG, and report where the baseline sits inside that crop so it can be
placed precisely in a PDF using reportlab.

Why this exists: reportlab's native drawString() does naive glyph-by-glyph
placement and does NOT correctly stack Thai combining vowels + tone marks
(e.g. the tone mark in "ปลื้ม" ends up floating in the wrong place). Routing
text through Pillow + libraqm (HarfBuzz) fixes this because it performs
proper complex-text-shaping before rasterizing.
"""
import os
import hashlib
from PIL import Image, ImageDraw, ImageFont

RENDER_SCALE = 10  # px per pt while rasterizing (higher = crisper)


def render_name_image(text, font_path, font_size_pt, out_dir):
    """Returns (png_path, width_pt, height_pt, top_to_baseline_pt)."""
    os.makedirs(out_dir, exist_ok=True)
    key = hashlib.md5(f"{text}|{font_path}|{font_size_pt}".encode("utf-8")).hexdigest()[:12]
    out_path = os.path.join(out_dir, f"name_{key}.png")

    px_size = int(font_size_pt * RENDER_SCALE)
    font = ImageFont.truetype(font_path, px_size, layout_engine=ImageFont.Layout.RAQM)
    ascent, descent = font.getmetrics()

    pad = px_size  # generous padding so nothing gets clipped pre-crop
    canvas_w = px_size * max(1, len(text)) + pad * 2
    canvas_h = px_size * 3 + pad * 2
    img = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    origin = (pad, pad)
    d.text(origin, text, font=font, fill=(0, 0, 0, 255))
    baseline_y_px = pad + ascent

    gray = img.convert("L")
    ink_bbox = gray.point(lambda p: 255 if p < 250 else 0).getbbox()
    if ink_bbox is None:
        raise ValueError(f"No ink rendered for text: {text!r}")

    crop = img.crop(ink_bbox)
    crop.save(out_path)

    width_pt = crop.width / RENDER_SCALE
    height_pt = crop.height / RENDER_SCALE
    top_to_baseline_pt = (baseline_y_px - ink_bbox[1]) / RENDER_SCALE

    return out_path, width_pt, height_pt, top_to_baseline_pt
