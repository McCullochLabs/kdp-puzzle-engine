"""Family plans exercise the existing transaction with a mocked package backend."""
from dataclasses import asdict, replace
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from publishing.studio_assistant import AssistantIntent, guide_request
from publishing.studio_chat_families import (
    SUPPORTED_KINDS, StudioChatBookPlan, check_family_content, family_plan_text,
    studio_family_chat_plan, validate_saved_family_plan,
)


@pytest.fixture(autouse=True)
def ready_checked_library(monkeypatch):
    import puzzle_book_studio as studio
    monkeypatch.setattr(studio, 'content_check', lambda kind, topic: (True, 'reviewed fixture', 240))


def plan(text='Create a 24-puzzle Cryptogram book with seed 42', **kwargs):
    return studio_family_chat_plan(text, guide_request(text), **kwargs)


@pytest.mark.parametrize('kind', SUPPORTED_KINDS)
def test_exact_family_defaults_and_truthful_summary(kind):
    import puzzle_book_studio as studio
    p = plan(f'Create a {kind} book')
    assert p.count == studio.DEFAULTS[kind][2] == 60
    assert p.difficulty == studio.DEFAULTS[kind][3]
    assert p.topic == 'General Starter' and p.kind == kind
    assert p.request == f'Create a {kind} book'
    assert 'Sudoku' not in p.subtitle if kind != 'Mixed Brain Games' else 'Sudoku' in p.subtitle
    text = family_plan_text(p)
    assert 'Actual page count is measured' in text and 'nothing is published' in text
    assert 'not difficulty-rated' in text.casefold()
    if kind == 'Mixed Brain Games':
        assert '20 Sudoku, 20 Cryptograms and 20 word scrambles' in text
        assert 'Sudoku: Mixed' in text
    else:
        assert 'Difficulty: Standard' not in text


@pytest.mark.parametrize('kind', SUPPORTED_KINDS)
def test_exact_supported_themes_and_requested_seed(kind):
    import puzzle_book_studio as studio
    for topic in studio.AVAILABLE_THEMES:
        p = plan(f'Create a 24-puzzle {kind} book about {topic} with seed 75')
        assert p.topic == topic and p.seed == 75


@pytest.mark.parametrize('text,topic', [
    ('Create a Space Cryptogram book', 'Space & Astronomy'),
    ('Create Garden Word Scrambles book', 'Garden & Growing'),
    ('Create a Cryptogram book about history', 'History & Heritage'),
    ('Create a hard 61-puzzle Mixed Brain Games book with seed 7', 'General Starter'),
])
def test_literal_aliases_and_mixed_section_counts(text, topic):
    p = plan(text)
    assert p.topic == topic
    if p.kind == 'Mixed Brain Games':
        assert p.difficulty == 'Hard'
        assert '21 Sudoku, 20 Cryptograms and 20 word scrambles' in family_plan_text(p)


@pytest.mark.parametrize('text', [
    'Create a 23-puzzle Cryptogram book', 'Create a 151-puzzle Cryptogram book',
    'Create a -24-puzzle Cryptogram book', 'Create a +24-puzzle Cryptogram book',
    'Create a 24.5-puzzle Cryptogram book', 'Create a 2e2-puzzle Cryptogram book',
    'Create twenty-four puzzles in a Cryptogram book',
    'Create a 24-puzzle 60-puzzle Cryptogram book',
    'Create a 100-page Cryptogram book', 'Create a 52-page Mixed Brain Games book',
    'Create an easy Cryptogram book', 'Create a hard Word Scramble + Trivia book',
    'Create a standard difficulty Cryptogram book', 'Create a medium Mixed Brain Games book',
    'Create an easy hard Mixed Brain Games book',
    'Create a Mixed Brain Games book with hard cryptograms',
    'Create a Cryptogram book about llamas', 'Create a llamas Word Scrambles book',
    'Create a large-print Cryptogram book', 'Create a Cryptogram book for kids',
    'Create a 6x9 Cryptogram book', 'Create a Cryptogram book by Jane Doe',
    'Create a Cryptogram book with a blue cover', 'Create a Cryptogram book without answers',
    'Create a Cryptogram book with bonus pages', 'Create a Signature Edition Cryptogram book',
    'Create a Word Scramble + Trivia book with a separate trivia quiz',
    'Create a Cryptogram and Word Scramble book', 'Create a trivia quiz book',
    'Do not create a Cryptogram book', 'Publish a Cryptogram book',
    'Create a Cryptogram book with seed -42', 'Create a Cryptogram book with seed 4.5',
    'Create a Cryptogram book with seed 0', 'Create a Cryptogram book with seed 2147483648',
    'Create a Cryptogram book with seed 4 and seed 5',
    'Create a Cryptogram book called NoQuotes', 'Create a Cryptogram book called "One" titled "Two"',
    'Create 24 Cryptogram books',
    'Create a Cryptogram book in French', 'Create a Cryptogram book with cartoon illustrations',
    'Create a Cryptogram book with no answers', 'Create a Cryptogram book excluding solutions',
    'Create a Cryptogram book without fact clues', 'Create a Cryptogram book as CSV',
    'Create a Cryptogram book using modified logic',
])
def test_unsupported_or_ambiguous_requests_are_rejected(text):
    with pytest.raises(ValueError):
        plan(text)


