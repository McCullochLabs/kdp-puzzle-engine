"""Confirmed Word Search plans over the existing checked-group and production route."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import secrets
import uuid

from .studio_chat_creation import ChatBookPlan, _numeric_request, _report_progress, _check_build_stop
from .studio_chat_families import _request_without_title
from background_generation.index import BackgroundAssetIndex


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class WordSearchChatPlan(ChatBookPlan):
    kind: str = 'Word Search'
    checked_theme_json: str = ''
    source_sha256_json: str = ''
    art_path: str = ''
    art_sha256: str = ''
    art_approval_json: str = ''
    settings_json: str = ''

    @property
    def subtitle(self):
        return f'{self.count} Themed Word Search Puzzles with Complete Solutions'


def _root(root=None):
    import word_search_creator as studio
    actual=studio.APP_DIR.resolve()
    selected=actual if root is None else Path(root).resolve()
    if selected != actual:
        raise ValueError('The Word Search project does not match the active studio.')
    return selected


def _sources(root):
    names=('Guided_Builder_Master_Word_Bank.json','word_intelligence/word_store.json',
           'editorial_wordsearch_topic_overlay.json','family_group_content_reviews.json')
    result={}
    for name in names:
        path=root/'word_banks'/name
        result[name]=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if not result[names[0]] or not result[names[1]]:
        raise ValueError('The checked Word Search library is unavailable; inspect it in the guided planner.')
    return _json(result)


class _ReadOnlyAssetIndex(BackgroundAssetIndex):
    """Select only already-reviewed assets; never migrate global approvals."""
    def ensure_provenance_audited(self):
        return

    def ledger_details(self, path):
        allowed, _reason, row = self.eligibility(path)
        return row if allowed else None


def _select_art(data):
    from background_generation.routing import request_from_mapping, select_cover_asset
    haystack = ' '.join(str(data.get(key) or '') for key in ('title','subtitle','detected_topic','series')).casefold()
    stable_number = sum(ord(character) for character in haystack) or 1
    request = request_from_mapping(str(data.get('_creation_route') or 'Word Search'), data,
        theme_path=str(data.get('_theme_path') or ''), selection_seed=stable_number)
    decision = select_cover_asset(request, index=_ReadOnlyAssetIndex())
    return {**decision.asset, 'routing_diagnostics': decision.diagnostics()} if decision.asset else None


def _approval(root, path):
    path=Path(path).resolve()
    if not path.is_relative_to(root/'cover_assets') or not path.is_file():
        raise ValueError('Choose approved local artwork from this project.')
    index=_ReadOnlyAssetIndex()
    record=index.ledger_details(path)
    if not record or not index.production_selectable(record):
        raise ValueError('Approved matching cover artwork is required.')
    fields=('asset_id','sha256','approval_revision','approval_state','production_approved',
            'classification','project_generated','rights_verified','source_type','provenance','retired')
    return str(path),hashlib.sha256(path.read_bytes()).hexdigest(),_json({k:record.get(k) for k in fields})


def needs_guided_wordsearch(request):
    """Keep established reader/design/page review for non-direct settings."""
    clean,_title=_request_without_title(request)
    try:
        _counts,pages,_seed=_numeric_request(clean)
    except ValueError:
        return False  # The direct parser will reject malformed quantities.
    return bool(pages or re.search(r'\b(?:signature|large[ -]print|seniors?|kids?|children|teens?|ages?|beginners?|font|bleed|hardcover|paperback|landscape|portrait|trim|easy|hard|relaxing|challenging|difficulty|medium|expert|intermediate|covers?|colou?rs?|author)\b|\b\d+\s*[x×]\s*\d+',clean,re.I))


def wordsearch_chat_plan(request, intent, root=None, *, draft_id=None, _seed=None, _pinned_art=None):
    import word_search_creator as studio
    from .studio_assistant import guide_request, requested_book_topic
    from word_intelligence.pipeline import prepare_family_wordsearch
    root=_root(root)
    if not isinstance(request,str) or not request.strip() or len(request)>1000 or any(ord(c)<32 for c in request):
        raise ValueError('Use one printable book request of 1 to 1000 characters.')
    if getattr(intent,'action',None)!='create_book' or getattr(intent,'kind',None)!='Word Search':
        raise ValueError('State a new Word Search book request explicitly.')
    clean,named=_request_without_title(request)
    explicit=guide_request(clean)
    if explicit.action!='create_book' or explicit.kind!='Word Search' or not re.search(r'\bword[ -]+search\b',clean,re.I):
        raise ValueError('State a new Word Search book request explicitly.')
    if re.search(r'\b(?:sudoku|cryptograms?|scrambles?|trivia|mixed|hybrid|signature|large[ -]print|seniors?|kids?|children|teens?|ages?|beginners?|font|bleed|hardcover|paperback|landscape|portrait|trim|easy|hard|relaxing|challenging|difficulty|medium|expert|intermediate|covers?|colou?rs?|author|by|only|bonus(?:es)?|interior\s+style|title\s+page|without|omit|exclude|answerless)\b|\b\d+\s*[x×]\s*\d+',clean,re.I):
        raise ValueError('Direct Word Search creation supports standard readers/layout with complete answers and automatic approved art. Reader, font, difficulty, edition, custom art and hybrid variants need their guided plan.')
    counts,pages,requested_seed=_numeric_request(clean)
    if pages:
        raise ValueError('Exact Word Search page targets are not enforced; request a puzzle count.')
    if len(set(counts))>1:
        raise ValueError('Specify one puzzle count.')
    count=int(counts[0]) if counts else 48
    if not 48<=count<=96 or count%12:
        raise ValueError('Standard Word Search production supports 48 to 96 puzzles in multiples of 12.')
    draft_id=draft_id or uuid.uuid4().hex
    if not re.fullmatch('[0-9a-f]{32}',draft_id):
        raise ValueError('Invalid creation draft identity.')
    seed=requested_seed if requested_seed is not None else (_seed if _seed is not None else secrets.randbelow(2**31-1)+1)
    if type(seed) is not int or not 1<=seed<2**31:
        raise ValueError('Seed must be from 1 to 2147483647.')
    topic_request=re.sub(r'\b(?:with\s+)?seed\b(?:\s*[:=]\s*|\s+)\S+', '', clean, flags=re.I)
    topic_request=re.sub(r'\b(?:with\s+)?\d+[ -]*puzzles?\b', '', topic_request, flags=re.I)
    if re.search(r'\d', topic_request):
        raise ValueError('Write settings as an unsigned puzzle count or seed.')
    raw_topic=requested_book_topic(topic_request).strip()
    if not raw_topic:
        raise ValueError('Name an existing checked Word Search topic explicitly.')
    # Topic-after-book syntax can otherwise absorb unknown settings into the
    # topic. Reject such clauses, rather than silently narrowing the request.
    if re.search(r'\bbooks?\s+(?:about|on|themed around)\b', topic_request, re.I) and re.search(r'\s+(?:with|in|as|using|without)\s+', raw_topic, re.I):
        raise ValueError('Unsupported language, output, artwork or generation clauses; request one literal checked topic.')
    residue=re.sub(r'\bword[ -]+search\b', ' ', topic_request, flags=re.I)
    residue=re.sub(r'\b'+r'\s+'.join(map(re.escape,raw_topic.split()))+r'\b',' ',residue,flags=re.I)
    residue=re.sub(r'\b(?:create|make|build|want|new|can|could|would|you|i|me|please|a|an|the|book|books|puzzle|puzzles|with|and|about|on|themed|around|standard|complete|full|answers|solutions)\b',' ',residue,flags=re.I)
    if re.search(r'[^\s.,!?\"“”\'’&+\-]',residue):
        raise ValueError('The request contains unsupported settings; use a literal checked topic, count, seed and optional quoted title.')
    before=_sources(root)
    selected=prepare_family_wordsearch(root,raw_topic,count,12,seed,
        minimum_puzzles=24,max_word_length=20,source_groups=(),reader='standard',balance='Balanced')
    if _sources(root)!=before:
        raise ValueError('Checked library changed while preparing; submit the request again.')
    groups=selected['groups']
    if len(groups)!=count:
        raise ValueError(f'The checked library supports {len(groups)} puzzles for this request, rather than {count}. Choose that supported count explicitly if it meets production minimums.')
    words=[word for group in groups for word in group.get('words',[])]
    if any(len(group.get('words',[]))!=12 for group in groups) or len(words)!=len(set(words)) or any(not re.fullmatch('[A-Z]{2,20}',str(w)) for w in words):
        raise ValueError('Checked groups must contain 12 unique suitable words per puzzle with no repeated word in the book.')
    topic=selected['topic']
    title=named or f'{topic} Word Search - {draft_id[:8]}'
    subtitle=f'{count} Themed Word Search Puzzles with Complete Solutions'
    recommendation=studio.recommend_theme_from_words(groups,topic)
    data={'title':title,'subtitle':subtitle,'author':'Jordan M. Slade','audience':'Standard readers',
        'detected_topic':topic,'palette':recommendation['palette'],'cover_style':'photo',
        'recommended_palette':recommendation['palette'],'recommended_cover_style':'photo',
        'difficulty_label':studio.puzzle_difficulty_label({'puzzles':groups}),
        'no_repeat_words':True,'cover_badge':'NO REPEATED WORDS','puzzles':groups,
        'reader_profile':'standard','theme_balance':'Balanced',
        'source_word_bank':{'topics':selected['source_topics'],'selection':'filtered_topic_pool','seed':seed},
        '_chat_creation_draft_id':draft_id,'_creation_route':'Word Search'}
    if _pinned_art is not None:
        record=_ReadOnlyAssetIndex().ledger_details(Path(_pinned_art))
        if not record:
            raise ValueError('The confirmed cover asset is no longer eligible; review a fresh plan.')
        choice={**record,'file':_pinned_art}
    else:
        choice=_select_art(data)
    if not choice:
        raise ValueError('No approved matching Word Search cover art is available.')
    art,art_sha,approval=_approval(root,root/str(choice.get('file') or choice.get('path') or ''))
    data['palette']=studio.photo_choice_palette(choice,recommendation['palette'])
    source=root/'data/studio_wordsearch_drafts'/draft_id/'theme.json'
    settings={'title':title,'subtitle':subtitle,'author':'Jordan M. Slade','imprint':'Jordan M. Slade',
        'badge':'NO REPEATED WORDS','puzzle_count':count,'difficulty':data['difficulty_label'],
        'format_label':'WORD SEARCH','palette':data['palette'],'style':'photo','theme':str(source),
        'art':art,'art_focus':str(choice.get('focus') or 'center'),'signature_edition':False,'archive_after_package':False}
    return WordSearchChatPlan(draft_id,request,title,topic,count,data['difficulty_label'],seed,
        checked_theme_json=_json(data),source_sha256_json=before,art_path=art,art_sha256=art_sha,
        art_approval_json=approval,settings_json=_json(settings))


def _durably_confirmed(root,saved,plan):
    """Only the existing persisted UI confirmation may pin a chosen asset."""
    from contextlib import closing
    import sqlite3
    from .studio_chat_creation import _plan_hash
    confirmation={'source':'studio_chat.create_button','plan_sha256':_plan_hash(plan)}
    if saved.get('confirmation')!=confirmation:
        return False
    catalog=root/'data/books.db'
    if not catalog.is_file():
        return False
    with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_drafts'").fetchone():
            return False
        row=db.execute('SELECT v.payload FROM studio_drafts d JOIN studio_draft_versions v USING(draft_id,revision) WHERE d.draft_id=?',(plan.draft_id,)).fetchone()
    actual=json.loads(row[0]).get('chat_creation',{}) if row else {}
    return (actual.get('confirmation')==confirmation and actual.get('plan')==asdict(plan)
        and actual.get('status') in ('confirmed','running','failed','complete'))


def validate_saved_wordsearch_plan(saved,root=None):
    from .studio_assistant import AssistantIntent
    plan=WordSearchChatPlan(**saved['plan'])
    root=_root(root)
    pinned=plan.art_path if _durably_confirmed(root,saved,plan) else None
    expected=wordsearch_chat_plan(plan.request,AssistantIntent(action='create_book',kind='Word Search'),
        root,draft_id=plan.draft_id,_seed=plan.seed,_pinned_art=pinned)
    if asdict(expected)!=asdict(plan):
        raise ValueError('Word Search plan, checked sources, settings or approved art changed; review a fresh plan.')
    return plan


def wordsearch_plan_text(plan):
    return (f'Create {plan.title!r}: exactly {plan.count} Word Search puzzles, 12 checked words per puzzle, '
        f'{plan.topic}, standard readers and 8.5 x 11 layout. Words are not repeated. '
        f'Author: {plan.author}. Actual pages depend on the existing layout; no exact page target is promised. '
        'The shown checked groups and approved artwork are frozen. Create this book approves this exact plan; nothing is published.')


class _PipelineFacade:
    def __init__(self, progress=None, stop_event=None):
        self.stop_event=stop_event
        self.progress=progress
        self.status=self
        self.completion=None
    def set(self,message):
        _check_build_stop(self.stop_event)
        _report_progress(self.progress,message)
    def after(self,delay,callback,*args):callback(*args)
    def _write_proof_bundle(self,*args):
        import word_search_creator as studio
        studio.WordSearchCreator._write_proof_bundle(*args)
    def _studio_package_finished(self,success,target,message):
        self.completion=(success,target,message)


def _owned_paths(root,plan):
    source=root/'data/studio_wordsearch_drafts'/plan.draft_id/'theme.json'
    folder=root/'out/studio_wordsearch_drafts'/plan.draft_id
    for path in (source.parent,folder):
        current=path
        while current!=root:
            if current.is_symlink() or current.is_junction():
                raise ValueError('Chat draft paths cannot contain links or junctions.')
            current=current.parent
        if not path.resolve().is_relative_to(root):
            raise ValueError('Chat draft path escaped this project.')
    settings=json.loads(plan.settings_json)
    if Path(settings['theme'])!=source or settings['archive_after_package'] is not False or settings['signature_edition'] is not False:
        raise ValueError('Word Search settings do not match their owned theme path.')
    return source,folder,settings


def build_wordsearch_chat_plan(root,plan,cancel=None,*,progress=None,stop_event=None):
    import word_search_creator as studio
    from publishing.job_queue import ProductionJobQueue
    root=_root(root)
    # Reuse the shared exact-plan approval record; this is not a second gate
    # that can grant approval independently of the existing Create button.
    from .studio_recovery import StudioDraftStore
    from .studio_chat_creation import _plan_hash
    draft=StudioDraftStore(root/'data/books.db').load(plan.draft_id)
    saved=draft['payload'].get('chat_creation',{}) if draft else {}
    if saved.get('plan')!=asdict(plan) or saved.get('confirmation')!={'source':'studio_chat.create_button','plan_sha256':_plan_hash(plan)}:
        raise ValueError('The exact Word Search plan must be confirmed with Create this book.')
    validate_saved_wordsearch_plan(saved,root)
    source,folder,settings=_owned_paths(root,plan)
    if cancel and cancel.is_set():
        raise ValueError('Creation cancelled before generation.')
    raw=plan.checked_theme_json.encode('utf-8')
    source.parent.mkdir(parents=True,exist_ok=True)
    if source.exists():
        if source.read_bytes()!=raw:
            raise ValueError('The owned checked theme changed; preserving it.')
    else:
        with source.open('xb') as stream:stream.write(raw)
    autopilot,facts=studio.WordSearchCreator._begin_wordsearch_autopilot(settings,plan.seed)
    errors,warnings,notes=studio.prepare_wordsearch_production_gate(source,plan.seed,settings)
    if errors:
        autopilot.fail('validate',' | '.join(errors),human_review=True)
        raise ValueError('Word Search production gate stopped this plan: '+' | '.join(errors))
    autopilot.complete('validate',autopilot.stage_fingerprint(facts,'validate'),
        'Capacity, title, safety, and source checks passed before generation.')
    autopilot.attach_orchestrator({**facts,**settings,'book_plan_id':plan.draft_id,'source_revision':facts.get('fingerprint','')})
    queue=ProductionJobQueue(root)
    acquired,note=queue.acquire(plan.draft_id,plan.title)
    if not acquired:
        raise ValueError(note)
    facade=_PipelineFacade(progress,stop_event)
    try:
        if cancel and cancel.is_set():
            raise ValueError('Creation cancelled before generation.')
        studio.WordSearchCreator._run_studio_package(facade,settings,plan.seed,folder,warnings,
            autopilot,facts,queue,plan.draft_id,sync_catalog=False)
        if not facade.completion or not facade.completion[0]:
            raise ValueError(facade.completion[2] if facade.completion else 'Production did not return a completed package.')
        target=Path(facade.completion[1]).resolve()
        if target!=folder.resolve():
            raise ValueError('Production returned a package outside this exact chat draft.')
        return target
    finally:
        queue.release(plan.draft_id,'complete' if facade.completion and facade.completion[0] else 'needs_attention')

