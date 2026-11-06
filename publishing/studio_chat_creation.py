"""Bounded chat Sudoku creation using the existing reviewed production route.

No paid provider, shell interpolation, approval writes or replacement generator.
The chat shows a concrete plan; the user's Create button records plan approval.
"""
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
import uuid
from types import SimpleNamespace

_BUILD_LOCK = threading.Lock()


def _report_progress(progress, message):
    """Progress is observational; it cannot approve or abort production."""
    if progress is None:return
    try:
        progress(str(message))
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Build progress notification could not be delivered.')



@dataclass(frozen=True)
class ChatBookPlan:
    draft_id: str
    request: str
    title: str
    topic: str
    count: int
    difficulty: str
    seed: int
    requested_pages: int | None = None
    author: str = 'Jordan M. Slade'
    kind: str = 'Sudoku'

    @property
    def typography(self):return None

    @property
    def subtitle(self):
        return f'{self.count} Number, Letter and Shape Sudoku Puzzles with Complete Solutions'


@dataclass(frozen=True)
class TypographyChatBookPlan(ChatBookPlan):
    plan_schema_version:int = 2
    typography_config:dict = field(default_factory=dict)

    def __post_init__(self):
        from .sudoku_typography import SudokuTypography
        if type(self.plan_schema_version) is not int or self.plan_schema_version!=2 or self.kind!='Sudoku':
            raise ValueError('Unsupported typography creation plan version or family.')
        SudokuTypography.from_dict(self.typography_config)

    @property
    def typography(self):
        from .sudoku_typography import SudokuTypography
        return SudokuTypography.from_dict(self.typography_config)


def _font_creation_suffix(request, config_type=None):
    # Exact terminal clauses cannot consume a quoted title or unrelated action.
    pattern=r'\s+with\s+(puzzle|solution)\s+font\s+size\s+([0-9]+(?:\.[0-9]+)?)\s*(?:points|pt)(?:\s+and\s+(puzzle|solution)\s+font\s+size\s+([0-9]+(?:\.[0-9]+)?)\s*(?:points|pt))?[.!?]?\s*$'
    match=re.search(pattern,request,re.I)
    if not match:return None
    from .sudoku_typography import SudokuTypography
    values={match.group(1).casefold()+'_font_pt':float(match.group(2))}
    if match.group(3):
        key=match.group(3).casefold()+'_font_pt'
        if key in values:raise ValueError('Specify each grid font size only once.')
        values[key]=float(match.group(4))
    return request[:match.start()].strip(),(config_type or SudokuTypography)(**values)


def _numeric_request(request):
    # Never reinterpret a negative/decimal count as its positive suffix.
    quantities=re.findall(r'(?<![\w.])([+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)\s*(?:-\s*)?(puzzles?|pages?)\b',request,re.I)
    if any(not re.fullmatch(r'[0-9]+',token) for token,_ in quantities):
        raise ValueError('Puzzle/page counts must be unsigned whole numbers; negative, decimal or scientific notation is unsupported.')
    if re.search(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)\b(?:[ -]+\w+){0,2}\s+(?:pages?|puzzles?)\b',request,re.I):
        raise ValueError('Write the requested puzzle/page count using digits.')
    counts=[token for token,unit in quantities if unit.casefold().startswith('puzzle')]
    pages=[token for token,unit in quantities if unit.casefold().startswith('page')]
    seeds=re.findall(r'\bseed\b(?:\s*[:=]\s*|\s+)(\S+)',request,re.I)
    if re.search(r'\bseed\b',request,re.I) and len(seeds)!=1:
        raise ValueError('Specify exactly one unsigned whole-number seed.')
    seed=None
    if seeds:
        token=seeds[0].rstrip('!?;,')
        if token.endswith('.'):token=token[:-1]
        if not re.fullmatch(r'[0-9]+',token):raise ValueError('Seed must be an unsigned whole number, not signed, decimal or ambiguous.')
        seed=int(token)
    return counts,pages,seed


