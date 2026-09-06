#!/usr/bin/env python3
"""Print-ready front cover for the large-print word-search books.

The hero is a real solved grid with the theme words highlighted, so the
cover shows what's actually inside rather than generic clip art. Theme
silhouettes per niche."""
import argparse, json, os, random, re
from PIL import Image, ImageDraw

from font_utils import image_font_candidates, load_image_font
from background_generation.index import require_production_approved_cover_asset, write_cover_approval_proof

W, H = 2550, 3300
# Set by ``main`` once per cover.  All layouts use ``hero_grid`` as their
# central proof-of-product, so this one setting prevents a Word Search visual
# from leaking onto any other puzzle type.
COVER_PUZZLE_TYPE = "Word Search"

PALETTES = {
    "nature":    {"bg": (244, 239, 226), "accent": (107, 142, 107), "deep": (32, 58, 38),  "mute": (120, 134, 116), "hi": (255, 211, 84)},
    "food":      {"bg": (250, 243, 229), "accent": (193, 84, 58),   "deep": (84, 28, 22),  "mute": (150, 108, 92),  "hi": (255, 200, 80)},
    "animals":   {"bg": (240, 238, 230), "accent": (58, 128, 124),  "deep": (18, 56, 54),  "mute": (108, 128, 124), "hi": (255, 211, 84)},
    "bible":     {"bg": (250, 244, 230), "accent": (176, 141, 60),  "deep": (96, 42, 48),  "mute": (130, 104, 76),  "hi": (255, 211, 84)},
    "usa":       {"bg": (245, 243, 236), "accent": (38, 58, 98),    "deep": (150, 44, 52), "mute": (92, 102, 120),  "hi": (255, 211, 84)},
    "kids":      {"bg": (255, 251, 243), "accent": (240, 112, 92),  "deep": (40, 62, 92),  "mute": (90, 120, 140),  "hi": (255, 211, 84)},
    "nostalgia": {"bg": (238, 228, 208), "accent": (150, 112, 70),  "deep": (72, 52, 36),  "mute": (140, 118, 94),  "hi": (255, 211, 84)},
    "beach-vacation": {"bg": (250, 243, 228), "accent": (40, 138, 158), "deep": (16, 54, 78), "mute": (104, 128, 142), "hi": (255, 205, 70)},
    "summer-vacation": {"bg": (252, 246, 230), "accent": (242, 158, 58), "deep": (40, 78, 120), "mute": (120, 120, 108), "hi": (255, 208, 70)},
    "birds":     {"bg": (243, 244, 236), "accent": (86, 140, 170), "deep": (30, 54, 74), "mute": (110, 124, 132), "hi": (255, 205, 80)},
    "gardening": {"bg": (244, 242, 228), "accent": (120, 150, 90), "deep": (44, 66, 40), "mute": (120, 130, 108), "hi": (255, 205, 80)},
    "sports":    {"bg": (245, 244, 238), "accent": (44, 92, 162), "deep": (20, 40, 74), "mute": (98, 110, 132), "hi": (255, 196, 60)},
    "ocean-life": {"bg": (236, 244, 247), "accent": (30, 112, 144), "deep": (12, 44, 68), "mute": (94, 120, 134), "hi": (255, 205, 80)},
    "retro-travel-and-landmarks": {"bg": (240, 230, 210), "accent": (176, 116, 62), "deep": (74, 52, 34), "mute": (140, 116, 90), "hi": (255, 200, 74)},
    "sunset":    {"bg": (255, 241, 224), "accent": (235, 101, 86), "deep": (74, 49, 70), "mute": (145, 92, 90), "hi": (255, 190, 74)},
    "ocean-breeze": {"bg": (234, 248, 247), "accent": (42, 153, 169), "deep": (22, 64, 91), "mute": (83, 126, 143), "hi": (255, 205, 86)},
    "lavender-pop": {"bg": (248, 240, 255), "accent": (143, 104, 204), "deep": (69, 51, 101), "mute": (125, 103, 151), "hi": (255, 194, 95)},
    "candy-pop": {"bg": (255, 244, 241), "accent": (232, 92, 132), "deep": (78, 53, 88), "mute": (149, 100, 122), "hi": (112, 205, 190)},
    "neon-arcade": {"bg": (24, 21, 52), "accent": (255, 71, 154), "deep": (250, 244, 255), "mute": (184, 177, 211), "hi": (52, 231, 213)},
    "midnight-gold": {"bg": (24, 31, 48), "accent": (211, 164, 69), "deep": (248, 242, 224), "mute": (160, 170, 187), "hi": (239, 202, 106)},
    "berry-blush": {"bg": (255, 240, 244), "accent": (194, 62, 100), "deep": (83, 35, 58), "mute": (150, 96, 118), "hi": (246, 178, 94)},
    "forest-cabin": {"bg": (238, 238, 219), "accent": (75, 111, 76), "deep": (38, 63, 43), "mute": (113, 129, 97), "hi": (220, 165, 75)},
    "desert-sun": {"bg": (255, 239, 211), "accent": (199, 91, 49), "deep": (93, 51, 41), "mute": (156, 106, 83), "hi": (245, 187, 76)},
    "coastal-blue": {"bg": (235, 247, 250), "accent": (43, 126, 164), "deep": (25, 66, 93), "mute": (100, 137, 151), "hi": (244, 191, 74)},
    "autumn-harvest": {"bg": (250, 237, 211), "accent": (181, 79, 37), "deep": (92, 52, 32), "mute": (144, 104, 70), "hi": (231, 161, 55)},
    "winter-frost": {"bg": (239, 248, 252), "accent": (77, 143, 177), "deep": (34, 66, 91), "mute": (112, 144, 161), "hi": (214, 238, 246)},
    "spring-meadow": {"bg": (245, 250, 230), "accent": (100, 160, 81), "deep": (45, 83, 52), "mute": (124, 151, 101), "hi": (244, 204, 73)},
    "royal-plum": {"bg": (247, 239, 250), "accent": (117, 60, 139), "deep": (64, 34, 79), "mute": (132, 98, 143), "hi": (228, 181, 76)},
    "espresso-cream": {"bg": (247, 238, 222), "accent": (126, 83, 53), "deep": (63, 42, 31), "mute": (134, 112, 91), "hi": (222, 168, 77)},
    "tropical-pop": {"bg": (255, 244, 209), "accent": (25, 153, 142), "deep": (26, 75, 88), "mute": (84, 144, 136), "hi": (244, 106, 89)},
    "holly-jolly": {"bg": (247, 244, 232), "accent": (184, 42, 50), "deep": (31, 91, 58), "mute": (112, 132, 101), "hi": (220, 174, 66)},
    "spooky-night": {"bg": (30, 25, 48), "accent": (238, 112, 39), "deep": (245, 238, 210), "mute": (151, 126, 174), "hi": (146, 87, 177)},
    "valentine-rose": {"bg": (255, 239, 244), "accent": (207, 52, 95), "deep": (111, 34, 61), "mute": (165, 105, 127), "hi": (240, 171, 100)},
    "easter-pastel": {"bg": (250, 246, 230), "accent": (115, 159, 201), "deep": (80, 78, 117), "mute": (151, 142, 169), "hi": (246, 193, 91)},
    "patriotic": {"bg": (247, 245, 238), "accent": (181, 46, 57), "deep": (35, 65, 117), "mute": (107, 122, 144), "hi": (222, 181, 69)},
    "scholarly-blue": {"bg": (241, 247, 252), "accent": (53, 124, 177), "deep": (28, 56, 91), "mute": (101, 133, 158), "hi": (243, 190, 74)},
    "notebook-mint": {"bg": (242, 250, 245), "accent": (67, 157, 128), "deep": (30, 74, 65), "mute": (108, 145, 132), "hi": (246, 198, 76)},
    "library-burgundy": {"bg": (250, 242, 238), "accent": (143, 49, 70), "deep": (80, 29, 42), "mute": (150, 100, 109), "hi": (223, 174, 76)},
    "starlight-indigo": {"bg": (240, 241, 252), "accent": (91, 91, 184), "deep": (43, 42, 97), "mute": (122, 122, 166), "hi": (244, 201, 87)},
    "citrus-study": {"bg": (255, 250, 229), "accent": (224, 132, 35), "deep": (77, 70, 37), "mute": (148, 132, 86), "hi": (87, 171, 130)},
    "graphite-copper": {"bg": (241, 240, 236), "accent": (180, 105, 55), "deep": (45, 49, 55), "mute": (111, 113, 115), "hi": (232, 185, 93)},
    "pixel-neon": {"bg": (26, 23, 46), "accent": (87, 232, 201), "deep": (248, 242, 255), "mute": (174, 160, 204), "hi": (255, 104, 173)},
    "cinema-red": {"bg": (252, 243, 236), "accent": (197, 52, 49), "deep": (83, 33, 37), "mute": (151, 100, 96), "hi": (235, 181, 68)},
}
# Kept as a friendly legacy option because older saved themes and the UI offer
# "christmas" as a palette name, while the newer name is "holly-jolly".
PALETTES["christmas"] = PALETTES["holly-jolly"]
# Historical launch themes used these earlier names.  Keeping aliases means
# older saved books stay visually intentional instead of silently falling back.
PALETTES["retro-drive"] = PALETTES["retro-travel-and-landmarks"]
PALETTES["retro-pop"] = PALETTES["nostalgia"]
PALETTES["cosmic-night"] = PALETTES["starlight-indigo"]

