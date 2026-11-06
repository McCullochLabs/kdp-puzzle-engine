"""Staged revisions of owned chat drafts; adoption is a separate service."""
from dataclasses import asdict,dataclass
import hashlib,json,re,uuid
from pathlib import Path
from .studio_chat_creation import _BUILD_LOCK,_validated_saved_plan,_plan_hash


@dataclass(frozen=True)
class ChatRevisionPlan:
    revision_id:str
    request:str
    selected_context:dict
    source_book_id:str
    source_snapshot:dict
    changed_field:str
    changed_value:object
    title:str
    count:int
    difficulty:str
    seed:int
    topic:str
    author:str
    cover_art:str
    cover_style:str
    interior_style:str
    title_page_style:str

    @property
    def typography(self):
        from .sudoku_typography import SudokuTypography
        raw=self.source_snapshot['manifest'].get('sudoku_typography') if self.kind=='Sudoku' else None
        return SudokuTypography.from_dict(raw) if raw is not None else None

    @property
    def subtitle(self):
        if self.kind=='Sudoku':return f'{self.count} Number, Letter and Shape Sudoku Puzzles with Complete Solutions'
        return self.source_snapshot['manifest']['subtitle']

    @property
    def kind(self):return self.source_snapshot['manifest']['puzzle_type']

    @property
    def expected_pages(self):
        return self.count*2+4 if self.kind=='Sudoku' else self.source_snapshot['book']['metadata']['page_count']


@dataclass(frozen=True)
class TypographyRevisionPlan(ChatRevisionPlan):
    plan_schema_version:int
    typography_config:dict

    def __post_init__(self):
        from .sudoku_typography import SudokuTypography
        if type(self.plan_schema_version) is not int or self.plan_schema_version!=2 or self.kind!='Sudoku':
            raise ValueError('Unsupported typography revision plan version or family.')
        config=SudokuTypography.from_dict(self.typography_config)
        if self.changed_field in ('puzzle_font_pt','solution_font_pt') and getattr(config,self.changed_field)!=self.changed_value:
            raise ValueError('Typography revision value does not match its versioned configuration.')

    @property
    def typography(self):
        from .sudoku_typography import SudokuTypography
        return SudokuTypography.from_dict(self.typography_config)


@dataclass(frozen=True)
class CryptogramTypographyRevisionPlan(TypographyRevisionPlan):
    def __post_init__(self):
        from .cryptogram_typography import CryptogramTypography
        if type(self.plan_schema_version) is not int or self.plan_schema_version != 3 or self.kind != 'Cryptogram':
            raise ValueError('Unsupported Cryptogram typography revision version or family.')
        config=CryptogramTypography.from_dict(self.typography_config)
        if self.changed_field in ('puzzle_font_pt','solution_font_pt') and getattr(config,self.changed_field)!=self.changed_value:
            raise ValueError('Typography revision value does not match its versioned configuration.')

    @property
    def typography(self):
        from .cryptogram_typography import CryptogramTypography
        return CryptogramTypography.from_dict(self.typography_config)


def load_revision_plan(raw):
    if not isinstance(raw,dict):raise ValueError('Invalid revision plan.')
    try:
        return (CryptogramTypographyRevisionPlan(**raw) if raw.get('plan_schema_version')==3 else TypographyRevisionPlan(**raw)) if 'plan_schema_version' in raw else ChatRevisionPlan(**raw)
    except (TypeError,KeyError) as exc:
        raise ValueError('Invalid or incomplete revision plan fields.') from exc


def verify_revision_typography(plan,folder,source):
    if plan.kind not in ('Sudoku','Cryptogram'):return
    if plan.kind=='Sudoku':
        from .sudoku_typography import package_typography,verify_typography_binding
    else:
        from .cryptogram_typography import package_typography,verify_typography_binding
    config=package_typography(plan.kind,plan.typography)
    key='sudoku_typography' if plan.kind=='Sudoku' else 'cryptogram_typography'
    if source.get(key)!=(config.to_dict() if config else None):
        raise ValueError('Candidate typography differs from its confirmed revision plan.')
    from .package_layout import package_file
    if config:verify_typography_binding(package_file(folder,'interior.pdf'),config)
    if plan.changed_field in ('puzzle_font_pt','solution_font_pt'):
        original=Path(plan.source_snapshot['book']['package_path'])
        old=json.loads(package_file(original,'interior.pdf').with_suffix('.puzzles.json').read_text(encoding='utf-8'))
        new=json.loads(package_file(folder,'interior.pdf').with_suffix('.puzzles.json').read_text(encoding='utf-8'))
        if old['puzzles']!=new['puzzles']:raise ValueError('Typography revision changed puzzles or answers.')


