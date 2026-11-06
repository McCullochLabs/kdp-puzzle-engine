"""Explicit reuse of the existing fixed holiday recipe; never clone a product."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3


@dataclass(frozen=True)
class HolidayReusePlan:
    request: str
    book_id: str
    title: str
    pages: int
    snapshot_json: str
    selected_context_json: str


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _request(text):
    from .studio_chat_creation import _numeric_request
    from .studio_chat_families import _request_without_title
    import holiday_combo
    if not isinstance(text, str) or not 1 <= len(text) <= 1000:
        raise ValueError('Use one explicit holiday combination request.')
    clean, title = _request_without_title(text)
    if title and title != holiday_combo.TITLE:
        raise ValueError('The existing holiday recipe is Celebrate All Year. Renaming or customizing it needs a reviewed revision; it will not be silently changed.')
    counts, pages, seed = _numeric_request(clean)
    if (counts and set(counts) != {'200'}) or len(set(pages)) > 1 or seed is not None:
        raise ValueError('This route reuses the existing 200-puzzle holiday recipe. Different counts or seeds require a new reviewed recipe.')
    clean = re.sub(r'\b(?:with\s+)?\d+\s*(?:-\s*)?(?:puzzles?|pages?)\b', '', clean, flags=re.I)
    clean = ' '.join(clean.strip(' .!?').split())
    pattern = r'(?:create|make|build|use|reuse)(?: me)? (?:a |an |the )?(?:(?:existing|fixed) )?holiday word[ -]?search\s*(?:and|\+|&)\s*sudoku(?: puzzle)? book'
    if not re.fullmatch(pattern, clean, re.I):
        raise ValueError('Only the fixed holiday Word Search + Sudoku recipe is supported here. Reader, design, difficulty and other custom variants are not silently substituted.')
    return int(pages[0]) if pages else None


def _records(root):
    catalog=Path(root)/'data/books.db'
    if not catalog.is_file():raise ValueError('The saved book catalog is unavailable.')
    with closing(sqlite3.connect(catalog.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        return [dict(row) for row in db.execute('SELECT book_id,source_key,metadata_json,package_path FROM books')]


def _snapshot(root,row):
    import holiday_combo
    from .package_layout import package_file,release_contract
    from pypdf import PdfReader
    root=Path(root).resolve();folder=Path(str(row['package_path'] or '')).resolve()
    if not folder.is_dir() or not folder.is_relative_to(root/'out'):
        raise ValueError('The existing holiday package is missing or outside the local output library.')
    meta=json.loads(row['metadata_json'])
    manifest_path=package_file(folder,'PACKAGE_SOURCE_RECORD.json').resolve()
    if not manifest_path.is_relative_to(folder):raise ValueError('The holiday source record points outside its package.')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    facts={'title':holiday_combo.TITLE,'subtitle':holiday_combo.SUBTITLE,'author':holiday_combo.AUTHOR,
           'puzzle_type':holiday_combo.TYPE,'puzzle_count':200}
    if any(manifest.get(key)!=value for key,value in facts.items()):
        raise ValueError('The saved package is not the fixed 200-puzzle holiday recipe.')
    if not release_contract(folder)['ready']:
        raise ValueError('The existing holiday package or cover proof needs repair before reuse.')
    files={}
    for name in ('interior.pdf','kdp_full_wrap.pdf','front_cover.png','PACKAGE_SOURCE_RECORD.json'):
        path=package_file(folder,name).resolve()
        if not path.is_file() or not path.is_relative_to(folder):raise ValueError('A holiday artifact is missing or outside its package.')
        files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    interior=package_file(folder,'interior.pdf')
    puzzle_record=interior.with_suffix('.puzzles.json').resolve()
    if not puzzle_record.is_file() or not puzzle_record.is_relative_to(folder):
        raise ValueError('The holiday puzzle/answer records are missing.')
    files['puzzle_records']=hashlib.sha256(puzzle_record.read_bytes()).hexdigest()
    return {'book_id':row['book_id'],'source_key':row['source_key'],'metadata':meta,'folder':str(folder),
            'pages':len(PdfReader(interior).pages),'files':files}


def prepare_holiday_reuse(root,text,context=None):
    import holiday_combo
    requested_pages=_request(text)
    matches=[]
    for row in _records(root):
        meta=json.loads(row['metadata_json'])
        if meta.get('title')==holiday_combo.TITLE and meta.get('puzzle_type')==holiday_combo.TYPE:
            matches.append(row)
    selected=next((row for row in matches if row['book_id']==(context or {}).get('book_id')),None)
    if selected is None:
        if len(matches)!=1:
            raise ValueError('Choose the existing Celebrate All Year book in My books first. No duplicate product was generated.')
        selected=matches[0]
    snapshot=_snapshot(root,selected)
    if requested_pages is not None and requested_pages!=snapshot['pages']:
        raise ValueError(f"The saved fixed recipe has {snapshot['pages']} pages; the requested page target will not be silently ignored.")
    return HolidayReusePlan(text,selected['book_id'],holiday_combo.TITLE,snapshot['pages'],
                           _canonical(snapshot),_canonical(context or {}))


def holiday_reuse_text(plan):
    return (f'Use the existing {plan.title!r}: 200 Holiday Word Search + Sudoku puzzles, {plan.pages} pages. '
            'This reuses the saved fixed recipe and keeps its catalog identity; it does not generate a duplicate book or change its contents. '
            'Use existing holiday book runs actual local QA/preflight before selecting it. Owner and platform approvals remain separate.')


def confirm_holiday_reuse(root,plan,cancel=None):
    from .studio_book_checks import check_saved_book
    if cancel and cancel.is_set():raise ValueError('Holiday reuse cancelled before checking.')
    row=next((row for row in _records(root) if row['book_id']==plan.book_id),None)
    if row is None or _canonical(_snapshot(root,row))!=plan.snapshot_json:
        raise ValueError('The existing holiday book changed. Review a fresh reuse proposal.')
    evidence=check_saved_book(root,plan.book_id,cancel)
    if not evidence['preflight']['passed'] or evidence['qa']['summary']['blockers']:
        raise ValueError('The existing holiday book has local QA/preflight blockers; it was not selected.')
    row=next((row for row in _records(root) if row['book_id']==plan.book_id),None)
    if row is None or _canonical(_snapshot(root,row))!=plan.snapshot_json:
        raise ValueError('The holiday book changed during checking. Reopen the proposal.')
    if cancel and cancel.is_set():raise ValueError('Holiday reuse cancelled after checking.')
    return {'book_id':plan.book_id,'title':plan.title,'topic':'Holidays & Seasons','kind':'Word Search + Sudoku',
            'pages':plan.pages,'puzzles':200,'qa':evidence['qa'],'preflight':evidence['preflight'],
            'folder':json.loads(plan.snapshot_json)['folder'],'reused_existing':True}
