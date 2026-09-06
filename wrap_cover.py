#!/usr/bin/env python3
"""Builds a KDP full-wrap cover (back + spine + front) as one print-ready
PDF. Width is trim_w*2 + spine + bleed*2, height is trim_h + bleed*2; spine
width follows KDP's white-paper B&W formula (pages * 0.002252in), with a
0.125in bleed on all outer edges. Upload the result via KDP's "upload a cover
you already have" option."""
import argparse, os, textwrap
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from font_utils import image_font_candidates, load_image_font
from reportlab.lib.units import inch
from cover import PALETTES as FRONT_COVER_PALETTES
from background_generation.index import verify_rendered_cover_approval

PALETTES = {
    "nature":    {"bg": (244, 239, 226), "accent": (107, 142, 107), "deep": (46, 70, 48),  "mute": (120, 134, 116)},
    "food":      {"bg": (250, 243, 229), "accent": (193, 84, 58),   "deep": (92, 34, 26),  "mute": (150, 108, 92)},
    "animals":   {"bg": (240, 238, 230), "accent": (58, 128, 124),  "deep": (26, 68, 64),  "mute": (108, 128, 124)},
    "bible":     {"bg": (250, 244, 230), "accent": (176, 141, 60),  "deep": (96, 42, 48),  "mute": (130, 104, 76)},
    "usa":       {"bg": (245, 243, 236), "accent": (38, 58, 98),    "deep": (150, 44, 52), "mute": (92, 102, 120)},
    "kids":      {"bg": (255, 251, 243), "accent": (240, 112, 92),  "deep": (40, 62, 92),  "mute": (90, 120, 140)},
    "nostalgia": {"bg": (238, 228, 208), "accent": (150, 112, 70),  "deep": (72, 52, 36),  "mute": (140, 118, 94)},
    "sudoku":    {"bg": (237, 242, 249), "accent": (72, 104, 156),  "deep": (22, 41, 78),  "mute": (108, 122, 148)},
    "maze":      {"bg": (238, 244, 236), "accent": (74, 122, 86),   "deep": (26, 58, 40),  "mute": (110, 130, 116)},
    "beach-vacation": {"bg": (250, 243, 228), "accent": (40, 138, 158), "deep": (16, 54, 78), "mute": (104, 128, 142)},
    "sunset":    {"bg": (255, 241, 224), "accent": (235, 101, 86), "deep": (74, 49, 70), "mute": (145, 92, 90)},
    "ocean-breeze": {"bg": (234, 248, 247), "accent": (42, 153, 169), "deep": (22, 64, 91), "mute": (83, 126, 143)},
    "lavender-pop": {"bg": (248, 240, 255), "accent": (143, 104, 204), "deep": (69, 51, 101), "mute": (125, 103, 151)},
    "candy-pop": {"bg": (255, 244, 241), "accent": (232, 92, 132), "deep": (78, 53, 88), "mute": (149, 100, 122)},
    "neon-arcade": {"bg": (24, 21, 52), "accent": (255, 71, 154), "deep": (250, 244, 255), "mute": (184, 177, 211)},
    "midnight-gold": {"bg": (24, 31, 48), "accent": (211, 164, 69), "deep": (248, 242, 224), "mute": (160, 170, 187)},
    "berry-blush": {"bg": (255, 240, 244), "accent": (194, 62, 100), "deep": (83, 35, 58), "mute": (150, 96, 118)},
    "forest-cabin": {"bg": (238, 238, 219), "accent": (75, 111, 76), "deep": (38, 63, 43), "mute": (113, 129, 97)},
    "desert-sun": {"bg": (255, 239, 211), "accent": (199, 91, 49), "deep": (93, 51, 41), "mute": (156, 106, 83)},
    "coastal-blue": {"bg": (235, 247, 250), "accent": (43, 126, 164), "deep": (25, 66, 93), "mute": (100, 137, 151)},
    "autumn-harvest": {"bg": (250, 237, 211), "accent": (181, 79, 37), "deep": (92, 52, 32), "mute": (144, 104, 70)},
    "winter-frost": {"bg": (239, 248, 252), "accent": (77, 143, 177), "deep": (34, 66, 91), "mute": (112, 144, 161)},
    "spring-meadow": {"bg": (245, 250, 230), "accent": (100, 160, 81), "deep": (45, 83, 52), "mute": (124, 151, 101)},
    "royal-plum": {"bg": (247, 239, 250), "accent": (117, 60, 139), "deep": (64, 34, 79), "mute": (132, 98, 143)},
    "espresso-cream": {"bg": (247, 238, 222), "accent": (126, 83, 53), "deep": (63, 42, 31), "mute": (134, 112, 91)},
    "tropical-pop": {"bg": (255, 244, 209), "accent": (25, 153, 142), "deep": (26, 75, 88), "mute": (84, 144, 136)},
    "holly-jolly": {"bg": (247, 244, 232), "accent": (184, 42, 50), "deep": (31, 91, 58), "mute": (112, 132, 101)},
    "spooky-night": {"bg": (30, 25, 48), "accent": (238, 112, 39), "deep": (245, 238, 210), "mute": (151, 126, 174)},
    "valentine-rose": {"bg": (255, 239, 244), "accent": (207, 52, 95), "deep": (111, 34, 61), "mute": (165, 105, 127)},
    "easter-pastel": {"bg": (250, 246, 230), "accent": (115, 159, 201), "deep": (80, 78, 117), "mute": (151, 142, 169)},
    "patriotic": {"bg": (247, 245, 238), "accent": (181, 46, 57), "deep": (35, 65, 117), "mute": (107, 122, 144)},
}
# The wrap should always use the same palette library as the front cover.
# Deriving it here prevents a new color option from working on the front while
# silently falling back to nature on the back/spine.
PALETTES = {
    name: {key: colors[key] for key in ("bg", "accent", "deep", "mute")}
    for name, colors in FRONT_COVER_PALETTES.items()
}

