import json,shutil
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import pytest
import puzzle_book_studio as studio
from test_studio_chat_revisions import owned
from publishing.studio_chat_families import studio_family_chat_plan
from publishing.studio_assistant import guide_request
from publishing.studio_chat_creation import save_creation_plan,confirm_creation_plan,_checkpoint,_plan_hash
from publishing.studio_chat_revisions import revision_plan,save_revision_plan,confirm_revision_plan,stage_revision
from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,reject_revision,_tree
from publishing.package_layout import package_file,initialize_package_layout
from publishing.metadata_service import build_metadata

@pytest.fixture(params=['Cryptogram','Word Scramble + Trivia','Mixed Brain Games'])
def family_owned(owned,monkeypatch,request):
    root,context,folder,service,manifest=owned;kind=request.param
    monkeypatch.setattr(studio,'content_check',lambda *a:(True,'reviewed fixture',240))
    text=f'Create a 24-puzzle {kind} book with seed 42 called "Family Fixture"'
    plan=studio_family_chat_plan(text,guide_request(text));save_creation_plan(root,plan);confirm_creation_plan(root,plan)
    manifest=dict(manifest,title=plan.title,subtitle=plan.subtitle,puzzle_type=kind,difficulty=plan.difficulty)
    package_file(folder,'PACKAGE_SOURCE_RECORD.json').write_text(json.dumps(manifest))
    meta=build_metadata({'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':kind,'detected_topic':plan.topic,'puzzle_count':24,'difficulty_label':plan.difficulty})
    meta.update(book_id=context['book_id'],trim_size='8.5x11',page_count=52,files=service._package_files(folder),production_status='Needs owner and platform review',puzzle_seed=42,studio_chat_creation={'draft_id':plan.draft_id,'plan_sha256':_plan_hash(plan)})
    service.db.save_metadata(context['book_id'],meta);_checkpoint(root,plan,'complete',result={'book_id':context['book_id'],'folder':str(folder),'pages':52})
    context={**context,'title':plan.title,'kind':kind}
    return root,context,folder,service,manifest

@pytest.mark.parametrize('change',['Change title to "Revised Family Fixture"','Change title page design to "Modern Minimal"'])
def test_family_stage_adopt_and_chain_preserves_identity_and_records(family_owned,monkeypatch,change):
    root,context,original,service,manifest=family_owned;before=_tree(original);book=service.db.get_book(context['book_id'])
    plan=revision_plan(root,change,context);assert plan.kind==context['kind'] and plan.expected_pages==52
    save_revision_plan(root,plan);confirm_revision_plan(root,plan,context)
    def build(kind,title,subtitle,author,count,difficulty,seed,**kw):
        assert kind==context['kind'] and count==24 and difficulty==manifest['difficulty']
        folder=Path(kw['output_parent'])/'candidate';initialize_package_layout(folder)
        shutil.copy2(package_file(original,'interior.pdf'),package_file(folder,'interior.pdf',for_write=True))
        shutil.copy2(package_file(original,'interior.pdf').with_suffix('.puzzles.json'),package_file(folder,'interior.pdf').with_suffix('.puzzles.json'))
        source=dict(manifest,title=title,subtitle=subtitle,title_page_style=kw['title_page_style'])
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(source));return folder
    monkeypatch.setattr(studio,'create_package',build)
    monkeypatch.setattr('preflight.preflight',lambda p:(True,[]));monkeypatch.setattr('publishing.package_layout.release_contract',lambda p:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    result=stage_revision(root,plan.revision_id);pending={**context,'pending_semantic_revision':{'revision_id':plan.revision_id}}
    confirm_adoption(root,plan.revision_id,pending);adopted=adopt_revision(root,plan.revision_id)
    updated=service.db.get_book(context['book_id'])
    assert adopted['kind']==context['kind'] and adopted['pages']==52 and len(service.db.list_books())==1
    assert updated['source_key']==book['source_key'] and updated['statuses']==book['statuses']
    assert updated['metadata']['puzzle_type']==context['kind'] and _tree(original)==before
    next_change='Change title to "Third Family Fixture"'
    assert revision_plan(root,next_change,{**context,'title':plan.title}).kind==context['kind']

@pytest.mark.parametrize('text',['Make it harder','Change puzzle count to 36'])
def test_family_count_and_difficulty_fail_closed(family_owned,text):
    root,context,*_=family_owned
    with pytest.raises(ValueError,match='title and title page design changes only'):revision_plan(root,text,context)


def test_actual_family_chat_design_plan(family_owned,monkeypatch):
    import gc,tkinter as tk
    import word_search_creator as desktop
    root,context,*_=family_owned
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',root,raising=False);monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.context=context
        f.prompt.set('Change title page design to "Modern Minimal"');f.send();app.update()
        import time
        deadline=time.monotonic()+5
        while f.busy and time.monotonic()<deadline:
            app.update();time.sleep(.01)
        assert not f.busy
        assert f._chat_revision_plan.kind==context['kind'] and f._chat_revision_plan.title_page_style=='Modern Minimal'
        assert f.proposal_button.cget('text')=='Create staged revision'
    finally:app.destroy();gc.collect()
