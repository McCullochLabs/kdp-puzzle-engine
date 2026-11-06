"""Bounded, read-only chat access to the selected canonical project."""
from contextlib import closing
import json
import hashlib
from pathlib import Path
import re
import sqlite3


def project_query(text):
    text=' '.join(str(text).strip().rstrip('.!?').casefold().split())
    patterns={
        'unfinished_drafts':r'(?:show|list)(?: me)? (?:my |the )?unfinished (?:drafts|work|projects)',
        'title_page_designs':r'(?:show|list)(?: me)? (?:the |available |supported )?title[ -]page (?:designs|styles|presets)',
        'themes':r'(?:show|list)(?: me)? (?:my |the )?saved themes',
        'duplicates':r'(?:find|show|identify)(?: me)? (?:the )?duplicate(?: saved)? themes',
        'files':r'(?:where (?:did you save|are)|locate|show)(?: me)? (?:the |my |this book.s )?(?:files|saved files|finished files|output files)',
        'select_project':r'select (?:project|book) [a-z0-9_-]{1,200}',
        'status':r'(?:show|report|what is)(?: me)? (?:the |my |current )?(?:project|book) status',
        'interior':r'(?:show|preview)(?: me)? (?:the |my |this book.s )?(?:interior|pages)',
        'solutions':r'(?:show|preview)(?: me)? (?:the |my |this book.s )?(?:solutions?|answers?|answer keys?)',
        'cover':r'(?:show|preview)(?: me)? (?:the |my |this book.s )?cover',
        'save_session':r'save(?: (?:my|the|this|current))? (?:project|book|conversation|progress)',
        'resume':r'(?:resume|recover|continue)(?: my| the)? (?:interrupted|unfinished|saved) (?:work|project|draft)',
    }
    return next((action for action,pattern in patterns.items() if re.fullmatch(pattern,text)),None)


def selected_project(root,context):
    """Resolve identity from SQLite, never a request/model supplied file path."""
    if not context or not context.get('book_id'):
        raise ValueError('Choose a saved book in My books first.')
    if context.get('pending_semantic_revision'):
        raise ValueError('A staged revision is pending. Accept or reject it before inspecting the active project.')
    root=Path(root).resolve();catalog=root/'data/books.db'
    if not catalog.is_file():raise ValueError('The saved project catalog is unavailable.')
    with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT book_id,metadata_json,package_path FROM books WHERE book_id=?',(context['book_id'],)).fetchone()
    if row is None:raise ValueError('The selected project is no longer in the catalog. Choose it again.')
    metadata=json.loads(row['metadata_json'])
    if not isinstance(metadata,dict):raise ValueError('The project metadata needs repair.')
    raw=str(row['package_path'] or '').strip()
    if not raw:raise ValueError('This project has no generated package yet.')
    folder=Path(raw).resolve()
    if not folder.is_dir() or not folder.is_relative_to(root/'out'):
        raise ValueError('The project package is missing or outside the local output library.')
    from .package_layout import package_file
    documents=[]
    for label,name in [('Interior','interior.pdf'),('Cover','kdp_full_wrap.pdf')]:
        path=package_file(folder,name).resolve()
        if path.is_file() and path.is_relative_to(folder):documents.append((label,path,0))
    return {'book_id':row['book_id'],'metadata':metadata,'folder':folder,'documents':documents}


def project_status_text(project):
    meta=project['metadata']
    return (f"Selected project: {meta.get('title') or 'Untitled book'}. "
            f"Family: {meta.get('puzzle_type') or 'Unspecified'}; puzzles: {meta.get('puzzle_count','unrecorded')}; "
            f"pages: {meta.get('page_count','unrecorded')}. Files: {project['folder']}. "
            'These are saved settings, not a fresh QA result. Ask Run QA or Run preflight for actual checks.')


