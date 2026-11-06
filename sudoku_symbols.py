"""Topic-aware, font-free vector symbols for special Sudoku editions.

Every drawing is made from PDF vector primitives.  This avoids missing-glyph
problems and keeps puzzle and solution pages identical on every computer.
"""
from __future__ import annotations

import math
import re


PACK_LABELS = {
    "classic": "CLASSIC SHAPE SUDOKU",
    "nature": "NATURE SYMBOL SUDOKU",
    "winter_holiday": "HOLIDAY SYMBOL SUDOKU",
    "new_year": "NEW YEAR SYMBOL SUDOKU",
    "valentine": "VALENTINE SYMBOL SUDOKU",
    "easter": "EASTER SYMBOL SUDOKU",
    "mothers_day": "MOTHER'S DAY SYMBOL SUDOKU",
    "fathers_day": "FATHER'S DAY SYMBOL SUDOKU",
    "independence": "INDEPENDENCE DAY SYMBOL SUDOKU",
    "thanksgiving": "THANKSGIVING SYMBOL SUDOKU",
    "hanukkah": "HANUKKAH SYMBOL SUDOKU",
    "halloween": "HALLOWEEN SYMBOL SUDOKU",
    "sports": "SPORTS SYMBOL SUDOKU",
    "space": "SPACE SYMBOL SUDOKU",
    "ocean": "OCEAN SYMBOL SUDOKU",
    "pets": "PET SYMBOL SUDOKU",
    "kitchen": "KITCHEN SYMBOL SUDOKU",
    "travel": "TRAVEL SYMBOL SUDOKU",
}

PACKS = {
    "classic": ("circle", "square", "triangle", "diamond", "plus", "cross", "dot", "ring", "star"),
    "nature": ("sun", "leaf", "flower", "tree", "mountain", "wave", "moon", "butterfly", "seedling"),
    "winter_holiday": ("snowflake", "tree", "gift", "ornament", "bell", "candy_cane", "star", "mitten", "candle"),
    "new_year": ("star", "bell", "balloon", "clock", "gift", "party_hat", "candle", "confetti", "firework"),
    "valentine": ("heart", "flower", "gift", "candy", "cupcake", "butterfly", "envelope", "bow", "candle"),
    "easter": ("egg", "bunny", "basket", "flower", "seedling", "sun", "bird", "butterfly", "carrot"),
    "mothers_day": ("flower", "heart", "gift", "envelope", "cupcake", "butterfly", "sun", "mug", "candle"),
    "fathers_day": ("tie", "trophy", "car", "compass", "heart", "gift", "camera", "hat", "mug"),
    "independence": ("flag", "star", "firework", "bell", "sun", "balloon", "medal", "bunting", "lantern"),
    "thanksgiving": ("pumpkin", "leaf", "pie", "turkey", "basket", "apple", "candle", "mug", "bread"),
    "hanukkah": ("candle", "menorah", "dreidel", "star", "gift", "coin", "oil_jug", "flame", "scroll"),
    "halloween": ("pumpkin", "ghost", "bat", "moon", "web", "candy", "hat", "skull", "cat"),
    "sports": ("soccer", "basketball", "football", "baseball", "trophy", "racket", "whistle", "flag", "medal"),
    "space": ("sun", "moon", "star", "planet", "rocket", "comet", "telescope", "orbit", "constellation"),
    "ocean": ("wave", "fish", "shell", "star", "anchor", "boat", "octopus", "lighthouse", "dolphin"),
    "pets": ("paw", "cat", "dog", "bone", "fish", "bird", "collar", "ball", "heart"),
    "kitchen": ("cupcake", "spoon", "pan", "rolling_pin", "apple", "mug", "bread", "chef_hat", "cookie"),
    "travel": ("car", "camper", "compass", "mountain", "sign", "suitcase", "pin", "tent", "camera"),
}