def sudoku_chat_plan(request, intent, *, draft_id=None):
    """Parse supported settings from the actual request, not model guesses."""
    if intent.kind != 'Sudoku' or intent.action != 'create_book':
        raise ValueError('Direct chat creation currently supports Sudoku. Other families retain their reviewed guided plans.')
    if not isinstance(request, str) or not request.strip() or len(request)>1000:
        raise ValueError('Use a book request of 1 to 1000 characters.')
    font_request=_font_creation_suffix(request)
    if font_request is not None:
        clean,config=font_request
        base=sudoku_chat_plan(clean,intent,draft_id=draft_id)
        values=asdict(base);values['request']=request
        return TypographyChatBookPlan(**values,typography_config=config.to_dict())
    if re.search(r'\b(?:large[ -]print|seniors?|kids?|children|ages?|font|bleed|hardcover|numbers?[- ]only|only numbers?)\b',request,re.I):
        raise ValueError('This direct Sudoku route uses the standard 8.5 × 11 layout with number, letter and shape puzzles. Requested reader/font/format variants need the reviewed guided plan.')
    if re.search(r'\b(?:covers?|colou?rs?|author|by|hardcover|paperback|landscape|portrait|trim|only|classic)\b|\b\d+\s*[x×]\s*\d+',request,re.I):
        raise ValueError('Direct chat Sudoku creation currently uses the shown default author, automatic approved cover and standard trim/style mix. Requested cover/author/format restrictions need the guided plan.')
    if re.search(r'\b(?:medium|intermediate|expert|very hard)\b',request,re.I):
        raise ValueError('Direct Sudoku creation supports Easy, Hard or Mixed difficulty; use one of those exact choices.')
    from .studio_assistant import guide_request
    if not re.search(r'\bsudoku\b',request,re.I):
        raise ValueError('State Sudoku and the new book settings explicitly; revisions of the selected book still need its reviewed editor.')
    explicit=guide_request(request)
    if explicit.action!='create_book' or explicit.kind!='Sudoku':
        raise ValueError('Use an explicit new Sudoku book creation request.')
    from puzzle_book_studio import AVAILABLE_THEMES
    aliases={'general':'General Starter','space':'Space & Astronomy','astronomy':'Space & Astronomy',
             'garden':'Garden & Growing','gardening':'Garden & Growing','nature':'Nature & Outdoors',
             'travel':'Travel & Adventure','road trip':'Road Trips & Highways','winter holidays':'Holidays & Seasons'}
    raw=explicit.topic.strip();topic=next((name for name in AVAILABLE_THEMES if name.casefold()==raw.casefold()),aliases.get(raw.casefold()))
    if not topic:
        raise ValueError(f'The topic {raw!r} has no supported Sudoku design here. Choose an existing theme; it will not be replaced silently.')
    counts,pages,requested_seed=_numeric_request(request)
    if len(set(counts))>1 or len(set(pages))>1:
        raise ValueError('Use one puzzle count and one optional page target.')
    target=int(pages[0]) if pages else None
    count=int(counts[0]) if counts else (target-4)//2 if target is not None else 48
    if not 24<=count<=150:
        raise ValueError('This production route supports 24 to 150 Sudoku puzzles.')
    if target is not None and (target!=count*2+4 or target%2):
        raise ValueError('This Sudoku layout uses two pages per puzzle plus four opening/solution/balancing pages. Request an even page count from 52 to 304, consistent with the puzzle count.')
    levels=[name for name in ('Easy','Hard','Mixed') if re.search(r'\b'+name+r'\b',request,re.I)]
    if len(levels)>1:raise ValueError('Choose one difficulty: Easy, Hard or Mixed.')
    level=levels[0] if levels else 'Mixed'
    draft_id=draft_id or uuid.uuid4().hex
    if not re.fullmatch('[0-9a-f]{32}',draft_id):raise ValueError('Invalid creation draft identity.')
    named=re.search(r'\b(?:called|titled)\s+["“]([^"”]+)["”]',request,re.I)
    if re.search(r'\b(?:called|titled)\b',request,re.I) and not named:
        raise ValueError('Put the requested book title in quotation marks after called or titled.')
    title=named.group(1).strip() if named else f'{topic} Sudoku — {draft_id[:8]}'
    if not 1<=len(title)<=110 or any(ord(c)<32 for c in title):raise ValueError('Use a title of 1 to 110 printable characters.')
    seed=requested_seed if requested_seed is not None else secrets.randbelow(2**31-1)+1
    if not 1<=seed<2**31:raise ValueError('Seed must be from 1 to 2147483647.')
    return ChatBookPlan(draft_id,request,title,topic,count,level,seed,target)


def plan_text(plan):
    if plan.kind=='Word Search':
        from .studio_chat_wordsearch import wordsearch_plan_text
        return wordsearch_plan_text(plan)
    if plan.kind!='Sudoku':
        from .studio_chat_families import family_plan_text
        return family_plan_text(plan)
    return (f'Create {plan.title!r}: {plan.count} {plan.difficulty} Sudoku puzzles, {plan.topic}, '
            f'{plan.count*2+4} expected pages, 8.5 × 11 inches, standard layout, number/letter/shape mix. '
            f'Author: {plan.author}. The existing approved-art and production gates apply. '+
            (f'Grid fonts: puzzles {plan.typography.puzzle_font_pt:g} pt, solutions {plan.typography.solution_font_pt:g} pt; shape grids retain their established geometry. ' if plan.typography else '')+
            'Create this book approves this exact plan and starts local generation; nothing is published.')


