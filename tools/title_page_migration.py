"""Validate the shared title-page system and safely migrate completed packages.

Only page one of an authoritative interior is replaced.  Every later page is
copied by pypdf without regeneration and verified with a content fingerprint.
Exact duplicate interior handoff files are updated too; covers and wraps are
never touched.
"""
from __future__ import annotations

import argparse, hashlib, io, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
OUT = ROOT / "out"
REPORTS = ROOT / "reports"
from publishing.title_pages import STYLE_LABELS, TitlePageSpec, render_title_page, spec_from_mapping


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()


def protected_fingerprint(reader: PdfReader) -> str:
    h=hashlib.sha256()
    for page in reader.pages[1:]:
        h.update(str(tuple(float(v) for v in page.mediabox)).encode())
        content=page.get_contents()
        h.update(content.get_data() if content else b"")
    return h.hexdigest()


def records():
    for package in sorted(p for p in OUT.iterdir() if p.is_dir() and not p.name.startswith(("_","."))):
        record=package/"04_REVIEW_AND_RECORDS"/"PACKAGE_SOURCE_RECORD.json"
        interior=package/"01_PRINT_UPLOADS"/"interior.pdf"
        if record.exists() and interior.exists():
            try: data=json.loads(record.read_text(encoding="utf-8"))
            except Exception: continue
            yield package,record,interior,data


def render_page(data: dict, size: tuple[float,float]) -> tuple[bytes,dict]:
    buf=io.BytesIO(); c=Canvas(buf,pagesize=size)
    result=render_title_page(c,spec_from_mapping(data),page_size=size)
    c.save(); return buf.getvalue(),result.to_dict()


def replace_title(source: Path, data: dict, destination: Path) -> dict:
    old=PdfReader(str(source)); old_count=len(old.pages)
    if old_count < 2: raise ValueError("interior has fewer than two pages")
    w=float(old.pages[0].mediabox.width); h=float(old.pages[0].mediabox.height)
    title_bytes,design=render_page(data,(w,h)); title=PdfReader(io.BytesIO(title_bytes))
    before=protected_fingerprint(old); writer=PdfWriter(); writer.add_page(title.pages[0])
    for page in old.pages[1:]: writer.add_page(page)
    if old.metadata: writer.add_metadata({str(k):str(v) for k,v in old.metadata.items() if v is not None})
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open("wb") as f: writer.write(f)
    new=PdfReader(str(destination)); after=protected_fingerprint(new)
    if len(new.pages)!=old_count or before!=after:
        destination.unlink(missing_ok=True); raise ValueError("protected pages changed")
    return {"pages":old_count,"protected_fingerprint_before":before,"protected_fingerprint_after":after,"design":design}


