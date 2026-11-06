from dataclasses import asdict
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from publishing.studio_assistant import guide_request
from publishing.studio_chat_creation import sudoku_chat_plan,save_creation_plan,create_chat_book,_reserve_title
from publishing.studio_recovery import StudioDraftStore


def plan(text='Create an easy 24-puzzle Sudoku book',**kwargs):
    return sudoku_chat_plan(text,guide_request(text),**kwargs)


def test_original_request_and_exact_page_plan_preserved():
    p=plan('Create an easy 100-page Space Sudoku book with seed 42')
    assert p.count==48 and p.requested_pages==100 and p.seed==42 and p.difficulty=='Easy'
    assert p.topic=='Space & Astronomy' and p.request.startswith('Create an easy')
    assert plan().title!=plan().title


@pytest.mark.parametrize('utterance',[
    'Create a 99-page Sudoku book','Create a 24-puzzle 100-page Sudoku book',
    'Create a large-print Sudoku book for seniors','Create a 4-puzzle Sudoku book',
    'Create a medium Sudoku book','Create a Sudoku book about llamas',
    'Create a number-only Sudoku book','Create a Sudoku book called Unquoted',
    'Create a Sudoku book with a blue cover','Create a Sudoku book by Jane Doe',
    'Create a 6x9 Sudoku book',
])
def test_unsupported_or_conflicting_settings_fail_honestly(utterance):
    with pytest.raises(ValueError):plan(utterance)


def test_title_reservation_preserves_existing_production(tmp_path):
    p=plan('Create a 24-puzzle Sudoku book called "Existing Book"')
    identity=__import__('hashlib').sha1(f'Sudoku|{p.title}'.encode()).hexdigest()[:12]
    old=tmp_path/'data/production_autopilot'/f'{identity}.json';old.parent.mkdir(parents=True);old.write_text('{"preserve":true}')
    with pytest.raises(ValueError,match='production history'):_reserve_title(tmp_path,p)
    assert old.read_text()=='{"preserve":true}'


def test_saved_draft_has_unique_identity_request_and_context(tmp_path):
    p=plan();save_creation_plan(tmp_path,p,{'book_id':'previous'})
    saved=StudioDraftStore(tmp_path/'data/books.db').load(p.draft_id)['payload']['chat_creation']
    assert saved['plan']['request']==p.request and saved['selected_context']=={'book_id':'previous'}
    assert saved['status']=='planned'


def test_cancellation_prevents_generation(tmp_path):
    event=threading.Event();event.set()
    with pytest.raises(ValueError,match='cancelled before'):create_chat_book(tmp_path,'missing',event)


def test_altered_draft_is_rejected_before_generation(tmp_path):
    p=plan();payload=save_creation_plan(tmp_path,p);payload['chat_creation']['plan']['count']=150
    store=StudioDraftStore(tmp_path/'data/books.db');store.save(p.draft_id,'book_plan',payload)
    with pytest.raises(ValueError,match='original request'):create_chat_book(tmp_path,p.draft_id)
    assert store.load(p.draft_id)['payload']['chat_creation']['status']=='failed'


