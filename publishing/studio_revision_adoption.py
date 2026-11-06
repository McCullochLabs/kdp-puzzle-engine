"""Explicit semantic adoption of owned staged chat revisions.

Original/staged packages are immutable; catalog and versioned recovery draft
advance together in one SQLite transaction. Print-only adoption is independent.
"""
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from .studio_chat_creation import _BUILD_LOCK
from .studio_chat_revisions import ChatRevisionPlan, load_revision_plan, verify_revision_typography, _hash, _source_snapshot
from .studio_recovery import StudioDraftStore


def _tree(folder):
    if not folder.is_dir():raise ValueError('Revision package is missing.')
    files={}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or path.is_junction():raise ValueError('Revision packages cannot contain links or junctions.')
        if path.is_file():files[str(path.relative_to(folder))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _load(root, revision_id):
    import re
    if not isinstance(revision_id,str) or not re.fullmatch('[0-9a-f]{32}',revision_id):raise ValueError('Invalid revision identity.')
    store=StudioDraftStore(Path(root)/'data/books.db');draft=store.load(revision_id)
    if not draft or 'chat_revision' not in draft['payload']:raise ValueError('No saved staged revision was found.')
    return store,draft,draft['payload']['chat_revision']


def _context(plan, context):
    clean=dict(context or {});pending=clean.pop('pending_semantic_revision',None)
    if clean!=plan.selected_context or not pending or pending.get('revision_id')!=plan.revision_id:
        raise ValueError('Choose this exact staged revision on its original project before deciding.')


def confirm_adoption(root, revision_id, context):
    store,draft,saved=_load(root,revision_id);plan=load_revision_plan(saved['plan']);_context(plan,context)
    if saved.get('status')!='complete':raise ValueError('Only a completed, pending candidate can be accepted.')
    if not saved.get('result',{}).get('candidate_sha256'):raise ValueError('This older candidate has no frozen fingerprint; stage a new candidate.')
    saved['adoption_confirmation']={'source':'studio_chat.accept_revision_button','plan_sha256':_hash(plan),
        'candidate_sha256':saved['result']['candidate_sha256']}
    store.save(revision_id,'book_plan',draft['payload'])


def _save_version(db,draft,payload,completed=False):
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False)
    if len(raw.encode())>256000:raise ValueError('Revision evidence exceeds the recovery draft limit.')
    latest=db.execute('SELECT revision FROM studio_drafts WHERE draft_id=?',(draft['draft_id'],)).fetchone()
    if latest is None or latest['revision']!=draft['revision']:raise ValueError('Recovery draft changed; reopen it before continuing.')
    version=db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM studio_draft_versions WHERE draft_id=?',(draft['draft_id'],)).fetchone()[0]
    db.execute('INSERT INTO studio_draft_versions VALUES(?,?,?)',(draft['draft_id'],version,raw))
    db.execute('UPDATE studio_drafts SET revision=?,updated_at=?,completed=? WHERE draft_id=?',
        (version,datetime.now(timezone.utc).isoformat(),int(completed),draft['draft_id']))


def reject_revision(root,revision_id,context):
    store,draft,saved=_load(root,revision_id);plan=load_revision_plan(saved['plan']);_context(plan,context)
    if saved.get('status')=='rejected':return dict(plan.selected_context)
    if saved.get('status')!='complete':raise ValueError('Only a pending completed candidate can be rejected.')
    saved['status']='rejected';saved['decision']={'source':'studio_chat.reject_revision_button','plan_sha256':_hash(plan)}
    with closing(store._connect()) as db,db:
        db.execute('BEGIN IMMEDIATE');_save_version(db,draft,draft['payload'],completed=True)
    return dict(plan.selected_context)