def inventory() -> list[dict]:
    rows=[]
    known={package.name:(package,record,interior,data) for package,record,interior,data in records()}
    for package in sorted(p for p in OUT.iterdir() if p.is_dir() and not p.name.startswith(("_","."))):
        if package.name not in known:
            interior=package/"01_PRINT_UPLOADS"/"interior.pdf"; record=package/"04_REVIEW_AND_RECORDS"/"PACKAGE_SOURCE_RECORD.json"
            reason="missing package source record" if interior.exists() else "not a completed standard package"
            rows.append({"package":package.name,"title":package.name,"type":"Unknown","pages":0,"eligible":False,"reason":reason})
            continue
        package,record,interior,data=known[package.name]
        reader=PdfReader(str(interior)); first=(reader.pages[0].extract_text() or "").casefold()
        title=str(data.get("title") or "").strip()
        eligible=bool(title and len(reader.pages)>1 and any(token in first for token in title.casefold().split()[:2]))
        rows.append({"package":package.name,"title":title,"type":data.get("puzzle_type","Unknown"),"pages":len(reader.pages),"eligible":eligible,"reason":"safe page-one replacement" if eligible else "title/page structure could not be confirmed"})
    REPORTS.mkdir(exist_ok=True)
    lines=["# Title Page Out-Folder Migration Inventory","",f"Generated: {datetime.now(timezone.utc).isoformat()}","", "| Package | Puzzle type | Pages | Decision | Reason |","|---|---:|---:|---|---|"]
    for r in rows: lines.append(f"| {r['package']} | {r['type']} | {r['pages']} | {'MIGRATE' if r['eligible'] else 'SKIP'} | {r['reason']} |")
    (REPORTS/"TITLE_PAGE_OUT_MIGRATION_INVENTORY.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return rows


def migrate_all(limit: int = 0, force: bool = False) -> list[dict]:
    inv={r["package"]:r for r in inventory()}; stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root=OUT/"_recovery_archive"/f"title_page_migration_{stamp}"; results=[{"package":r["package"],"status":"skipped","reason":r["reason"]} for r in inv.values() if not r["eligible"]]
    for package,record,interior,data in records():
        existing=package/"04_REVIEW_AND_RECORDS"/"TITLE_PAGE_MIGRATION_RECORD.json"
        if not force and existing.exists():
            try: results.append(json.loads(existing.read_text(encoding="utf-8")))
            except Exception: results.append({"package":package.name,"status":"failed","reason":"unreadable migration record"})
            continue
        if limit and sum(1 for r in results if r.get("status")=="migrated") >= limit:
            break
        if not inv[package.name]["eligible"]:
            results.append({"package":package.name,"status":"skipped","reason":inv[package.name]["reason"]}); continue
        old_hash=sha(interior); covers={str(p.relative_to(package)):sha(p) for p in package.rglob("*.pdf") if any(k in p.name.casefold() for k in ("cover","wrap"))}
        backup=backup_root/package.name/"interior_before.pdf"; backup.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(interior,backup)
        temp=interior.with_suffix(".title-page.tmp.pdf")
        try:
            check=replace_title(interior,data,temp); temp.replace(interior); new_hash=sha(interior)
            updated=[]
            for pdf in package.rglob("*.pdf"):
                if pdf==interior or any(k in pdf.name.casefold() for k in ("cover","wrap","preview")): continue
                if sha(pdf)==old_hash: shutil.copy2(interior,pdf); updated.append(str(pdf.relative_to(package)))
            cover_after={str(p.relative_to(package)):sha(p) for p in package.rglob("*.pdf") if any(k in p.name.casefold() for k in ("cover","wrap"))}
            if covers!=cover_after: raise ValueError("cover/wrap changed")
            result={"package":package.name,"title":data.get("title"),"type":data.get("puzzle_type"),"status":"migrated","old_sha256":old_hash,"new_sha256":new_hash,"backup":str(backup),"updated_exact_copies":updated,**check}
            (package/"04_REVIEW_AND_RECORDS"/"TITLE_PAGE_MIGRATION_RECORD.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            results.append(result)
        except Exception as exc:
            temp.unlink(missing_ok=True)
            if backup.exists(): shutil.copy2(backup,interior)
            results.append({"package":package.name,"status":"failed","reason":str(exc)})
    (REPORTS/"TITLE_PAGE_OUT_MIGRATION.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    lines=["# Title Page Out-Folder Migration","","Each migrated package records its exact recovery backup in `04_REVIEW_AND_RECORDS/TITLE_PAGE_MIGRATION_RECORD.json`.","", "| Package | Type | Status | Protected pages |","|---|---|---|---|"]
    for r in results: lines.append(f"| {r['package']} | {r.get('type','')} | {r['status'].upper()} | {'UNCHANGED' if r['status']=='migrated' and r['protected_fingerprint_before']==r['protected_fingerprint_after'] else r.get('reason','')} |")
    (REPORTS/"TITLE_PAGE_OUT_MIGRATION.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return results


CONCEPTS=[
 ("Word Search","Space & Astronomy","Journey Through the Solar System","48 Large-Print Cosmic Word Searches","8.5x11"),
 ("Word Search","Gardening and Homesteading","Garden, Homestead & Harvest","100 Nature-Inspired Signature Puzzles","8x10"),
 ("Word Search","Vocabulary Grade 5","Vocabulary Adventures: Grade 5","A confidence-building school word-search collection","6x9"),
 ("Sudoku","Nature","Forest Logic Sudoku","100 Calm Number and Nature Challenges","8.5x11"),
 ("Sudoku","Christmas","Holiday Symbols Sudoku","Festive logic games with themed symbols","8x10"),
 ("Cryptogram","American History","American Heritage Cipher Challenge","Decode remarkable moments from the American story","6x9"),
 ("Cryptogram","Bible and Faith","Faithful Words Cryptograms","Uplifting messages to decode and reflect upon","8.5x11"),
 ("Word Scramble + Trivia","Road Trips","Road Trip Scramble & Trivia","Games for highways, landmarks, and open-road fun","8x10"),
 ("Word Scramble + Trivia","Food and Cooking","Kitchen Table Challenge","Scrambles and trivia for food lovers","6x9"),
 ("Mixed Brain Games","Ocean Life","Under the Sea Brain Games","A varied puzzle voyage beneath the waves","8.5x11"),
 ("Mixed Brain Games","General Knowledge","The Complete Brain Games Signature Edition","100 varied challenges for curious minds","8x10"),
 ("Word Search","Birds","Backyard Birds Word Search","48 large-print puzzles for bird lovers","6x9"),
 ("Word Search","National Parks","America's National Parks Word Search","Trails, wildlife, and scenic wonders","8.5x11"),
 ("Sudoku","Sports","Game Day Sudoku","Number puzzles for sports fans","8x10"),
 ("Mixed Brain Games","Travel","Around the World Brain Games","A screen-free journey of varied challenges","6x9"),
]


def design_validation() -> dict:
    REPORTS.mkdir(exist_ok=True); review=REPORTS/"TITLE_PAGE_DESIGN_REVIEW.pdf"; c=Canvas(str(review),pagesize=letter)
    results=[]
    for i,(kind,topic,title,subtitle,trim) in enumerate(CONCEPTS):
        style=list(STYLE_LABELS)[i%len(STYLE_LABELS)] if i<6 else "Automatic"
        spec=TitlePageSpec(title,subtitle,"Jordan M. Slade","Slade Puzzles",kind,topic,"Signature Edition" if "Signature" in title else "Standard","Adults & Teens","",100 if "100" in subtitle else 48,"large-print" in subtitle.casefold(),style,trim)
        result=render_title_page(c,spec,page_size=letter); results.append(result.to_dict()|{"title":title,"topic":topic})
    c.save()
    stress=REPORTS/"TITLE_PAGE_STRESS_TEST.pdf"; c=Canvas(str(stress),pagesize=letter); failures=[]
    kinds=["Word Search","Sudoku","Cryptogram","Word Scramble + Trivia","Mixed Brain Games"]; topics=[x[1] for x in CONCEPTS]
    trims=["8.5x11","8x10","6x9"]
    for i in range(100):
        spec=TitlePageSpec(f"{topics[i%len(topics)]}: An Extraordinarily Engaging Puzzle Adventure Collection {i+1}","A carefully designed collection of satisfying, screen-free challenges with complete solutions", "Jordan M. Slade","Slade Puzzles",kinds[i%5],topics[i%len(topics)],"Signature Edition" if i%9==0 else "Standard","Adults & Teens",f"Series {i%7}",100 if i%9==0 else 48,i%4==0,list(STYLE_LABELS)[i%6] if i<30 else "Automatic",trims[i%3])
        result=render_title_page(c,spec,page_size=letter)
        if result.qa: failures.append({"case":i+1,"qa":result.qa})
    c.save()
    payload={"concept_count":len(results),"stress_count":100,"failures":failures,"styles":list(STYLE_LABELS.values()),"results":results}
    (REPORTS/"TITLE_PAGE_DESIGN_VALIDATION.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    (REPORTS/"TITLE_PAGE_DESIGN_SYSTEM.md").write_text("# Title Page Design System\n\nShared by Word Search, Sudoku, Cryptogram, Scramble + Trivia, and Mixed Brain Games. Automatic selection is deterministic; manual overrides accept the six named styles. Pages are vector-only, grayscale, safe-margin aware, and designed for low ink.\n",encoding="utf-8")
    return payload


def catalog_reviews() -> dict:
    """Create compact visual review PDFs from the migrated catalog."""
    catalog=REPORTS/"TITLE_PAGE_CATALOG_REVIEW.pdf"; writer=PdfWriter(); count=0
    for package,record,interior,data in records():
        reader=PdfReader(str(interior)); writer.add_page(reader.pages[0]); count+=1
    with catalog.open("wb") as f: writer.write(f)
    before_after=REPORTS/"TITLE_PAGE_BEFORE_AFTER_REVIEW.pdf"; writer=PdfWriter()
    backups=sorted((OUT/"_recovery_archive").glob("title_page_migration_*/*/interior_before.pdf"))
    if backups:
        before=backups[0]; package_name=before.parent.name
        current=OUT/package_name/"01_PRINT_UPLOADS"/"interior.pdf"
        writer.add_page(PdfReader(str(before)).pages[0]); writer.add_page(PdfReader(str(current)).pages[0])
    with before_after.open("wb") as f: writer.write(f)
    return {"catalog":str(catalog),"catalog_pages":count,"before_after":str(before_after)}


if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--inventory",action="store_true"); ap.add_argument("--validate",action="store_true"); ap.add_argument("--migrate",action="store_true"); ap.add_argument("--reviews",action="store_true"); ap.add_argument("--limit",type=int,default=0); ap.add_argument("--force",action="store_true"); args=ap.parse_args()
    result={}
    if args.inventory: result["inventory"]=inventory()
    if args.validate: result["validation"]=design_validation()
    if args.migrate: result["migration"]=migrate_all(args.limit,args.force)
    if args.reviews: result["reviews"]=catalog_reviews()
    print(json.dumps(result,indent=2,default=str))
