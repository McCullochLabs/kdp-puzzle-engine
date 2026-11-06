"""Explicit same-product print revision adoption; never grants publication approval."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from pypdf import PdfReader
from .package_layout import package_file,release_contract


def fingerprint(folder):
    files=[package_file(folder,name) for name in ('interior.pdf','kdp_full_wrap.pdf','front_cover.png','PACKAGE_SOURCE_RECORD.json')]
    files.append(package_file(folder,'interior.pdf').with_suffix('.puzzles.json'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def compare_revision(old,new):
    old,new=Path(old),Path(new)
    sources=[json.loads(package_file(p,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig')) for p in (old,new)]
    for field in ('title','subtitle','author','puzzle_type','seed','trim_size','puzzle_count','theme','difficulty','cover_style'):
        if sources[0].get(field)!=sources[1].get(field):raise ValueError('Print-only revision changed '+field+'.')
    puzzles=[json.loads(package_file(p,'interior.pdf').with_suffix('.puzzles.json').read_text(encoding='utf-8-sig')) for p in (old,new)]
    if not puzzles[0].get('puzzles') or puzzles[0]['puzzles']!=puzzles[1].get('puzzles'):
        raise ValueError('Print-only revisions must preserve every puzzle and answer record.')
    for folder,manifest in zip((old,new),puzzles):
        if hashlib.sha256(package_file(folder,'interior.pdf').read_bytes()).hexdigest()!=manifest.get('pdf_sha256'):
            raise ValueError('Puzzle records do not match the actual PDF.')
    proofs=[json.loads(package_file(folder,'front_cover.png').with_suffix('.approval.json').read_text(encoding='utf-8-sig')) for folder in (old,new)]
    for field in ('asset_id','asset_sha256'):
        if not proofs[0].get(field) or proofs[0][field]!=proofs[1].get(field):
            raise ValueError('A print-only revision must retain its approved artwork.')
    from PIL import Image
    pixels=[]
    for folder in (old,new):
        with Image.open(package_file(folder,'front_cover.png')) as image:
            rgb=image.convert('RGBA')
            pixels.append((rgb.size,hashlib.sha256(rgb.tobytes()).hexdigest()))
    if pixels[0]!=pixels[1]:raise ValueError('Print-only revision changed the approved front-cover pixels.')
    geometry=[]
    for folder in (old,new):
        reader=PdfReader(package_file(folder,'interior.pdf'))
        geometry.append([(tuple(page.mediabox),tuple(page.cropbox),page.rotation) for page in reader.pages])
    if geometry[0]!=geometry[1]:raise ValueError('Print-only revisions must preserve every page dimension and rotation.')
    return sources[1]


def validate_revision(service,book,target):
    old=Path(book['package_path']).resolve()
    if not release_contract(target)['ready']:raise ValueError('The revision package is incomplete.')
    source=compare_revision(old,target)
    for field in ('title','author'):
        if str(book['metadata'].get(field) or '').strip()!=str(source.get(field) or '').strip():
            raise ValueError('Saved '+field+' differs from the revision; review the product identity first.')
    from .product_qa import inspect_product
    from preflight import preflight
    metadata={**source,**book['metadata'],'require_puzzle_manifest':True}
    qa=inspect_product(service.project,target,metadata)
    if qa.blockers:raise ValueError('Revision QA failed: '+'; '.join(row.message for row in qa.blockers[:5]))
    ok,notes=preflight(target)
    if not ok:raise ValueError('Revision preflight failed: '+'; '.join(notes))
    return {'file_sha256':fingerprint(target),'previous_file_sha256':fingerprint(old),'qa_status':qa.status,'qa_blockers':0,'preflight_passed':True,
            'puzzles_preserved':True,'page_geometry_preserved':True,'approval':'No human or marketplace approval granted'}


def adopt_print_revision(service,book_id,package):
    book=service.db.get_book(book_id)
    if not book:raise ValueError('Choose an existing catalog book.')
    target=Path(package).resolve();old=Path(str(book.get('package_path') or '')).resolve()
    if not target.is_relative_to(service.output.resolve()) or '_recovery_archive' in {p.casefold() for p in target.parts}:
        raise ValueError('Choose a complete local output revision outside recovery archives.')
    if not target.is_dir() or not old.is_dir():raise ValueError('Both existing and revision packages must be available.')
    if target==old:raise ValueError('This package is already selected; no adoption is needed.')
    if any(other['book_id']!=book_id and other.get('package_path') and Path(other['package_path']).resolve()==target for other in service.db.list_books()):
        raise ValueError('The revision is already assigned to another catalog book; resolve its identity first.')
    evidence=validate_revision(service,book,target)
    if evidence.get('qa_blockers')!=0 or evidence.get('preflight_passed') is not True:
        raise ValueError('Passing revision validation is required.')
    # Recheck artifacts after potentially expensive validation, before commit.
    if fingerprint(target)!=evidence['file_sha256'] or fingerprint(old)!=evidence['previous_file_sha256']:raise ValueError('Revision files changed during validation; run the check again.')
    files=dict(book['metadata'].get('files') or {})
    files.update({k:v for k,v in service._package_files(target).items() if k!='printable_pdf'})
    return service.db._commit_print_revision(book_id,book['package_path'],book['metadata'],str(target),files,evidence,book['source_key'],book['metadata_locked'])
