"""Slow read-only validation must not block Tk or open stale previews."""
import gc
import threading
import time
import tkinter as tk
from types import SimpleNamespace
from queue import Queue

import pytest
from publishing.family_studio import FamilyStudio
from publishing.studio_providers import RequestGate


def test_late_result_does_not_cancel_new_request_or_open_preview(monkeypatch):
    previews=[]
    monkeypatch.setattr('publishing.studio_preview.StudioPreview',lambda *a,**k:previews.append(k))
    gate=RequestGate();old,_=gate.begin('Guide',{'book_id':'old'});gate.stop()
    new,_=gate.begin('Guide',{'book_id':'new'})
    fake=SimpleNamespace(request_gate=gate,provider='Guide',context={'book_id':'new'},
                         cancel_request=lambda:pytest.fail('Late result cancelled the current request'))
    FamilyStudio._receive_project_query_result(fake,old,'interior',{},'')
    assert gate.active==new and not previews


@pytest.mark.parametrize('decision',['open','cancel','switch','error'])
def test_actual_chat_slow_lookup_keeps_tk_alive_and_checks_selection(tmp_path,monkeypatch,decision):
    import word_search_creator as studio
    monkeypatch.setattr(studio,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(studio.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    started=threading.Event();release=threading.Event();finished=threading.Event()
    main=threading.get_ident();worker_ids=[];previews=[];errors=[]
    def slow(root,context):
        worker_ids.append(threading.get_ident());started.set()
        try:
            assert release.wait(3)
            if decision=='error':raise ValueError('Candidate files changed after staging; the original was not opened.')
            return {'folder':tmp_path,'metadata':{'title':'Candidate'},'documents':[('Interior',tmp_path/'interior.pdf',0)]}
        finally:finished.set()
    monkeypatch.setattr('publishing.studio_project_queries.preview_project',slow)
    monkeypatch.setattr('publishing.studio_preview.StudioPreview',lambda *a,**k:previews.append((threading.get_ident(),k)))
    gc.collect()
    try:app=studio.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    app.report_callback_exception=lambda *args:errors.append(args)
    try:
        app.update();family=app.family_studio
        family.context={'book_id':'owned','pending_semantic_revision':{'revision_id':'a'*32}}
        family.prompt.set('Show me the interior');family.send()
        assert started.wait(1) and family.busy
        ticks=[];app.after(0,lambda:ticks.append(True));app.update()
        assert ticks and not release.is_set() and worker_ids[0]!=main
        if decision=='cancel':family.cancel_request()
        if decision=='switch':family.context={'book_id':'other'}
        release.set();assert finished.wait(1)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and (family.busy or (decision=='open' and not previews)):
            app.update();time.sleep(.01)
        app.update()
        if decision=='open':assert len(previews)==1 and previews[0][0]==main
        else:assert not previews
        if decision=='error':assert 'Candidate files changed' in family.chat.get('1.0','end')
        assert not family.busy
    finally:
        release.set();app.destroy();gc.collect()
    assert not errors
