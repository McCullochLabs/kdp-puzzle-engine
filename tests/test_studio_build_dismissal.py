"""Dismissal isolates late worker results; it is not a hard production stop."""
import gc
import threading
import time
import tkinter as tk
import pytest
from publishing import studio_chat_creation as creation


def test_busy_build_refuses_second_build_without_touching_catalog(tmp_path):
    assert creation._BUILD_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ValueError,match='Another chat book is still being built'):
            creation.create_chat_book(tmp_path,'not-a-real-draft')
        assert not (tmp_path/'data').exists()
    finally:
        creation._BUILD_LOCK.release()


@pytest.mark.parametrize('outcome',['success','error'])
def test_actual_chat_dismissed_build_cannot_replace_context_or_stop_new_request(tmp_path,monkeypatch,outcome):
    import word_search_creator as desktop
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    entered=threading.Event();release=threading.Event();finished=threading.Event();events=[]
    def worker(root,draft_id,cancel,*,progress=None,stop_event=None):
        events.append(cancel);entered.set()
        try:
            assert release.wait(4)
            if outcome=='error':raise ValueError('late fixture failure')
            return {'book_id':'late-book','title':'Late fixture','topic':'General Starter','kind':'Sudoku','puzzles':24,'pages':52,'folder':str(tmp_path/'out/late'),'qa':{'summary':{'blockers':0}}}
        finally:finished.set()
    monkeypatch.setattr(creation,'create_chat_book',worker)
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *args:errors.append(args)
    try:
        app.update();f=app.family_studio
        queued=threading.Event();original_put=f.results.put
        def put(item):
            original_put(item)
            if item[0]=='book_creation_result':queued.set()
        monkeypatch.setattr(f.results,'put',put)
        f.context={'book_id':'original','title':'Original'}
        f.prompt.set('Create an easy 24-puzzle Sudoku book');f.send();app.update()
        f.proposal_button.invoke();assert entered.wait(1)
        assert 'production and its recovery draft continue' in f.mode.get()
        f.cancel_button.invoke();assert events[0].is_set() and not f.busy
        f.context={'book_id':'new-selection','title':'New selection'}
        ticket,new_cancel=f.request_gate.begin(f.provider,dict(f.context))
        f.busy=True;f.send_button.configure(state='disabled')
        release.set();assert finished.wait(1) and queued.wait(1)
        end=time.monotonic()+2
        while time.monotonic()<end:
            app.update()
            if f.results.empty():break
            time.sleep(.01)
        assert f.results.empty(), 'Late result was not consumed by the actual UI poll'
        assert f.context['book_id']=='new-selection'
        assert f.request_gate.active==ticket and not new_cancel.is_set()
        assert f.busy and str(f.send_button.cget('state'))=='disabled'
        text=f.chat.get('1.0','end')
        assert 'Created Late fixture' not in text and 'late fixture failure' not in text
        assert not errors
    finally:
        release.set();app.destroy();gc.collect()