def adopt_revision(root,revision_id,cancel=None):
    root=Path(root).resolve()
    if not _BUILD_LOCK.acquire(blocking=False):raise ValueError('Another book operation is still finishing.')
    try:
        if cancel and cancel.is_set():raise ValueError('Adoption cancelled before commit.')
        store,draft,saved=_load(root,revision_id);plan=load_revision_plan(saved['plan'])
        if saved.get('status')=='adopted':return saved['adoption_result']
        expected={'source':'studio_chat.accept_revision_button','plan_sha256':_hash(plan),'candidate_sha256':saved.get('result',{}).get('candidate_sha256')}
        if saved.get('status')!='complete' or saved.get('adoption_confirmation')!=expected or not expected['candidate_sha256']:
            raise ValueError('Accept this exact completed candidate before adopting it.')
        if saved.get('confirmation')!={'source':'studio_chat.revision_button','plan_sha256':_hash(plan)}:
            raise ValueError('The generation plan confirmation is invalid.')
        snapshot=_source_snapshot(root,plan.selected_context)
        if snapshot!=plan.source_snapshot:raise ValueError('Source changed since staging; preserve the candidate and review again.')
        import puzzle_book_studio as studio
        _,staging=studio._production_scope(plan.kind,plan.title,revision_id)
        candidate=Path(saved['result']['folder']).resolve()
        if candidate==staging or not candidate.is_relative_to(staging):raise ValueError('Candidate is outside its revision staging folder.')
        if _tree(candidate)!=expected['candidate_sha256']:raise ValueError('Candidate files changed after staging.')
        from .package_layout import package_file,release_contract
        source=json.loads(package_file(candidate,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))
        from .studio_title_page_candidate import candidate_manifest_facts,protected_pages
        source=candidate_manifest_facts(root,plan,candidate,source)
        if plan.kind=='Word Search':
            from .package_revisions import compare_revision
            original_folder=Path(snapshot['book']['package_path'])
            compare_revision(original_folder,candidate)
            if protected_pages(package_file(original_folder,'interior.pdf'))!=protected_pages(package_file(candidate,'interior.pdf')):
                raise ValueError('Protected Word Search pages/resources changed since staging.')
        facts={'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':plan.kind,'theme':plan.topic,
            'puzzle_count':plan.count,'difficulty':plan.difficulty,'puzzle_seed':plan.seed,'interior_style':plan.interior_style,'title_page_style':plan.title_page_style,'cover_art_sha256':snapshot['approved_art_sha256']}
        if any(source.get(k)!=v for k,v in facts.items()):raise ValueError('Candidate facts differ from its confirmed plan.')
        verify_revision_typography(plan,candidate,source)
        from .product_qa import inspect_product
        from preflight import preflight
        from pypdf import PdfReader
        pages=len(PdfReader(package_file(candidate,'interior.pdf')).pages)
        qa=inspect_product(root,candidate,{**source,'require_puzzle_manifest':True})
        if pages!=plan.expected_pages or qa.blockers or not preflight(candidate)[0] or not release_contract(candidate)['ready']:
            raise ValueError('Candidate failed fresh adoption QA/preflight.')
        # Create a stable local handoff before the database transaction. A crash
        # leaves a recoverable copy; a retry reuses only byte-identical content.
        parent=root/'out/studio_adopted_revisions'
        for path in (root/'out',parent):
            if path.is_symlink() or path.is_junction():raise ValueError('Adoption output cannot use links or junctions.')
        destination=parent/revision_id
        if destination.is_symlink() or destination.is_junction():raise ValueError('Adoption destination cannot be a link.')
        if not destination.resolve().is_relative_to((root/'out').resolve()):raise ValueError('Adoption destination escaped output folder.')
        if destination.exists():
            if _tree(destination)!=expected['candidate_sha256']:raise ValueError('Existing recovery copy differs; preserving it.')
        else:
            parent.mkdir(parents=True,exist_ok=True);shutil.copytree(candidate,destination)
        if _tree(destination)!=expected['candidate_sha256'] or _tree(candidate)!=expected['candidate_sha256']:
            raise ValueError('Revision changed during copying; no catalog changes were made.')
        if _source_snapshot(root,plan.selected_context)!=snapshot:raise ValueError('Source changed during adoption checks.')
        from .manager import PublishingService
        from .metadata_service import build_metadata
        service=PublishingService(root);book=snapshot['book'];book_id=book['book_id']
        original_store=StudioDraftStore(root/'data/books.db')
        original=original_store.load(book['metadata']['studio_chat_creation']['draft_id'])
        lineage={'revision_id':revision_id,'plan_sha256':_hash(plan),'source_key':book['source_key']}
        meta=build_metadata({'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':plan.kind,
            'detected_topic':plan.topic,'puzzle_count':plan.count,'difficulty_label':plan.difficulty})
        meta.update(book_id=book_id,trim_size='8.5x11',page_count=pages,files=service._package_files(destination),
            production_status='Needs owner and platform review',puzzle_seed=plan.seed,
            studio_chat_creation=book['metadata']['studio_chat_creation'],studio_chat_adoption=lineage)
        result={'book_id':book_id,'title':plan.title,'topic':plan.topic,'kind':plan.kind,'folder':str(destination),'pages':pages,
            'puzzles':plan.count,'revision_id':revision_id,'status':'ADOPTED_OWNER_REVIEW_PENDING',
            'previous_folder':book['package_path'],'qa':qa.to_dict()}
        saved.update(status='adopted',adoption_result=result)
        original_saved=original['payload']['chat_creation'];original_saved['adopted_revision']=lineage
        original_saved['result'].update(book_id=book_id,folder=str(destination),pages=pages,title=plan.title,puzzles=plan.count)
        with closing(store._connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM books WHERE book_id=?',(book_id,)).fetchone()
            if not row or json.loads(row['metadata_json'])!=book['metadata'] or row['package_path']!=book['package_path'] or row['source_key']!=book['source_key'] or row['metadata_locked']:
                raise ValueError('Catalog changed before commit; adoption was not applied.')
            statuses={r['marketplace']:r['status'] for r in db.execute('SELECT marketplace,status FROM marketplace_status WHERE book_id=?',(book_id,))}
            if statuses!=book['statuses'] or any(v!='Not Prepared' for v in statuses.values()) or db.execute('SELECT 1 FROM release_locks WHERE book_id=?',(book_id,)).fetchone():
                raise ValueError('Marketplace or release state changed; adoption was not applied.')
            for other in db.execute('SELECT book_id,metadata_json,package_path FROM books WHERE book_id<>?',(book_id,)):
                if json.loads(other['metadata_json']).get('title','').casefold()==plan.title.casefold() or other['package_path']==str(destination):
                    raise ValueError('Another catalog book already owns that title or package.')
            if cancel and cancel.is_set():raise ValueError('Adoption cancelled before commit; recovery files are preserved.')
            db.execute('UPDATE books SET metadata_json=?,package_path=?,updated_at=? WHERE book_id=?',
                (json.dumps(meta),str(destination),datetime.now(timezone.utc).isoformat(),book_id))
            _save_version(db,original,original['payload'])
            _save_version(db,draft,draft['payload'])
        return result
    finally:_BUILD_LOCK.release()


def managed_chat_package_paths(project):
    """Prevent broad rescans from replacing owned identities or old revisions."""
    import sqlite3
    catalog=Path(project)/'data/books.db'
    if not catalog.is_file():return set()
    paths=set()
    with closing(sqlite3.connect(catalog.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        for metadata,folder in db.execute('SELECT metadata_json,package_path FROM books'):
            if json.loads(metadata).get('studio_chat_creation') and folder:paths.add(Path(folder).resolve())
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_drafts'").fetchone()
        if exists:
            for (raw,) in db.execute('SELECT v.payload FROM studio_drafts d JOIN studio_draft_versions v USING(draft_id,revision)'):
                saved=json.loads(raw).get('chat_revision',{})
                if saved.get('status')=='adopted':
                    plan=saved['plan'];result=saved['adoption_result']
                    paths.add(Path(plan['source_snapshot']['book']['package_path']).resolve())
                    paths.add(Path(result['folder']).resolve())
    return paths