def save_creation_plan(root, plan, context=None):
    from .studio_recovery import StudioDraftStore
    payload={'kind':plan.kind,'topic':plan.topic,'editor':{'title':plan.title,'count':plan.count,'difficulty':plan.difficulty},
             'chat_creation':{'plan':asdict(plan),'status':'planned','selected_context':dict(context or {})}}
    StudioDraftStore(Path(root)/'data/books.db').save(plan.draft_id,'book_plan',payload)
    return payload


def _validated_saved_plan(saved):
    if saved.get('plan',{}).get('kind')=='Word Search':
        from .studio_chat_wordsearch import validate_saved_wordsearch_plan
        return validate_saved_wordsearch_plan(saved)
    if saved.get('plan',{}).get('kind','Sudoku')!='Sudoku':
        from .studio_chat_families import validate_saved_family_plan
        return validate_saved_family_plan(saved)
    from .studio_assistant import AssistantIntent
    raw=saved['plan']
    try:plan=TypographyChatBookPlan(**raw) if 'plan_schema_version' in raw else ChatBookPlan(**raw)
    except TypeError as exc:raise ValueError('Invalid creation plan fields.') from exc
    expected=sudoku_chat_plan(plan.request,AssistantIntent(action='create_book',kind='Sudoku',topic=plan.topic),draft_id=plan.draft_id)
    expected_data=asdict(expected)
    # A generated seed is preserved for reproducibility, but an explicitly
    # requested seed must match the original text exactly.
    if _numeric_request(plan.request)[2] is None:expected_data['seed']=plan.seed
    if asdict(plan)!=expected_data or type(plan.seed) is not int or not 1<=plan.seed<2**31:
        raise ValueError('Saved creation parameters do not match the original request.')
    return plan


