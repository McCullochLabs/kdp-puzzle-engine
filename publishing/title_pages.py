"""Shared, low-ink, theme-aware interior title pages.

The renderer uses only ReportLab vector primitives and caller-supplied embedded
font aliases.  It is offline, deterministic, trim-responsive, and deliberately
keeps the page mostly white for economical black-and-white printing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re


STYLE_LABELS = {
    "classic_frame": "Classic Frame",
    "modern_minimal": "Modern Minimal",
    "puzzle_motif": "Puzzle Motif",
    "themed_emblem": "Themed Emblem",
    "corner_art": "Corner Art",
    "signature": "Signature",
}


@dataclass(frozen=True)
class TitlePageSpec:
    title: str
    subtitle: str = ""
    author: str = ""
    publisher: str = "Slade Puzzles"
    puzzle_type: str = "Word Search"
    topic: str = "General"
    edition: str = "Standard"
    audience: str = ""
    series: str = ""
    puzzle_count: int = 0
    large_print: bool = False
    style: str = "Automatic"
    trim_size: str = "8.5x11"


@dataclass(frozen=True)
class TitlePageResult:
    style: str
    style_label: str
    puzzle_motif: str
    theme_motif: str
    trim_size: str
    ink_score: float
    qa: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def theme_motif(topic: str) -> str:
    text = _norm(topic)
    rules = (
        (("space", "astronomy", "planet", "cosmic"), "space"),
        (("garden", "homestead", "flower", "herb", "growing"), "garden"),
        (("travel", "road trip", "adventure", "camping"), "travel"),
        (("american history", "history", "patriot"), "americana"),
        (("bird",), "bird"),
        (("ocean", "marine", "sea", "beach"), "ocean"),
        (("christmas", "winter", "holiday"), "winter"),
        (("halloween", "spooky"), "halloween"),
        (("cat", "dog", "pet"), "pets"),
        (("food", "baking", "kitchen", "cooking"), "kitchen"),
        (("1950", "1960", "1970", "1980", "1990", "nostalgia", "decade"), "retro"),
        (("bible", "faith", "christian"), "faith"),
        (("school", "vocabulary", "grade"), "learning"),
        (("nature", "forest", "park", "wildlife", "outdoor"), "nature"),
        (("sport", "football", "baseball", "basketball", "soccer"), "sports"),
    )
    for needles, motif in rules:
        if any(value in text for value in needles):
            return motif
    return "geometric"


def puzzle_motif(kind: str) -> str:
    text = _norm(kind)
    if "word search" in text and "sudoku" in text: return "dual_grid"
    if "word search" in text: return "word_grid"
    if "sudoku" in text: return "number_grid"
    if "cryptogram" in text: return "cipher"
    if "scramble" in text or "trivia" in text: return "word_tiles"
    if "mixed" in text or "brain" in text: return "mixed"
    return "geometric"


def select_style(spec: TitlePageSpec) -> str:
    requested = _norm(spec.style).replace(" ", "_")
    if requested in STYLE_LABELS:
        return requested
    if "signature" in _norm(spec.edition) or "signature" in _norm(spec.title):
        return "signature"
    if spec.series:
        # Stable across a series; a different topic changes only the emblem.
        value = int(hashlib.sha256(_norm(spec.series).encode()).hexdigest()[:8], 16)
        return ("classic_frame", "corner_art", "themed_emblem")[value % 3]
    if spec.large_print:
        # Large print changes typography, not every book into the same design.
        value = int(hashlib.sha256(_norm(spec.topic).encode()).hexdigest()[:8], 16)
        return ("modern_minimal", "classic_frame", "corner_art")[value % 3]
    motif = theme_motif(spec.topic)
    if motif != "geometric":
        return "themed_emblem"
    return "puzzle_motif" if puzzle_motif(spec.puzzle_type) != "geometric" else "modern_minimal"


def _line(c, x1, y1, x2, y2, width=.7, gray=.35):
    c.setStrokeGray(gray); c.setLineWidth(max(.75, width)); c.line(x1, y1, x2, y2)


def _poly(c, points, fill=0, gray=.25):
    c.setStrokeGray(gray); c.setFillGray(gray)
    p=c.beginPath(); p.moveTo(*points[0])
    for point in points[1:]: p.lineTo(*point)
    p.close(); c.drawPath(p,stroke=1,fill=fill)


def _star(c,x,y,r,gray=.28):
    points=[]
    for i in range(10):
        angle=-math.pi/2+i*math.pi/5; radius=r if i%2==0 else r*.42
        points.append((x+math.cos(angle)*radius,y+math.sin(angle)*radius))
    _poly(c,points,0,gray)


def _divider(c, x, y, width, motif="diamond"):
    _line(c,x-width/2,y,x-12,y,.6,.55); _line(c,x+12,y,x+width/2,y,.6,.55)
    if motif == "star": _star(c,x,y,5,.4)
    elif motif == "dots":
        for dx in (-8,0,8): c.setFillGray(.45); c.circle(x+dx,y,1.7,stroke=0,fill=1)
    else: _poly(c,[(x,y+5),(x-5,y),(x,y-5),(x+5,y)],0,.4)


def _puzzle_icon(c, kind, x, y, size, bold_font="Helvetica-Bold"):
    motif=puzzle_motif(kind); c.setStrokeGray(.22); c.setFillGray(.22); c.setLineWidth(max(.75,size*.012))
    if motif == "word_grid":
        cells=4; cell=size/cells
        for i in range(cells+1): c.line(x-size/2+i*cell,y-size/2,x-size/2+i*cell,y+size/2); c.line(x-size/2,y-size/2+i*cell,x+size/2,y-size/2+i*cell)
        c.circle(x+cell*.5,y+cell*.5,cell*.42,stroke=1,fill=0); c.line(x+cell*.8,y+cell*.18,x+size*.68,y-size*.66)
    elif motif == "number_grid":
        for i in range(4): c.line(x-size/2+i*size/3,y-size/2,x-size/2+i*size/3,y+size/2); c.line(x-size/2,y-size/2+i*size/3,x+size/2,y-size/2+i*size/3)
        c.setFont(bold_font,max(7,size*.16))
        for row in range(3):
            for col in range(3): c.drawCentredString(x+(col-1)*size/3,y+(1-row)*size/3-size*.055,str(row*3+col+1))
    elif motif == "cipher":
        c.roundRect(x-size*.48,y-size*.28,size*.96,size*.56,size*.08,stroke=1,fill=0); c.setFont(bold_font,max(8,size*.18)); c.drawCentredString(x,y-size*.06,"A = ?")
        c.circle(x,y+size*.44,size*.14,stroke=1,fill=0); c.line(x-size*.14,y+size*.44,x+size*.14,y+size*.44)
    elif motif == "word_tiles":
        letters="WORD"; tile=size*.22; start=x-tile*2
        for i,ch in enumerate(letters):
            c.roundRect(start+i*tile,y-size*.12,tile*.85,tile*.85,tile*.1,stroke=1,fill=0)
            c.setFont(bold_font,max(7,size*.13))
            c.drawCentredString(start+i*tile+tile*.425,y-size*.12+tile*.85*.32,ch)
        c.setFont(bold_font,max(7,size*.32)); c.drawCentredString(x,y+size*.34,"?")
    elif motif == "mixed":
        _puzzle_icon(c,"Word Search",x-size*.24,y,size*.35,bold_font=bold_font); _puzzle_icon(c,"Sudoku",x+size*.24,y,size*.35,bold_font=bold_font); c.setFont(bold_font,max(7,size*.24)); c.drawCentredString(x,y+size*.36,"?")
    elif motif == "dual_grid":
        _puzzle_icon(c,"Word Search",x-size*.26,y,size*.46,bold_font=bold_font)
        _puzzle_icon(c,"Sudoku",x+size*.26,y,size*.46,bold_font=bold_font)
    else:
        c.circle(x,y,size*.35,stroke=1,fill=0); _poly(c,[(x,y+size*.45),(x-size*.4,y-size*.3),(x+size*.4,y-size*.3)],0,.3)


def _theme_icon(c, motif, x, y, size, bold_font="Helvetica-Bold"):
    r=size*.35; c.setStrokeGray(.3); c.setFillGray(.3); c.setLineWidth(max(.75,size*.012))
    if motif=="garden":
        # Flower, leaves, and planter: unmistakably garden-related at a glance.
        c.rect(x-r*.65,y-r*1.05,r*1.3,r*.45,stroke=1,fill=0); c.line(x,y-r*.6,x,y+r*.25)
        for angle in (0,math.pi/2,math.pi,3*math.pi/2):
            c.circle(x+math.cos(angle)*r*.48,y+r*.55+math.sin(angle)*r*.48,r*.24,stroke=1,fill=0)
        c.circle(x,y+r*.55,r*.18,stroke=1,fill=0)
        c.ellipse(x-r*.72,y-r*.32,x-r*.05,y+r*.05,stroke=1,fill=0); c.ellipse(x+r*.05,y-r*.10,x+r*.72,y+r*.28,stroke=1,fill=0)
    elif motif=="nature":
        # A small mountain-and-pine landscape replaces the former abstract leaf.
        _poly(c,[(x-r*1.25,y-r*.35),(x-r*.35,y+r*.72),(x+r*.15,y+r*.05),(x+r*.55,y+r*.55),(x+r*1.25,y-r*.35)],0,.3)
        for dx,scale in ((-r*.7,.72),(r*.72,.9)):
            c.line(x+dx,y-r*.95,x+dx,y-r*.1)
            for level in (0,.28,.55):
                yy=y-r*.15-level*r; span=r*(.42-level*.20)*scale
                _poly(c,[(x+dx,yy+r*.42*scale),(x+dx-span,yy),(x+dx+span,yy)],0,.3)
    elif motif=="space": c.circle(x,y,r*.55,stroke=1,fill=0); c.ellipse(x-r*1.45,y-r*.35,x+r*1.45,y+r*.35,stroke=1,fill=0); _star(c,x+r*1.5,y+r*.9,r*.25,.35)
    elif motif=="travel":
        c.circle(x,y,r,stroke=1,fill=0); _poly(c,[(x,y+r*.82),(x-r*.22,y),(x,y-r*.82),(x+r*.22,y)],0,.3)
        c.setFont(bold_font,max(7,r*.25)); c.drawCentredString(x,y+r*1.18,"N")
    elif motif=="americana":
        c.rect(x-r*1.1,y-r*.72,r*2.2,r*1.44,stroke=1,fill=0)
        c.rect(x-r*1.1,y+r*.05,r*.85,r*.67,stroke=1,fill=0)
        for row in (-.45,-.05,.35): c.line(x-r*.25,y+row*r,x+r*1.1,y+row*r)
        for dx in (-r*.88,-r*.66,-r*.44): _star(c,x+dx,y+r*.38,r*.09,.3)
    elif motif=="bird":
        c.arc(x-r*1.35,y-r*.2,x,y+r*.75,0,170); c.arc(x,y-r*.2,x+r*1.35,y+r*.75,10,170)
        c.circle(x+r*.72,y-r*.12,r*.28,stroke=1,fill=0); _poly(c,[(x+r,y-r*.05),(x+r*1.35,y-r*.16),(x+r,y-r*.25)],0,.3)
    elif motif=="ocean":
        for dy in (-r*.55,-r*.15,r*.25): c.bezier(x-r*1.35,y+dy,x-r*.7,y+dy+r*.45,x,y+dy-r*.45,x+r*1.35,y+dy)
        c.ellipse(x-r*.35,y+r*.48,x+r*.45,y+r*.95,stroke=1,fill=0); _poly(c,[(x+r*.45,y+r*.72),(x+r*.9,y+r*.98),(x+r*.9,y+r*.46)],0,.3)
    elif motif=="winter":
        for a in (0,math.pi/3,2*math.pi/3): c.line(x-math.cos(a)*r,y-math.sin(a)*r,x+math.cos(a)*r,y+math.sin(a)*r)
    elif motif=="halloween":
        c.circle(x,y,r,stroke=1,fill=0); c.line(x,y+r,x+r*.15,y+r*1.35)
        _poly(c,[(x-r*.55,y+r*.18),(x-r*.2,y+r*.08),(x-r*.38,y-r*.18)],0,.3); _poly(c,[(x+r*.55,y+r*.18),(x+r*.2,y+r*.08),(x+r*.38,y-r*.18)],0,.3)
        c.arc(x-r*.48,y-r*.58,x+r*.48,y+r*.05,190,160)
    elif motif=="pets":
        c.circle(x,y-r*.2,r*.55,stroke=1,fill=0)
        for dx in (-r*.75,-r*.25,r*.25,r*.75): c.circle(x+dx,y+r*.75,r*.22,stroke=1,fill=0)
    elif motif=="kitchen":
        c.ellipse(x-r*.72,y-r*.55,x+r*.72,y+r*.2,stroke=1,fill=0); c.line(x+r*.7,y-r*.15,x+r*1.3,y+r*.22)
        c.ellipse(x-r*.18,y+r*.08,x+r*.18,y+r*.92,stroke=1,fill=0); c.line(x,y+r*.08,x,y-r*.95)
    elif motif=="retro":
        c.circle(x,y,r,stroke=1,fill=0); c.circle(x,y,r*.16,stroke=1,fill=0); c.line(x+r*.55,y+r*.72,x+r*1.2,y+r*1.05); c.line(x+r*1.2,y+r*1.05,x+r*.55,y-r*.2)
    elif motif=="faith": c.line(x,y-r*1.2,x,y+r*1.2); c.line(x-r*.7,y+r*.35,x+r*.7,y+r*.35)
    elif motif=="learning": c.rect(x-r*1.15,y-r*.75,r*1.05,r*1.45,stroke=1,fill=0); c.rect(x+r*.1,y-r*.75,r*1.05,r*1.45,stroke=1,fill=0); c.line(x,y-r*.8,x,y+r*.72)
    elif motif=="sports":
        c.circle(x,y,r,stroke=1,fill=0); c.arc(x-r,y-r*.45,x+r,y+r*.45,0,180); c.arc(x-r,y-r*.45,x+r,y+r*.45,180,180); c.line(x,y-r,x,y+r)
    else: _poly(c,[(x,y+r),(x-r,y),(x,y-r),(x+r,y)],0,.35)


def _wrapped(c,text,font,size,max_width,max_lines=3):
    words=str(text or "").split(); lines=[]; line=""
    for word in words:
        trial=(line+" "+word).strip()
        if not line or c.stringWidth(trial,font,size)<=max_width: line=trial
        else: lines.append(line); line=word
    if line: lines.append(line)
    return lines[:max_lines]


def _fit_title(c,title,font,max_width,max_lines,preferred,min_size):
    for size in range(preferred,min_size-1,-1):
        lines=_wrapped(c,title.upper(),font,size,max_width,max_lines)
        if len(lines)<=max_lines and all(c.stringWidth(line,font,size)<=max_width for line in lines): return size,lines
    return min_size,_wrapped(c,title.upper(),font,min_size,max_width,max_lines)


def render_title_page(c, spec: TitlePageSpec, *, page_size=None, margin=None,
                      regular_font="Helvetica", bold_font="Helvetica-Bold") -> TitlePageResult:
    width,height=page_size or c._pagesize
    safe=float(margin or max(42,min(width,height)*.09)); style=select_style(spec)
    p_motif=puzzle_motif(spec.puzzle_type); t_motif=theme_motif(spec.topic)
    scale=min(width/612.0,height/792.0); large=bool(spec.large_print)
    c.saveState(); c.setFillGray(1); c.rect(0,0,width,height,stroke=0,fill=1)

    # Six intentionally different structures; all stay inside the safe area.
    if style in {"classic_frame","signature"}:
        inset=safe*(.72 if style=="signature" else .9); c.setStrokeGray(.35); c.setLineWidth(1.2 if style=="signature" else .75); c.rect(inset,inset,width-2*inset,height-2*inset,stroke=1,fill=0)
        if style=="signature": c.setLineWidth(0.75); c.rect(inset+8,inset+8,width-2*(inset+8),height-2*(inset+8),stroke=1,fill=0)
        for x,y in ((inset,inset),(width-inset,inset),(inset,height-inset),(width-inset,height-inset)): c.circle(x,y,3.2,stroke=1,fill=0)
    elif style=="corner_art":
        _theme_icon(c,t_motif,safe+24,height-safe-24,42*scale,bold_font=bold_font); _theme_icon(c,t_motif,width-safe-24,safe+24,42*scale,bold_font=bold_font)
        _line(c,safe,height-safe,width*.35,height-safe,.6,.6); _line(c,width*.65,safe,width-safe,safe,.6,.6)
    elif style=="modern_minimal":
        c.setFillGray(.16); c.rect(safe,height-safe-7,width*.18,7,stroke=0,fill=1); _line(c,safe,safe,width-safe,safe,.6,.65)
    elif style=="puzzle_motif":
        # Keep the lower count label clear; the central puzzle icon already
        # supplies the themed motif, so these are restrained side accents.
        _line(c,safe,height*.20,width*.27,height*.20,.5,.82)
        _line(c,width*.73,height*.20,width-safe,height*.20,.5,.82)
    elif style=="themed_emblem":
        c.setStrokeGray(.6); c.circle(width/2,height*.39,58*scale,stroke=1,fill=0); c.circle(width/2,height*.39,64*scale,stroke=1,fill=0)

    label=("Word Scrambles + Fact Clues" if spec.puzzle_type == "Word Scramble + Trivia" else str(spec.puzzle_type or "Puzzle Book")).upper()
    if spec.large_print: label += "  |  LARGE PRINT"
    c.setFont(bold_font,max(8,10*scale)); c.setFillGray(.35); c.drawCentredString(width/2,height*.84,label)
    preferred=(31 if large else 34)*scale; max_width=width-2*safe-24
    title_size,title_lines=_fit_title(c,spec.title,bold_font,max_width,3,int(preferred),max(15,int(17*scale)))
    title_top=height*.76; title_step=title_size*1.18
    c.setFillGray(.08)
    for i,line in enumerate(title_lines): c.setFont(bold_font,title_size); c.drawCentredString(width/2,title_top-i*title_step,line)
    title_bottom=title_top-(len(title_lines)-1)*title_step
    divider_y=title_bottom-title_size*.75; _divider(c,width/2,divider_y,min(180*scale,max_width*.45),"star" if style=="signature" else "diamond")
    sub_size=max(10,(14 if large else 12)*scale); subtitle_lines=_wrapped(c,spec.subtitle,regular_font,sub_size,max_width,4)
    c.setFillGray(.28); sub_top=divider_y-28*scale
    for i,line in enumerate(subtitle_lines): c.setFont(regular_font,sub_size); c.drawCentredString(width/2,sub_top-i*sub_size*1.45,line)

    visual_y=height*.39; visual_size=(82 if style in {"puzzle_motif","modern_minimal"} else 76)*scale
    if t_motif != "geometric": _theme_icon(c,t_motif,width/2,visual_y,visual_size,bold_font=bold_font)
    else: _puzzle_icon(c,spec.puzzle_type,width/2,visual_y,visual_size,bold_font=bold_font)
    # A plain-language caption makes the illustration meaningful, even when a
    # topic is broad or the icon is viewed at a small print-preview scale.
    topic_caption=" ".join(str(spec.topic or "").split()).upper()
    if topic_caption and _norm(topic_caption) not in {"general","general starter"}:
        if len(topic_caption)>42: topic_caption=topic_caption[:39].rstrip()+"..."
        caption_offset=78 if style=="themed_emblem" else 54
        c.setFont(bold_font,max(7,8.5*scale)); c.setFillGray(.42); c.drawCentredString(width/2,visual_y-caption_offset*scale,topic_caption)

    details=[]
    if spec.puzzle_count: details.append(f"{spec.puzzle_count} PUZZLES")
    if spec.edition and _norm(spec.edition)!="standard": details.append(str(spec.edition).upper())
    if details:
        c.setFont(bold_font,max(8,10*scale)); c.setFillGray(.3); c.drawCentredString(width/2,height*.20,"  |  ".join(details))
    if spec.author:
        c.setFont(regular_font,max(9,12*scale)); c.setFillGray(.18); c.drawCentredString(width/2,safe+36*scale,spec.author)
    if spec.publisher and _norm(spec.publisher)!=_norm(spec.author):
        c.setFont(bold_font,max(7,8*scale)); c.setFillGray(.48); c.drawCentredString(width/2,safe+20*scale,spec.publisher.upper())
    c.restoreState(); c.showPage()

    qa=[]
    if not str(spec.title).strip(): qa.append("missing_title")
    if any(c.stringWidth(line,bold_font,title_size)>max_width+.1 for line in title_lines): qa.append("title_overflow")
    if len(subtitle_lines)>4: qa.append("subtitle_overflow")
    # Conservative geometric estimate; renderer contains no raster or large dark fill.
    ink={"modern_minimal":.025,"puzzle_motif":.035,"themed_emblem":.04,"corner_art":.03,"classic_frame":.045,"signature":.055}[style]
    if ink>.10: qa.append("excessive_ink")
    return TitlePageResult(style,STYLE_LABELS[style],p_motif,t_motif,spec.trim_size,ink,tuple(qa))


def spec_from_mapping(data: dict, *, puzzle_type: str | None = None, style: str | None = None) -> TitlePageSpec:
    count=int(data.get("puzzle_count") or len(data.get("puzzles") or []) or 0)
    explicit_signature = bool(data.get("signature_edition")) or "signature" in _norm(str(data.get("edition") or "")) or "signature" in _norm(str(data.get("title") or ""))
    edition=str(data.get("edition") or ("Signature Edition" if explicit_signature else "Standard"))
    large=bool(data.get("large_print")) or "large print" in _norm(str(data.get("title") or "")+" "+str(data.get("subtitle") or ""))
    return TitlePageSpec(
        title=str(data.get("title") or "Puzzle Book"), subtitle=str(data.get("subtitle") or ""),
        author=str(data.get("author") or ""), publisher=str(data.get("brand") or data.get("publisher") or "Slade Puzzles"),
        puzzle_type=str(puzzle_type or data.get("puzzle_type") or "Word Search"),
        topic=str(data.get("detected_topic") or data.get("cover_visual_topic") or data.get("theme") or data.get("topic") or "General"),
        edition=edition, audience=str(data.get("audience") or ""), series=str(data.get("series") or ""),
        puzzle_count=count, large_print=large, style=str(style or data.get("title_page_style") or "Automatic"),
        trim_size=str(data.get("trim_size") or "8.5x11"))
