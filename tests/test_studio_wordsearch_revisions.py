import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas
import puzzle_book_studio as engine
from test_studio_chat_wordsearch import library,confirm,REQUEST,INTENT
from publishing.studio_chat_wordsearch import wordsearch_chat_plan,_owned_paths
from publishing.studio_chat_creation import _checkpoint,_plan_hash
from publishing.studio_chat_revisions import revision_plan,save_revision_plan,confirm_revision_plan,stage_revision
from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,_tree
from publishing.package_layout import initialize_package_layout,package_file
from publishing.manager import PublishingService
from publishing.metadata_service import build_metadata

@pytest.fixture
def owned_ws(library,monkeypatch):
    root,groups,asset,calls=library
    monkeypatch.setattr(engine,'APP',root);monkeypatch.setattr(engine,'OUT',root/'out')
    art=root/'cover_assets/approved.png';Image.new('RGB',(100,120),'black').save(art);asset['sha256']=hashlib.sha256(art.read_bytes()).hexdigest()
    monkeypatch.setattr('background_generation.index.BackgroundAssetIndex',lambda:SimpleNamespace(ledger_details=lambda p:asset,production_selectable=lambda a:a['production_approved']))
    plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    source,folder,settings=_owned_paths(root,plan);source.parent.mkdir(parents=True);source.write_bytes(plan.checked_theme_json.encode())
    initialize_package_layout(folder);pdf=package_file(folder,'interior.pdf',for_write=True);c=Canvas(str(pdf))
    for text in ['Original title','Puzzle fixture','Solution fixture']:c.drawString(60,600,text);c.showPage()
    c.save();records=[{'type':'word_search','words':g['words']} for g in groups['groups']]
    pdf.with_suffix('.puzzles.json').write_text(json.dumps({'schema_version':1,'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzles':records,'layout_regions':[]}))
    front=package_file(folder,'front_cover.png',for_write=True);front.write_bytes(art.read_bytes());front.with_suffix('.approval.json').write_text(json.dumps({'asset_id':'fixture','asset_sha256':asset['sha256']}))
    package_file(folder,'kdp_full_wrap.pdf',for_write=True).write_bytes(pdf.read_bytes())
    raw={'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':'Word Search','puzzle_count':48,'difficulty':plan.difficulty,'cover_layout':'photo','cover_art':str(art),'cover_art_sha256':asset['sha256'],'source_theme':str(source),'source_theme_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(raw))
    service=PublishingService(root);key='package:'+str(folder);identity=service._id(key)
    meta=build_metadata({'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':'Word Search','detected_topic':plan.topic,'puzzle_count':48,'difficulty_label':plan.difficulty})
    meta.update(book_id=identity,trim_size='8.5x11',page_count=3,files=service._package_files(folder),production_status='Needs owner and platform review',puzzle_seed=42,studio_chat_creation={'draft_id':plan.draft_id,'plan_sha256':_plan_hash(plan)})
    service.db.upsert_book(identity,key,meta,str(folder));_checkpoint(root,plan,'complete',result={'book_id':identity,'folder':str(folder),'pages':3})
    monkeypatch.setattr('preflight.preflight',lambda p:(True,[]));monkeypatch.setattr('publishing.package_layout.release_contract',lambda p:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    monkeypatch.setattr(engine,'create_package',lambda *a,**k:pytest.fail('Word Search grids regenerated'))
    return root,{'book_id':identity,'title':plan.title,'topic':plan.topic,'kind':'Word Search'},folder,service,source


def test_owned_ws_exact_stage_adopt_chain_and_original_preservation(owned_ws):
    root,context,original,service,source=owned_ws;before=_tree(original);old_book=service.db.get_book(context['book_id'])
    for style in ['Modern Minimal','Classic Frame']:
        p=revision_plan(root,f'Change title page design to "{style}"',context);assert p.kind=='Word Search' and p.count==48 and p.expected_pages==3
        save_revision_plan(root,p);confirm_revision_plan(root,p,context);result=stage_revision(root,p.revision_id)
        pending={**context,'pending_semantic_revision':{'revision_id':p.revision_id}}
        confirm_adoption(root,p.revision_id,pending);adopted=adopt_revision(root,p.revision_id)
        after=service.db.get_book(context['book_id'])
        assert adopted['kind']=='Word Search' and after['source_key']==old_book['source_key'] and after['statuses']==old_book['statuses']
        assert len(service.db.list_books())==1 and _tree(original)==before
        assert json.loads(package_file(Path(adopted['folder']),'PACKAGE_SOURCE_RECORD.json').read_text())['title_page_style']==style

@pytest.mark.parametrize('text',['Change title to "Other"','Change count to 60','Make it harder'])
def test_ws_other_revisions_are_held(owned_ws,text):
    root,context,*_=owned_ws
    with pytest.raises(ValueError,match='title page design revisions only'):revision_plan(root,text,context)


def test_ws_unconfirmed_and_source_drift_fail_closed(owned_ws):
    root,context,original,service,source=owned_ws;p=revision_plan(root,'Change title page design to "Modern Minimal"',context)
    save_revision_plan(root,p)
    with pytest.raises(ValueError,match='not confirmed'):stage_revision(root,p.revision_id)
    save_revision_plan(root,p);confirm_revision_plan(root,p,context);source.write_text('{"owner":"changed"}')
    with pytest.raises(ValueError,match='theme changed'):stage_revision(root,p.revision_id)
    assert not (root/'data/studio_revision_candidates').exists()


def test_adoption_independently_detects_resource_drift_even_if_hashes_refrozen(owned_ws):
    from io import BytesIO
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import NameObject
    from publishing.studio_recovery import StudioDraftStore
    root,context,original,service,source=owned_ws;before=service.db.get_book(context['book_id'])
    p=revision_plan(root,'Change title page design to "Modern Minimal"',context);save_revision_plan(root,p);confirm_revision_plan(root,p,context)
    result=stage_revision(root,p.revision_id);folder=Path(result['folder']);pdf=package_file(folder,'interior.pdf')
    reader=PdfReader(pdf);writer=PdfWriter()
    for page in reader.pages:writer.add_page(page)
    fonts=writer.pages[1]['/Resources']['/Font'];next(iter(fonts.values())).get_object()[NameObject('/BaseFont')]=NameObject('/Courier')
    buffer=BytesIO();writer.write(buffer);pdf.write_bytes(buffer.getvalue())
    manifest=pdf.with_suffix('.puzzles.json');raw=json.loads(manifest.read_text());raw['pdf_sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest();manifest.write_text(json.dumps(raw))
    store=StudioDraftStore(root/'data/books.db');saved=store.load(p.revision_id);saved['payload']['chat_revision']['result']['candidate_sha256']=_tree(folder);store.save(p.revision_id,'book_plan',saved['payload'])
    pending={**context,'pending_semantic_revision':{'revision_id':p.revision_id}};confirm_adoption(root,p.revision_id,pending)
    with pytest.raises(ValueError,match='pages/resources changed'):adopt_revision(root,p.revision_id)
    assert service.db.get_book(context['book_id'])==before


def test_stage_recovers_after_completed_copy_before_result_checkpoint(owned_ws,monkeypatch):
    import publishing.studio_chat_revisions as revisions
    root,context,original,service,source=owned_ws;p=revision_plan(root,'Change title page design to "Modern Minimal"',context)
    save_revision_plan(root,p);confirm_revision_plan(root,p,context);real=revisions._state;failed=[False]
    def interrupt(root,plan,status,**extra):
        if status=='complete' and not failed[0]:failed[0]=True;raise RuntimeError('Simulated interruption before completion checkpoint')
        return real(root,plan,status,**extra)
    monkeypatch.setattr(revisions,'_state',interrupt)
    with pytest.raises(RuntimeError,match='Simulated interruption'):stage_revision(root,p.revision_id)
    candidate=root/'data/studio_revision_candidates'/p.revision_id/'candidate';before=_tree(candidate)
    monkeypatch.setattr('publishing.studio_title_page_candidate.render_title_page',lambda *a,**k:pytest.fail('Recovery regenerated the completed title page'))
    result=stage_revision(root,p.revision_id)
    assert Path(result['folder'])==candidate and _tree(candidate)==before


def test_stage_preserves_partial_copy_and_recovers_in_sibling(owned_ws,monkeypatch):
    import publishing.studio_title_page_candidate as copier
    root,context,original,service,source=owned_ws;p=revision_plan(root,'Change title page design to "Modern Minimal"',context)
    save_revision_plan(root,p);confirm_revision_plan(root,p,context);real=copier.shutil.copytree
    def interrupt(source,destination,*a,**k):
        Path(destination).mkdir();(Path(destination)/'keep.txt').write_text('partial work preserved');raise OSError('Simulated partial copy interruption')
    monkeypatch.setattr(copier.shutil,'copytree',interrupt)
    with pytest.raises(OSError,match='partial copy'):stage_revision(root,p.revision_id)
    partial=root/'data/studio_revision_candidates'/p.revision_id/'candidate';before=_tree(partial)
    monkeypatch.setattr(copier.shutil,'copytree',real)
    result=stage_revision(root,p.revision_id)
    assert Path(result['folder']).name=='candidate_recovery_001' and _tree(partial)==before