def symbol_pack_for_theme(theme: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(theme or "").casefold()).strip()
    rules = (
        (("new year", "new year's"), "new_year"),
        (("valentine",), "valentine"),
        (("easter",), "easter"),
        (("mother s day", "mothers day"), "mothers_day"),
        (("father s day", "fathers day"), "fathers_day"),
        (("independence day", "fourth of july", "july fourth"), "independence"),
        (("thanksgiving",), "thanksgiving"),
        (("hanukkah", "chanukah"), "hanukkah"),
        (("halloween", "spooky", "haunted"), "halloween"),
        (("christmas", "winter", "holiday", "festive"), "winter_holiday"),
        (("sport", "football", "baseball", "basketball", "soccer", "athletic"), "sports"),
        (("space", "planet", "astronomy", "cosmic", "stargazer"), "space"),
        (("ocean", "sea", "marine", "beach", "coastal"), "ocean"),
        (("cat", "dog", "pet", "animal companion"), "pets"),
        (("baking", "food", "kitchen", "cooking", "culinary"), "kitchen"),
        (("travel", "road trip", "camping", "adventure", "rv", "camper"), "travel"),
        (("nature", "garden", "growing", "forest", "national park", "outdoor", "wildlife"), "nature"),
    )
    for needles, pack in rules:
        if any(needle in text for needle in needles):
            return pack
    return "classic"


def pack_label(pack: str) -> str:
    return PACK_LABELS.get(pack, PACK_LABELS["classic"])


def _poly(c, points, fill=0):
    p = c.beginPath(); p.moveTo(*points[0])
    for point in points[1:]: p.lineTo(*point)
    p.close(); c.drawPath(p, stroke=1, fill=fill)


def _star(c, x, y, r, fill=0):
    points=[]
    for i in range(10):
        a=math.pi/2+i*math.pi/5; rr=r if i%2==0 else r*.42
        points.append((x+math.cos(a)*rr, y+math.sin(a)*rr))
    _poly(c, points, fill)