ARIALB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
GEORGIA = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
MONO = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"


_FAMILY_BY_PATH = {
    ARIALB: "sans-bold",
    ARIAL: "sans",
    GEORGIA: "georgia-bold",
    IMPACT: "impact",
    MONO: "display-mono",
}


def f(path, size):
    """Load a sensible font on macOS, Windows, or a bundled Python runtime."""
    family = _FAMILY_BY_PATH.get(path) or ("sans-bold" if "Bold" in path else "sans")
    return load_image_font(image_font_candidates(family), size)


def wrap(d, text, fnt, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


# ---------- theme silhouettes (drawn in accent color) ----------
def pine_tree(d, cx, cy, scale, color):
    """Stacked triangles + trunk."""
    h = int(220 * scale); w = int(130 * scale)
    for i, frac in enumerate([0.55, 0.78, 1.0]):
        tw = int(w * frac); tier_h = int(h * 0.42)
        ty = cy - int(h * (0.9 - i * 0.3))
        d.polygon([(cx - tw // 2, ty + tier_h), (cx + tw // 2, ty + tier_h), (cx, ty)], fill=color)
    tw = max(10, int(20 * scale)); th = int(35 * scale)
    d.rectangle([cx - tw // 2, cy + 6, cx + tw // 2, cy + th], fill=color)


def leaf(d, cx, cy, scale, color):
    """Real leaf shape: pointed ellipse with a stem and center vein."""
    w = int(120 * scale); h = int(54 * scale)
    layer = Image.new("RGBA", (w * 2 + 40, h * 2 + 40), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # Build a leaf via two arcs meeting at points (vesica piscis):
    # draw two filled ellipses whose intersection forms the leaf, masked together
    # Simpler approach: polygon with many curve points
    pts = []
    n = 24
    import math
    for i in range(n + 1):           # upper arc, left point -> right point
        t = i / n
        x = -w + (2 * w) * t
        y = -h * (1 - (2 * t - 1) ** 2) ** 0.5
        pts.append((x + w + 20, y + h + 20))
    for i in range(n + 1):           # lower arc, right point -> left point
        t = i / n
        x = w - (2 * w) * t
        y = h * (1 - (2 * t - 1) ** 2) ** 0.5 * 0.55  # less rounded bottom = leaf-y
        pts.append((x + w + 20, y + h + 20))
    ld.polygon(pts, fill=color + (255,))
    # center vein
    ld.line([(20, h + 20), (2 * w + 20, h + 20)], fill=(255, 255, 255, 120), width=max(2, int(3 * scale)))
    # stem
    sx0, sy0 = 2 * w + 20, h + 20
    sx1, sy1 = sx0 + int(34 * scale), sy0 + int(14 * scale)
    layer_with_stem = layer
    rotated = layer_with_stem.rotate(-28, resample=Image.BICUBIC, expand=True)
    d._image.paste(rotated, (cx - rotated.width // 2, cy - rotated.height // 2), rotated)
    # short stem in main image (so rotation doesn't bend it weirdly)
    d.line([(cx + int(w * 0.7 * scale), cy + int(h * 0.5 * scale)),
            (cx + int(w * 1.1 * scale), cy + int(h * 0.85 * scale))],
           fill=color, width=max(3, int(6 * scale)))


def fork(d, cx, cy, scale, color):
    """Simple fork silhouette."""
    w = max(4, int(8 * scale)); h = int(180 * scale)
    # handle
    d.rectangle([cx - w, cy, cx + w, cy + int(h * 0.6)], fill=color)
    # tines
    tw, th = max(3, int(5 * scale)), int(h * 0.5)
    for ox in (-w * 3, -w, w, w * 3):
        d.rectangle([cx + ox - tw // 2, cy - th, cx + ox + tw // 2, cy], fill=color)
    d.rectangle([cx - w * 4, cy, cx + w * 4, cy + int(h * 0.08)], fill=color)


def spoon(d, cx, cy, scale, color):
    """Simple spoon silhouette."""
    w = max(4, int(8 * scale)); h = int(180 * scale)
    d.rectangle([cx - w, cy, cx + w, cy + int(h * 0.6)], fill=color)
    bw, bh = int(38 * scale), int(50 * scale)
    d.ellipse([cx - bw, cy - bh, cx + bw, cy + int(bh * 0.2)], fill=color)


def paw(d, cx, cy, scale, color):
    """Paw print: 4 toes + pad."""
    s = scale
    # pad
    d.ellipse([cx - int(45 * s), cy - int(10 * s), cx + int(45 * s), cy + int(60 * s)], fill=color)
    # 4 toes
    for ox, oy, rx, ry in [(-50, -45, 18, 22), (-20, -65, 18, 22), (20, -65, 18, 22), (50, -45, 18, 22)]:
        d.ellipse([cx + int(ox * s) - int(rx * s), cy + int(oy * s) - int(ry * s),
                   cx + int(ox * s) + int(rx * s), cy + int(oy * s) + int(ry * s)], fill=color)


def star(d, cx, cy, scale, color):
    """5-point star silhouette."""
    import math as _m
    R = int(70 * scale)
    pts = []
    for k in range(10):
        ang = -_m.pi / 2 + k * _m.pi / 5
        r = R if k % 2 == 0 else R * 0.45
        pts.append((cx + r * _m.cos(ang), cy + r * _m.sin(ang)))
    d.polygon(pts, fill=color)


def holly(d, cx, cy, scale, color):
    """Holly leaf cluster with two berries — Christmas decoration."""
    # two leaves crossed
    for ang_deg in (-25, 25):
        layer = Image.new("RGBA", (int(200 * scale), int(120 * scale)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        w = int(80 * scale); h = int(36 * scale)
        # use a simple ellipse approximation
        ld.ellipse([int(10 * scale), (layer.height - 2 * h) // 2,
                    int(10 * scale) + 2 * w, (layer.height + 2 * h) // 2], fill=color + (255,))
        rotated = layer.rotate(ang_deg, resample=Image.BICUBIC, expand=True)
        d._image.paste(rotated, (cx - rotated.width // 2, cy - rotated.height // 2), rotated)
    # red berries
    br = int(14 * scale)
    d.ellipse([cx - br - 4, cy - br, cx + br - 4, cy + br], fill=(180, 30, 30))
    d.ellipse([cx - br + 22, cy - br + 6, cx + br + 22, cy + br + 6], fill=(180, 30, 30))


def sun(d, cx, cy, scale, color):
    """Sun: center disc with straight rays — beach/summer motif."""
    import math as _m
    R = int(40 * scale)
    inner = R + int(10 * scale)
    outer = R + int(46 * scale)
    for k in range(12):
        ang = k * _m.pi / 6
        x0, y0 = cx + inner * _m.cos(ang), cy + inner * _m.sin(ang)
        x1, y1 = cx + outer * _m.cos(ang), cy + outer * _m.sin(ang)
        d.line([(x0, y0), (x1, y1)], fill=color, width=max(3, int(7 * scale)))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=color)


def palmtree(d, cx, cy, scale, color):
    """Palm tree: leaning trunk + radiating fronds — tropical/beach motif."""
    import math as _m
    th = int(150 * scale)
    tw = max(5, int(13 * scale))
    top_x, top_y = cx - int(20 * scale), cy - th
    d.line([(cx, cy), (top_x, top_y)], fill=color, width=tw)        # trunk (leaning)
    for ang_deg in (-165, -125, -90, -55, -15):                    # fronds fan upward
        ang = _m.radians(ang_deg)
        fx = top_x + int(108 * scale * _m.cos(ang))
        fy = top_y + int(108 * scale * _m.sin(ang))
        d.line([(top_x, top_y), (fx, fy)], fill=color, width=max(3, int(9 * scale)))


def wave(d, cx, cy, scale, color):
    """Three stacked rolling waves — ocean motif."""
    import math as _m
    span = int(150 * scale)
    amp = int(16 * scale)
    for row in range(3):
        oy = cy + row * int(30 * scale)
        pts = []
        for i in range(0, span + 1, 6):
            x = cx - span // 2 + i
            y = oy + amp * _m.sin(i / span * 2 * _m.pi * 2)
            pts.append((x, y))
        d.line(pts, fill=color, width=max(3, int(8 * scale)), joint="curve")


THEME_DECOR = {
    "nature":    [(pine_tree, 0.10, 0.16, 1.1), (leaf, 0.86, 0.14, 1.0),
                  (pine_tree, 0.91, 0.92, 0.95), (leaf, 0.09, 0.92, 0.95)],
    "food":      [(fork, 0.10, 0.13, 1.0), (spoon, 0.90, 0.13, 1.0),
                  (fork, 0.10, 0.88, 0.9), (spoon, 0.90, 0.88, 0.9)],
    "animals":   [(paw, 0.12, 0.16, 1.1), (paw, 0.88, 0.16, 1.1),
                  (paw, 0.12, 0.93, 1.0), (paw, 0.88, 0.93, 1.0)],
    "bible":     [(leaf, 0.10, 0.14, 1.0), (leaf, 0.90, 0.14, 1.0),
                  (leaf, 0.10, 0.92, 0.9), (leaf, 0.90, 0.92, 0.9)],
    "usa":       [(star, 0.10, 0.14, 1.0), (star, 0.90, 0.14, 1.0),
                  (star, 0.10, 0.93, 0.9), (star, 0.90, 0.93, 0.9)],
    "kids":      [(star, 0.10, 0.14, 1.1), (star, 0.90, 0.14, 1.1),
                  (star, 0.10, 0.93, 1.0), (star, 0.90, 0.93, 1.0)],
    "christmas": [(pine_tree, 0.10, 0.16, 1.0), (holly, 0.88, 0.14, 0.95),
                  (holly, 0.10, 0.93, 0.95), (pine_tree, 0.91, 0.92, 0.9)],
    "nostalgia": [],
    "beach-vacation": [(sun, 0.12, 0.15, 1.05), (palmtree, 0.88, 0.17, 1.0),
                       (wave, 0.12, 0.90, 1.0), (palmtree, 0.90, 0.90, 0.95)],
    "summer-vacation": [(sun, 0.12, 0.15, 1.15), (palmtree, 0.88, 0.16, 1.0),
                        (wave, 0.10, 0.90, 1.0), (sun, 0.90, 0.90, 0.8)],
    "birds":     [(leaf, 0.10, 0.15, 1.0), (sun, 0.88, 0.16, 0.9),
                  (leaf, 0.10, 0.90, 0.95), (leaf, 0.90, 0.90, 0.95)],
    "gardening": [(pine_tree, 0.10, 0.15, 1.0), (leaf, 0.88, 0.16, 1.0),
                  (leaf, 0.10, 0.90, 0.95), (pine_tree, 0.90, 0.90, 0.9)],
    "sports":    [(star, 0.10, 0.14, 1.1), (star, 0.90, 0.14, 1.1),
                  (star, 0.10, 0.93, 1.0), (star, 0.90, 0.93, 1.0)],
    "ocean-life": [(wave, 0.12, 0.14, 1.0), (wave, 0.88, 0.14, 1.0),
                   (wave, 0.12, 0.90, 1.0), (wave, 0.88, 0.90, 1.0)],
    "retro-travel-and-landmarks": [(sun, 0.12, 0.15, 1.05), (palmtree, 0.88, 0.17, 1.0),
                                   (star, 0.10, 0.92, 0.9), (palmtree, 0.90, 0.90, 0.95)],
}


# ---------- hero puzzle grid (the centerpiece — looks like a real solved word search) ----------
THEME_WORDS = {
    "nature":    ["NATURE", "TREE", "BIRD", "LEAF"],
    "food":      ["TASTY", "BAKE", "MINT", "PIE"],
    "animals":   ["ANIMAL", "CAT", "PAW", "WILD"],
    "bible":     ["FAITH", "HOPE", "LOVE", "PRAY"],
    "usa":       ["USA", "FREE", "FLAG", "WEST"],
    "kids":      ["FUN", "PLAY", "KIDS", "STAR"],
    "christmas": ["JOY", "NOEL", "SANTA", "STAR"],
    "nostalgia": ["RETRO", "DINER", "DISCO", "RADIO"],
    "beach-vacation": ["BEACH", "OCEAN", "WAVES", "SANDY"],
    "summer-vacation": ["SUMMER", "SUNNY", "TRAVEL", "RELAX"],
    "birds":     ["ROBIN", "FINCH", "CANARY", "FLOCK"],
    "gardening": ["GARDEN", "SEEDS", "FLOWER", "TROWEL"],
    "sports":    ["SOCCER", "TENNIS", "MEDAL", "HOCKEY"],
    "ocean-life": ["WHALE", "DOLPHIN", "SHARK", "CORAL"],
    "retro-travel-and-landmarks": ["TRAVEL", "VOYAGE", "RETRO", "CRUISE"],
}
# 4 fallback words so a theme not in THEME_WORDS never crashes the hero grid.
DEFAULT_HERO_WORDS = ["WORD", "SEARCH", "PUZZLE", "SOLVE"]


def hero_grid(d, cx, cy, cell, theme, accent, deep, hi, words=None):
    """A solved-looking word search: 9x9 grid, some words highlighted with yellow sweeps."""
    if COVER_PUZZLE_TYPE != "Word Search":
        return puzzle_type_hero(d, cx, cy, cell, accent, deep, hi)
    n = 9
    size = n * cell
    x0, y0 = cx - size // 2, cy - size // 2

    rng = random.Random(42)
    grid = [[rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(n)] for _ in range(n)]

    # placements: (word, (r,c), (dr,dc)). Pad to 4 words so an unregistered
    # theme falls back gracefully instead of an IndexError.
    source_words = words or list(THEME_WORDS.get(theme, [])) or list(DEFAULT_HERO_WORDS)
    cleaned = ["".join(ch for ch in word.upper() if ch.isalpha()) for word in source_words]
    cleaned = [word for word in cleaned if word]
    # Select real theme words that fit the four demonstration paths.
    words = []
    for limit in (8, 7, 6, 7):
        match = next((word for word in cleaned if len(word) <= limit and word not in words), None)
        words.append(match or DEFAULT_HERO_WORDS[len(words)])
    # Four pairwise-DISJOINT placements (top row / right col / center diagonal /
    # left col) so no two highlighted words share a cell — otherwise the later
    # word overwrites the crossing letter and the sweep reads as a garbled word.
    plans = [
        (words[0], (1, 1), (0, 1)),     # horizontal, top      (row 1, cols 1+)
        (words[1], (2, 7), (1, 0)),     # vertical, right edge (col 7, rows 2+)
        (words[2], (3, 1), (1, 1)),     # diagonal, center     ((3,1) down-right)
        (words[3], (2, 0), (1, 0)),     # vertical, left edge  (col 0, rows 2+)
    ]
    highlights = []
    for word, (r0, c0), (dr, dc) in plans:
        cells = []
        valid = True
        for i, ch in enumerate(word):
            r, c = r0 + dr * i, c0 + dc * i
            if not (0 <= r < n and 0 <= c < n):
                valid = False; break
            cells.append((r, c, ch))
        if valid:
            for r, c, ch in cells:
                grid[r][c] = ch
            highlights.append([(r, c) for r, c, _ in cells])

    # 1) Yellow highlight sweeps UNDER letters
    for cells in highlights:
        (r0, c0), (r1, c1) = cells[0], cells[-1]
        p0 = (x0 + c0 * cell + cell // 2, y0 + r0 * cell + cell // 2)
        p1 = (x0 + c1 * cell + cell // 2, y0 + r1 * cell + cell // 2)
        d.line([p0, p1], fill=hi, width=int(cell * 0.78))

    # 2) Grid lines
    for i in range(n + 1):
        d.line([(x0 + i * cell, y0), (x0 + i * cell, y0 + size)], fill=accent, width=2)
        d.line([(x0, y0 + i * cell), (x0 + size, y0 + i * cell)], fill=accent, width=2)

    # 3) Heavy outer border
    d.rectangle([x0, y0, x0 + size, y0 + size], outline=deep, width=6)

    # 4) Letters
    # Use the cross-platform font helper here too; MONO is a macOS path.
    lf = f(MONO, int(cell * 0.56))
    for r in range(n):
        for c in range(n):
            ch = grid[r][c]
            tw = d.textlength(ch, font=lf)
            d.text((x0 + c * cell + (cell - tw) / 2, y0 + r * cell + cell * 0.17),
                   ch, font=lf, fill=deep)


def puzzle_type_hero(d, cx, cy, cell, accent, deep, hi):
    """Use a truthful cover visual for non-word-search puzzle books."""
    if COVER_PUZZLE_TYPE == "Sudoku":
        n, size = 9, cell * 9; x0, y0 = cx - size // 2, cy - size // 2
        d.rectangle([x0, y0, x0 + size, y0 + size], fill=(255, 255, 255), outline=deep, width=10)
        digits = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"
        font = f(ARIALB, int(cell * .54))
        for row in range(n + 1):
            width = 10 if row % 3 == 0 else 3
            d.line([(x0, y0 + row * cell), (x0 + size, y0 + row * cell)], fill=deep, width=width)
            d.line([(x0 + row * cell, y0), (x0 + row * cell, y0 + size)], fill=deep, width=width)
        for row in range(n):
            for col in range(n):
                value = digits[row * n + col]
                color = accent if (row + col) % 4 == 0 else deep
                d.text((x0 + col * cell + cell * .31, y0 + row * cell + cell * .18), value, font=font, fill=color)
        return
    if COVER_PUZZLE_TYPE == "Cryptogram":
        width, height = cell * 8, cell * 5; x0, y0 = cx - width // 2, cy - height // 2
        d.rounded_rectangle([x0, y0, x0 + width, y0 + height], radius=28, fill=(255, 255, 255), outline=deep, width=10)
        title_font, code_font = f(ARIALB, int(cell * .34)), f(MONO, int(cell * .43))
        _centered(d, "DECODE THE MESSAGE", title_font, y0 + cell * .35, accent)
        code = "XQF LQJ YPMK  •  RST UVW  •  KLM NOP"
        for index, line in enumerate((code, "_ _ _   _ _ _ _   _ _ _", "KEY:  A→M   B→N   C→O")):
            _centered(d, line, code_font, y0 + cell * (1.45 + index * 1.05), deep if index < 2 else accent)
        return
    if COVER_PUZZLE_TYPE == "Word Scramble + Trivia":
        width, height = cell * 8, cell * 5; x0, y0 = cx - width // 2, cy - height // 2
        d.rounded_rectangle([x0, y0, x0 + width, y0 + height], radius=28, fill=(255, 255, 255), outline=deep, width=10)
        tile_font = f(ARIALB, int(cell * .45))
        _centered(d, "UNSCRAMBLE + DISCOVER", f(ARIALB, int(cell * .32)), y0 + cell * .32, accent)
        letters = "P L A N E T"; tile = int(cell * .75)
        start = cx - (len(letters.split()) * tile) // 2
        for index, letter in enumerate(letters.split()):
            x = start + index * tile
            d.rounded_rectangle([x, y0 + cell * 1.25, x + tile - 12, y0 + cell * 2.0], radius=15, fill=hi, outline=deep, width=4)
            d.text((x + tile * .24, y0 + cell * 1.36), letter, font=tile_font, fill=deep)
        _centered(d, "Which planet is known as the Red Planet?", f(ARIALB, int(cell * .27)), y0 + cell * 2.65, deep)
        d.line([(x0 + cell, y0 + cell * 3.65), (x0 + width - cell, y0 + cell * 3.65)], fill=accent, width=5)
        return
    # Mixed Brain Games deliberately avoids the former large white frame and
    # three-card contact sheet.  Variety is communicated with independent
    # edge motifs, so the topic artwork and title still own the composition.
    ink = (38, 48, 62) if sum(deep) > 480 else deep
    small = max(34, int(cell * .42))
    # Sudoku fragment — upper left, light enough to read as a motif not a card.
    gx, gy, step = cx - int(cell * 3.7), cy - int(cell * 1.15), int(cell * .48)
    for line in range(4):
        d.line([(gx, gy + line * step), (gx + 3 * step, gy + line * step)], fill=accent, width=4)
        d.line([(gx + line * step, gy), (gx + line * step, gy + 3 * step)], fill=accent, width=4)
    for row, values in enumerate((("3", "", "7"), ("", "5", ""), ("8", "", "2"))):
        for col, value in enumerate(values):
            if value:
                d.text((gx + col * step + step * .31, gy + row * step + step * .18), value, font=f(ARIALB, small), fill=ink)
    # A free-standing cipher ribbon — lower centre, no enclosing panel.
    ribbon_y = cy + int(cell * .85)
    d.line([(cx - int(cell * 2.0), ribbon_y), (cx + int(cell * 2.0), ribbon_y)], fill=hi, width=8)
    d.text((cx - int(cell * 1.65), ribbon_y - int(cell * .58)), "QZP  →  ?", font=f(MONO, max(30, int(cell * .43))), fill=ink)
    # Word tiles — upper right, individually floating rather than a boxed preview.
    tx, ty = cx + int(cell * 1.35), cy - int(cell * 1.28)
    for offset, letter in enumerate("MIX"):
        left = tx + offset * int(cell * .74)
        top = ty + (offset % 2) * int(cell * .18)
        d.rounded_rectangle([left, top, left + int(cell * .58), top + int(cell * .62)], radius=12, fill=hi, outline=accent, width=4)
        d.text((left + int(cell * .16), top + int(cell * .10)), letter, font=f(ARIALB, max(28, int(cell * .37))), fill=ink)


def theme_words(path):
    """Return the selected theme's words for cover detail; gracefully fall back."""
    if not path:
        return None
    try:
        data = json.load(open(path, encoding="utf-8"))
        return [word for puzzle in data.get("puzzles", []) for word in puzzle.get("words", [])]
    except (OSError, ValueError, TypeError):
        return None


def translucent_puzzle_overlay(d, a):
    """Place a quiet, genuine-theme puzzle excerpt in unused lower cover space."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    hero_grid(od, W // 2, 2390, cell=80, theme=a.theme or a.palette,
              accent=(57, 191, 183), deep=(47, 45, 78), hi=(255, 209, 80),
              words=getattr(a, "cover_words", None))
    alpha = overlay.getchannel("A").point(lambda value: value * 36 // 255)
    overlay.putalpha(alpha)
    d._image.paste(overlay, (0, 0), overlay)


def _centered(d, text, font, y, color):
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=color)


def difficulty_chip(d, difficulty, palette):
    """Draw a compact book-level difficulty marker without competing with the title."""
    if not difficulty:
        return
    label = str(difficulty).upper()
    font = f(ARIALB, 30)
    width = d.textlength(label, font=font)
    x1, y1 = W - 145, 126
    x0, y0 = x1 - width - 42, y1 - 10
    d.rounded_rectangle([x0, y0, x1, y1 + 42], radius=18,
                        fill=palette["deep"], outline=palette["hi"], width=3)
    d.text((x0 + 21, y0 + 6), label, font=font, fill=palette["bg"])


def puzzle_count_label(puzzle_count) -> str:
    """Return the buyer-facing count promise, or an empty string when unknown."""
    try:
        count = int(puzzle_count or 0)
    except (TypeError, ValueError):
        return ""
    if count <= 0:
        return ""
    return f"{count} PUZZLES"


def cover_quality_report(title, subtitle, badge, puzzle_count, format_label, style, art_path="") -> tuple[int, str, list[str]]:
    """Return transparent, buyer-facing cover checks before or after rendering."""
    notes: list[str] = []
    score = 100
    title_length = len(str(title or "").strip())
    subtitle_length = len(str(subtitle or "").strip())
    if title_length > 48:
        score -= 18; notes.append("Shorten the title for stronger thumbnail readability.")
    elif title_length > 38:
        score -= 7; notes.append("The title is long; use a bold or photo layout and inspect the thumbnail.")
    if subtitle_length > 78:
        score -= 12; notes.append("Shorten the subtitle so it stays readable at storefront size.")
    if not puzzle_count_label(puzzle_count):
        score -= 25; notes.append("Add the actual puzzle count before creating the final cover.")
    if "LARGE PRINT" in str(format_label or "").upper():
        notes.append("Large Print promise is shown as a high-contrast front-cover stamp.")
    if str(style or "").lower() == "photo" and not str(art_path or "").strip():
        score -= 20; notes.append("Photo Hero needs a selected local image; choose another layout or add artwork.")
    if str(badge or "").strip():
        notes.append("The extra cover callout is separate from the puzzle-count badge.")
    else:
        notes.append("A clean count badge is present even without an extra marketing callout.")
    score = max(0, score)
    label = "Strong storefront cover" if score >= 90 else ("Review before publishing" if score >= 70 else "Needs cover edits")
    return score, label, notes


def puzzle_count_stamp(d, puzzle_count, palette):
    """Draw the non-optional, thumbnail-readable count promise on a cover."""
    label = puzzle_count_label(puzzle_count)
    if not label:
        return
    font = f(ARIALB, 62)
    label_width = d.textlength(label, font=font)
    x1, y0 = W - 115, 205
    x0, y1 = x1 - label_width - 72, y0 + 118
    d.rounded_rectangle([x0, y0, x1, y1], radius=28,
                        fill=palette["hi"], outline=palette["deep"], width=6)
    d.text((x0 + 36, y0 + 20), label, font=font, fill=palette["deep"])


def _title_lines(d, title, font, max_width):
    return wrap(d, title.upper().replace("LARGE PRINT ", ""), font, max_width)


def format_label(a, include_word_search=False):
    """Use a truthful format label instead of assuming every book is large print."""
    label = str(getattr(a, "format_label", "") or "WORD SEARCH").upper().strip()
    if label == "LARGE PRINT" and include_word_search:
        return "LARGE PRINT WORD SEARCH"
    return label


def cassette(d, x, y, s, body, detail):
    w, h = int(360 * s), int(230 * s)
    d.rounded_rectangle([x, y, x + w, y + h], radius=int(28 * s), fill=body, outline=(47, 45, 78), width=max(3, int(8 * s)))
    d.rounded_rectangle([x + int(54*s), y + int(38*s), x + w - int(54*s), y + int(128*s)], radius=int(10*s), fill=(250, 244, 226))
    for cx in (x + int(115*s), x + w - int(115*s)):
        d.ellipse([cx - int(34*s), y + int(125*s), cx + int(34*s), y + int(193*s)], fill=detail, outline=(47, 45, 78), width=max(2, int(5*s)))
        d.ellipse([cx - int(10*s), y + int(149*s), cx + int(10*s), y + int(169*s)], fill=(250, 244, 226))
    d.rectangle([x + int(135*s), y + int(158*s), x + w - int(135*s), y + int(178*s)], fill=(47, 45, 78))


def game_controller(d, x, y, s, body, detail):
    w, h = int(390 * s), int(190 * s)
    d.rounded_rectangle([x, y, x + w, y + h], radius=int(75*s), fill=body, outline=(47, 45, 78), width=max(3, int(8*s)))
    cx, cy = x + int(110*s), y + int(95*s)
    d.rectangle([cx - int(15*s), cy - int(48*s), cx + int(15*s), cy + int(48*s)], fill=(47, 45, 78))
    d.rectangle([cx - int(48*s), cy - int(15*s), cx + int(48*s), cy + int(15*s)], fill=(47, 45, 78))
    for ox, oy in ((285, 62), (325, 105)):
        d.ellipse([x + int((ox-20)*s), y + int((oy-20)*s), x + int((ox+20)*s), y + int((oy+20)*s)], fill=detail, outline=(47,45,78), width=max(2, int(4*s)))
    d.ellipse([x + int(180*s), y + int(78*s), x + int(210*s), y + int(108*s)], fill=(47,45,78))


def tv(d, x, y, s, screen, body):
    w, h = int(300*s), int(240*s)
    d.rounded_rectangle([x, y, x+w, y+h], radius=int(32*s), fill=body, outline=(47,45,78), width=max(3,int(8*s)))
    d.rounded_rectangle([x+int(30*s), y+int(38*s), x+int(205*s), y+int(178*s)], radius=int(12*s), fill=screen)
    d.ellipse([x+int(235*s), y+int(67*s), x+int(265*s), y+int(97*s)], fill=(47,45,78))
    d.ellipse([x+int(235*s), y+int(122*s), x+int(265*s), y+int(152*s)], fill=(47,45,78))
    d.line([(x+int(90*s), y), (x+int(55*s), y-int(75*s))], fill=(47,45,78), width=max(3,int(7*s)))
    d.line([(x+int(120*s), y), (x+int(155*s), y-int(75*s))], fill=(47,45,78), width=max(3,int(7*s)))


def playful_90s_cover(d, a, palette):
    """Colorful, object-led layout that respects the selected palette."""
    cream, teal, navy, pink, yellow = palette["bg"], palette["accent"], palette["deep"], palette["mute"], palette["hi"]
    purple = tuple(min(255, value + 28) for value in pink)
    d.rectangle([0, 0, W, H], fill=cream)
    d.rectangle([0, 0, W, 330], fill=teal)
    d.rectangle([0, H-275, W, H], fill=purple)
    translucent_puzzle_overlay(d, a)
    # Playful background shapes stay outside the title's safe reading zone.
    for x, y, r, color in [(210,480,86,yellow), (2325,475,72,pink), (250,2580,100,teal), (2300,2600,95,yellow)]:
        d.ellipse([x-r, y-r, x+r, y+r], fill=color, outline=navy, width=8)
    cassette(d, 120, 720, 0.92, pink, yellow)
    game_controller(d, 1990, 780, 0.95, purple, yellow)
    tv(d, 145, 2300, 0.86, teal, yellow)
    cassette(d, 1930, 2250, 0.82, teal, pink)
    # Central title card gives the copy an uncluttered, high-contrast home.
    d.rounded_rectangle([320, 405, W-320, 1645], radius=58, fill=navy)
    _centered(d, format_label(a), f(IMPACT, 95), 510, yellow)
    title_font = f(IMPACT, 155)
    y = 685
    for line in _title_lines(d, a.title, title_font, W-790):
        _centered(d, line, title_font, y, cream)
        y += 175
    subtitle_font = f(ARIALB, 48)
    for line in wrap(d, a.subtitle, subtitle_font, W-800):
        _centered(d, line, subtitle_font, y+18, yellow)
        y += 65
    if a.badge:
        badge_font = f(IMPACT, 80)
        badge_w = d.textlength(a.badge, font=badge_font)
        d.rounded_rectangle([(W-badge_w)/2-52, 1700, (W+badge_w)/2+52, 1835], radius=32, fill=yellow, outline=navy, width=7)
        _centered(d, a.badge, badge_font, 1722, navy)
    # Give the lower half a real proof-of-product focal point instead of a faint background grid.
    d.rounded_rectangle([430, 1940, W-430, 2820], radius=40, fill=cream, outline=navy, width=12)
    hero_grid(d, W // 2, 2380, cell=96, theme=a.theme or a.palette, accent=teal, deep=navy, hi=yellow)
    # A few simple confetti marks add energy without reducing small-size clarity.
    for x, y, color in [(280,2050,pink), (2200,2200,teal), (2180,1990,purple), (320,2620,pink), (2240,2690,yellow)]:
        d.line([(x-38,y-38),(x+38,y+38)], fill=color, width=18)
        d.line([(x-38,y+38),(x+38,y-38)], fill=color, width=18)
    if a.author:
        _centered(d, a.author, f(ARIALB, 58), 2920, cream)


def sunburst_cover(d, a, palette):
    """A poster-like layout with energetic rays and a protected copy area."""
    bg, accent, deep, mute, hi = palette["bg"], palette["accent"], palette["deep"], palette["mute"], palette["hi"]
    d.rectangle([0, 0, W, H], fill=bg)
    cx, cy = W // 2, H // 2
    import math
    for n in range(28):
        a0, a1 = math.tau * n / 28, math.tau * (n + 0.48) / 28
        d.polygon([(cx, cy), (cx + 2900 * math.cos(a0), cy + 2900 * math.sin(a0)), (cx + 2900 * math.cos(a1), cy + 2900 * math.sin(a1))], fill=accent if n % 2 == 0 else hi)
    d.rounded_rectangle([220, 210, W - 220, 1150], radius=50, fill=bg, outline=deep, width=12)
    _centered(d, format_label(a), f(IMPACT, 95), 300, accent)
    title_font, y = f(IMPACT, 144), 470
    for line in _title_lines(d, a.title, title_font, W - 620):
        _centered(d, line, title_font, y, deep); y += 163
    for line in wrap(d, a.subtitle, f(ARIALB, 45), W - 650):
        _centered(d, line, f(ARIALB, 45), y + 12, mute); y += 62
    d.rounded_rectangle([500, 1290, W - 500, 2390], radius=34, fill=bg, outline=deep, width=12)
    hero_grid(d, W // 2, 1840, cell=102, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
    if a.badge:
        badge_font, badge_width = f(IMPACT, 74), d.textlength(a.badge, font=f(IMPACT, 74))
        d.rounded_rectangle([(W-badge_width)/2-48, 2545, (W+badge_width)/2+48, 2675], radius=28, fill=deep)
        _centered(d, a.badge, badge_font, 2567, bg)
    if a.author:
        _centered(d, a.author, f(ARIALB, 56), 2900, deep)


def photo_hero_cover(d, a, palette):
    """A photo-led editorial cover: image first, with refined readable type."""
    if not a.art or not os.path.isfile(a.art):
        raise ValueError("Photo Hero needs a hero artwork image.")
    source = Image.open(a.art).convert("RGB")
    scale = max(W / source.width, H / source.height)
    resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - W) // 2
    extra_height = max(0, resized.height - H)
    top = 0 if getattr(a, "art_focus", "center") == "top" else (extra_height if getattr(a, "art_focus", "center") == "bottom" else extra_height // 2)
    d._image.paste(resized.crop((left, top, left + W, top + H)), (0, 0))
    # A gentle top-to-bottom vignette protects type without hiding the art.
    # This deliberately avoids the old, oversized rounded title card.
    vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    for y in range(H):
        if y < 1220:
            alpha = int(176 - (y / 1220) * 142)
        elif y > 2380:
            alpha = int(20 + ((y - 2380) / (H - 2380)) * 95)
        else:
            alpha = 24
        vd.line([(0, y), (W, y)], fill=(14, 20, 30, max(0, min(176, alpha))))
    d._image.paste(vignette, (0, 0), vignette)
    bg, accent, deep, mute, hi = palette["bg"], palette["accent"], palette["deep"], palette["mute"], palette["hi"]
    # Keep the cover visibly connected to the puzzle inside it.  Word Search
    # uses its quiet letter-grid texture; every other format gets its own
    # truthful puzzle proof instead.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    if COVER_PUZZLE_TYPE != "Word Search":
        puzzle_type_hero(od, W // 2, 2350, 94, accent, deep, hi)
    else:
        grid_left, grid_top, cell, size = 1320, 1880, 118, 9
        line_color = (*hi, 48)
        letter_color = (*bg, 64)
        font = f(ARIALB, 48)
        word_source = list(getattr(a, "cover_words", []) or DEFAULT_HERO_WORDS)
        letters = "".join(re.sub(r"[^A-Z]", "", str(word).upper()) for word in word_source) or "WORDSEARCHPUZZLES"
        for row in range(size + 1):
            od.line([(grid_left, grid_top + row * cell), (grid_left + size * cell, grid_top + row * cell)], fill=line_color, width=3)
        for column in range(size + 1):
            od.line([(grid_left + column * cell, grid_top), (grid_left + column * cell, grid_top + size * cell)], fill=line_color, width=3)
        for row in range(size):
            for column in range(size):
                letter = letters[(row * size + column) % len(letters)]
                od.text((grid_left + column * cell + 35, grid_top + row * cell + 31), letter, font=font, fill=letter_color)
    d._image.paste(overlay, (0, 0), overlay)
    # Restrained editorial label and a short accent rule make the cover feel
    # designed for this image rather than dropped into a template.
    format_text = format_label(a, include_word_search=True)
    is_large_print = "LARGE PRINT" in format_text
    # Photo covers used to render this important promise as a tiny caption.
    # A high-contrast pill makes it genuinely readable in a storefront thumbnail.
    label_font = f(ARIALB, 70 if is_large_print else 38)
    if is_large_print:
        label_width = d.textlength(format_text, font=label_font)
        d.rounded_rectangle([(W - label_width) / 2 - 38, 150, (W + label_width) / 2 + 38, 274],
                            radius=28, fill=deep, outline=hi, width=4)
        _centered(d, format_text, label_font, 169, hi)
    else:
        _centered(d, format_text, label_font, 205, hi)
        d.line([(W // 2 - 165, 278), (W // 2 + 165, 278)], fill=hi, width=5)
    title_size = 142
    title_lines = []
    for candidate in (154, 142, 130, 118, 106, 94):
        candidate_font = f(IMPACT, candidate)
        candidate_lines = _title_lines(d, a.title, candidate_font, W - 480)
        if len(candidate_lines) <= 3:
            title_size, title_lines = candidate, candidate_lines
            break
    if not title_lines:
        title_lines = _title_lines(d, a.title, f(IMPACT, title_size), W - 480)
    title_font = f(IMPACT, title_size)
    y = 345
    for line in title_lines:
        x = (W - d.textlength(line, font=title_font)) / 2
        # Photo covers can use a very dark palette background.  The old
        # palette-bg title ink became nearly invisible over a dark photo, so
        # use the palette highlight for consistently readable display type.
        d.text((x + 4, y + 5), line, font=title_font, fill=(0, 0, 0))
        d.text((x, y), line, font=title_font, fill=hi)
        y += int(title_size * 1.02)
    subtitle_font = f(ARIALB, 42)
    for line in wrap(d, a.subtitle, subtitle_font, W - 560)[:2]:
        _centered(d, line, subtitle_font, y + 20, hi)
        y += 58
    if a.badge:
        badge_font = f(ARIALB, 40)
        badge = a.badge.upper()
        badge_width = min(d.textlength(badge, font=badge_font), W - 420)
        bx0, bx1 = (W - badge_width) / 2 - 34, (W + badge_width) / 2 + 34
        d.rounded_rectangle([bx0, 2820, bx1, 2896], radius=20, fill=deep, outline=hi, width=3)
        _centered(d, badge, badge_font, 2837, bg)
    if a.author:
        _centered(d, a.author, f(ARIALB, 42), 3090, hi)


def mixed_brain_cover(d, a, palette, direction):
    """Premium mixed-puzzle compositions with no central preview panel."""
    bg, accent, deep, mute, hi = palette["bg"], palette["accent"], palette["deep"], palette["mute"], palette["hi"]
    if a.art and os.path.isfile(a.art):
        source = Image.open(a.art).convert("RGB")
        scale = max(W / source.width, H / source.height)
        resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
        left, top = (resized.width - W) // 2, max(0, (resized.height - H) // 2)
        d._image.paste(resized.crop((left, top, left + W, top + H)), (0, 0))
        veil = Image.new("RGBA", (W, H), (12, 20, 32, 128))
        d._image.paste(veil, (0, 0), veil)
    else:
        d.rectangle([0, 0, W, H], fill=deep)
    if direction == "mixed-editorial":
        d.rectangle([0, 0, int(W * .55), H], fill=deep)
        title_x, title_w, title_y = 190, int(W * .48), 360
        motif_center = (int(W * .77), 1830)
    elif direction == "mixed-logic":
        for radius, color in ((1300, accent), (990, hi), (680, deep)):
            d.ellipse([W // 2 - radius, 1650 - radius, W // 2 + radius, 1650 + radius], outline=color, width=32)
        title_x, title_w, title_y = 250, W - 500, 300
        motif_center = (W // 2, 2040)
    else:  # mixed-edge
        d.rectangle([0, 0, W, 920], fill=deep)
        d.rectangle([0, 920, W, 970], fill=hi)
        title_x, title_w, title_y = 220, W - 440, 260
        motif_center = (W // 2, 2110)
    label = format_label(a)
    d.text((title_x, title_y), label, font=f(ARIALB, 58), fill=hi)
    y = title_y + 115
    title_font = f(IMPACT, 142 if direction != "mixed-editorial" else 126)
    for line in _title_lines(d, a.title, title_font, title_w):
        d.text((title_x, y), line, font=title_font, fill=bg)
        y += 157
    subtitle_font = f(ARIALB, 40)
    for line in wrap(d, a.subtitle, subtitle_font, title_w)[:3]:
        d.text((title_x, y + 15), line, font=subtitle_font, fill=hi)
        y += 58
    # Independent motifs form a loose edge collage.  There is intentionally
    # no surrounding rectangle and no single dominant sample page.
    puzzle_type_hero(d, motif_center[0], motif_center[1], 118, accent, deep, hi)
    if a.badge:
        badge_font = f(ARIALB, 45)
        width = d.textlength(a.badge.upper(), font=badge_font)
        x0 = (W - width) / 2 - 30
        d.rounded_rectangle([x0, 2820, x0 + width + 60, 2900], radius=22, fill=hi, outline=deep, width=4)
        d.text((x0 + 30, 2835), a.badge.upper(), font=badge_font, fill=deep)
    if a.author:
        _centered(d, a.author, f(ARIALB, 44), 3100, bg)


def standout_cover(d, a, palette):
    """Three higher-contrast, print-safe alternatives to the classic layout."""
    bg, accent, deep, mute, hi = palette["bg"], palette["accent"], palette["deep"], palette["mute"], palette["hi"]
    style = a.style
    if style in {"mixed-edge", "mixed-editorial", "mixed-logic"} and COVER_PUZZLE_TYPE == "Mixed Brain Games":
        mixed_brain_cover(d, a, palette, style)
    elif style == "photo":
        photo_hero_cover(d, a, palette)
    elif style == "sunburst":
        sunburst_cover(d, a, palette)
    elif style == "playful":
        playful_90s_cover(d, a, palette)
    elif style == "bold":
        d.rectangle([0, 0, W, H], fill=deep)
        for x in range(-400, W + 500, 250):
            d.line([(x, 0), (x + 880, H)], fill=accent, width=42)
        d.rounded_rectangle([150, 130, W - 150, 940], radius=50, fill=bg)
        label_font = f(IMPACT, 112)
        _centered(d, format_label(a), label_font, 205, deep)
        title_font = f(IMPACT, 174)
        y = 390
        for line in _title_lines(d, a.title, title_font, W - 420):
            _centered(d, line, title_font, y, deep)
            y += 185
        subtitle_font = f(ARIAL, 54)
        for line in wrap(d, a.subtitle, subtitle_font, W - 520):
            _centered(d, line, subtitle_font, y + 25, mute)
            y += 72
        d.rounded_rectangle([335, 1135, W - 335, 2580], radius=42, fill=bg, outline=hi, width=18)
        hero_grid(d, W // 2, 1850, cell=132, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
        if a.badge:
            badge_font = f(IMPACT, 92)
            badge_w = d.textlength(a.badge, font=badge_font)
            d.rounded_rectangle([(W - badge_w) / 2 - 58, 2665, (W + badge_w) / 2 + 58, 2805], radius=30, fill=hi)
            _centered(d, a.badge, badge_font, 2684, deep)
        if a.author:
            _centered(d, a.author, f(ARIALB, 62), 3050, bg)
    elif style == "retro":
        d.rectangle([0, 0, W, H], fill=bg)
        # A restrained 90s-inspired frame: visual personality without competing
        # with title legibility when the cover is seen at Amazon thumbnail size.
        d.rectangle([0, 0, W, 165], fill=accent)
        d.rectangle([0, H - 165, W, H], fill=accent)
        d.rounded_rectangle([170, 210, W - 170, 1040], radius=44, fill=deep)
        for cx, cy, radius in [(230, 250, 78), (2320, 250, 78), (230, 3070, 78), (2320, 3070, 78)]:
            d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=hi)
            d.line([(cx - radius // 2, cy + radius // 2), (cx + radius // 2, cy - radius // 2)], fill=accent, width=15)
        _centered(d, format_label(a), f(IMPACT, 90), 285, hi)
        title_font = f(IMPACT, 132)
        y = 445
        for line in _title_lines(d, a.title, title_font, W - 500):
            _centered(d, line, title_font, y, bg)
            y += 150
        subtitle_font = f(ARIALB, 44)
        for line in wrap(d, a.subtitle, subtitle_font, W - 560):
            _centered(d, line, subtitle_font, y + 14, hi)
            y += 59
        # The proof grid supports the sale without overwhelming the cover.
        d.rounded_rectangle([545, 1215, W - 545, 2355], radius=26, fill=bg, outline=deep, width=12)
        hero_grid(d, W // 2, 1785, cell=104, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
        if a.badge:
            badge_font = f(IMPACT, 72)
            badge_width = d.textlength(a.badge, font=badge_font)
            d.rounded_rectangle([(W - badge_width) / 2 - 42, 2475, (W + badge_width) / 2 + 42, 2605], radius=28, fill=hi)
            _centered(d, a.badge, badge_font, 2497, deep)
        if a.author:
            _centered(d, a.author, f(ARIALB, 56), 2820, deep)
    elif style == "gallery":
        d.rectangle([0, 0, W, H], fill=bg)
        d.rectangle([0, 0, W, 920], fill=deep)
        d.rectangle([0, 920, W, 980], fill=hi)
        _centered(d, format_label(a), f(ARIALB, 72), 150, hi)
        y = 300
        title_font = f(IMPACT, 138)
        for line in _title_lines(d, a.title, title_font, W - 430):
            _centered(d, line, title_font, y, bg); y += 150
        d.rounded_rectangle([300, 1160, W - 300, 2540], radius=38, fill=(255, 255, 255), outline=accent, width=18)
        hero_grid(d, W // 2, 1845, cell=126, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
        if a.badge: _centered(d, a.badge, f(ARIALB, 70), 2665, accent)
        if a.author: _centered(d, a.author, f(ARIALB, 58), 3000, deep)
    elif style == "colorblock":
        d.rectangle([0, 0, W, H], fill=accent)
        d.rectangle([0, 0, W, 1120], fill=deep)
        d.rectangle([150, 150, W - 150, 970], fill=bg)
        _centered(d, format_label(a), f(ARIALB, 70), 220, accent)
        y = 390
        for line in _title_lines(d, a.title, f(IMPACT, 132), W - 440):
            _centered(d, line, f(IMPACT, 132), y, deep); y += 145
        hero_grid(d, W // 2, 1900, cell=146, theme=a.theme or a.palette, accent=hi, deep=deep, hi=bg)
        if a.badge: _centered(d, a.badge, f(ARIALB, 72), 2780, deep)
        if a.author: _centered(d, a.author, f(ARIALB, 58), 3040, deep)
    elif style == "ticket":
        d.rectangle([0, 0, W, H], fill=hi)
        d.rounded_rectangle([130, 150, W - 130, H - 150], radius=55, fill=bg, outline=deep, width=16)
        for y in (520, 2780): d.line([(220, y), (W - 220, y)], fill=accent, width=8)
        _centered(d, f"{format_label(a)} COLLECTION", f(ARIALB, 65), 260, accent)
        y = 640
        for line in _title_lines(d, a.title, f(IMPACT, 135), W - 460): _centered(d, line, f(IMPACT, 135), y, deep); y += 150
        hero_grid(d, W // 2, 1790, cell=128, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
        if a.badge: _centered(d, a.badge, f(ARIALB, 72), 2475, accent)
        if a.author: _centered(d, a.author, f(ARIALB, 56), 2950, deep)
    elif style == "halo":
        d.rectangle([0, 0, W, H], fill=deep)
        for radius, color in ((1050, accent), (800, hi), (560, bg)):
            d.ellipse([W//2-radius, 1700-radius, W//2+radius, 1700+radius], outline=color, width=34)
        d.rounded_rectangle([190, 160, W-190, 1010], radius=48, fill=bg)
        _centered(d, format_label(a), f(ARIALB, 68), 245, accent)
        y=440
        for line in _title_lines(d, a.title, f(IMPACT, 138), W-480): _centered(d,line,f(IMPACT,138),y,deep); y+=150
        hero_grid(d, W//2, 1750, cell=122, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
        if a.badge: _centered(d,a.badge,f(ARIALB,70),2600,bg)
        if a.author: _centered(d,a.author,f(ARIALB,56),3040,bg)
    elif style == "stripe":
        d.rectangle([0,0,W,H],fill=bg)
        for x in range(-500,W+600,330): d.polygon([(x,0),(x+110,0),(x+W,H),(x+W-110,H)],fill=accent)
        d.rounded_rectangle([260,210,W-260,1120],radius=46,fill=deep)
        _centered(d,format_label(a),f(ARIALB,68),290,hi); y=480
        for line in _title_lines(d,a.title,f(IMPACT,134),W-580): _centered(d,line,f(IMPACT,134),y,bg); y+=148
        hero_grid(d,W//2,1920,cell=138,theme=a.theme or a.palette,accent=hi,deep=deep,hi=bg)
        if a.badge: _centered(d,a.badge,f(ARIALB,72),2750,deep)
        if a.author: _centered(d,a.author,f(ARIALB,56),3030,deep)
    else:  # minimal
        d.rectangle([0, 0, W, H], fill=bg)
        d.rectangle([150, 150, W - 150, H - 150], outline=accent, width=7)
        d.line([(360, 385), (W - 360, 385)], fill=accent, width=8)
        _centered(d, format_label(a), f(ARIALB, 78), 220, accent)
        title_font = f(GEORGIA, 126)
        y = 480
        for line in _title_lines(d, a.title, title_font, W - 500):
            _centered(d, line, title_font, y, deep)
            y += 145
        subtitle_font = f(ARIAL, 50)
        for line in wrap(d, a.subtitle, subtitle_font, W - 600):
            _centered(d, line, subtitle_font, y + 14, mute)
            y += 64
        hero_grid(d, W // 2, 1930, cell=140, theme=a.theme or a.palette, accent=accent, deep=deep, hi=hi)
        if a.badge:
            _centered(d, a.badge, f(ARIALB, 68), 2695, accent)
        if a.author:
            _centered(d, a.author, f(ARIALB, 58), 3005, deep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--badge", default="")
    ap.add_argument("--puzzle-count", type=int, default=0,
                    help="actual number of puzzles; shown as a clear cover stamp")
    ap.add_argument("--difficulty", default="", help="book-level difficulty shown as a small cover marker")
    ap.add_argument("--format-label", default="WORD SEARCH", help="truthful cover format label, such as LARGE PRINT or WORD SEARCH")
    ap.add_argument("--puzzle-type", default="Word Search", choices=("Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"), help="selects the truthful cover proof visual")
    ap.add_argument("--palette", default="nature")
    ap.add_argument("--theme", default=None, help="silhouette theme; defaults to --palette")
    ap.add_argument("--theme-file", default=None, help="theme JSON used for real-word puzzle cover details")
    ap.add_argument("--art", default=None, help="licensed image used by the Photo Hero layout")
    ap.add_argument("--art-focus", choices=("top", "center", "bottom"), default="center", help="automatic crop focus for Photo Hero artwork")
    ap.add_argument("--style", choices=("classic", "photo", "playful", "sunburst", "bold", "retro", "minimal", "gallery", "colorblock", "ticket", "halo", "stripe", "mixed-edge", "mixed-editorial", "mixed-logic"), default="classic")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true", help="write a quick 510x660 preview instead of a print cover")
    a = ap.parse_args()

    # Review-only previews may display a pending candidate. Every printable
    # render fails closed here, regardless of which caller supplied the path.
    approved_asset = None if a.preview else require_production_approved_cover_asset(a.art)

    global COVER_PUZZLE_TYPE
    COVER_PUZZLE_TYPE = a.puzzle_type
    random.seed(11)
    theme = a.theme or a.palette
    a.cover_words = theme_words(a.theme_file)
    P = PALETTES.get(a.palette, PALETTES["nature"])
    bg, accent, deep, mute, hi = P["bg"], P["accent"], P["deep"], P["mute"], P["hi"]

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    if a.style != "classic":
        standout_cover(d, a, P)
        difficulty_chip(d, a.difficulty, P)
        puzzle_count_stamp(d, a.puzzle_count, P)
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        if a.preview:
            img.resize((510, 660), Image.Resampling.LANCZOS).save(a.out, "PNG")
            print(f"PREVIEW -> {a.out}")
            return
        img.save(a.out, "PNG")
        write_cover_approval_proof(a.out, approved_asset)
        img.resize((255, 330), Image.Resampling.LANCZOS).save(
            os.path.splitext(a.out)[0] + "_thumbnail.png", "PNG"
        )
        print(f"DONE -> {a.out}  ({W}x{H}, palette={a.palette}, style={a.style})")
        return

    # double frame
    m = 120
    d.rectangle([m, m, W - m, H - m], outline=accent, width=8)
    d.rectangle([m + 32, m + 32, W - m - 32, H - m - 32], outline=accent, width=3)

    # theme silhouettes (4 corners-ish)
    for fn, fx, fy, scale in THEME_DECOR.get(theme, []):
        fn(d, int(W * fx), int(H * fy), scale, accent)

    # ---- TITLE block ----
    # Truthful stand-alone format bar (high contrast attention grab at thumbnail size)
    lpf = f(IMPACT, 138)
    lp = format_label(a)
    lpw = d.textlength(lp, font=lpf)
    bar_pad_x, bar_pad_y = 60, 28
    bx0, by0 = (W - lpw) / 2 - bar_pad_x, 380 - bar_pad_y
    bx1, by1 = (W + lpw) / 2 + bar_pad_x, 380 + 138 + bar_pad_y
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=22, fill=deep)
    d.text(((W - lpw) / 2, 380 - 6), lp, font=lpf, fill=hi)

    # niche line ("NATURE WORD SEARCH" / "FOOD & KITCHEN WORD SEARCH" / etc.)
    # extract everything AFTER "LARGE PRINT " from the title
    title_rest = a.title.upper()
    if title_rest.startswith("LARGE PRINT "):
        title_rest = title_rest[len("LARGE PRINT "):]
    # Auto-fit the niche title to at most 2 lines so a long title (e.g.
    # "RETRO TRAVEL AND LANDMARKS WORD SEARCH") can't wrap to 3 lines and push
    # the subtitle down into the hero grid — that overlap is a defective cover.
    maxw = W - 2 * (m + 90)
    tsize = 96
    for cand in (174, 156, 138, 122, 108, 96):
        if len(wrap(d, title_rest, f(GEORGIA, cand), maxw)) <= 2:
            tsize = cand
            break
    tf = f(GEORGIA, tsize)
    lh = int(tsize * 1.13)
    y = by1 + 60
    for ln in wrap(d, title_rest, tf, maxw):
        tw = d.textlength(ln, font=tf)
        d.text(((W - tw) / 2, y), ln, font=tf, fill=deep)
        y += lh

    # divider
    y += 14
    d.line([(W // 2 - 240, y), (W // 2 + 240, y)], fill=accent, width=4)
    y += 56

    # subtitle
    sf = f(ARIAL, 60)
    for ln in wrap(d, a.subtitle, sf, W - 2 * (m + 200)):
        tw = d.textlength(ln, font=sf)
        d.text(((W - tw) / 2, y), ln, font=sf, fill=mute)
        y += 84

    # ---- HERO puzzle grid (the proof) — sized so badge sits cleanly BELOW it ----
    grid_cell = 128
    grid_cy = 1980
    hero_grid(d, W // 2, grid_cy, cell=grid_cell, theme=theme, accent=accent, deep=deep, hi=hi)

    # ---- BADGE (placed below grid with clear gap) ----
    grid_bottom = grid_cy + (9 * grid_cell) // 2
    if a.badge:
        vf = f(IMPACT, 110)
        vw = d.textlength(a.badge, font=vf)
        by = grid_bottom + 140
        bx = (W - vw) / 2
        pad = 64
        d.rounded_rectangle([bx - pad, by - 26, bx + vw + pad, by + 128], radius=30,
                            fill=hi, outline=deep, width=5)
        d.text((bx, by - 6), a.badge, font=vf, fill=deep)

    # ---- author ----
    if a.author:
        af = f(ARIALB, 68)
        aw = d.textlength(a.author, font=af)
        d.text(((W - aw) / 2, H - 280), a.author, font=af, fill=deep)

    difficulty_chip(d, a.difficulty, P)
    puzzle_count_stamp(d, a.puzzle_count, P)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    if a.preview:
        img.resize((510, 660), Image.Resampling.LANCZOS).save(a.out, "PNG")
        print(f"PREVIEW -> {a.out}")
        return
    img.save(a.out, "PNG")
    write_cover_approval_proof(a.out, approved_asset)
    img.resize((255, 330), Image.Resampling.LANCZOS).save(
        os.path.splitext(a.out)[0] + "_thumbnail.png", "PNG"
    )
    print(f"DONE -> {a.out}  ({W}x{H}, palette={a.palette}, theme={theme})")


if __name__ == "__main__":
    main()