def test_guide_chat_confirms_plan_without_opening_guided_dialog(tmp_path,monkeypatch):
    import tkinter as tk
    import word_search_creator as studio
    monkeypatch.setattr(studio,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    try:app=studio.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    app.APP_DIR=tmp_path
    try:
        family=app.family_studio;family.provider='Guide';family.prompt.set('Create an easy 24-puzzle Sudoku book')
        family.send();app.update()
        assert family.proposal_button.cget('text')=='Create this book'
        assert family._chat_creation_plan.count==24
        assert not app._advanced_built
        called=[]
        def worker(root,draft_id,cancel,*,progress=None,stop_event=None):
            called.append(draft_id)
            return {'book_id':'new-book','title':'Created','topic':'General Starter','kind':'Sudoku','puzzles':24,'pages':52,
                    'folder':str(tmp_path/'out/new'),'qa':{'summary':{'blockers':0}}}
        monkeypatch.setattr('publishing.studio_chat_creation.create_chat_book',worker)
        family.proposal_button.invoke();deadline=time.monotonic()+5
        while family.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
        assert called and not family.busy and family.context['book_id']=='new-book'
        assert 'Created Created' in family.chat.get('1.0','end')
        assert not app._advanced_built
    finally:app.destroy()


def test_unconfirmed_saved_plan_never_generates(tmp_path):
    p=plan();save_creation_plan(tmp_path,p)
    with pytest.raises(ValueError,match='not been confirmed'):create_chat_book(tmp_path,p.draft_id)


def test_confirmation_binds_original_seed_and_context(tmp_path):
    from publishing.studio_chat_creation import confirm_creation_plan
    p=plan('Create an easy 24-puzzle Sudoku book with seed 42')
    save_creation_plan(tmp_path,p,{'book_id':'first'})
    with pytest.raises(ValueError,match='selected project changed'):confirm_creation_plan(tmp_path,p,{'book_id':'second'})
    confirm_creation_plan(tmp_path,p,{'book_id':'first'})
    store=StudioDraftStore(tmp_path/'data/books.db');confirmed=store.load(p.draft_id)['payload']
    assert confirmed['chat_creation']['confirmation']['source']=='studio_chat.create_button'
    confirmed['chat_creation']['plan']['seed']=43;store.save(p.draft_id,'book_plan',confirmed)
    with pytest.raises(ValueError,match='original request'):create_chat_book(tmp_path,p.draft_id)


def test_context_switch_blocks_actual_ui_create():
    from publishing.family_studio import FamilyStudio
    p=plan();messages=[]
    fake=SimpleNamespace(busy=False,_chat_creation_plan=p,_chat_creation_context={'book_id':'first'},
                         context={'book_id':'second'},app=SimpleNamespace(APP_DIR=Path('.')),
                         _say=lambda role,text:messages.append(text))
    FamilyStudio._create_confirmed_chat_book(fake)
    assert messages and 'selected project changed' in messages[0]


@pytest.mark.parametrize('utterance',[
    'Create a -24-puzzle Sudoku book','Create a +24-puzzle Sudoku book',
    'Create a 24.5-puzzle Sudoku book','Create a 52.5-page Sudoku book',
    'Create a Sudoku book with seed -5','Create a Sudoku book with seed +42',
    'Create a Sudoku book with seed 42.5','Create a Sudoku book with seed 4/5',
    'Create a Sudoku book with seed 4 and seed 5','Create a Sudoku book with seed 0',
])
def test_signed_decimal_or_ambiguous_numbers_fail(utterance):
    with pytest.raises(ValueError):plan(utterance)


def test_registration_checkpoint_failure_recovers_only_exact_draft(tmp_path,monkeypatch):
    import publishing.studio_chat_creation as creation
    import puzzle_book_studio as studio
    from publishing.package_layout import initialize_package_layout,package_file
    from publishing.database import PublishingDatabase
    from reportlab.pdfgen import canvas
    p=plan('Create an easy 24-puzzle Sudoku book with seed 42');save_creation_plan(tmp_path,p)
    creation.confirm_creation_plan(tmp_path,p)
    folder=tmp_path/'out/generated_fixture';initialize_package_layout(folder)
    target=package_file(folder,'interior.pdf',for_write=True);c=canvas.Canvas(str(target))
    for _ in range(52):c.drawString(80,600,'Recovery fixture');c.showPage()
    c.save()
    package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps({
        'title':p.title,'subtitle':p.subtitle,'author':p.author,'puzzle_type':'Sudoku','theme':p.topic,
        'difficulty':p.difficulty,'puzzle_count':24,'puzzle_seed':42}))
    monkeypatch.setattr(studio,'APP',tmp_path)
    monkeypatch.setattr(studio,'create_package',lambda *args,**kwargs:folder)
    monkeypatch.setattr('preflight.preflight',lambda package:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda package:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    original=creation._checkpoint;failed=[]
    def checkpoint(root,plan,status,**extra):
        if status=='complete' and not failed:
            failed.append(True);raise OSError('Simulated process checkpoint failure after registration')
        return original(root,plan,status,**extra)
    monkeypatch.setattr(creation,'_checkpoint',checkpoint)
    with pytest.raises(OSError,match='checkpoint failure'):create_chat_book(tmp_path,p.draft_id)
    db=PublishingDatabase(tmp_path/'data/books.db');before=db.list_books();assert len(before)==1
    progress=[]
    result=create_chat_book(tmp_path,p.draft_id,progress=progress.append)
    assert progress==['Preparing the confirmed Sudoku book…','Generating puzzles, solutions and package files…','Running local preflight and puzzle QA…','Registering the locally checked draft and saving recovery state…']
    assert result['book_id']==before[0]['book_id'] and db.list_books()==before
    # A third read-only recovery still may not undo an owner's metadata edits.
    payload=StudioDraftStore(tmp_path/'data/books.db').load(p.draft_id)['payload'];payload['chat_creation']['status']='failed'
    StudioDraftStore(tmp_path/'data/books.db').save(p.draft_id,'book_plan',payload)
    changed=dict(before[0]['metadata']);changed['subtitle']='Owner changed subtitle';db.save_metadata(before[0]['book_id'],changed)
    with pytest.raises(ValueError,match='preserving owner data'):create_chat_book(tmp_path,p.draft_id)
    assert db.get_book(before[0]['book_id'])['metadata']['subtitle']=='Owner changed subtitle'
