import gc,hashlib,json,sqlite3,time,tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from queue import Queue
import pytest
from reportlab.pdfgen.canvas import Canvas
from publishing.studio_project_queries import project_query,solution_preview_project
from publishing.studio_preview import StudioPreview,render_document,render_saved_documents
from publishing.studio_providers import RequestGate
from publishing.family_studio import FamilyStudio


def make_pdf(folder):
    folder.mkdir(parents=True);pdf=folder/'interior.pdf';c=Canvas(str(pdf))
    for text,color in zip(['Title','First recorded answers','Other answers'],[(1,0,0),(0,1,0),(0,0,1)]):
        c.setFillColorRGB(0,0,0);c.drawString(70,600,text);c.setFillColorRGB(*color);c.rect(100,100,100,100,fill=1,stroke=0);c.showPage()
    c.save();data={'schema_version':1,'puzzle_count':2,'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzles':[{'puzzle_page':1,'solution_page':3},{'puzzle_page':1,'solution_page':2}]}
    pdf.with_suffix('.puzzles.json').write_text(json.dumps(data));return pdf,data

@pytest.fixture
def saved(tmp_path):
    pdf,data=make_pdf(tmp_path/'out/book');catalog=tmp_path/'data/books.db';catalog.parent.mkdir()
    with sqlite3.connect(catalog) as c:
        c.execute('CREATE TABLE books(book_id TEXT,metadata_json TEXT,package_path TEXT)');c.execute('INSERT INTO books VALUES(?,?,?)',('owned',json.dumps({'title':'Owned'}),str(pdf.parent)))
    return tmp_path,{'book_id':'owned'},pdf,data

@pytest.mark.parametrize('text,expected',[('Show me the solutions','solutions'),('Preview my answer key','solutions'),('Show answers','solutions'),('Show my interior','interior'),('Do not show solutions',None),('Show answers and export them',None)])
def test_bounded_solution_commands(text,expected):assert project_query(text)==expected


def test_first_solution_page_uses_bound_index_and_changes_nothing(saved):
    root,context,pdf,data=saved;before={p:p.read_bytes() for p in [pdf,pdf.with_suffix('.puzzles.json'),root/'data/books.db']}
    result=solution_preview_project(root,context)
    assert result['solution_start_page']==2 and result['documents']==[('Interior',pdf,1,data['pdf_sha256'])]
    assert all(p.read_bytes()==raw for p,raw in before.items())

@pytest.mark.parametrize('fault',['hash','schema','count','empty','boolean','float','outside','missing'])
def test_bad_index_fails_without_opening_title_page(saved,fault):
    root,context,pdf,data=saved
    if fault=='hash':data['pdf_sha256']='0'*64
    if fault=='schema':data['schema_version']=2
    if fault=='count':data['puzzle_count']=3
    if fault=='empty':data['puzzles']=[]
    if fault=='boolean':data['puzzles'][0]['solution_page']=True
    if fault=='float':data['puzzles'][0]['solution_page']=2.0
    if fault=='outside':data['puzzles'][0]['solution_page']=4
    if fault=='missing':del data['puzzles'][0]['solution_page']
    pdf.with_suffix('.puzzles.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):solution_preview_project(root,context)


def test_pending_solution_preview_uses_candidate_and_never_original(saved):
    from publishing.studio_recovery import StudioDraftStore
    from publishing.studio_revision_adoption import _tree
    root,context,original,_=saved;identity='a'*32;pdf,data=make_pdf(root/'data/studio_revision_candidates'/identity/'candidate')
    data['puzzles'][1]['solution_page']=3;pdf.with_suffix('.puzzles.json').write_text(json.dumps(data))
    plan={'revision_id':identity,'source_book_id':'owned','title':'Candidate'};digest=hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    StudioDraftStore(root/'data/books.db').save(identity,'book_plan',{'chat_revision':{'plan':plan,'status':'complete','confirmation':{'source':'studio_chat.revision_button','plan_sha256':digest},'result':{'source_book_id':'owned','folder':str(pdf.parent),'candidate_sha256':_tree(pdf.parent)}}})
    result=solution_preview_project(root,{**context,'pending_semantic_revision':{'revision_id':identity}})
    assert result['documents'][0][1:3]==(pdf,2) and result['documents'][0][1]!=original
    pdf.with_suffix('.puzzles.json').write_text('{}')
    with pytest.raises(ValueError,match='files changed'):solution_preview_project(root,{**context,'pending_semantic_revision':{'revision_id':identity}})


def test_chat_dispatch_opens_indexed_interior(saved,monkeypatch):
    root,context,pdf,data=saved;opened=[];messages=[];gate=RequestGate()
    monkeypatch.setattr('publishing.studio_preview.StudioPreview',lambda app,documents:opened.extend(documents))
    fake=SimpleNamespace(app=SimpleNamespace(APP_DIR=root),context=context,busy=False,provider='Guide',request_gate=gate,results=Queue(),send_button=SimpleNamespace(configure=lambda **kw:None),cancel_button=SimpleNamespace(grid=lambda **kw:None),mode=SimpleNamespace(set=lambda text:None),_say=lambda role,text:messages.append(text),cancel_request=gate.stop)
    assert FamilyStudio._handle_project_query(fake,'Show me the solutions')
    kind,value=fake.results.get(timeout=3);FamilyStudio._receive_project_query_result(fake,*value)
    assert opened==[('Interior',pdf,1,data['pdf_sha256'])] and 'PDF page 2' in messages[-1] and fake.context==context


def test_frozen_solution_render_rejects_later_pdf_changes(saved):
    root,context,pdf,data=saved;documents=solution_preview_project(root,context)['documents']
    images,info=render_saved_documents(documents);assert info==(3,1)
    image=images[0][1]
    # Independent page marker: physical page2 is green, unlike pages1/3.
    assert image.getpixel((165,image.height-165))==(0,255,0)
    pdf.write_bytes(pdf.read_bytes()+b'\n% changed')
    with pytest.raises(ValueError,match='PDF changed'):render_saved_documents(documents)


def test_actual_navigation_retains_solution_fingerprint(saved):
    root,context,pdf,data=saved;documents=solution_preview_project(root,context)['documents'];gc.collect()
    try:app=tk.Tk()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    try:
        window=StudioPreview(app,documents=documents);end=time.monotonic()+5
        while time.monotonic()<end:
            app.update()
            if window.images and not window.busy:break
            time.sleep(.01)
        assert window.document_page==1 and window.images
        pdf.write_bytes(pdf.read_bytes()+b'\n% changed')
        window.next_button.invoke();end=time.monotonic()+5
        while time.monotonic()<end:
            app.update()
            if not window.busy and 'PDF changed' in window.note.get():break
            time.sleep(.01)
        assert not window.images and 'PDF changed' in window.note.get() and not errors
    finally:app.destroy();gc.collect()
