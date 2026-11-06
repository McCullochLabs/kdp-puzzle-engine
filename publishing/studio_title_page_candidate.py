"""Immutable single-package title-page copies; no catalog or approval changes.

This low-level builder does not authorize adoption or replace chat confirmation.
A caller must supply an independently frozen authoritative source tree. Only
Word Search title-page design changes are supported here.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import uuid

from pypdf import PdfReader,PdfWriter
from pypdf.generic import IndirectObject,NullObject
from reportlab.pdfgen.canvas import Canvas

from .package_layout import package_file
from .package_revisions import compare_revision
from .studio_revision_adoption import _tree
from .title_pages import STYLE_LABELS,render_title_page,spec_from_mapping


def _resource_digester():
    # Scope to one reader/check and retain objects to prevent Python ID reuse.
    cache={};active=set()
    def visit(obj):
        if isinstance(obj,IndirectObject):obj=obj.get_object()
        key=id(obj)
        if key in cache:return cache[key][1]
        if key in active:raise ValueError('Cyclic PDF resources require separate review.')
        active.add(key)
        try:
            if isinstance(obj,dict):
                data={str(k):visit(v) for k,v in sorted(obj.items(),key=lambda pair:str(pair[0])) if str(k) not in ('/Length',)}
                if hasattr(obj,'get_data'):data['__decoded_stream_sha256__']=hashlib.sha256(obj.get_data()).hexdigest()
            elif isinstance(obj,(list,tuple)):data=[visit(v) for v in obj]
            elif isinstance(obj,bytes):data={'bytes_sha256':hashlib.sha256(obj).hexdigest()}
            elif isinstance(obj,NullObject):data=None
            else:data={'type':type(obj).__name__,'value':str(obj)}
            digest=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            cache[key]=(obj,digest);return digest
        finally:active.remove(key)
    return visit


def _resource_digest(value):
    return _resource_digester()(value)


def protected_pages(path):
    """Bind every page after the title, including decoded resources/fonts."""
    reader=PdfReader(path);result=[];resource_digest=_resource_digester()
    for page in reader.pages[1:]:
        contents=page.get_contents()
        result.append({'media':[float(v) for v in page.mediabox],
                       'crop':[float(v) for v in page.cropbox],'rotation':page.rotation,
                       'content_sha256':hashlib.sha256(contents.get_data() if contents else b'').hexdigest(),
                       'resources_sha256':resource_digest(page.get('/Resources',{}))})
    return result


def _unlinked(path,root):
    current=path
    while current!=root:
        if current.is_symlink() or current.is_junction():raise ValueError('Linked package/staging locations are not supported.')
        if current==current.parent:raise ValueError('Package location escaped this project.')
        current=current.parent


def _reuse_completed_copy(source,candidate,revision_id,style,expected_files):
    proof_name='TITLE_PAGE_COPY_PROOF_'+revision_id+'.json'
    proof_path=candidate/proof_name
    if proof_path.is_symlink() or proof_path.stat().st_size>2_000_000:
        raise ValueError('Recovery proof requires separate review.')
    try:proof=json.loads(proof_path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:raise ValueError('Recovery proof is incomplete or invalid; candidate preserved.') from exc
    if (proof.get('status')!='PRINT_EQUIVALENCE_ONLY_NOT_ADOPTED' or proof.get('style')!=style
            or proof.get('source_sha256')!=expected_files):
        raise ValueError('Recovery proof does not match the confirmed source/design.')
    actual=_tree(candidate)
    extras={proof_name,'STAGED_REVISION_PROVENANCE_'+revision_id+'.json'}
    body={name:digest for name,digest in actual.items() if name not in extras}
    if set(body)!=set(expected_files) or body!=proof.get('candidate_sha256'):
        raise ValueError('Completed candidate files changed; preserving them for review.')
    old_pdf=package_file(source,'interior.pdf');new_pdf=package_file(candidate,'interior.pdf')
    old_records=old_pdf.with_suffix('.puzzles.json');new_records=new_pdf.with_suffix('.puzzles.json')
    old_sha=hashlib.sha256(old_pdf.read_bytes()).hexdigest();record_sha=hashlib.sha256(old_records.read_bytes()).hexdigest()
    source_record=package_file(source,'PACKAGE_SOURCE_RECORD.json')
    allowed={str(source_record.relative_to(source))}
    allowed.update(name for name,digest in expected_files.items() if digest in (old_sha,record_sha) and not any(word in Path(name).name.casefold() for word in ('cover','wrap')))
    if any(body[name]!=digest for name,digest in expected_files.items() if name not in allowed):
        raise ValueError('Recovery changed an unrelated package/cover file.')
    raw=json.loads(source_record.read_text(encoding='utf-8-sig'))
    if json.loads(package_file(candidate,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))!={**raw,'title_page_style':style}:
        raise ValueError('Recovery source metadata differs from the title-page-only change.')
    expected_records=json.loads(old_records.read_text(encoding='utf-8-sig'))
    expected_records['pdf_sha256']=hashlib.sha256(new_pdf.read_bytes()).hexdigest()
    if json.loads(new_records.read_text(encoding='utf-8-sig'))!=expected_records:
        raise ValueError('Recovery puzzle bindings or layout records changed.')
    for name,digest in expected_files.items():
        if name in allowed and digest==old_sha and body[name]!=expected_records['pdf_sha256']:
            raise ValueError('Recovery interior handoff differs from its canonical PDF.')
        if name in allowed and digest==record_sha and body[name]!=hashlib.sha256(new_records.read_bytes()).hexdigest():
            raise ValueError('Recovery puzzle-record handoff differs.')
    compare_revision(source,candidate)
    if protected_pages(old_pdf)!=protected_pages(new_pdf):raise ValueError('Recovery protected pages/resources changed.')
    if _tree(source)!=expected_files:raise ValueError('Source changed during recovery validation.')
    return candidate,{**proof,'recovery_reused':True}


def build_title_page_candidate(root,source,revision_id,style,expected_files,*,recover=False):
    root=Path(root).resolve();raw=Path(source)
    if not raw.is_absolute():raise ValueError('Use an authoritative absolute source package.')
    _unlinked(raw,root);source=raw.resolve()
    if not source.is_relative_to(root/'out') or not source.is_dir():raise ValueError('Source must be an existing local output package.')
    try:valid=uuid.UUID(revision_id).version==4 and uuid.UUID(revision_id).hex==revision_id
    except (ValueError,AttributeError,TypeError):valid=False
    if not valid:raise ValueError('Use an exact revision UUID.')
    if style not in ('Automatic',*STYLE_LABELS.values()):raise ValueError('Unsupported title-page design.')
    if not expected_files or _tree(source)!=expected_files:raise ValueError('Source files changed after planning.')
    record=package_file(source,'PACKAGE_SOURCE_RECORD.json')
    original=json.loads(record.read_text(encoding='utf-8-sig'))
    if original.get('puzzle_type')!='Word Search':raise ValueError('This copy route supports Word Search title-page design only.')
    if original.get('title_page_style','Automatic')==style:raise ValueError('That title-page design is already selected.')
    base=root/'data/studio_revision_candidates'/revision_id
    choices=[base/'candidate']+[base/f'candidate_recovery_{n:03}' for n in range(1,4)]
    for choice in choices:
        _unlinked(choice,root)
        if not choice.resolve().is_relative_to(root/'data/studio_revision_candidates'):
            raise ValueError('Candidate escaped the local staging folder.')
    if recover:
        for choice in reversed(choices):
            proof=choice/('TITLE_PAGE_COPY_PROOF_'+revision_id+'.json')
            if proof.exists():return _reuse_completed_copy(source,choice,revision_id,style,expected_files)
        destination=next((choice for choice in choices if not choice.exists()),None)
        if destination is None:raise ValueError('Recovery attempts are held; all preserved copy locations need review.')
    else:
        destination=choices[0]
        if destination.exists():raise ValueError('Existing candidate is preserved; review it before starting a new revision.')
    old_pdf=package_file(source,'interior.pdf');old_manifest=old_pdf.with_suffix('.puzzles.json')
    old_pdf_sha=hashlib.sha256(old_pdf.read_bytes()).hexdigest();old_manifest_sha=hashlib.sha256(old_manifest.read_bytes()).hexdigest()
    puzzles=json.loads(old_manifest.read_text(encoding='utf-8-sig'))
    if puzzles.get('pdf_sha256')!=old_pdf_sha or not puzzles.get('puzzles'):raise ValueError('Source puzzle/PDF binding is invalid.')
    before=protected_pages(old_pdf);reader=PdfReader(old_pdf)
    if len(reader.pages)<2 or tuple(float(v) for v in reader.pages[0].mediabox[:2])!=(0.0,0.0) or reader.pages[0].rotation:
        raise ValueError('This first-page geometry requires separate review.')
    import puzzle_book_studio as studio
    studio.fonts()
    stream=io.BytesIO();size=(float(reader.pages[0].mediabox.width),float(reader.pages[0].mediabox.height))
    canvas=Canvas(stream,pagesize=size)
    data={**original,'title_page_style':style,'theme':original.get('theme') or original.get('cover_visual_topic') or 'General'}
    design=render_title_page(canvas,spec_from_mapping(data),page_size=size,regular_font=studio.font('BookSans'),bold_font=studio.font('BookBold'))
    canvas.save();title=PdfReader(io.BytesIO(stream.getvalue())).pages[0]
    title.cropbox=reader.pages[0].cropbox
    writer=PdfWriter();writer.add_page(title)
    for page in reader.pages[1:]:writer.add_page(page)
    if reader.metadata:writer.add_metadata({str(k):str(v) for k,v in reader.metadata.items() if v is not None})
    target=io.BytesIO();writer.write(target);new_pdf=target.getvalue()
    # Originals are never modified; partial candidates are retained on failure.
    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,destination)
    new_pdf_sha=hashlib.sha256(new_pdf).hexdigest();updated=dict(puzzles,pdf_sha256=new_pdf_sha)
    manifest_bytes=json.dumps(updated,indent=2,ensure_ascii=False).encode('utf-8')
    changed=[]
    for relative,digest in expected_files.items():
        path=destination/relative
        # A cover can share bytes with a fixture/placeholder interior. It is
        # never an interior handoff, regardless of a matching digest.
        if any(token in path.name.casefold() for token in ('cover','wrap')):continue
        if digest==old_pdf_sha:path.write_bytes(new_pdf);changed.append(relative)
        elif digest==old_manifest_sha:path.write_bytes(manifest_bytes);changed.append(relative)
    package_file(destination,'PACKAGE_SOURCE_RECORD.json').write_text(json.dumps({**original,'title_page_style':style},indent=2,ensure_ascii=False),encoding='utf-8')
    changed.append(str(record.relative_to(source)))
    if protected_pages(package_file(destination,'interior.pdf'))!=before:raise ValueError('Protected PDF page content/resources changed; candidate held.')
    compare_revision(source,destination)
    if _tree(source)!=expected_files:raise ValueError('Source changed during copying; candidate held.')
    actual=_tree(destination)
    if any(actual.get(name)!=digest for name,digest in expected_files.items() if name not in changed):raise ValueError('An unrelated package file changed; candidate held.')
    proof={'status':'PRINT_EQUIVALENCE_ONLY_NOT_ADOPTED','style':style,'design':design.to_dict(),
           'pages':len(reader.pages),'protected_pages':len(before),'puzzles_preserved':True,
           'source_sha256':expected_files,'candidate_sha256':actual,'changed_files':sorted(set(changed)),
           'limitations':'Fresh product QA/preflight, exact chat confirmation and adoption gates remain required. No human or marketplace approval granted.'}
    (destination/('TITLE_PAGE_COPY_PROOF_'+revision_id+'.json')).write_text(json.dumps(proof,indent=2),encoding='utf-8')
    return destination,proof


def wordsearch_manifest_facts(root,creation_plan,folder,raw,*,expected_style=None):
    """Derive legacy omissions only from the exact frozen owned theme/art."""
    from .studio_chat_wordsearch import _owned_paths
    source,_owned,_settings=_owned_paths(Path(root),creation_plan)
    frozen=creation_plan.checked_theme_json.encode('utf-8')
    if source.read_bytes()!=frozen or Path(str(raw.get('source_theme') or '')).resolve()!=source.resolve():
        raise ValueError('Owned Word Search theme changed after creation.')
    if raw.get('source_theme_sha256')!=hashlib.sha256(frozen).hexdigest() or raw.get('cover_art_sha256')!=creation_plan.art_sha256:
        raise ValueError('Owned Word Search source/art fingerprints differ.')
    if Path(str(raw.get('cover_art') or '')).resolve()!=Path(creation_plan.art_path).resolve():raise ValueError('Owned Word Search artwork path changed.')
    data=json.loads(frozen);groups=data.get('puzzles',[])
    records=json.loads(package_file(Path(folder),'interior.pdf').with_suffix('.puzzles.json').read_text(encoding='utf-8-sig')).get('puzzles',[])
    if data.get('detected_topic')!=creation_plan.topic or data.get('source_word_bank',{}).get('seed')!=creation_plan.seed:
        raise ValueError('Frozen Word Search topic/seed differs.')
    if len(groups)!=creation_plan.count or len(records)!=creation_plan.count or any(p.get('type')!='word_search' or set(p.get('words',[]))!=set(g['words']) for p,g in zip(records,groups)):
        raise ValueError('Word Search targets differ from the frozen checked groups.')
    for key,value in [('theme',creation_plan.topic),('puzzle_seed',creation_plan.seed)]:
        if key in raw and raw[key]!=value:raise ValueError('Word Search '+key+' changed.')
    style=raw.get('title_page_style','Automatic')
    if expected_style is not None and style!=expected_style:raise ValueError('Word Search title-page source changed outside its owned revision history.')
    return {**raw,'theme':creation_plan.topic,'puzzle_seed':creation_plan.seed,
            'cover_style':raw.get('cover_style',raw.get('cover_layout','photo')),
            'interior_style':raw.get('interior_style','Word Search Standard'),'title_page_style':style}


def candidate_manifest_facts(root,plan,folder,raw):
    if plan.kind!='Word Search':return raw
    from .studio_recovery import StudioDraftStore
    from .studio_chat_wordsearch import WordSearchChatPlan
    from .studio_chat_creation import _plan_hash
    owner=plan.source_snapshot['book']['metadata']['studio_chat_creation']
    saved=StudioDraftStore(Path(root)/'data/books.db').load(owner['draft_id'])
    creation=saved['payload']['chat_creation'] if saved else {}
    original=WordSearchChatPlan(**creation['plan'])
    if creation.get('status')!='complete' or _plan_hash(original)!=owner['plan_sha256'] or creation.get('confirmation')!={'source':'studio_chat.create_button','plan_sha256':owner['plan_sha256']}:
        raise ValueError('Word Search creation ownership changed.')
    return wordsearch_manifest_facts(root,original,folder,raw,expected_style=plan.title_page_style)
