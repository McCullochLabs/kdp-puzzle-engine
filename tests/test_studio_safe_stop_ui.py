import gc,threading,time
from types import SimpleNamespace
import pytest
from publishing.family_studio import FamilyStudio

def test_other_worker_completion_cannot_clear_stop_owner():
    event=threading.Event()
    fake=SimpleNamespace(_build_stop_owner=('current',event))
    FamilyStudio._finish_build_stop(fake,'older')
    assert fake._build_stop_owner==('current',event)

@pytest.mark.parametrize('dismiss',[False,True])
def test_actual_stop_control_owns_separate_event_and_preserves_new_request(tmp_path,monkeypatch,dismiss):
    import tkinter as tk
    import word_search_creator as desktop
    import publishing.studio_chat_creation as creation
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    entered=threading.Event();release=threading.Event();queued=threading.Event();seen=[]
    def worker(root,draft_id,cancel,*,progress=None,stop_event=None):
        seen.append((cancel,stop_event));entered.set();assert release.wait(4)
        creation._check_build_stop(stop_event)
        pytest.fail('Stop signal was not delivered')
    monkeypatch.setattr(creation,'create_chat_book',worker)
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    try:
        app.update();f=app.family_studio;original_put=f.results.put
        def put(item):
            original_put(item)
            if item[0]=='book_creation_result':queued.set()
        monkeypatch.setattr(f.results,'put',put)
        f.prompt.set('Create a 24-puzzle Sudoku book');f.send();app.update();f.proposal_button.invoke();assert entered.wait(1)
        cancel,stop=seen[0];assert cancel is not stop and not stop.is_set()
        if dismiss:
            f.cancel_button.invoke();assert cancel.is_set() and not stop.is_set()
            f._create_confirmed_chat_book();assert len(seen)==1
            f.context={'book_id':'newer'};new_ticket,new_cancel=f.request_gate.begin(f.provider,dict(f.context));f.busy=True
        f.build_stop_button.invoke();assert stop.is_set()
        assert str(f.build_stop_button.cget('state'))=='disabled'
        if not dismiss:assert not cancel.is_set()
        release.set();assert queued.wait(1);end=time.monotonic()+2
        while f._build_stop_owner and time.monotonic()<end:app.update();time.sleep(.01)
        assert f._build_stop_owner is None and not f.build_stop_button.winfo_ismapped()
        if dismiss:
            assert f.context=={'book_id':'newer'} and f.request_gate.active==new_ticket and not new_cancel.is_set() and f.busy
        else:
            assert not f.busy and 'safe boundary' in f.chat.get('1.0','end')
        assert not errors
    finally:release.set();app.destroy();gc.collect()