def revision_decision(text):
    """Only an explicit whole-message decision targets a pending revision."""
    match=re.fullmatch(r'\s*(accept|reject)\s+(?:(?:the|this)\s+)?(?:staged\s+)?revision[.!]?\s*',str(text),re.I)
    return match.group(1).casefold() if match else None


def unsupported_design_revision(text):
    """Catch selected-book design edits before a provider can create a new book."""
    return bool(re.search(
        r'^\s*(?:(?:change|set|increase|decrease|enlarge|reduce)\s+(?:(?:the|its|my)\s+)?(?:(?:puzzle|solution)\s+)?(?:fonts?|font\s+size|layout|trim(?:\s+size)?|page\s+size|reader\s+profile)\b'
        r'|make\s+(?:it|(?:this|the|my)\s+book)\s+(?:large[ -]print\b|landscape\b|portrait\b|\d+(?:\.\d+)?\s*[x×]\s*\d+|use\s+(?:larger|smaller|bigger)\s+fonts?\b))',
        str(text), re.I))


def is_revision_request(text):
    return unsupported_design_revision(text) or bool(re.search(r"^\s*(?:change|set)\s+(?:(?:the|its)\s+)?(?:difficulty|puzzle\s+count|number\s+of\s+puzzles|count|title|title[ -]page\s+(?:design|style))\b|^\s*make\s+(?:it|this book)\s+(?:easier|harder)\b|^\s*add\b.*\bpuzzles?\b",text,re.I))


def _change(text, *, validate_fonts=True):
    text=text.strip().rstrip('.!?')
    font_match=re.fullmatch(r'(?:change|set)\s+(?:the\s+)?(puzzle|solution)\s+font\s+size\s+to\s+([0-9]+(?:\.[0-9]+)?)(?:\s*(?:pt|points))?',text,re.I)
    if font_match:
        from .sudoku_typography import SudokuTypography
        key=font_match.group(1).casefold()+'_font_pt';value=float(font_match.group(2))
        if validate_fonts:SudokuTypography(**{key:value})
        return key,value
    if unsupported_design_revision(text):
        raise ValueError('This font, layout, trim or reader-profile request is not supported for an existing book. For an owned Sudoku draft, use Set puzzle font size to 34 points or Set solution font size to 22 points. For opening-page presets, ask Show title page designs. Other formats need a separately reviewed guided plan.')
    if re.fullmatch(r'make\s+(?:it|this book)\s+easier',text,re.I):return 'difficulty','Easy'
    if re.fullmatch(r'make\s+(?:it|this book)\s+harder',text,re.I):return 'difficulty','Hard'
    match=re.fullmatch(r'(?:change|set)\s+(?:the\s+)?difficulty\s+to\s+(Easy|Hard|Mixed)',text,re.I)
    if match:return 'difficulty',match.group(1).title()
    match=re.fullmatch(r'(?:change|set)\s+(?:the\s+)?(?:puzzle\s+count|number\s+of\s+puzzles|count)\s+to\s+([0-9]+)',text,re.I)
    if match:
        count=int(match.group(1))
        if not 24<=count<=150:raise ValueError('Staged Sudoku revisions support 24 to150 puzzles.')
        return 'count',count
    match=re.fullmatch(r'(?:change|set)\s+(?:the\s+)?title\s+to\s+["“]([^"”]+)["”]',text,re.I)
    if match:
        title=match.group(1).strip()
        if not 1<=len(title)<=110 or any(ord(c)<32 for c in title):raise ValueError('Use a title of1 to110 printable characters.')
        return 'title',title
    match=re.fullmatch(r'(?:change|set)\s+(?:the\s+)?title[ -]page\s+(?:design|style)\s+to\s+(.+)',text,re.I)
    if match:
        from .title_pages import STYLE_LABELS
        labels=('Automatic',*STYLE_LABELS.values())
        styles={name.casefold():name for name in labels}
        raw=match.group(1).strip()
        if len(raw)>=2 and (raw[0],raw[-1]) in (('"','"'),('“','”')):raw=raw[1:-1].strip()
        selected=styles.get(raw.casefold())
        if selected:return 'title_page_style',selected
        raise ValueError('Choose a supported title page design: '+', '.join(labels)+'.')
    raise ValueError('Direct staged revisions support one change: difficulty to Easy/Hard/Mixed, puzzle count to24–150, title to a quoted name, or title page design to a quoted preset. Adding puzzles while preserving all old grids is not supported; changing the total regenerates the candidate.')