def _plan_hash(plan):
    return hashlib.sha256(json.dumps(asdict(plan),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def confirm_creation_plan(root,plan,context=None):
    """Called only by the actual chat Create button for the displayed plan."""
    from .studio_recovery import StudioDraftStore
    store=StudioDraftStore(Path(root)/'data/books.db');draft=store.load(plan.draft_id)
    if not draft or 'chat_creation' not in draft['payload']:raise ValueError('The creation draft is missing.')
    payload=draft['payload'];saved=payload['chat_creation'];validated=_validated_saved_plan(saved)
    if asdict(validated)!=asdict(plan):raise ValueError('The displayed plan changed; submit the request again.')
    if saved.get('selected_context',{})!=dict(context or {}):
        raise ValueError('The selected project changed. Submit the creation request again before approving it.')
    saved.update(status='confirmed',confirmation={'source':'studio_chat.create_button','plan_sha256':_plan_hash(plan)})
    store.save(plan.draft_id,'book_plan',payload)


def _checkpoint(root,plan,status,**extra):
    from .studio_recovery import StudioDraftStore
    store=StudioDraftStore(Path(root)/'data/books.db');draft=store.load(plan.draft_id)
    if not draft:raise ValueError('The creation draft was not saved. Submit the request again.')
    payload=draft['payload'];payload['chat_creation'].update(status=status,**extra)
    store.save(plan.draft_id,'book_plan',payload,completed=False)


def _reserve_title(root,plan):
    from .database import PublishingDatabase
    from puzzle_book_studio import slug
    identity=hashlib.sha1(f'{plan.kind}|{plan.title}'.encode()).hexdigest()[:12]
    reservations=Path(root)/'data/chat_creation_reservations';reservations.mkdir(parents=True,exist_ok=True)
    lock=reservations/f'{identity}.json'
    if lock.exists():
        saved=json.loads(lock.read_text())
        if saved.get('draft_id')!=plan.draft_id:raise ValueError('That title already belongs to another creation draft. Choose a new title.')
        return
    if (Path(root)/'data/production_autopilot'/f'{identity}.json').exists():
        raise ValueError('That title already has production history. Choose a new title to preserve the existing book.')
    if any((Path(root)/'out').glob(slug(plan.title)+'_*')):
        raise ValueError('That title already has output files. Choose a new title.')
    database=PublishingDatabase(Path(root)/'data/books.db')
    if any(str(b.get('metadata',{}).get('title','')).casefold()==plan.title.casefold() for b in database.list_books()):
        raise ValueError('That title is already in your catalog. Choose a new title.')
    with lock.open('x',encoding='utf-8') as stream:json.dump({'draft_id':plan.draft_id,'title':plan.title},stream)


def _register_draft_owned_package(service,book_id,key,metadata,folder):
    """Recover registration-before-checkpoint without rewriting owner changes."""
    existing=service.db.get_book(book_id)
    if existing:
        if (existing.get('source_key')!=key or Path(existing.get('package_path','')).resolve()!=folder.resolve()
                or existing.get('metadata')!=metadata or existing.get('metadata_locked')
                or any(status!='Not Prepared' for status in existing.get('statuses',{}).values())):
            raise ValueError('Existing catalog identity changed or belongs to another plan; preserving owner data.')
        return  # Exact draft-owned identity: read-only adoption, no upsert.
    if any(str(row.get('metadata',{}).get('title','')).casefold()==str(metadata.get('title','')).casefold() for row in service.db.list_books()):
        raise ValueError('Another catalog book now owns that title; preserving both packages for review.')
    service.db.upsert_book(book_id,key,metadata,str(folder))


def _wordsearch_package_facts(root,plan,folder,manifest):
    """Adapt the legacy manifest using its exact frozen source, never guesses."""
    from .studio_chat_wordsearch import _owned_paths
    from .package_layout import package_file
    source,expected_folder,_settings=_owned_paths(root,plan)
    raw=plan.checked_theme_json.encode('utf-8')
    if folder!=expected_folder.resolve() or source.read_bytes()!=raw:
        raise ValueError('Word Search output/source does not match its exact owned draft.')
    if (Path(str(manifest.get('source_theme') or '')).resolve()!=source.resolve()
            or manifest.get('source_theme_sha256')!=hashlib.sha256(raw).hexdigest()
            or manifest.get('cover_art_sha256')!=plan.art_sha256):
        raise ValueError('Word Search source/artwork fingerprints do not match the confirmed plan.')
    data=json.loads(raw)
    if data.get('detected_topic')!=plan.topic or data.get('source_word_bank',{}).get('seed')!=plan.seed:
        raise ValueError('Word Search topic/seed provenance does not match the request.')
    record=package_file(folder,'interior.pdf').with_suffix('.puzzles.json')
    puzzles=json.loads(record.read_text(encoding='utf-8-sig')).get('puzzles',[])
    groups=data.get('puzzles',[])
    if len(puzzles)!=plan.count or len(groups)!=plan.count or any(
            puzzle.get('type')!='word_search' or set(puzzle.get('words',[]))!=set(group['words'])
            for puzzle,group in zip(puzzles,groups)):
        raise ValueError('Generated Word Search target words differ from the confirmed checked groups.')
    # Legacy Word Search source records omit these fields. They are derived
    # only after the exact source bytes and generated targets are verified.
    return {**manifest,'theme':data['detected_topic'],'puzzle_seed':data['source_word_bank']['seed']}


def _check_build_stop(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise ValueError('Production stopped at a safe boundary. Generated files and the recovery draft are preserved; resume explicitly to continue.')


def create_chat_book(root,draft_id,cancel=None,*,progress=None,stop_event=None):
    """One worker at a time; dismissal never destroys a running package."""
    root=Path(root).resolve()
    _check_build_stop(stop_event)
    if cancel and cancel.is_set():raise ValueError('Creation cancelled before generation.')
    if not _BUILD_LOCK.acquire(blocking=False):raise ValueError('Another chat book is still being built. Wait for it to finish; its files are preserved.')
    plan=None
    try:
        from .studio_recovery import StudioDraftStore
        draft=StudioDraftStore(root/'data/books.db').load(draft_id)
        if not draft or 'chat_creation' not in draft['payload']:raise ValueError('No saved chat creation plan was found.')
        saved=draft['payload']['chat_creation']
        plan=SimpleNamespace(draft_id=draft_id)  # Preserve failure checkpointing before subtype validation.
        plan=_validated_saved_plan(saved)
        confirmation=saved.get('confirmation',{})
        if confirmation.get('source')!='studio_chat.create_button' or confirmation.get('plan_sha256')!=_plan_hash(plan):
            raise ValueError('The exact creation plan has not been confirmed with Create this book.')
        if saved.get('status')=='complete':return saved['result']
        import puzzle_book_studio as studio
        if root!=studio.APP.resolve():raise ValueError('The production project does not match the active studio.')
        _reserve_title(root,plan)
        _checkpoint(root,plan,'running')
        _report_progress(progress,'Preparing the confirmed '+plan.kind+' book…')
        _check_build_stop(stop_event)
        approval={'source':'studio_chat.operator_confirmation','evidence_id':confirmation['plan_sha256'][:20]}
        if plan.kind=='Word Search':
            from .studio_chat_wordsearch import build_wordsearch_chat_plan
            folder=Path(build_wordsearch_chat_plan(root,plan,cancel,progress=progress,stop_event=stop_event)).resolve()
        else:
            _report_progress(progress,'Generating puzzles, solutions and package files…')
            folder=Path(studio.create_package(plan.kind,plan.title,plan.subtitle,plan.author,plan.count,plan.difficulty,plan.seed,
                        theme=plan.topic,content_plan_approval=approval,force_rebuild=False,sync_catalog=False,**({} if plan.typography is None else {('sudoku_typography' if plan.kind=='Sudoku' else 'cryptogram_typography'):plan.typography}))).resolve()
        if not folder.is_relative_to(root/'out'):raise ValueError('Production returned a package outside the project output folder.')
        _check_build_stop(stop_event)
        from .package_layout import package_file,release_contract
        from pypdf import PdfReader
        from preflight import preflight
        from .product_qa import inspect_product
        manifest=json.loads(package_file(folder,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))
        if plan.kind=='Word Search':manifest=_wordsearch_package_facts(root,plan,folder,manifest)
        if any(manifest.get(key)!=value for key,value in {'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':plan.kind,'theme':plan.topic,'difficulty':plan.difficulty,'puzzle_count':plan.count,'puzzle_seed':plan.seed}.items()):
            raise ValueError('Generated package does not match the confirmed request.')
        if plan.kind in ('Sudoku','Cryptogram'):
            if plan.kind=='Sudoku':
                from .sudoku_typography import package_typography,verify_typography_binding
            else:
                from .cryptogram_typography import package_typography,verify_typography_binding
            config=package_typography(plan.kind,plan.typography)
            config_key='sudoku_typography' if plan.kind=='Sudoku' else 'cryptogram_typography'
            if manifest.get(config_key)!=(config.to_dict() if config else None):
                raise ValueError('Generated typography does not match the confirmed creation plan.')
            if config:verify_typography_binding(package_file(folder,'interior.pdf'),config)
        pages=len(PdfReader(package_file(folder,'interior.pdf')).pages)
        if plan.requested_pages is not None and pages!=plan.requested_pages:
            raise ValueError(f'Requested {plan.requested_pages} pages but production produced {pages}; package preserved for review, not registered.')
        _report_progress(progress,'Running local preflight and puzzle QA…')
        ok,notes=preflight(folder);qa=inspect_product(root,folder,{**manifest,'require_puzzle_manifest':True})
        if not ok or qa.blockers or not release_contract(folder)['ready']:
            raise ValueError('Generated package has local production/QA blockers. Its files and recoverable draft are preserved.')
        if plan.kind in ('Sudoku','Cryptogram') and plan.typography is not None:
            current_source=json.loads(package_file(folder,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))
            if current_source!=manifest:raise ValueError('Generated typography source changed during QA; registration held.')
            if config:verify_typography_binding(package_file(folder,'interior.pdf'),config)
        # Register only this new package; never rescan/rewrite existing catalog rows.
        from .manager import PublishingService
        from .metadata_service import build_metadata
        service=PublishingService(root);key='package:'+str(folder);book_id=service._id(key)
        meta=build_metadata({'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':plan.kind,
                            'detected_topic':plan.topic,'puzzle_count':plan.count,'difficulty_label':plan.difficulty})
        meta.update(book_id=book_id,trim_size='8.5x11',page_count=pages,files=service._package_files(folder),
                    production_status='Needs owner and platform review',puzzle_seed=plan.seed,
                    studio_chat_creation={'draft_id':plan.draft_id,'plan_sha256':_plan_hash(plan)})
        _report_progress(progress,'Registering the locally checked draft and saving recovery state…')
        _check_build_stop(stop_event)
        _register_draft_owned_package(service,book_id,key,meta,folder)
        result={'book_id':book_id,'title':plan.title,'topic':plan.topic,'kind':plan.kind,'folder':str(folder),'pages':pages,
                'puzzles':plan.count,'preflight':True,'qa':qa.to_dict(),'readiness':'READY WITH LIMITATIONS','draft_id':plan.draft_id}
        _checkpoint(root,plan,'complete',result=result)
        return result
    except Exception as exc:
        if plan:
            try:_checkpoint(root,plan,'failed',error=str(exc))
            except Exception:pass
        raise
    finally:_BUILD_LOCK.release()
