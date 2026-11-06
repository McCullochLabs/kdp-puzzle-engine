import json,shutil
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import pytest
import puzzle_book_studio as studio
from test_studio_chat_revisions import owned
from publishing.studio_chat_revisions import _change,is_revision_request,revision_plan,save_revision_plan,confirm_revision_plan,stage_revision
from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,_tree
from publishing.package_layout import package_file,initialize_package_layout

@pytest.mark.parametrize('name',['Automatic','Classic Frame','Modern Minimal','Puzzle Motif','Themed Emblem','Corner Art','Signature'])
def test_named_existing_presets(name):
    text='Change title page design to "'+name.lower()+'"'
    assert is_revision_request(text) and _change(text)==('title_page_style',name)

@pytest.mark.parametrize('text',['Change title page design to blue','Change title page design to "Unknown"','Change title page design to "Modern Minimal" and publish','Change title page design to "Modern Minimal" and change title'])
def test_unsupported_design_changes_fail_closed(text):
    with pytest.raises(ValueError):_change(text)

@pytest.mark.parametrize('fault',[None,'style','puzzles'])
def test_design_stage_adoption_preserves_puzzles_art_and_original(owned,monkeypatch,fault):
    root,context,original,service,manifest=owned
    plan=revision_plan(root,'Change title page design to "Modern Minimal"',context)
    assert plan.title_page_style=='Modern Minimal' and plan.count==24 and plan.cover_art==manifest['cover_art']
    before=_tree(original);save_revision_plan(root,plan);confirm_revision_plan(root,plan,context)
    def build(kind,title,subtitle,author,count,difficulty,seed,**kw):
        folder=Path(kw['output_parent'])/'candidate';initialize_package_layout(folder)
        shutil.copy2(package_file(original,'interior.pdf'),package_file(folder,'interior.pdf',for_write=True))
        records=package_file(original,'interior.pdf').with_suffix('.puzzles.json').read_text()
        package_file(folder,'interior.pdf').with_suffix('.puzzles.json').write_text(records if fault!='puzzles' else '{"puzzles":[]}')
        updated=dict(manifest,title_page_style=kw['title_page_style'] if fault!='style' else 'Automatic')
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(updated))
        return folder
    monkeypatch.setattr(studio,'create_package',build)
    monkeypatch.setattr('preflight.preflight',lambda p:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda p:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    if fault:
        with pytest.raises(ValueError,match='facts/artwork|puzzles or answers'):stage_revision(root,plan.revision_id)
    else:
        result=stage_revision(root,plan.revision_id);pending={**context,'pending_semantic_revision':{'revision_id':plan.revision_id}}
        confirm_adoption(root,plan.revision_id,pending);adopted=adopt_revision(root,plan.revision_id)
        after=json.loads(package_file(Path(adopted['folder']),'PACKAGE_SOURCE_RECORD.json').read_text())
        assert after['title_page_style']=='Modern Minimal' and after['cover_art_sha256']==manifest['cover_art_sha256']
        assert len(service.db.list_books())==1 and adopted['book_id']==context['book_id']
        next_plan=revision_plan(root,'Make it harder',context)
        assert next_plan.title_page_style=='Modern Minimal'
        with pytest.raises(ValueError,match='already selected'):revision_plan(root,plan.request,context)
    assert _tree(original)==before


def test_actual_chat_prepares_design_revision_without_generating(owned,monkeypatch):
    import gc,tkinter as tk
    import word_search_creator as desktop
    root,context,*_=owned
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',root,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    monkeypatch.setattr(studio,'create_package',lambda *a,**k:pytest.fail('Unconfirmed generation'))
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
        assert f._chat_revision_plan.title_page_style=='Modern Minimal'
        assert f.proposal_button.cget('text')=='Create staged revision'
        assert 'title page design: Modern Minimal' in f.proposal_text.get()
    finally:app.destroy();gc.collect()
