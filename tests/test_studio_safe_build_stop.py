import threading
from pathlib import Path
import pytest
from publishing.studio_chat_creation import sudoku_chat_plan,save_creation_plan,confirm_creation_plan,create_chat_book,_BUILD_LOCK
from publishing.studio_assistant import guide_request
from publishing.studio_recovery import StudioDraftStore

def confirmed(root):
    request='Create an easy 24-puzzle Sudoku book with seed 42'
    plan=sudoku_chat_plan(request,guide_request(request));save_creation_plan(root,plan);confirm_creation_plan(root,plan)
    return plan

def test_preexisting_stop_has_no_side_effects(tmp_path):
    stop=threading.Event();stop.set()
    with pytest.raises(ValueError,match='safe boundary'):create_chat_book(tmp_path,'missing',stop_event=stop)
    assert not (tmp_path/'data').exists()

@pytest.mark.parametrize('boundary',['before_generation','after_generation'])
def test_safe_stop_preserves_recovery_and_prevents_registration(tmp_path,monkeypatch,boundary):
    import puzzle_book_studio as studio
    import publishing.product_qa as qa
    plan=confirmed(tmp_path);stop=threading.Event();calls=[]
    monkeypatch.setattr(studio,'APP',tmp_path)
    folder=tmp_path/'out/stopped_fixture'
    def generate(*a,**k):
        calls.append(True);folder.mkdir(parents=True);(folder/'preserve.txt').write_text('generated fixture')
        stop.set();return folder
    monkeypatch.setattr(studio,'create_package',generate)
    monkeypatch.setattr(qa,'inspect_product',lambda *a,**k:pytest.fail('Stopped build entered QA'))
    progress=(lambda message:stop.set()) if boundary=='before_generation' else None
    with pytest.raises(ValueError,match='safe boundary'):create_chat_book(tmp_path,plan.draft_id,progress=progress,stop_event=stop)
    assert bool(calls)==(boundary=='after_generation')
    if calls:assert (folder/'preserve.txt').read_text()=='generated fixture'
    draft=StudioDraftStore(tmp_path/'data/books.db').load(plan.draft_id)
    assert draft['payload']['chat_creation']['status']=='failed'
    assert 'safe boundary' in draft['payload']['chat_creation']['error']
    import sqlite3
    with sqlite3.connect(tmp_path/'data/books.db') as db:
        assert db.execute("SELECT count(*) FROM books").fetchone()[0]==0
    assert _BUILD_LOCK.acquire(blocking=False);_BUILD_LOCK.release()


def test_stop_after_qa_preserves_checked_package_without_catalog_registration(tmp_path,monkeypatch):
    import json,sqlite3
    from types import SimpleNamespace
    import puzzle_book_studio as studio
    from publishing.package_layout import initialize_package_layout,package_file
    from reportlab.pdfgen import canvas
    plan=confirmed(tmp_path);stop=threading.Event();folder=tmp_path/'out/checked_fixture';initialize_package_layout(folder)
    target=package_file(folder,'interior.pdf',for_write=True);c=canvas.Canvas(str(target))
    for _ in range(52):c.drawString(80,600,'Safe stop fixture');c.showPage()
    c.save()
    package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps({'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':'Sudoku','theme':plan.topic,'difficulty':plan.difficulty,'puzzle_count':24,'puzzle_seed':42}))
    before=target.read_bytes();qa_calls=[]
    monkeypatch.setattr(studio,'APP',tmp_path)
    monkeypatch.setattr(studio,'create_package',lambda *a,**k:folder)
    monkeypatch.setattr('preflight.preflight',lambda *a:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda *a:{'ready':True})
    def qa(*a,**k):qa_calls.append(True);return SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}})
    monkeypatch.setattr('publishing.product_qa.inspect_product',qa)
    def progress(message):
        if message.startswith('Registering'):stop.set()
    with pytest.raises(ValueError,match='safe boundary'):create_chat_book(tmp_path,plan.draft_id,progress=progress,stop_event=stop)
    assert qa_calls==[True] and target.read_bytes()==before
    with sqlite3.connect(tmp_path/'data/books.db') as db:assert db.execute('SELECT count(*) FROM books').fetchone()[0]==0
