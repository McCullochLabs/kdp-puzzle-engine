from types import SimpleNamespace
import threading
import pytest


@pytest.mark.parametrize("chat_active,answer", [(True,False),(True,True),(False,False)])
def test_close_warns_for_chat_owned_build(monkeypatch,chat_active,answer):
    import word_search_creator as desktop
    calls=[];saved=[];destroyed=[]
    monkeypatch.setattr(desktop.messagebox,"askyesno",lambda *a,**k:calls.append(a) or answer)
    monkeypatch.setattr(desktop,"save_app_preferences",lambda value:saved.append(value))
    var=lambda value:SimpleNamespace(get=lambda:value)
    family=SimpleNamespace(_build_stop_owner=("ticket",threading.Event()) if chat_active else None,provider="Guide",model="",local_ai_enabled=False)
    app=SimpleNamespace(winfo_children=lambda:[],_package_in_progress=False,family_studio=family,_app_preferences={},ui_theme=var("Studio Dark"),compact_home=var(False),selected_theme=None,geometry=lambda:"800x600",state=lambda:"normal",destroy=lambda:destroyed.append(True))
    desktop.WordSearchCreator._on_close(app)
    assert len(calls)==int(chat_active)
    assert bool(destroyed)==(not chat_active or answer)
    assert bool(saved)==bool(destroyed)
    if chat_active:assert not family._build_stop_owner[1].is_set()





def test_actual_ui_declined_close_preserves_chat_owner(tmp_path,monkeypatch):
    import gc,tkinter as tk
    import word_search_creator as desktop
    monkeypatch.setattr(desktop,"load_app_preferences",lambda:{"assistant_provider":"Guide","local_ai_enabled":False})
    monkeypatch.setattr(desktop.WordSearchCreator,"APP_DIR",tmp_path,raising=False)
    monkeypatch.setattr("publishing.family_studio.LocalAssistant.models",lambda self:[])
    prompts=[]
    monkeypatch.setattr(desktop.messagebox,"askyesno",lambda *a,**k:prompts.append(a) or False)
    monkeypatch.setattr(desktop,"save_app_preferences",lambda *a:pytest.fail("Declined close saved preferences"))
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();event=threading.Event();owner=("fixture-ticket",event)
        app.family_studio._build_stop_owner=owner
        app._on_close();app.update()
        assert app.winfo_exists() and prompts
        assert app.family_studio._build_stop_owner is owner and not event.is_set()
    finally:app.destroy();gc.collect()


def test_close_warns_for_dismissed_revision_worker(monkeypatch):
    import word_search_creator as desktop
    prompts=[]
    monkeypatch.setattr(desktop.messagebox,"askyesno",lambda *a,**k:prompts.append(a) or False)
    family=SimpleNamespace(_build_stop_owner=None,_revision_worker_owner="ticket")
    app=SimpleNamespace(winfo_children=lambda:[],_package_in_progress=False,family_studio=family)
    desktop.WordSearchCreator._on_close(app)
    assert prompts and family._revision_worker_owner=="ticket"


def test_only_matching_revision_completion_releases_owner():
    from publishing.family_studio import FamilyStudio
    fake=SimpleNamespace(_revision_worker_owner="current")
    FamilyStudio._finish_revision_worker(fake,"older")
    assert fake._revision_worker_owner=="current"
    FamilyStudio._finish_revision_worker(fake,"current")
    assert fake._revision_worker_owner is None


from test_studio_chat_revisions import owned

def test_actual_dismissed_revision_keeps_close_guard_until_result(owned,monkeypatch):
    import gc,time,tkinter as tk
    import word_search_creator as desktop
    import publishing.studio_chat_revisions as revisions
    root,context,*_=owned
    entered=threading.Event();release=threading.Event();prompts=[]
    def stage(*a,**k):
        entered.set();assert release.wait(5)
        raise ValueError("Isolated delayed worker finished")
    monkeypatch.setattr(revisions,"stage_revision",stage)
    monkeypatch.setattr(desktop,"load_app_preferences",lambda:{"assistant_provider":"Guide","local_ai_enabled":False})
    monkeypatch.setattr(desktop.WordSearchCreator,"APP_DIR",root,raising=False)
    monkeypatch.setattr("publishing.family_studio.LocalAssistant.models",lambda self:[])
    monkeypatch.setattr(desktop.messagebox,"askyesno",lambda *a,**k:prompts.append(a) or False)
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.context=context
        f._show_chat_revision_plan(revisions.revision_plan(root,'Change title to "Revision owner fixture"',context))
        f.proposal_button.invoke();assert entered.wait(1)
        owner=f._revision_worker_owner;assert owner is not None
        f.cancel_request();assert not f.busy and f._revision_worker_owner==owner
        app._on_close();assert prompts and app.winfo_exists()
        f._create_confirmed_revision();assert f._revision_worker_owner==owner and not f.busy
        f.context={"book_id":"newer"};ticket,cancel=f.request_gate.begin(f.provider,dict(f.context));f.busy=True
        release.set();end=time.monotonic()+3
        while f._revision_worker_owner and time.monotonic()<end:app.update();time.sleep(.01)
        assert f._revision_worker_owner is None
        assert f.context=={"book_id":"newer"} and f.request_gate.active==ticket and f.busy and not cancel.is_set()
    finally:release.set();app.destroy();gc.collect()