def _source_snapshot(root,context):
    from .database import PublishingDatabase
    from .studio_recovery import StudioDraftStore
    from .package_layout import package_file
    from .metadata_service import build_metadata
    from .manager import PublishingService
    import puzzle_book_studio as studio
    root=Path(root).resolve()
    if root!=studio.APP.resolve():raise ValueError('The production project does not match this studio.')
    if not context or not context.get('book_id'):raise ValueError('Select a supported new chat-created project first.')
    db=PublishingDatabase(root/'data/books.db');book=db.get_book(context['book_id'])
    if not book:raise ValueError('Selected book is missing.')
    if book.get('metadata_locked') or db.release_locks(book['book_id']) or any(v!='Not Prepared' for v in book.get('statuses',{}).values()):
        raise ValueError('Locked, released or marketplace-tracked books are not supported by this draft revision route.')
    meta=book['metadata'];owner=meta.get('studio_chat_creation',{})
    draft=StudioDraftStore(root/'data/books.db').load(owner.get('draft_id',''))
    saved=draft['payload'].get('chat_creation',{}) if draft else {}
    if saved.get('status')!='complete':raise ValueError('This route only revises completed new chat-created drafts.')
    original=_validated_saved_plan(saved)
    if original.kind not in ('Sudoku','Cryptogram','Word Scramble + Trivia','Mixed Brain Games','Word Search'):
        raise ValueError('This owned draft family does not support staged revisions yet.')
    if owner.get('plan_sha256')!=_plan_hash(original) or saved.get('confirmation',{}).get('plan_sha256')!=_plan_hash(original):
        raise ValueError('Source project ownership does not match its confirmed creation plan.')
    original_hash=_plan_hash(original)
    owned_title_style='Automatic'
    owned_typography=original.typography
    adopted=saved.get('adopted_revision')
    if adopted:
        from dataclasses import replace
        history=StudioDraftStore(root/'data/books.db').load(adopted['revision_id'])
        entry=history['payload']['chat_revision'] if history else {}
        if entry.get('status')!='adopted' or entry.get('adoption_result',{}).get('book_id')!=book['book_id'] or entry.get('adoption_result',{}).get('folder')!=book['package_path']:
            raise ValueError('Adopted revision ownership no longer matches the project.')
        prior=load_revision_plan(entry['plan'])
        owned_title_style=prior.title_page_style
        owned_typography=prior.typography
        if _hash(prior)!=adopted['plan_sha256']:raise ValueError('Adopted revision plan changed.')
        original=replace(original,title=prior.title,count=prior.count,difficulty=prior.difficulty)
    package=Path(book['package_path']).resolve()
    if not package.is_relative_to(root/'out') or saved.get('result',{}).get('book_id')!=book['book_id'] or Path(saved.get('result',{}).get('folder','')).resolve()!=package:
        raise ValueError('Source package identity no longer matches the chat-created project.')
    source=json.loads(package_file(package,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))
    if original.kind=='Word Search':
        from .studio_title_page_candidate import wordsearch_manifest_facts
        source=wordsearch_manifest_facts(root,original,package,source,expected_style=owned_title_style)
    if original.kind in ('Sudoku','Cryptogram'):
        if original.kind=='Sudoku':
            from .sudoku_typography import package_typography,verify_typography_binding
        else:
            from .cryptogram_typography import package_typography,verify_typography_binding
        expected_typography=package_typography(original.kind,owned_typography)
        key='sudoku_typography' if original.kind=='Sudoku' else 'cryptogram_typography'
        if source.get(key)!=(expected_typography.to_dict() if expected_typography else None):
            raise ValueError('Source typography changed outside its adopted revision history.')
        if expected_typography:verify_typography_binding(package_file(package,'interior.pdf'),expected_typography)
    expected=build_metadata({'title':original.title,'subtitle':original.subtitle,'author':original.author,'puzzle_type':original.kind,
                            'detected_topic':original.topic,'puzzle_count':original.count,'difficulty_label':original.difficulty})
    expected.update(book_id=book['book_id'],trim_size='8.5x11',page_count=saved['result']['pages'],files=PublishingService(root)._package_files(package),
                    production_status='Needs owner and platform review',puzzle_seed=original.seed,
                    studio_chat_creation={'draft_id':original.draft_id,'plan_sha256':original_hash})
    if adopted: expected['studio_chat_adoption']=adopted
    if meta!=expected or book['source_key']!=(adopted['source_key'] if adopted else 'package:'+str(package)):
        raise ValueError('Source metadata was edited after chat creation; preserving owner changes.')
    actual={'title':original.title,'subtitle':original.subtitle,'author':original.author,'puzzle_type':original.kind,'theme':original.topic,
            'puzzle_count':original.count,'difficulty':original.difficulty,'puzzle_seed':original.seed}
    if any(source.get(k)!=v for k,v in actual.items()):raise ValueError('Source manifest changed after creation.')
    art=studio.cover_art_path(source.get('cover_art'))
    if not art or not art.is_file() or not art.resolve().is_relative_to(root/'cover_assets'):
        raise ValueError('Source approved artwork is missing or outside the project library.')
    from background_generation.index import BackgroundAssetIndex
    index=BackgroundAssetIndex();asset=index.ledger_details(art)
    if not asset or not index.production_selectable(asset) or hashlib.sha256(art.read_bytes()).hexdigest()!=source.get('cover_art_sha256'):
        raise ValueError('Source artwork approval/fingerprint changed; review it before revision.')
    hashes={str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.rglob('*')) if p.is_file()}
    return {'book':book,'manifest':source,'package_file_sha256':hashes,'approved_art_sha256':source['cover_art_sha256']}


