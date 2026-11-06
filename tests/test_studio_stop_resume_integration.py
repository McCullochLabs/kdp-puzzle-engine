import gc,json,threading,time
from types import SimpleNamespace
import pytest

def test_actual_ui_real_service_stop_persists_and_explicit_resume_reuses_fixture(tmp_path,monkeypatch):
    import tkinter as tk
    import word_search_creator as desktop
    import puzzle_book_studio as studio
    from publishing.database import PublishingDatabase
    from publishing.studio_recovery import StudioDraftStore
    from publishing.package_layout import initialize_package_layout,package_file
    from reportlab.pdfgen import canvas
    db=PublishingDatabase(tmp_path/'data/books.db');db.upsert_book('original','original-source',{'title':'Preserved original','puzzle_type':'Sudoku'},'')
    original=db.get_book('original');entered=threading.Event();release=threading.Event();calls=[];qa_calls=[]
    folder=tmp_path/'out/stop_resume_fixture';initialize_package_layout(folder)
    def fixture(kind,title,subtitle,author,count,difficulty,seed,**kwargs):
        target=package_file(folder,'interior.pdf',for_write=True)
        if target.exists():
            calls.append('reuse');return folder
        calls.append('write');c=canvas.Canvas(str(target))
        for _ in range(52):c.drawString(80,600,'Synthetic stop/resume fixture');c.showPage()
        c.save()
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps({'title':title,'subtitle':subtitle,'author':author,'puzzle_type':kind,'theme':kwargs['theme'],'difficulty':difficulty,'puzzle_count':count,'puzzle_seed':seed}))
        entered.set();assert release.wait(5);return folder
    monkeypatch.setattr(studio,'APP',tmp_path);monkeypatch.setattr(studio,'create_package',fixture)
    monkeypatch.setattr('preflight.preflight',lambda *a:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda *a:{'ready':True})
    def qa(*a,**k):qa_calls.append(True);return SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}})
    monkeypatch.setattr('publishing.product_qa.inspect_product',qa)
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    def wait_idle(f):
        end=time.monotonic()+5
        while f.busy and time.monotonic()<end:app.update();time.sleep(.01)
        assert not f.busy
    try:
        app.update();f=app.family_studio;f.context={'book_id':'original','title':'Preserved original','kind':'Sudoku'}
        f.prompt.set('Create an easy 24-puzzle Sudoku book with seed 42');f.send();app.update();draft_id=f._chat_creation_plan.draft_id
        f.proposal_button.invoke();assert entered.wait(1)
        pdf=package_file(folder,'interior.pdf');before=pdf.read_bytes()
        f.build_stop_button.invoke();release.set();wait_idle(f)
        store=StudioDraftStore(tmp_path/'data/books.db');stopped=store.load(draft_id)
        assert stopped['payload']['chat_creation']['status']=='failed'
        assert 'safe boundary' in stopped['payload']['chat_creation']['error']
        assert calls==['write'] and not qa_calls and len(db.list_books())==1
        assert pdf.read_bytes()==before and db.get_book('original')==original
        assert f.context['book_id']=='original' and f._build_stop_owner is None
        f.prompt.set('Resume unfinished work');f.send();app.update()
        assert f._chat_creation_plan.draft_id==draft_id and not f.busy
        assert calls==['write'], 'Resume must show a plan, not replay Create'
        f.proposal_button.invoke();wait_idle(f)
        completed=store.load(draft_id)
        assert completed['payload']['chat_creation']['status']=='complete'
        assert calls==['write','reuse'] and qa_calls==[True]
        assert len(db.list_books())==2 and db.get_book('original')==original
        assert f.context['book_id']==completed['payload']['chat_creation']['result']['book_id']
        assert pdf.read_bytes()==before and f._build_stop_owner is None and not errors
        assert stopped['revision']<completed['revision']
    finally:release.set();app.destroy();gc.collect()