def test_provider_guesses_do_not_override_actual_kind_or_topic():
    guessed = AssistantIntent(action='create_book', kind='Cryptogram', topic='Space')
    with pytest.raises(ValueError):
        studio_family_chat_plan('Create a Word Scramble + Trivia book', guessed)
    with pytest.raises(ValueError, match='llamas'):
        studio_family_chat_plan('Create a Cryptogram book about llamas', guessed)
    assert studio_family_chat_plan('Create a Cryptogram book', guessed).topic == 'General Starter'


def test_quoted_title_is_data_and_number_settings_inside_it_do_not_change_plan():
    p = plan('Create a Cryptogram book called "Hard 99-puzzle Covers by Example" with seed 42')
    assert p.title == 'Hard 99-puzzle Covers by Example' and p.count == 60
    assert p.difficulty == 'Standard' and p.seed == 42
    assert plan('Create a Cryptogram book called "Called to Adventure"').title == 'Called to Adventure'
    assert len(asdict(p)) == len(asdict(__import__('publishing.studio_chat_creation', fromlist=['ChatBookPlan']).ChatBookPlan(
        p.draft_id,p.request,p.title,p.topic,p.count,p.difficulty,p.seed)))


def test_content_gate_preserves_guided_safety_buffer_and_rechecks(monkeypatch):
    import puzzle_book_studio as studio
    calls = []
    monkeypatch.setattr(studio, 'content_check', lambda kind, topic: (True, 'only 129 reviewed', 129))
    with pytest.raises(ValueError, match='130 reviewed entries'):
        plan()
    monkeypatch.setattr(studio, 'content_check', lambda kind, topic: (False, 'duplicate source', 240))
    with pytest.raises(ValueError, match='duplicate source'):
        plan()
    monkeypatch.setattr(studio, 'content_check', lambda kind, topic: (True, 'ready', 240))
    p = plan()
    monkeypatch.setattr(studio, 'content_check', lambda kind, topic: (True, 'library changed', 0))
    with pytest.raises(ValueError, match='library changed'):
        validate_saved_family_plan({'plan':asdict(p)})


@pytest.mark.parametrize('field,value', [
    ('count', 25), ('count',24.0), ('difficulty','Hard'), ('topic','Space & Astronomy'),
    ('author','Somebody Else'), ('seed',43), ('seed',True), ('requested_pages',100),
    ('kind','Sudoku'), ('title','Different title'), ('draft_id','not-a-draft-id'),
])
def test_saved_plan_tampering_cannot_reach_the_backend(field,value):
    data = asdict(plan());data[field] = value
    with pytest.raises(ValueError):
        validate_saved_family_plan({'plan':data})


def test_implicit_random_seed_survives_recovery_but_explicit_seed_is_bound():
    p = plan('Create a Cryptogram book')
    assert validate_saved_family_plan({'plan':asdict(p)}) == p
    assert validate_saved_family_plan({'plan':asdict(plan())}).seed == 42
    with pytest.raises(ValueError, match='incomplete or unsupported'):
        validate_saved_family_plan({'plan':dict(asdict(p),shell='not allowed')})


