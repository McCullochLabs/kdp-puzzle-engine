import gc,threading,time,tkinter as tk
from types import SimpleNamespace
import pytest
from publishing.family_studio import FamilyStudio
from publishing.studio_providers import RequestGate

@pytest.mark.parametrize('decision',['show','cancel','switch','provider','error','save_error'])
def test_actual_chat_waiting_revision_plan_keeps_tk_alive_and_rejects_stale_results(tmp_path,monkeypatch,decision):
    import word_search_creator as desktop
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    entered=threading.Event();release=threading.Event();done=threading.Event();threads=[];shown=[]
    main=threading.get_ident();plan=object()
    def slow(root,text,context):
        threads.append(threading.get_ident());entered.set()
        try:
            assert release.wait(3)
            if decision=='error':raise ValueError('Source changed; review again.')
            return plan
        finally:done.set()
    monkeypatch.setattr('publishing.studio_chat_revisions.revision_plan',slow)
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    try:
        app.update();f=app.family_studio;f.context={'book_id':'owned'}
        def show(value):
            if decision=='save_error':raise ValueError('Draft save unavailable')
            shown.append((value,threading.get_ident()))
        monkeypatch.setattr(f,'_show_chat_revision_plan',show)
        f.prompt.set('Make it harder');f.send();assert entered.wait(1)
        ticks=[];app.after(0,lambda:ticks.append(True));app.update()
        assert f.busy and ticks and threads[0]!=main and not release.is_set()
        if decision=='cancel':f.cancel_request()
        if decision=='switch':f.context={'book_id':'other'}
        if decision=='provider':f.provider='Ollama'
        release.set();assert done.wait(1)
        deadline=time.monotonic()+2
        while f.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
        app.update();assert not f.busy
        if decision=='show':assert shown==[(plan,main)]
        else:assert not shown
        if decision=='error':assert 'Source changed' in f.chat.get('1.0','end')
        if decision=='save_error':assert 'Draft save unavailable' in f.chat.get('1.0','end')
        assert not errors
    finally:release.set();app.destroy();gc.collect()


def test_old_result_cannot_cancel_a_new_plan():
    gate=RequestGate();old,_=gate.begin('Guide',{'book_id':'old'});gate.stop();new,_=gate.begin('Guide',{'book_id':'new'})
    fake=SimpleNamespace(request_gate=gate,provider='Guide',context={'book_id':'new'},cancel_request=lambda:pytest.fail('Cancelled new request'),_show_chat_revision_plan=lambda p:pytest.fail('Stale proposal shown'))
    FamilyStudio._receive_revision_plan(fake,old,object(),'')
    assert gate.active==new


def test_confirmation_does_not_start_after_selected_project_changed(tmp_path):
    messages=[]
    fake=SimpleNamespace(busy=False,_chat_revision_plan=SimpleNamespace(selected_context={'book_id':'old'}),context={'book_id':'new'},app=SimpleNamespace(APP_DIR=tmp_path),_say=lambda *a:messages.append(a),request_gate=SimpleNamespace(begin=lambda *a:pytest.fail('Stale confirmation started')))
    FamilyStudio._create_confirmed_revision(fake)
    assert messages and 'selected project changed' in messages[-1][1]


def test_actual_slow_confirmation_keeps_tk_alive_and_uses_click_context(tmp_path,monkeypatch):
    import word_search_creator as desktop
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    entered=threading.Event();release=threading.Event();threads=[];shown=[];scopes=[];main=threading.get_ident()
    def confirm(root,plan,context):
        threads.append(threading.get_ident());scopes.append(context);entered.set();assert release.wait(3)
    monkeypatch.setattr('publishing.studio_chat_revisions.confirm_revision_plan',confirm)
    monkeypatch.setattr('publishing.studio_chat_revisions.stage_revision',lambda *a:{'fixture':'staged result'})
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    try:
        app.update();f=app.family_studio;f.context={'book_id':'owned'}
        f._chat_revision_plan=SimpleNamespace(revision_id='a'*32,selected_context={'book_id':'owned'})
        monkeypatch.setattr(f,'_receive_staged_revision',lambda result:shown.append((result,threading.get_ident())))
        f.proposal_button.configure(command=f._create_confirmed_revision);f.proposal.grid();f.proposal_button.invoke()
        assert entered.wait(1);ticks=[];app.after(0,lambda:ticks.append(True));app.update()
        assert ticks and f.busy and threads[0]!=main and scopes==[{'book_id':'owned'}]
        release.set();end=time.monotonic()+3
        while f.busy and time.monotonic()<end:app.update();time.sleep(.01)
        assert not f.busy and shown==[({'fixture':'staged result'},main)] and not errors
    finally:release.set();app.destroy();gc.collect()
