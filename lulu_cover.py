"""Render a Lulu-specific full wrap from the approved front-cover artwork.

This intentionally does not open, resize, or stretch a KDP wrap.  It lays out
the same front art in a new back/spine/front canvas whose dimensions come from
the selected Lulu project/template.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from font_utils import image_font_candidates, load_image_font

DPI = 300


def _font(size: int, bold: bool = False):
    return load_image_font(image_font_candidates("sans-bold" if bold else "sans"), size)


def build_lulu_wrap(*, front: Path, output: Path, trim_width: float, trim_height: float,
                    spine_width: float, title: str, author: str, back_text: str,
                    bleed: float = .125) -> tuple[float, float]:
    if spine_width <= 0:
        raise ValueError("Lulu spine width must come from the selected Lulu project or template.")
    full_width = 2 * trim_width + spine_width + 2 * bleed
    full_height = trim_height + 2 * bleed
    size = lambda value: int(round(value * DPI))
    fw, fh, trim_w, trim_h, spine, bleed_px = map(size, (full_width, full_height, trim_width, trim_height, spine_width, bleed))
    image = Image.new("RGB", (fw, fh), "#171d23")
    draw = ImageDraw.Draw(image)
    back_left, back_right = bleed_px, bleed_px + trim_w
    spine_left, spine_right = back_right, back_right + spine
    front_left = spine_right
    with Image.open(front).convert("RGB") as cover:
        # This resizes only the front panel to trim size; it never alters a
        # platform wrap or attempts to hide a mismatched spine calculation.
        cover = cover.resize((trim_w, trim_h), Image.LANCZOS)
        image.paste(cover, (front_left, bleed_px))
        edge = cover.crop((trim_w - 2, 0, trim_w, trim_h)).resize((bleed_px, trim_h))
        image.paste(edge, (front_left + trim_w, bleed_px))
        image.paste(cover.crop((0, 0, trim_w, 2)).resize((trim_w, bleed_px)), (front_left, 0))
        image.paste(cover.crop((0, trim_h - 2, trim_w, trim_h)).resize((trim_w, bleed_px)), (front_left, bleed_px + trim_h))
    draw.rectangle((spine_left, 0, spine_right, fh), fill="#cfa445")
    draw.rectangle((0, 0, back_right, fh), fill="#f8f1e5")
    safe = bleed_px + size(.35)
    draw.rounded_rectangle((safe, safe, back_right - size(.35), fh - safe), radius=size(.08), outline="#cfa445", width=4)
    heading = _font(54, True); body = _font(34); imprint = _font(40, True)
    y = safe + size(.55)
    for line in ("MORE TO EXPLORE", "A premium collection of", "screen-free brain games."):
        draw.text((safe + size(.25), y), line, font=heading if line == "MORE TO EXPLORE" else body, fill="#252e38")
        y += size(.38)
    y += size(.35)
    words, line = back_text.split(), ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textlength(candidate, font=body) > trim_w - size(1.25):
            draw.text((safe + size(.25), y), line, font=body, fill="#252e38"); y += size(.28); line = word
        else: line = candidate
    if line: draw.text((safe + size(.25), y), line, font=body, fill="#252e38")
    draw.text((safe + size(.25), fh - safe - size(.55)), author, font=imprint, fill="#252e38")
    # Spine title is centered in the actual Lulu spine, not KDP's spine.
    if spine >= size(.30):
        spine_img = Image.new("RGBA", (fh, spine), "#cfa445"); sd = ImageDraw.Draw(spine_img)
        font = _font(max(18, min(58, spine - 18)), True); text = title.upper()
        while sd.textlength(text, font=font) > fh - 2 * size(.35) and font.size > 14: font = _font(font.size - 2, True)
        sd.text(((fh - sd.textlength(text, font=font)) / 2, (spine - font.size) / 2), text, font=font, fill="#171d23")
        image.paste(spine_img.rotate(90, expand=True), (spine_left, 0))
    png = output.with_suffix(".png"); image.save(png, dpi=(DPI, DPI))
    pdf = canvas.Canvas(str(output), pagesize=(full_width * inch, full_height * inch))
    pdf.drawImage(str(png), 0, 0, width=full_width * inch, height=full_height * inch); pdf.save(); png.unlink()
    return full_width, full_height


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--front", required=True); parser.add_argument("--out", required=True)
    parser.add_argument("--trim-width", type=float, required=True); parser.add_argument("--trim-height", type=float, required=True)
    parser.add_argument("--spine-width", type=float, required=True); parser.add_argument("--title", required=True); parser.add_argument("--author", required=True); parser.add_argument("--back", required=True)
    args = parser.parse_args(); width, height = build_lulu_wrap(front=Path(args.front), output=Path(args.out), trim_width=args.trim_width, trim_height=args.trim_height, spine_width=args.spine_width, title=args.title, author=args.author, back_text=args.back)
    print(f"Lulu wrap created: {width:.3f} x {height:.3f} inches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
