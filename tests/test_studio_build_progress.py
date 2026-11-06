import gc,threading,time
import pytest
from publishing.studio_chat_wordsearch import _PipelineFacade

def test_pipeline_facade_forwards_existing_phase_messages_without_tk():
    messages=[];facade=_PipelineFacade(messages.append)
    facade.after(0,lambda:facade.status.set('Building interior'))
    facade.status.set('Inspecting package')
    assert messages==['Building interior','Inspecting package']
    assert facade.completion is None
    _PipelineFacade().status.set('Optional progress remains compatible')

@pytest.mark.parametrize('dismiss',[False,True])
def test_actual_offline_worker_progress_is_ticket_gated(tmp_path,monkeypatch,dismiss):
    import tkinter as tk
    import word_search_creator as desktop
    import publishing.studio_chat_creation as creation
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    started=threading.Event();release=threading.Event();queued=threading.Event();finish=threading.Event();threads=[]
    def worker(root,draft_id,cancel,*,progress=None,stop_event=None):
        started.set();assert release.wait(4);threads.append(threading.get_ident())
        progress('Fixture phase: checking solutions');queued.set();assert finish.wait(4)
        raise ValueError('fixture worker stopped without generation')
    monkeypatch.setattr(creation,'create_chat_book',worker)
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    try:
        app.update();f=app.family_studio;f.prompt.set('Create a 24-puzzle Sudoku book');f.send();app.update()
        f.proposal_button.invoke();assert started.wait(1)
        if dismiss:
            f.cancel_button.invoke();f.mode.set('New request status')
        release.set();assert queued.wait(1);end=time.monotonic()+2
        while time.monotonic()<end:
            app.update()
            if f.results.empty():break
            time.sleep(.01)
        assert f.results.empty()
        assert threads[0]!=threading.get_ident()
        if dismiss:assert f.mode.get()=='New request status'
        else:assert 'Fixture phase: checking solutions' in f.mode.get() and f.busy
        assert not errors
    finally:
        release.set();finish.set();app.destroy();gc.collect()


def test_progress_callback_failure_cannot_abort_pipeline(caplog):
    from publishing.studio_chat_creation import _report_progress
    def failed(message):raise RuntimeError('private callback detail')
    _report_progress(failed,'Generating')
    facade=_PipelineFacade(failed)
    facade.set('Checking')
    facade._studio_package_finished(True,'package','Complete')
    assert facade.completion==(True,'package','Complete')
    assert 'could not be delivered' in caplog.text
    assert 'private callback detail' not in caplog.text
