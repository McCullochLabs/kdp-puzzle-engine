from types import SimpleNamespace
import pytest
from publishing.studio_chat_revisions import revision_decision
from publishing.family_studio import FamilyStudio

@pytest.mark.parametrize('text,expected',[("Accept staged revision",'accept'),("Reject this revision!",'reject'),("accept the revision.",'accept'),("yes",None),("Do not accept staged revision",None),("Accept staged revision and publish it",None),("Accept another book",None)])
def test_explicit_decision(text,expected):assert revision_decision(text)==expected

@pytest.mark.parametrize('decision',[True,False])
def test_dispatch_requires_matching_pending_identity(decision):
    calls=[];messages=[]
    fake=SimpleNamespace(context={'book_id':'owned','pending_semantic_revision':{'revision_id':'current'}},_adoption_revision_id='current',_say=lambda *a:messages.append(a),_decide_staged_revision=lambda value:calls.append(value))
    text=('Accept' if decision else 'Reject')+' staged revision'
    assert FamilyStudio._handle_revision_decision(fake,text) and calls==[decision]
    fake._adoption_revision_id='stale';calls.clear()
    assert FamilyStudio._handle_revision_decision(fake,text) and not calls and messages
    assert not FamilyStudio._handle_revision_decision(fake,'yes')

@pytest.mark.parametrize('decision',[True,False])
def test_actual_chat_send_uses_existing_decision_action(tmp_path,monkeypatch,decision):
    import gc,tkinter as tk
    import word_search_creator as studio
    monkeypatch.setattr(studio,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(studio.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=studio.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;calls=[]
        f.context={'book_id':'owned','pending_semantic_revision':{'revision_id':'current'}};f._adoption_revision_id='current'
        monkeypatch.setattr(f,'_decide_staged_revision',lambda value:calls.append(value))
        f.prompt.set(('Accept' if decision else 'Reject')+' staged revision');f.send();app.update()
        assert calls==[decision] and not f.busy
    finally:app.destroy();gc.collect()
