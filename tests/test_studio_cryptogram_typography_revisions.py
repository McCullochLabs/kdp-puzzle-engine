import json
from dataclasses import asdict
import pytest
from test_studio_family_revisions import family_owned
from test_studio_chat_revisions import owned
from publishing.studio_chat_revisions import revision_plan,load_revision_plan,CryptogramTypographyRevisionPlan
from publishing.cryptogram_typography import bind_typography

@pytest.mark.parametrize("family_owned", ["Cryptogram"], indirect=True)
def test_cryptogram_font_plan_uses_separate_version(family_owned):
    root,context,*_=family_owned
    plan=revision_plan(root,"Set puzzle font size to 22 points",context)
    assert type(plan) is CryptogramTypographyRevisionPlan and plan.plan_schema_version==3
    assert plan.typography.puzzle_font_pt==22 and plan.typography.solution_font_pt==11
    assert asdict(load_revision_plan(asdict(plan)))==asdict(plan)
    for value in (23,34):
        with pytest.raises(ValueError):revision_plan(root,f"Set puzzle font size to {value}",context)
    raw=asdict(plan);raw['plan_schema_version']=2
    with pytest.raises(ValueError):load_revision_plan(raw)

@pytest.mark.parametrize("family_owned", ["Cryptogram"], indirect=True)
def test_font_revision_stage_adopt_and_chain_preserve_legacy_identity(family_owned,monkeypatch):
    import shutil
    from pathlib import Path
    from types import SimpleNamespace
    import puzzle_book_studio as studio
    from publishing.package_layout import package_file
    from publishing.studio_chat_revisions import save_revision_plan,confirm_revision_plan,stage_revision
    from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,_tree
    root,context,original,service,manifest=family_owned
    before=service.db.get_book(context['book_id']);original_hashes=_tree(original)
    plan=revision_plan(root,'Set puzzle font size to 22 points',context);save_revision_plan(root,plan);confirm_revision_plan(root,plan,context)
    def build(kind,title,subtitle,author,count,difficulty,seed,**kwargs):
        folder=kwargs['output_parent']/'candidate';shutil.copytree(original,folder)
        source=dict(manifest);source['cryptogram_typography']=kwargs['cryptogram_typography'].to_dict()
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(source))
        bind_typography(package_file(folder,'interior.pdf'),kwargs['cryptogram_typography'])
        return folder
    monkeypatch.setattr(studio,'create_package',build)
    monkeypatch.setattr('preflight.preflight',lambda *a:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda *a:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    result=stage_revision(root,plan.revision_id);pending={**context,'pending_semantic_revision':{'revision_id':plan.revision_id}}
    confirm_adoption(root,plan.revision_id,pending);adopted=adopt_revision(root,plan.revision_id)
    after=service.db.get_book(context['book_id'])
    assert len(service.db.list_books())==1 and after['book_id']==before['book_id'] and after['source_key']==before['source_key']
    assert after['statuses']==before['statuses'] and after['metadata_locked']==before['metadata_locked']
    assert _tree(original)==original_hashes
    next_plan=revision_plan(root,'Set solution font size to 14',context)
    assert next_plan.typography.puzzle_font_pt==22 and next_plan.typography.solution_font_pt==14
    title_plan=revision_plan(root,'Change title to "Retained typography"',context)
    assert isinstance(title_plan,CryptogramTypographyRevisionPlan) and title_plan.typography.puzzle_font_pt==22
    assert adopted['folder']==after['package_path']


@pytest.mark.parametrize("family_owned", ["Cryptogram"], indirect=True)
def test_actual_offline_chat_proposes_versioned_font_revision(family_owned,monkeypatch):
    import gc,time,tkinter as tk
    import word_search_creator as desktop
    root,context,*_=family_owned
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',root,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.context=context;f.prompt.set('Set solution font size to 14 points');f.send();end=time.monotonic()+4
        while f.busy and time.monotonic()<end:app.update();time.sleep(.01)
        assert not f.busy and isinstance(f._chat_revision_plan,CryptogramTypographyRevisionPlan)
        assert f._chat_revision_plan.typography.solution_font_pt==14
        assert f.proposal_button.cget('text')=='Create staged revision'
        assert 'solutions 14 pt' in f.proposal_text.get() and f.context==context
    finally:app.destroy();gc.collect()