@pytest.fixture
def shared_worker(tmp_path,monkeypatch):
    import puzzle_book_studio as studio
    import publishing.studio_chat_creation as creation
    from publishing.package_layout import initialize_package_layout, package_file
    monkeypatch.setattr(studio,'APP',tmp_path)
    monkeypatch.setattr('pypdf.PdfReader',lambda path:SimpleNamespace(pages=[None]*24))
    monkeypatch.setattr('preflight.preflight',lambda package:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda package:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**kw:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    calls=[]
    def fixture_package(*args,**kwargs):
        calls.append((args,kwargs))
        folder=tmp_path/'out'/f'fixture_{len(calls)}'
        initialize_package_layout(folder)
        package_file(folder,'interior.pdf',for_write=True).write_bytes(b'%PDF fixture: reader is mocked')
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(dict(
            zip(('puzzle_type','title','subtitle','author','puzzle_count','difficulty','puzzle_seed'),args[:7]),theme=kwargs['theme'])))
        return folder
    monkeypatch.setattr(studio,'create_package',fixture_package)
    return SimpleNamespace(root=tmp_path,creation=creation,studio=studio,calls=calls,package_file=package_file)


@pytest.mark.parametrize('kind',SUPPORTED_KINDS)
def test_shared_transaction_requires_exact_confirmation_and_creates_requested_family(shared_worker,kind):
    x=shared_worker;p=plan(f'Create a 24-puzzle {kind} book with seed 42')
    x.creation.save_creation_plan(x.root,p,{'book_id':'old'})
    with pytest.raises(ValueError,match='not been confirmed'):
        x.creation.create_chat_book(x.root,p.draft_id)
    assert not x.calls
    with pytest.raises(ValueError,match='selected project changed'):
        x.creation.confirm_creation_plan(x.root,p,{'book_id':'new'})
    x.creation.confirm_creation_plan(x.root,p,{'book_id':'old'})
    result=x.creation.create_chat_book(x.root,p.draft_id)
    assert result['kind']==kind and result['puzzles']==24 and result['pages']==24
    args,kwargs=x.calls[0]
    assert args[:7]==(kind,p.title,p.subtitle,p.author,24,p.difficulty,42)
    assert kwargs['theme']=='General Starter' and kwargs['force_rebuild'] is False and kwargs['sync_catalog'] is False
    assert kwargs['content_plan_approval']['source']=='studio_chat.operator_confirmation'
    assert x.creation.create_chat_book(x.root,p.draft_id)==result and len(x.calls)==1


def test_shared_cancellation_and_lock_never_start_a_new_family_backend(shared_worker):
    x=shared_worker;p=plan();x.creation.save_creation_plan(x.root,p);x.creation.confirm_creation_plan(x.root,p)
    event=threading.Event();event.set()
    with pytest.raises(ValueError,match='cancelled before'):
        x.creation.create_chat_book(x.root,p.draft_id,event)
    assert x.creation._BUILD_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ValueError,match='still being built'):
            x.creation.create_chat_book(x.root,p.draft_id)
    finally:x.creation._BUILD_LOCK.release()
    assert not x.calls


def test_backend_manifest_drift_or_external_output_is_not_registered(shared_worker,monkeypatch):
    x=shared_worker;p=plan();x.creation.save_creation_plan(x.root,p);x.creation.confirm_creation_plan(x.root,p)
    original=x.studio.create_package
    def drift(*args,**kwargs):
        folder=original(*args,**kwargs)
        path=x.package_file(folder,'PACKAGE_SOURCE_RECORD.json')
        data=json.loads(path.read_text());data['puzzle_type']='Sudoku';path.write_text(json.dumps(data))
        return folder
    monkeypatch.setattr(x.studio,'create_package',drift)
    with pytest.raises(ValueError,match='does not match'):
        x.creation.create_chat_book(x.root,p.draft_id)
    from publishing.database import PublishingDatabase
    from publishing.studio_recovery import StudioDraftStore
    assert PublishingDatabase(x.root/'data/books.db').list_books()==[]
    assert StudioDraftStore(x.root/'data/books.db').load(p.draft_id)['payload']['chat_creation']['status']=='failed'
    assert (x.root/'out/fixture_1').is_dir()
    monkeypatch.setattr(x.studio,'create_package',lambda *a,**k:x.root/'outside-output')
    with pytest.raises(ValueError,match='outside the project output'):
        x.creation.create_chat_book(x.root,p.draft_id)
    assert PublishingDatabase(x.root/'data/books.db').list_books()==[]


def test_content_change_after_confirmation_blocks_generation(shared_worker,monkeypatch):
    x=shared_worker;p=plan();x.creation.save_creation_plan(x.root,p);x.creation.confirm_creation_plan(x.root,p)
    monkeypatch.setattr(x.studio,'content_check',lambda kind,topic:(False,'source review revoked',0))
    with pytest.raises(ValueError,match='source review revoked'):
        x.creation.create_chat_book(x.root,p.draft_id)
    assert not x.calls
