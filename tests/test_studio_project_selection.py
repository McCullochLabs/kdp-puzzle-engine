import json,sqlite3,threading,time,gc
from types import SimpleNamespace
import pytest
from publishing.studio_project_queries import project_query,select_catalog_project

@pytest.mark.parametrize('text',['Select project abc123','Select book BOOK_1','Select project abc-2!'])
def test_selection_queries(text):assert project_query(text)=='select_project'

@pytest.mark.parametrize('text',['Select project ../outside','Select project abc and export it','Do not select project abc','Select project "abc"'])
def test_invalid_selection_queries(text):assert project_query(text) is None

def make_catalog(root):
    path=root/'data/books.db';path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE books(book_id TEXT PRIMARY KEY,metadata_json TEXT)')
        db.execute('INSERT INTO books VALUES(?,?)',('BOOK_1',json.dumps({'title':'Canonical','puzzle_type':'Sudoku'})))
    return path

def test_read_only_exact_identity_and_no_paths(tmp_path):
    path=make_catalog(tmp_path);before=path.read_bytes()
    result=select_catalog_project(tmp_path,'Select project BOOK_1')
    assert result['book_id']=='BOOK_1' and result['metadata']['title']=='Canonical'
    with pytest.raises(ValueError,match='exact book ID'):select_catalog_project(tmp_path,'Select project book_1')
    with pytest.raises(ValueError):select_catalog_project(tmp_path,'Select project ../BOOK_1')
    assert path.read_bytes()==before

def test_missing_catalog_not_created(tmp_path):
    with pytest.raises(ValueError,match='unavailable'):select_catalog_project(tmp_path,'Select project missing')
    assert not (tmp_path/'data').exists()

@pytest.mark.parametrize('stale',[False,True])
def test_actual_offline_selection_respects_worker_and_current_context(tmp_path,monkeypatch,stale):
    import tkinter as tk
    import word_search_creator as desktop
    import publishing.studio_project_queries as queries
    path=make_catalog(tmp_path);original=queries.select_catalog_project
    entered=threading.Event();release=threading.Event();done=threading.Event();threads=[]
    def slow(root,text):
        threads.append(threading.get_ident());entered.set()
        try:assert release.wait(3);return original(root,text)
        finally:done.set()
    monkeypatch.setattr(queries,'select_catalog_project',slow)
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    try:
        app.update();f=app.family_studio;f.context={'book_id':'old'}
        f.prompt.set('Select project BOOK_1');f.send();assert entered.wait(1)
        assert f.busy and threads==[threads[0]] and threads[0]!=threading.get_ident()
        if stale:f.context={'book_id':'newer'}
        release.set();assert done.wait(1);end=time.monotonic()+2
        while f.busy and time.monotonic()<end:app.update();time.sleep(.01)
        assert not f.busy and not errors
        if stale:assert f.context=={'book_id':'newer'}
        else:assert f.context['book_id']=='BOOK_1' and f.context['title']=='Canonical'
        with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM books').fetchone()[0]==1
    finally:release.set();app.destroy();gc.collect()