def revision_plan(root,text,context,*,revision_id=None):
    if context and context.get('pending_semantic_revision'):
        raise ValueError('A staged candidate is still pending. Accept or reject it before staging another change, or choose the original book explicitly.')
    field,value=_change(text,validate_fonts=False);snapshot=_source_snapshot(root,context);source=snapshot['manifest']
    if source['puzzle_type']=='Word Search' and field!='title_page_style':
        raise ValueError('Owned Word Search currently supports title page design revisions only; title, count and difficulty are preserved.')
    if source['puzzle_type']!='Sudoku' and field not in ('title','title_page_style') and not (source['puzzle_type']=='Cryptogram' and field in ('puzzle_font_pt','solution_font_pt')):
        raise ValueError('This family currently supports staged title and title page design changes only; puzzle count and difficulty are preserved.')
    values={'title':source['title'],'count':source['puzzle_count'],'difficulty':source['difficulty'],'title_page_style':source['title_page_style']}
    from .sudoku_typography import SudokuTypography
    from .cryptogram_typography import CryptogramTypography
    config_type=CryptogramTypography if source['puzzle_type']=='Cryptogram' else SudokuTypography
    config_key='cryptogram_typography' if source['puzzle_type']=='Cryptogram' else 'sudoku_typography'
    typography=config_type.from_dict(source[config_key]) if source.get(config_key) else config_type()
    values.update(puzzle_font_pt=typography.puzzle_font_pt,solution_font_pt=typography.solution_font_pt)
    if values[field]==value:raise ValueError('That setting is already selected; no revision is needed.')
    values[field]=value
    run=revision_id or uuid.uuid4().hex
    if not re.fullmatch('[0-9a-f]{32}',run) or uuid.UUID(hex=run).version!=4:raise ValueError('Invalid revision UUID.')
    args=(run,text,dict(context),context['book_id'],snapshot,field,value,
          values['title'],values['count'],values['difficulty'],source['puzzle_seed'],source['theme'],source['author'],
          source['cover_art'],source['cover_style'],source['interior_style'],values['title_page_style'])
    if field in ('puzzle_font_pt','solution_font_pt') or source.get(config_key):
        configured=config_type(puzzle_font_pt=values['puzzle_font_pt'],solution_font_pt=values['solution_font_pt'])
        return CryptogramTypographyRevisionPlan(*args,3,configured.to_dict()) if source['puzzle_type']=='Cryptogram' else TypographyRevisionPlan(*args,2,configured.to_dict())
    return ChatRevisionPlan(*args)