ARIALB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
GEORGIA = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"

TRIM_W, TRIM_H = 8.5, 11.0
BLEED = 0.125
SPINE_FACTOR = 0.002252  # white paper, B&W

DPI = 300


_FAMILY_BY_PATH = {
    ARIALB: "sans-bold",
    ARIAL: "sans",
    GEORGIA: "georgia-bold",
}


def f(path, size):
    """Load a sensible font on macOS, Windows, or a bundled Python runtime."""
    family = _FAMILY_BY_PATH.get(path) or ("sans-bold" if "Bold" in path else "sans")
    return load_image_font(image_font_candidates(family), size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--front", required=True, help="front cover PNG (already at 2550x3300)")
    ap.add_argument("--pages", type=int, required=True)
    ap.add_argument("--palette", default="nature")
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", default="Evergreen Puzzle Press")
    ap.add_argument("--back", required=True, help="back cover blurb text")
    ap.add_argument("--back-heading", default="A WORD SEARCH JOURNEY", help="short, reader-facing heading for the back cover")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview-out", help="optional smaller PNG preview of the full KDP wrap")
    a = ap.parse_args()

    approved, approval_reason, _approval_proof = verify_rendered_cover_approval(a.front)
    if not approved:
        raise ValueError("COVER ART REQUIRED — full-wrap production stopped: " + approval_reason)

    spine_in = a.pages * SPINE_FACTOR
    full_w_in = TRIM_W * 2 + spine_in + BLEED * 2
    full_h_in = TRIM_H + BLEED * 2
    full_w_px = int(round(full_w_in * DPI))
    full_h_px = int(round(full_h_in * DPI))
    spine_px = int(round(spine_in * DPI))
    bleed_px = int(round(BLEED * DPI))
    trim_w_px = int(round(TRIM_W * DPI))
    trim_h_px = int(round(TRIM_H * DPI))

    P = PALETTES.get(a.palette, PALETTES["nature"])
    bg, accent, deep, mute = P["bg"], P["accent"], P["deep"], P["mute"]

    img = Image.new("RGB", (full_w_px, full_h_px), bg)
    d = ImageDraw.Draw(img)

    # X coordinates of the 4 region boundaries (left edge -> right edge)
    back_x0 = bleed_px
    back_x1 = bleed_px + trim_w_px
    spine_x0 = back_x1
    spine_x1 = spine_x0 + spine_px
    front_x0 = spine_x1
    front_x1 = front_x0 + trim_w_px

    # --- FRONT (right): paste the user's front cover, bleed-padded ---
    front = Image.open(a.front).convert("RGB")
    # Resize front to fit the trim_w_px x trim_h_px area; bleed will be filled by extending edges
    front = front.resize((trim_w_px, trim_h_px), Image.LANCZOS)
    img.paste(front, (front_x0, bleed_px))
    # Extend the front's edge color into the right + top + bottom bleed strips
    # Right bleed: extend the rightmost column
    right_strip = front.crop((trim_w_px - 2, 0, trim_w_px, trim_h_px)).resize((bleed_px, trim_h_px))
    img.paste(right_strip, (front_x1, bleed_px))
    # Top + bottom bleed for the FRONT area
    top_strip = front.crop((0, 0, trim_w_px, 2)).resize((trim_w_px, bleed_px))
    img.paste(top_strip, (front_x0, 0))
    bot_strip = front.crop((0, trim_h_px - 2, trim_w_px, trim_h_px)).resize((trim_w_px, bleed_px))
    img.paste(bot_strip, (front_x0, bleed_px + trim_h_px))
    # Right-top + right-bottom corner squares
    img.paste(right_strip.crop((0, 0, bleed_px, 2)).resize((bleed_px, bleed_px)), (front_x1, 0))
    img.paste(right_strip.crop((0, trim_h_px - 2, bleed_px, trim_h_px)).resize((bleed_px, bleed_px)),
              (front_x1, bleed_px + trim_h_px))

    # --- SPINE (middle) ---
    d.rectangle([spine_x0, 0, spine_x1, full_h_px], fill=accent)
    # KDP rule: spine text is only allowed/safe on thick books. A 73-79pp spine is too thin and
    # Amazon flags the text as "too close to the edges." Only render spine text at >= 100 pages,
    # AND keep it >= 0.375" clear of the top/bottom cover edges (shrink to fit if the title is long).
    if a.pages >= 100 and spine_px > 40:
        edge_clear = int(0.375 * DPI)              # required clearance from top & bottom edges
        max_text_len = full_h_px - 2 * edge_clear  # spine text must fit within this vertical span
        spine_text = a.title.upper()
        spine_font_size = max(20, min(spine_px - 30, 80))
        sf = f(GEORGIA, spine_font_size)
        tw = d.textlength(spine_text, font=sf)
        while tw > max_text_len and spine_font_size > 14:
            spine_font_size -= 2
            sf = f(GEORGIA, spine_font_size)
            tw = d.textlength(spine_text, font=sf)
        if tw <= max_text_len:  # only draw if it fits with full clearance
            spine_img = Image.new("RGBA", (full_h_px, spine_px), (accent[0], accent[1], accent[2], 255))
            sd = ImageDraw.Draw(spine_img)
            sd.text(((full_h_px - tw) // 2, (spine_px - spine_font_size) // 2 - 6),
                    spine_text, font=sf, fill=bg)
            spine_img = spine_img.rotate(90, expand=True)
            img.paste(spine_img, (spine_x0, 0))

    # --- BACK (left) ---
    # Mirror the front's bleed treatment on the left side
    d.rectangle([0, 0, back_x1, full_h_px], fill=bg)
    # A restrained editorial back cover: one fine border and a small accent bar.
    safe_pad = int(0.375 * DPI)  # 0.375" inside trim edge → comfortably inside KDP's 0.25" safe margin
    bx0, by0 = bleed_px + safe_pad, bleed_px + safe_pad
    bx1, by1 = back_x1 - safe_pad, full_h_px - bleed_px - safe_pad
    d.rectangle([bx0, by0, bx1, by1], outline=accent, width=4)
    d.rectangle([bx0, by0, bx1, by0 + 22], fill=accent)

    # back blurb title
    btf = f(GEORGIA, 88)
    blurb_title = a.back_heading.upper()
    while d.textlength(blurb_title, font=btf) > trim_w_px - 2 * safe_pad and btf.size > 42:
        btf = f(GEORGIA, btf.size - 2)
    btw = d.textlength(blurb_title, font=btf)
    d.text((bleed_px + (trim_w_px - btw) // 2, by0 + 110), blurb_title, font=btf, fill=deep)
    # divider
    d.line([(bleed_px + trim_w_px // 2 - 200, by0 + 230),
            (bleed_px + trim_w_px // 2 + 200, by0 + 230)], fill=accent, width=4)

    # Body text uses headings supplied by the topic-aware blurb.
    body_font = f(ARIAL, 50)
    body_color = deep
    text_w = trim_w_px - 2 * (safe_pad + 80)
    text_x = bleed_px + safe_pad + 80
    text_y = by0 + 300

    def wrap_text(s, fnt, maxw):
        lines = []
        for para in s.split("\n"):
            words = para.split()
            cur = ""
            for w in words:
                t = (cur + " " + w).strip()
                if d.textlength(t, font=fnt) <= maxw:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines

    for section in [part.strip() for part in a.back.split("\n\n") if part.strip()]:
        is_heading = section.isupper() and len(section) < 34
        if is_heading:
            heading_font = f(ARIALB, 34)
            d.text((text_x, text_y), section, font=heading_font, fill=accent)
            text_y += 60
            continue
        for ln in wrap_text(section, body_font, text_w):
            d.text((text_x, text_y), ln, font=body_font, fill=body_color)
            text_y += int(body_font.size * 1.31)
        text_y += 35

    # imprint at bottom of back
    pf = f(ARIALB, 56)
    imp = a.author
    iw = d.textlength(imp, font=pf)
    d.text((bleed_px + (trim_w_px - iw) // 2, by1 - 110), imp, font=pf, fill=deep)

    # KDP BARCODE ZONE — leave a CLEAR white area (~2.0 x 1.2 in) in the lower-right of the
    # back cover so Amazon can place its barcode. Without this, the colored back + the
    # decorative border give KDP no clean zone and its scanner reads the border lines as an
    # invalid "custom barcode", which blocks the Print Previewer's Approve button.
    bc_w, bc_h = int(2.0 * DPI), int(1.2 * DPI)
    bc_margin = int(0.25 * DPI)
    bc_y1 = (full_h_px - bleed_px) - bc_margin       # bottom edge (above the bottom trim)
    bc_y0 = bc_y1 - bc_h
    # Reserve one standard barcode zone at the lower-right of the back panel.
    # The additional outer-corner box previously used here looked like a
    # template artifact in the preview and is not needed for KDP's placement.
    # right/spine-side corner:
    d.rectangle([back_x1 - bc_margin - bc_w, bc_y0, back_x1 - bc_margin, bc_y1], fill=(255, 255, 255))

    # Save high-res PNG, then wrap into a PDF at exact physical size
    tmp_png = a.out.replace(".pdf", "_full.png")
    img.save(tmp_png, "PNG", dpi=(DPI, DPI))
    if a.preview_out:
        preview = img.copy()
        preview.thumbnail((1800, 1050), Image.LANCZOS)
        preview.save(a.preview_out, "PNG")

    c = canvas.Canvas(a.out, pagesize=(full_w_in * inch, full_h_in * inch))
    c.drawImage(tmp_png, 0, 0, width=full_w_in * inch, height=full_h_in * inch)
    c.save()
    os.remove(tmp_png)

    print(f"DONE -> {a.out}")
    print(f"  size: {full_w_in:.3f} x {full_h_in:.3f} in  ({full_w_px} x {full_h_px} px @ 300 DPI)")
    print(f"  spine: {spine_in:.3f} in ({a.pages} pages × 0.002252)")
    print(f"  back+spine+front layout, RGB, bleed included — upload as 'print-ready PDF'")


if __name__ == "__main__":
    main()