def preview_project(root,context):
    """Preview the pending candidate explicitly; never fall back to its original."""
    pending=(context or {}).get('pending_semantic_revision')
    if not pending:return selected_project(root,context)
    root=Path(root).resolve();identity=pending.get('revision_id')
    if not isinstance(identity,str) or not re.fullmatch('[0-9a-f]{32}',identity):
        raise ValueError('The pending candidate identity is invalid; reopen its saved draft.')
    catalog=root/'data/books.db'
    if not catalog.is_file():raise ValueError('The saved project catalog is unavailable.')
    with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT v.payload FROM studio_drafts d JOIN studio_draft_versions v USING(draft_id,revision) WHERE d.draft_id=?',(identity,)).fetchone()
    if not row:raise ValueError('The pending candidate draft is missing; the original was not opened.')
    saved=json.loads(row[0]).get('chat_revision',{});plan=saved.get('plan',{});result=saved.get('result',{})
    digest=hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if (saved.get('status')!='complete' or plan.get('revision_id')!=identity or
            plan.get('source_book_id')!=context.get('book_id') or result.get('source_book_id')!=context.get('book_id') or
            saved.get('confirmation')!={'source':'studio_chat.revision_button','plan_sha256':digest}):
        raise ValueError('The candidate is no longer pending on this project; reopen its decision.')
    base=root/'data/studio_revision_candidates'/identity
    raw=Path(str(result.get('folder') or ''));folder=raw.resolve()
    if not raw.is_absolute() or not folder.is_relative_to(base) or folder==base:
        raise ValueError('The candidate is outside its saved staging location.')
    for parent in (root/'data',base.parent,base,raw):
        if parent.is_symlink() or parent.is_junction():raise ValueError('Linked candidate locations cannot be previewed.')
    from .studio_revision_adoption import _tree
    if not result.get('candidate_sha256') or _tree(folder)!=result['candidate_sha256']:
        raise ValueError('Candidate files changed after staging; the original was not opened.')
    from .package_layout import package_file
    documents=[]
    for label,name in [('Interior','interior.pdf'),('Cover','kdp_full_wrap.pdf')]:
        path=package_file(folder,name).resolve()
        if path.is_file() and path.is_relative_to(folder):documents.append((label,path,0))
    return {'book_id':context['book_id'],'metadata':{'title':'Staged candidate: '+str(plan.get('title') or 'Untitled')},
            'folder':folder,'documents':documents}


def solution_preview_project(root,context):
    """Navigate a bound answer-page index; never guess or open its original."""
    import io
    from pypdf import PdfReader
    project=preview_project(root,context)
    interiors=[row for row in project['documents'] if row[0]=='Interior']
    if len(interiors)!=1:raise ValueError('The selected project has no unique interior PDF.')
    pdf=Path(interiors[0][1]);index=pdf.with_suffix('.puzzles.json').resolve()
    if not index.is_relative_to(project['folder']) or not index.is_file():
        raise ValueError('No saved answer-page index is available. Open the interior directly to inspect it.')
    raw=index.read_bytes();data=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version']!=1:
        raise ValueError('The saved answer-page index has an unsupported schema.')
    contents=pdf.read_bytes();digest=hashlib.sha256(contents).hexdigest()
    if data.get('pdf_sha256')!=digest:
        raise ValueError('The saved answer-page index does not match this PDF. Open the interior directly to inspect it.')
    pages=len(PdfReader(io.BytesIO(contents)).pages);records=data.get('puzzles')
    if not isinstance(records,list) or not records or type(data.get('puzzle_count')) is not int or data['puzzle_count']!=len(records):
        raise ValueError('The saved answer-page index needs review.')
    solutions=[]
    for record in records:
        if not isinstance(record,dict):raise ValueError('The saved answer-page index needs review.')
        for field in ('puzzle_page','solution_page'):
            if type(record.get(field)) is not int or not 1<=record[field]<=pages:
                raise ValueError('The saved answer-page index contains an invalid PDF page.')
        solutions.append(record['solution_page'])
    if index.read_bytes()!=raw:raise ValueError('The answer-page index changed while reading it; retry the request.')
    first=min(solutions)
    return {**project,'solution_start_page':first,'documents':[
        (label,path,first-1,digest) if label=='Interior' else (label,path,page)
        for label,path,page in project['documents']]}


def title_page_designs_text():
    """Describe renderer presets without reading or changing a selected book."""
    from .title_pages import STYLE_LABELS
    labels = ('Automatic', *STYLE_LABELS.values())
    return ('Available title-page designs: ' + ', '.join(labels) + '. '
            'For a supported owned chat-created draft, ask: Change the title page design to "'
            + labels[1] + '". Review the staged candidate before accepting it. '
            'This changes the opening title page; general puzzle-font, layout and reader-profile edits '
            'are not provided by this command. Existing ownership, artwork and approval checks still apply.')


def select_catalog_project(root, request):
    """Resolve an explicit ID read-only; titles and file paths are not identities."""
    match=re.fullmatch(r'\s*select\s+(?:project|book)\s+([a-z0-9_-]{1,200})[.!?]?\s*',str(request),re.I)
    if not match:raise ValueError('Use Select project followed by its exact catalog book ID.')
    catalog=Path(root).resolve()/'data/books.db'
    if not catalog.is_file():raise ValueError('The saved project catalog is unavailable.')
    with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT book_id,metadata_json FROM books WHERE book_id=?',(match.group(1),)).fetchone()
    if row is None:raise ValueError('No saved project has that exact book ID. Find it in My books.')
    metadata=json.loads(row['metadata_json'])
    if not isinstance(metadata,dict):raise ValueError('The project metadata needs repair.')
    return {'book_id':row['book_id'],'metadata':metadata}