def revision_text(plan):
    label={'title_page_style':'title-page design','count':'puzzle count','title':'title','difficulty':'difficulty','puzzle_font_pt':'puzzle grid font size','solution_font_pt':'solution grid font size'}[plan.changed_field]
    return (f'Stage a revision candidate for {plan.source_snapshot["manifest"]["title"]!r}: {label} → {plan.changed_value}. '+
            (f'Grid fonts: puzzles {plan.typography.puzzle_font_pt:g} pt, solutions {plan.typography.solution_font_pt:g} pt; only text sizes change. ' if isinstance(plan,TypographyRevisionPlan) else '')+
            f'Candidate: {plan.title!r}, {plan.count} {plan.kind} puzzles, {plan.expected_pages} expected pages; title page design: {plan.title_page_style}. '
            'The existing source stays selected and unchanged. '+('Only the title page is replaced; puzzles, solutions and cover files are copied unchanged. ' if plan.kind=='Word Search' else 'The candidate regenerates puzzles from the retained seed and retains the same approved artwork. ')+
            'Create staged revision confirms this exact candidate; it does not adopt, publish or replace the original book.')


def _hash(plan):return hashlib.sha256(json.dumps(asdict(plan),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def save_revision_plan(root,plan):
    from .studio_recovery import StudioDraftStore
    payload={'kind':plan.kind,'topic':plan.topic,'chat_revision':{'plan':asdict(plan),'status':'planned'}}
    StudioDraftStore(Path(root)/'data/books.db').save(plan.revision_id,'book_plan',payload)


def _state(root,plan,status,**extra):
    from .studio_recovery import StudioDraftStore
    store=StudioDraftStore(Path(root)/'data/books.db');draft=store.load(plan.revision_id)
    if not draft:raise ValueError('Revision draft is missing.')
    payload=draft['payload'];payload['chat_revision'].update(status=status,**extra)
    store.save(plan.revision_id,'book_plan',payload)


def confirm_revision_plan(root,plan,context):
    from .studio_recovery import StudioDraftStore
    if dict(context or {})!=plan.selected_context:raise ValueError('Selected project changed; submit the revision again.')
    expected=revision_plan(root,plan.request,context,revision_id=plan.revision_id)
    if asdict(expected)!=asdict(plan):raise ValueError('Source or revision plan changed; review a new plan.')
    draft=StudioDraftStore(Path(root)/'data/books.db').load(plan.revision_id)
    if not draft or draft['payload'].get('chat_revision',{}).get('plan')!=asdict(plan):raise ValueError('Displayed revision does not match the saved plan.')
    _state(root,plan,'confirmed',confirmation={'source':'studio_chat.revision_button','plan_sha256':_hash(plan)})


def stage_revision(root,revision_id,cancel=None):
    from .studio_recovery import StudioDraftStore
    root=Path(root).resolve();plan=None
    if cancel and cancel.is_set():raise ValueError('Revision cancelled before generation.')
    if not _BUILD_LOCK.acquire(blocking=False):raise ValueError('Another chat book build is still finishing.')
    try:
        draft=StudioDraftStore(root/'data/books.db').load(revision_id)
        saved=draft['payload']['chat_revision'] if draft else {}
        if not saved:raise ValueError('Revision draft not found.')
        plan=load_revision_plan(saved['plan'])
        if saved.get('confirmation')!={'source':'studio_chat.revision_button','plan_sha256':_hash(plan)}:
            raise ValueError('The exact revision was not confirmed with Create staged revision.')
        expected=revision_plan(root,plan.request,plan.selected_context,revision_id=plan.revision_id)
        if asdict(expected)!=asdict(plan):raise ValueError('Source or revision plan changed; preserving the original project.')
        if saved.get('status')=='complete':return saved['result']
        _state(root,plan,'running')
        import puzzle_book_studio as studio
        destination=root/'data/studio_revision_candidates'/plan.revision_id
        if plan.kind=='Word Search':
            from .studio_title_page_candidate import build_title_page_candidate
            folder,_copy_proof=build_title_page_candidate(root,plan.source_snapshot['book']['package_path'],plan.revision_id,plan.title_page_style,plan.source_snapshot['package_file_sha256'],recover=True)
        else:
            friendly=next((key for key,value in studio.COVER_STYLE_OPTIONS.items() if value==plan.cover_style),None)
            if not friendly:raise ValueError('The source cover layout cannot be retained by this route.')
            folder=Path(studio.create_package(plan.kind,plan.title,plan.subtitle,plan.author,plan.count,plan.difficulty,plan.seed,theme=plan.topic,
                        cover_style=friendly,cover_photo=plan.cover_art,interior_style=plan.interior_style,title_page_style=plan.title_page_style,
                        content_plan_approval={'source':'studio_chat.revision_confirmation','evidence_id':_hash(plan)[:20]},sync_catalog=False,
                        production_run_id=plan.revision_id,output_parent=destination,**({} if plan.typography is None else {('sudoku_typography' if plan.kind=='Sudoku' else 'cryptogram_typography'):plan.typography}))).resolve()
        if not folder.is_relative_to(destination):raise ValueError('Candidate escaped its revision staging folder.')
        from .package_layout import package_file,release_contract
        from .product_qa import inspect_product
        from preflight import preflight
        from pypdf import PdfReader
        source=json.loads(package_file(folder,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))
        from .studio_title_page_candidate import candidate_manifest_facts
        source=candidate_manifest_facts(root,plan,folder,source)
        fields={'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':plan.kind,'puzzle_count':plan.count,
                'difficulty':plan.difficulty,'puzzle_seed':plan.seed,'theme':plan.topic,'interior_style':plan.interior_style,'title_page_style':plan.title_page_style,'cover_art_sha256':plan.source_snapshot['approved_art_sha256']}
        if any(source.get(k)!=v for k,v in fields.items()):raise ValueError('Candidate facts/artwork do not match the confirmed revision.')
        verify_revision_typography(plan,folder,source)
        if plan.changed_field in ('title','title_page_style'):
            old=json.loads(package_file(Path(plan.source_snapshot['book']['package_path']),'interior.pdf').with_suffix('.puzzles.json').read_text())
            new=json.loads(package_file(folder,'interior.pdf').with_suffix('.puzzles.json').read_text())
            if old['puzzles']!=new['puzzles']:raise ValueError('Title/design-only revision changed puzzles or answers.')
        pages=len(PdfReader(package_file(folder,'interior.pdf')).pages)
        if pages!=plan.expected_pages:raise ValueError('Staged revision page count differs from the confirmed plan.')
        ok,notes=preflight(folder);qa=inspect_product(root,folder,{**source,'require_puzzle_manifest':True})
        if not ok or qa.blockers or not release_contract(folder)['ready']:raise ValueError('Staged candidate has local production/QA blockers; original preserved.')
        if _source_snapshot(root,plan.selected_context)!=plan.source_snapshot:raise ValueError('Source changed while generating; candidate is held for review.')
        provenance={'status':'STAGED_SEMANTIC_REVISION_NOT_ADOPTED','source_book_id':plan.source_book_id,'source_package':plan.source_snapshot['book']['package_path'],
                    'source_package_sha256':plan.source_snapshot['package_file_sha256'],'confirmed_plan_sha256':_hash(plan),'changed_field':plan.changed_field,
                    'changed_value':plan.changed_value,'canonical_catalog_changed':False,'approval':'No new rights, human editorial or marketplace approval'}
        proof=folder/(('STAGED_REVISION_PROVENANCE_'+plan.revision_id+'.json') if plan.kind=='Word Search' else 'STAGED_REVISION_PROVENANCE.json')
        if proof.exists():
            if json.loads(proof.read_text())!=provenance:raise ValueError('Existing revision provenance differs; preserving it.')
        else:
            with proof.open('x',encoding='utf-8') as stream:json.dump(provenance,stream,indent=2)
        result={'source_book_id':plan.source_book_id,'source_title':plan.source_snapshot['manifest']['title'],'revision_id':plan.revision_id,'folder':str(folder),
                'title':plan.title,'puzzles':plan.count,'pages':pages,'preflight':True,'qa':qa.to_dict(),'status':'STAGED_NOT_ADOPTED','source_unchanged':True,
                'candidate_sha256':{str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()}}
        _state(root,plan,'complete',result=result);return result
    except Exception as exc:
        if plan:
            try:_state(root,plan,'failed',error=str(exc))
            except Exception:pass
        raise
    finally:_BUILD_LOCK.release()