def _icon(c, name, x, y, r):
    # Small, deliberately simple silhouettes remain legible in 30-50 pt cells.
    if name in {"circle", "ball", "cookie"}: c.circle(x,y,r*.72,stroke=1,fill=0)
    elif name == "ornament": c.circle(x,y-r*.05,r*.65,stroke=1,fill=0); c.rect(x-r*.15,y+r*.58,r*.3,r*.18,stroke=1,fill=0); c.arc(x-r*.22,y+r*.67,x+r*.22,y+r*1.05,0,180)
    elif name == "baseball": c.circle(x,y,r*.72,stroke=1,fill=0); c.arc(x-r*.52,y-r*.72,x+r*.18,y+r*.72,270,180); c.arc(x-r*.18,y-r*.72,x+r*.52,y+r*.72,90,180)
    elif name == "square": c.rect(x-r*.68,y-r*.68,r*1.36,r*1.36,stroke=1,fill=0)
    elif name == "triangle": _poly(c,[(x,y+r*.8),(x-r*.75,y-r*.65),(x+r*.75,y-r*.65)])
    elif name == "diamond": _poly(c,[(x,y+r*.8),(x-r*.7,y),(x,y-r*.8),(x+r*.7,y)])
    elif name == "plus": c.line(x-r*.7,y,x+r*.7,y); c.line(x,y-r*.7,x,y+r*.7)
    elif name == "cross": c.line(x-r*.6,y-r*.6,x+r*.6,y+r*.6); c.line(x-r*.6,y+r*.6,x+r*.6,y-r*.6)
    elif name == "dot": c.circle(x,y,r*.6,stroke=1,fill=1)
    elif name == "ring": c.circle(x,y,r*.72,stroke=1,fill=0); c.circle(x,y,r*.3,stroke=1,fill=0)
    elif name in {"star", "starfish"}: _star(c,x,y,r*.82)
    elif name == "sun": c.circle(x,y,r*.35,stroke=1,fill=0); [c.line(x+math.cos(a)*r*.48,y+math.sin(a)*r*.48,x+math.cos(a)*r*.82,y+math.sin(a)*r*.82) for a in [i*math.pi/4 for i in range(8)]]
    elif name == "moon": c.circle(x,y,r*.72,stroke=1,fill=0); c.arc(x-r*.05,y-r*.7,x+r*.95,y+r*.7,90,180)
    elif name == "leaf": c.ellipse(x-r*.7,y-r*.35,x+r*.7,y+r*.35,stroke=1,fill=0); c.line(x-r*.55,y-r*.25,x+r*.55,y+r*.25)
    elif name == "flower": c.circle(x,y,r*.2,stroke=1,fill=0); [c.circle(x+math.cos(a)*r*.48,y+math.sin(a)*r*.48,r*.25,stroke=1,fill=0) for a in [i*math.pi/2 for i in range(4)]]
    elif name == "tree": _poly(c,[(x,y+r*.85),(x-r*.7,y-r*.2),(x+r*.7,y-r*.2)]); c.rect(x-r*.12,y-r*.72,r*.24,r*.52,stroke=1,fill=0)
    elif name == "mountain": _poly(c,[(x-r*.85,y-r*.55),(x-r*.2,y+r*.65),(x+r*.15,y),(x+r*.45,y+r*.5),(x+r*.85,y-r*.55)],0)
    elif name == "wave": c.bezier(x-r*.85,y,x-r*.4,y+r*.7,x,y-r*.7,x+r*.85,y)
    elif name == "butterfly": c.ellipse(x-r*.75,y,x-r*.05,y+r*.65,stroke=1,fill=0); c.ellipse(x+r*.05,y,x+r*.75,y+r*.65,stroke=1,fill=0); c.line(x,y-r*.55,x,y+r*.5)
    elif name == "seedling": c.line(x,y-r*.75,x,y+r*.35); c.ellipse(x-r*.65,y,x,y+r*.45,stroke=1,fill=0); c.ellipse(x,y-r*.05,x+r*.65,y+r*.4,stroke=1,fill=0)
    elif name == "snowflake": [c.line(x+math.cos(a)*r*.8,y+math.sin(a)*r*.8,x-math.cos(a)*r*.8,y-math.sin(a)*r*.8) for a in (0,math.pi/3,2*math.pi/3)]
    elif name == "gift": c.rect(x-r*.65,y-r*.55,r*1.3,r*1.05,stroke=1,fill=0); c.line(x,y-r*.55,x,y+r*.5); c.line(x-r*.65,y+r*.15,x+r*.65,y+r*.15)
    elif name == "bell": c.arc(x-r*.55,y-r*.35,x+r*.55,y+r*.7,0,180); c.line(x-r*.55,y+.15*r,x-r*.7,y-r*.4); c.line(x+r*.55,y+.15*r,x+r*.7,y-r*.4); c.line(x-r*.7,y-r*.4,x+r*.7,y-r*.4); c.circle(x,y-r*.58,r*.12,stroke=1,fill=1)
    elif name == "candy_cane": c.arc(x-r*.2,y,x+r*.7,y+r*.8,0,180); c.line(x-r*.2,y+r*.4,x-r*.2,y-r*.75)
    elif name == "mitten": c.roundRect(x-r*.35,y-r*.65,r*.7,r*1.2,r*.25,stroke=1,fill=0); c.circle(x-r*.4,y,r*.3,stroke=1,fill=0)
    elif name == "candle": c.rect(x-r*.28,y-r*.65,r*.56,r*1.0,stroke=1,fill=0); _poly(c,[(x,y+r*.85),(x-r*.2,y+r*.45),(x+r*.2,y+r*.45)])
    elif name == "balloon": c.ellipse(x-r*.45,y-r*.2,x+r*.45,y+r*.7,stroke=1,fill=0); c.line(x,y-r*.2,x+r*.15,y-r*.78)
    elif name == "clock":
        c.circle(x,y,r*.7,stroke=1,fill=0); c.line(x,y,x,y+r*.43); c.line(x,y,x+r*.34,y-r*.18)
    elif name == "party_hat": _poly(c,[(x,y+r*.82),(x-r*.65,y-r*.5),(x+r*.65,y-r*.5)]); c.circle(x,y+r*.83,r*.12,stroke=1,fill=0)
    elif name == "confetti":
        for dx,dy in ((-.55,.5),(.25,.55),(.55,-.1),(-.4,-.35),(.1,-.6)):
            c.circle(x+dx*r,y+dy*r,r*.12,stroke=1,fill=0)
    elif name == "firework":
        for i in range(8):
            a=i*math.pi/4; c.line(x+math.cos(a)*r*.25,y+math.sin(a)*r*.25,x+math.cos(a)*r*.8,y+math.sin(a)*r*.8)
        c.circle(x,y,r*.14,stroke=1,fill=0)
    elif name == "envelope": c.rect(x-r*.75,y-r*.4,r*1.5,r*.85,stroke=1,fill=0); c.line(x-r*.75,y+r*.45,x,y-r*.05); c.line(x+r*.75,y+r*.45,x,y-r*.05)
    elif name == "bow":
        _poly(c,[(x,y),(x-r*.8,y+r*.5),(x-r*.8,y-r*.5)]); _poly(c,[(x,y),(x+r*.8,y+r*.5),(x+r*.8,y-r*.5)]); c.circle(x,y,r*.18,stroke=1,fill=0)
    elif name == "egg": c.ellipse(x-r*.5,y-r*.7,x+r*.5,y+r*.7,stroke=1,fill=0); c.line(x-r*.36,y,x+r*.36,y)
    elif name == "bunny":
        c.circle(x,y-r*.2,r*.48,stroke=1,fill=0)
        for dx in (-r*.26,r*.26): c.ellipse(x+dx-r*.16,y+r*.12,x+dx+r*.16,y+r*.88,stroke=1,fill=0)
        c.circle(x-r*.15,y-r*.15,r*.05,stroke=1,fill=1); c.circle(x+r*.15,y-r*.15,r*.05,stroke=1,fill=1)
    elif name == "basket": c.arc(x-r*.55,y-r*.2,x+r*.55,y+r*.85,0,180); c.rect(x-r*.7,y-r*.48,r*1.4,r*.78,stroke=1,fill=0)
    elif name == "carrot": _poly(c,[(x-r*.4,y+r*.55),(x+r*.4,y+r*.55),(x,y-r*.78)]); c.line(x,y+r*.52,x-r*.35,y+r*.85); c.line(x,y+r*.52,x+r*.35,y+r*.85)
    elif name == "tie": _poly(c,[(x-r*.28,y+r*.72),(x+r*.28,y+r*.72),(x+r*.15,y+r*.4),(x+r*.36,y-r*.64),(x,y-r*.82),(x-r*.36,y-r*.64),(x-r*.15,y+r*.4)]);
    elif name == "bunting":
        c.line(x-r*.85,y+r*.45,x+r*.85,y+r*.45)
        for dx in (-r*.58,0,r*.58): _poly(c,[(x+dx-r*.23,y+r*.44),(x+dx+r*.23,y+r*.44),(x+dx,y-r*.35)])
    elif name == "lantern": c.roundRect(x-r*.55,y-r*.55,r*1.1,r*1.05,r*.18,stroke=1,fill=0); c.arc(x-r*.32,y+r*.35,x+r*.32,y+r*.82,0,180)
    elif name == "pie": c.ellipse(x-r*.75,y-r*.45,x+r*.75,y+r*.35,stroke=1,fill=0); c.line(x-r*.65,y,x+r*.65,y); c.line(x,y,x+r*.35,y+r*.32)
    elif name == "turkey":
        for dx in (-r*.5,-r*.25,0,r*.25,r*.5): c.ellipse(x+dx-r*.2,y+r*.05,x+dx+r*.2,y+r*.75,stroke=1,fill=0)
        c.circle(x,y-r*.22,r*.42,stroke=1,fill=0); c.circle(x-r*.11,y-r*.18,r*.05,stroke=1,fill=1)
    elif name == "menorah":
        c.line(x-r*.7,y-r*.55,x+r*.7,y-r*.55); c.line(x,y-r*.55,x,y+r*.55)
        for dx in (-.72,-.52,-.34,-.16,.16,.34,.52,.72):
            c.line(x+dx*r,y-r*.06,x+dx*r,y+r*.48); c.circle(x+dx*r,y+r*.6,r*.07,stroke=1,fill=0)
        c.circle(x,y+r*.72,r*.07,stroke=1,fill=0)
    elif name == "dreidel": _poly(c,[(x-r*.52,y+r*.42),(x+r*.52,y+r*.42),(x+r*.52,y-r*.18),(x,y-r*.78),(x-r*.52,y-r*.18)]); c.line(x,y+r*.42,x,y+r*.82)
    elif name == "coin": c.circle(x,y,r*.7,stroke=1,fill=0); c.circle(x,y,r*.48,stroke=1,fill=0)
    elif name == "oil_jug": c.ellipse(x-r*.48,y-r*.65,x+r*.48,y+r*.4,stroke=1,fill=0); c.line(x-r*.18,y+r*.4,x-r*.18,y+r*.75); c.line(x+r*.18,y+r*.4,x+r*.18,y+r*.75); c.line(x-r*.18,y+r*.75,x+r*.18,y+r*.75)
    elif name == "flame": _poly(c,[(x,y+r*.85),(x-r*.48,y-r*.15),(x-r*.2,y-r*.67),(x+r*.2,y-r*.67),(x+r*.48,y-r*.15)]);
    elif name == "scroll": c.rect(x-r*.58,y-r*.65,r*1.16,r*1.3,stroke=1,fill=0); c.circle(x-r*.58,y-r*.65,r*.11,stroke=1,fill=0); c.circle(x+r*.58,y+r*.65,r*.11,stroke=1,fill=0)
    elif name in {"pumpkin", "apple"}: c.ellipse(x-r*.72,y-r*.55,x+r*.72,y+r*.55,stroke=1,fill=0); c.line(x,y+r*.5,x+r*.12,y+r*.82)
    elif name == "ghost": c.circle(x,y+r*.18,r*.58,stroke=1,fill=0); c.line(x-r*.58,y+.15*r,x-r*.58,y-r*.65); c.line(x+r*.58,y+.15*r,x+r*.58,y-r*.65); c.circle(x-r*.2,y+r*.25,r*.06,stroke=1,fill=1); c.circle(x+r*.2,y+r*.25,r*.06,stroke=1,fill=1)
    elif name == "bat": c.line(x-r*.85,y+r*.2,x,y-r*.3); c.line(x,y-r*.3,x+r*.85,y+r*.2); c.arc(x-r*.8,y-r*.45,x,y+r*.35,0,180); c.arc(x,y-r*.45,x+r*.8,y+r*.35,0,180)
    elif name == "web": [c.line(x,y,x+math.cos(a)*r*.8,y+math.sin(a)*r*.8) for a in [i*math.pi/4 for i in range(8)]]; c.circle(x,y,r*.5,stroke=1,fill=0)
    elif name == "candy": c.ellipse(x-r*.35,y-r*.3,x+r*.35,y+r*.3,stroke=1,fill=0); _poly(c,[(x-r*.35,y),(x-r*.8,y+r*.35),(x-r*.75,y-r*.35)]); _poly(c,[(x+r*.35,y),(x+r*.8,y+r*.35),(x+r*.75,y-r*.35)])
    elif name == "hat": _poly(c,[(x-r*.15,y+r*.8),(x-r*.55,y-r*.25),(x+r*.55,y-r*.25)]); c.line(x-r*.8,y-r*.3,x+r*.8,y-r*.3)
    elif name == "skull": c.circle(x,y+r*.15,r*.58,stroke=1,fill=0); c.rect(x-r*.32,y-r*.65,r*.64,r*.35,stroke=1,fill=0); c.circle(x-r*.2,y+r*.2,r*.1,stroke=1,fill=1); c.circle(x+r*.2,y+r*.2,r*.1,stroke=1,fill=1)
    elif name == "cat": c.circle(x,y,r*.55,stroke=1,fill=0); _poly(c,[(x-r*.5,y+r*.35),(x-r*.7,y+r*.8),(x-r*.15,y+r*.55)]); _poly(c,[(x+r*.5,y+r*.35),(x+r*.7,y+r*.8),(x+r*.15,y+r*.55)])
    elif name == "dog": c.circle(x,y,r*.55,stroke=1,fill=0); c.ellipse(x-r*.82,y-r*.05,x-r*.42,y+r*.65,stroke=1,fill=0); c.ellipse(x+r*.42,y-r*.05,x+r*.82,y+r*.65,stroke=1,fill=0); c.circle(x,y-r*.12,r*.12,stroke=1,fill=1)
    elif name == "soccer": c.circle(x,y,r*.75,stroke=1,fill=0); _poly(c,[(x,y+r*.3),(x-r*.28,y+r*.08),(x-r*.17,y-r*.25),(x+r*.17,y-r*.25),(x+r*.28,y+r*.08)])
    elif name == "basketball": c.circle(x,y,r*.75,stroke=1,fill=0); c.line(x-r*.75,y,x+r*.75,y); c.line(x,y-r*.75,x,y+r*.75); c.arc(x-r*.75,y-r*.45,x+r*.75,y+r*.45,180,180)
    elif name == "football": c.ellipse(x-r*.82,y-r*.45,x+r*.82,y+r*.45,stroke=1,fill=0); c.line(x-r*.28,y,x+r*.28,y); [c.line(x+d,y-r*.12,x+d,y+r*.12) for d in (-r*.16,0,r*.16)]
    elif name == "trophy": c.rect(x-r*.35,y-r*.1,r*.7,r*.7,stroke=1,fill=0); c.arc(x-r*.75,y,x-r*.2,y+r*.55,90,180); c.arc(x+r*.2,y,x+r*.75,y+r*.55,270,180); c.line(x,y-r*.1,x,y-r*.6); c.line(x-r*.35,y-r*.6,x+r*.35,y-r*.6)
    elif name == "racket": c.ellipse(x-r*.6,y,x+r*.2,y+r*.8,stroke=1,fill=0); c.line(x,y,x+r*.65,y-r*.65)
    elif name == "whistle": c.circle(x-r*.15,y,r*.42,stroke=1,fill=0); c.rect(x+r*.2,y-r*.15,r*.55,r*.3,stroke=1,fill=0)
    elif name == "flag": c.line(x-r*.55,y-r*.75,x-r*.55,y+r*.75); _poly(c,[(x-r*.55,y+r*.7),(x+r*.65,y+r*.35),(x-r*.55,y)])
    elif name == "medal": c.circle(x,y-r*.25,r*.4,stroke=1,fill=0); c.line(x-r*.35,y+r*.75,x,y+r*.15); c.line(x+r*.35,y+r*.75,x,y+r*.15)
    elif name == "planet": c.circle(x,y,r*.42,stroke=1,fill=0); c.ellipse(x-r*.85,y-r*.25,x+r*.85,y+r*.25,stroke=1,fill=0)
    elif name == "rocket": _poly(c,[(x,y+r*.85),(x-r*.35,y-r*.35),(x,y-r*.15),(x+r*.35,y-r*.35)]); c.line(x-r*.18,y-r*.25,x-r*.35,y-r*.75); c.line(x+r*.18,y-r*.25,x+r*.35,y-r*.75)
    elif name == "comet": c.circle(x+r*.35,y+r*.2,r*.3,stroke=1,fill=0); c.line(x+r*.05,y,x-r*.75,y-r*.55); c.line(x+r*.08,y+r*.25,x-r*.65,y-r*.1)
    elif name == "telescope": c.line(x-r*.1,y-r*.1,x-r*.45,y-r*.75); c.line(x-r*.1,y-r*.1,x+r*.35,y-r*.75); c.rotate(0); c.rect(x-r*.6,y,r*1.15,r*.35,stroke=1,fill=0)
    elif name == "orbit": c.ellipse(x-r*.85,y-r*.35,x+r*.85,y+r*.35,stroke=1,fill=0); c.circle(x,y,r*.18,stroke=1,fill=1); c.circle(x+r*.72,y,r*.08,stroke=1,fill=1)
    elif name == "constellation":
        pts=[(x-r*.65,y-r*.25),(x-r*.2,y+r*.55),(x+r*.25,y),(x+r*.7,y+r*.45)]
        for a,b in zip(pts,pts[1:]): c.line(*a,*b)
        for px,py in pts: c.circle(px,py,r*.08,stroke=1,fill=1)
    elif name in {"fish", "dolphin"}: c.ellipse(x-r*.6,y-r*.3,x+r*.4,y+r*.3,stroke=1,fill=0); _poly(c,[(x+r*.35,y),(x+r*.82,y+r*.42),(x+r*.82,y-r*.42)])
    elif name == "shell": [c.arc(x-r*.7+i*r*.18,y-r*.6,x+r*.7-i*r*.18,y+r*.65,0,180) for i in range(4)]
    elif name == "anchor": c.circle(x,y+r*.6,r*.18,stroke=1,fill=0); c.line(x,y+r*.42,x,y-r*.55); c.arc(x-r*.65,y-r*.65,x+r*.65,y+r*.15,180,180)
    elif name == "boat": _poly(c,[(x-r*.75,y-r*.2),(x+r*.75,y-r*.2),(x+r*.45,y-r*.6),(x-r*.45,y-r*.6)]); c.line(x,y-r*.2,x,y+r*.75); _poly(c,[(x,y+r*.65),(x,y),(x+r*.55,y)])
    elif name == "octopus": c.circle(x,y+r*.2,r*.48,stroke=1,fill=0); [c.line(x+d,y-r*.2,x+d*1.4,y-r*.75) for d in (-r*.42,-r*.14,r*.14,r*.42)]
    elif name == "lighthouse": _poly(c,[(x-r*.35,y-r*.7),(x-r*.22,y+r*.3),(x+r*.22,y+r*.3),(x+r*.35,y-r*.7)]); c.rect(x-r*.38,y+r*.3,r*.76,r*.25,stroke=1,fill=0); c.line(x-r*.75,y+r*.5,x-r*.4,y+r*.5); c.line(x+r*.4,y+r*.5,x+r*.75,y+r*.5)
    elif name == "paw": c.circle(x,y-r*.18,r*.38,stroke=1,fill=0); [c.circle(x+d,y+r*.48,r*.17,stroke=1,fill=0) for d in (-r*.5,-r*.17,r*.17,r*.5)]
    elif name == "bone": c.line(x-r*.55,y-r*.4,x+r*.55,y+r*.4); [c.circle(px,py,r*.2,stroke=1,fill=0) for px,py in ((x-r*.65,y-r*.5),(x-r*.45,y-r*.65),(x+r*.65,y+r*.5),(x+r*.45,y+r*.65))]
    elif name == "bird": c.arc(x-r*.7,y-r*.1,x,y+r*.55,0,180); c.arc(x,y-r*.1,x+r*.7,y+r*.55,0,180)
    elif name == "collar": c.arc(x-r*.7,y-r*.5,x+r*.7,y+r*.55,180,180); c.circle(x,y-r*.55,r*.18,stroke=1,fill=0)
    elif name == "heart":
        p=c.beginPath(); p.moveTo(x,y-r*.72); p.curveTo(x-r*.95,y-r*.05,x-r*.72,y+r*.72,x-r*.28,y+r*.65); p.curveTo(x,y+r*.65,x,y+r*.35,x,y+r*.28); p.curveTo(x,y+r*.35,x,y+r*.65,x+r*.28,y+r*.65); p.curveTo(x+r*.72,y+r*.72,x+r*.95,y-r*.05,x,y-r*.72); p.close(); c.drawPath(p,stroke=1,fill=0)
    elif name == "cupcake": c.rect(x-r*.5,y-r*.65,r,r*.65,stroke=1,fill=0); c.arc(x-r*.6,y-r*.05,x+r*.6,y+r*.7,0,180)
    elif name == "spoon": c.ellipse(x-r*.2,y+r*.1,x+r*.2,y+r*.75,stroke=1,fill=0); c.line(x,y+r*.1,x,y-r*.75)
    elif name == "pan": c.circle(x-r*.15,y,r*.52,stroke=1,fill=0); c.line(x+r*.35,y+r*.1,x+r*.85,y+r*.35)
    elif name == "rolling_pin": c.rect(x-r*.6,y-r*.22,r*1.2,r*.44,stroke=1,fill=0); c.line(x-r*.85,y,x-r*.6,y); c.line(x+r*.6,y,x+r*.85,y)
    elif name == "mug": c.rect(x-r*.55,y-r*.55,r*.85,r*1.05,stroke=1,fill=0); c.circle(x+r*.35,y,r*.35,stroke=1,fill=0)
    elif name == "bread": c.roundRect(x-r*.65,y-r*.55,r*1.3,r*1.05,r*.35,stroke=1,fill=0)
    elif name == "chef_hat": c.rect(x-r*.5,y-r*.6,r,r*.45,stroke=1,fill=0); [c.circle(x+d,y+r*.25,r*.35,stroke=1,fill=0) for d in (-r*.35,0,r*.35)]
    elif name == "car": c.rect(x-r*.65,y-r*.3,r*1.3,r*.55,stroke=1,fill=0); _poly(c,[(x-r*.4,y+r*.25),(x-r*.15,y+r*.65),(x+r*.35,y+r*.65),(x+r*.6,y+r*.25)]); c.circle(x-r*.4,y-r*.38,r*.17,stroke=1,fill=0); c.circle(x+r*.4,y-r*.38,r*.17,stroke=1,fill=0)
    elif name == "camper": c.roundRect(x-r*.75,y-r*.45,r*1.5,r*.95,r*.12,stroke=1,fill=0); c.rect(x-r*.5,y,r*.45,r*.25,stroke=1,fill=0); c.circle(x-r*.42,y-r*.5,r*.15,stroke=1,fill=0); c.circle(x+r*.42,y-r*.5,r*.15,stroke=1,fill=0)
    elif name == "compass": c.circle(x,y,r*.72,stroke=1,fill=0); _poly(c,[(x,y+r*.58),(x-r*.18,y),(x,y-r*.58),(x+r*.18,y)])
    elif name == "sign": c.rect(x-r*.65,y,r*1.3,r*.5,stroke=1,fill=0); c.line(x,y,x,y-r*.75)
    elif name == "suitcase": c.rect(x-r*.65,y-r*.5,r*1.3,r,stroke=1,fill=0); c.arc(x-r*.25,y+r*.35,x+r*.25,y+r*.8,0,180)
    elif name == "pin": c.circle(x,y+r*.25,r*.45,stroke=1,fill=0); _poly(c,[(x-r*.34,y),(x+r*.34,y),(x,y-r*.8)]); c.circle(x,y+r*.25,r*.12,stroke=1,fill=0)
    elif name == "tent": _poly(c,[(x,y+r*.75),(x-r*.8,y-r*.65),(x+r*.8,y-r*.65)]); c.line(x,y+r*.7,x,y-r*.65)
    elif name == "camera": c.rect(x-r*.7,y-r*.45,r*1.4,r*.9,stroke=1,fill=0); c.circle(x,y,r*.3,stroke=1,fill=0); c.rect(x-r*.4,y+r*.45,r*.45,r*.2,stroke=1,fill=0)


def draw_symbol(c, pack: str, value: int, cx: float, cy: float, size: float) -> None:
    names = PACKS.get(pack, PACKS["classic"])
    c.saveState(); c.setLineCap(1); c.setLineJoin(1); c.setLineWidth(max(1.1, size*.035)); c.setStrokeColorRGB(.05,.05,.05); c.setFillColorRGB(.05,.05,.05)
    _icon(c, names[(int(value)-1) % 9], cx, cy, size*.28)
    c.restoreState()
