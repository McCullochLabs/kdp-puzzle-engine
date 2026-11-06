import pytest
from types import SimpleNamespace
from publishing.studio_project_queries import project_query
from publishing.family_studio import FamilyStudio

@pytest.mark.parametrize('text',['Save this project','Save my book','Save conversation','Save current progress'])
def test_save_query(text):
    assert project_query(text)=='save_session'

@pytest.mark.parametrize('text',['Do not save this project','Save this project and publish','Save this project as another book','Save files to C:/other'])
def test_save_query_is_bounded(text):
    assert project_query(text) is None

@pytest.mark.parametrize('error',['','database is locked'])
def test_save_reports_actual_result(error):
    messages=[];calls=[]
    fake=SimpleNamespace(_session_ready=True,_session_restoring=False,_session_save_error=error,_say=lambda *a:messages.append(a),_flush_session=lambda:calls.append(True))
    assert FamilyStudio._handle_project_query(fake,'Save this project')
    assert calls==[True]
    assert ('Save needs attention' if error else 'Saved the conversation') in messages[-1][1]

def test_restore_guard_never_claims_save():
    messages=[]
    fake=SimpleNamespace(_session_ready=False,_session_restoring=True,_say=lambda *a:messages.append(a))
    assert FamilyStudio._handle_project_query(fake,'Save this project')
    assert 'still starting' in messages[-1][1]


def test_actual_offline_save_reopens_canonical_context(tmp_path,monkeypatch):
    import gc,tkinter as tk
    import word_search_creator as desktop
    from publishing.database import PublishingDatabase
    from publishing.studio_session import load_session
    db=PublishingDatabase(tmp_path/'data/books.db')
    db.upsert_book('owned','source-owned',{'title':'Canonical','puzzle_type':'Sudoku','puzzle_count':24},'')
    before=db.get_book('owned')
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.context={'book_id':'owned','title':'Stale display title'}
        f.prompt.set('Save this project');f.send();app.update()
        assert 'Saved the conversation' in f.chat.get('1.0','end')
        saved=load_session(tmp_path)
        assert saved['context']['book_id']=='owned' and saved['context']['title']=='Canonical'
        assert any(m['text']=='Save this project' for m in saved['messages'])
        assert db.get_book('owned')==before
        assert not list((tmp_path/'out').glob('**/*'))
    finally:app.destroy();gc.collect()
