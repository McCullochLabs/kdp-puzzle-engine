import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from queue import Queue
from publishing.studio_providers import RequestGate

import pytest
from publishing.studio_project_queries import project_query,selected_project,project_status_text
from publishing.family_studio import FamilyStudio


@pytest.mark.parametrize('text,action',[
    ('Where did you save the files?','files'),('Show me the interior','interior'),
    ('Show my cover','cover'),('Report current project status','status'),
    ('Resume interrupted work','resume'),('Show me the solutions','solutions'),
    ('Do not show my cover',None),('Change the cover',None),
    ('Show my cover and publish it',None),('Show saved themes','themes')])
def test_bounded_queries(text,action):
    assert project_query(text)==action


def catalog(tmp_path,package):
    path=tmp_path/'data/books.db';path.parent.mkdir()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE books(book_id TEXT,metadata_json TEXT,package_path TEXT)')
        db.execute('INSERT INTO books VALUES(?,?,?)',('owned',json.dumps({'title':'Owned','files':{'print_interior':'C:/unrelated.pdf'}}),str(package)))
    return path


def test_identity_paths_and_read_only(tmp_path):
    package=tmp_path/'out/owned';package.mkdir(parents=True)
    (package/'interior.pdf').write_bytes(b'fixture')
    path=catalog(tmp_path,package);before=path.read_bytes()
    result=selected_project(tmp_path,{'book_id':'owned','path':'C:/unrelated'})
    assert result['folder']==package
    assert result['documents']==[('Interior',package/'interior.pdf',0)]
    assert 'not a fresh QA result' in project_status_text(result)
    assert before==path.read_bytes()
    with pytest.raises(ValueError,match='pending'):
        selected_project(tmp_path,{'book_id':'owned','pending_semantic_revision':True})
    with pytest.raises(ValueError,match='no longer'):
        selected_project(tmp_path,{'book_id':'unknown'})


def test_external_package_rejected(tmp_path):
    package=tmp_path/'outside';package.mkdir();catalog(tmp_path,package)
    with pytest.raises(ValueError,match='outside'):
        selected_project(tmp_path,{'book_id':'owned'})


def test_ui_routes_existing_preview_without_changing_context(tmp_path,monkeypatch):
    package=tmp_path/'out/owned';package.mkdir(parents=True)
    (package/'interior.pdf').write_bytes(b'fixture');catalog(tmp_path,package)
    messages=[];previews=[]
    monkeypatch.setattr('publishing.studio_preview.StudioPreview',lambda app,documents:previews.extend(documents))
    fake=SimpleNamespace(app=SimpleNamespace(APP_DIR=tmp_path),context={'book_id':'owned'},
                         _say=lambda who,text:messages.append(text),busy=False,provider='Guide',
                         results=Queue(),request_gate=RequestGate(),
                         send_button=SimpleNamespace(configure=lambda **kw:None),
                         cancel_button=SimpleNamespace(grid=lambda **kw:None),mode=SimpleNamespace(set=lambda text:None))
    fake.cancel_request=lambda:fake.request_gate.stop()
    assert FamilyStudio._handle_project_query(fake,'Show me the interior')
    kind,value=fake.results.get(timeout=3)
    assert kind=='project_query_result'
    FamilyStudio._receive_project_query_result(fake,*value)
    assert previews==[('Interior',package/'interior.pdf',0)]
    assert fake.context=={'book_id':'owned'}
    assert messages[-1]=='Opened the saved interior for Owned.'
    assert not FamilyStudio._handle_project_query(fake,'Change the cover')


def test_combined_request_never_silently_becomes_sudoku():
    from publishing.studio_assistant import guide_request,parse_proposal,AssistantIntent
    from dataclasses import asdict
    request='Create a 200-puzzle holiday word search and Sudoku book'
    assert guide_request(request).action=='clarify'
    proposal=asdict(AssistantIntent(action='create_book',kind='Sudoku',topic='Winter Holidays'))
    proposal['source_groups']=[]
    assert parse_proposal(proposal,request).action=='clarify'
    assert guide_request('Create a Sudoku book called "Word Search"').kind=='Sudoku'


def test_pending_candidate_preview_frozen_identity_and_drift(tmp_path):
    from publishing.studio_project_queries import preview_project
    from publishing.studio_recovery import StudioDraftStore
    from publishing.studio_revision_adoption import _tree
    import hashlib
    identity='a'*32;folder=tmp_path/'data/studio_revision_candidates'/identity/'candidate';folder.mkdir(parents=True)
    (folder/'interior.pdf').write_bytes(b'candidate')
    store=StudioDraftStore(tmp_path/'data/books.db')
    plan={'revision_id':identity,'source_book_id':'owned','title':'New title'}
    confirmation={'source':'studio_chat.revision_button','plan_sha256':hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    payload={'chat_revision':{'plan':plan,'status':'complete','confirmation':confirmation,'result':{
        'source_book_id':'owned','folder':str(folder),'candidate_sha256':_tree(folder)}}}
    store.save(identity,'book_plan',payload)
    context={'book_id':'owned','pending_semantic_revision':{'revision_id':identity}}
    before=(tmp_path/'data/books.db').read_bytes()
    project=preview_project(tmp_path,context)
    assert project['documents']==[('Interior',folder/'interior.pdf',0)]
    assert project['metadata']['title']=='Staged candidate: New title'
    assert (tmp_path/'data/books.db').read_bytes()==before
    with pytest.raises(ValueError,match='no longer pending'):
        preview_project(tmp_path,{**context,'book_id':'other'})
    (folder/'interior.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError,match='files changed'):preview_project(tmp_path,context)
    payload['chat_revision']['status']='adopted';store.save(identity,'book_plan',payload)
    with pytest.raises(ValueError,match='no longer pending'):preview_project(tmp_path,context)


def test_pending_candidate_cannot_redirect_to_original_or_external(tmp_path):
    from publishing.studio_project_queries import preview_project
    from publishing.studio_recovery import StudioDraftStore
    import hashlib
    identity='b'*32;store=StudioDraftStore(tmp_path/'data/books.db')
    plan={'revision_id':identity,'source_book_id':'owned','title':'New'}
    saved={'plan':plan,'status':'complete','confirmation':{'source':'studio_chat.revision_button',
        'plan_sha256':hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()},
        'result':{'source_book_id':'owned','folder':str(tmp_path/'out/original'),'candidate_sha256':{'interior.pdf':'fake'}}}
    store.save(identity,'book_plan',{'chat_revision':saved})
    context={'book_id':'owned','pending_semantic_revision':{'revision_id':identity}}
    with pytest.raises(ValueError,match='outside'):preview_project(tmp_path,context)
