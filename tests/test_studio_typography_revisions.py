from dataclasses import asdict
import hashlib,json
import pytest
from test_studio_chat_revisions import owned
from publishing.studio_chat_revisions import revision_plan,load_revision_plan,TypographyRevisionPlan,ChatRevisionPlan,_hash,_change,is_revision_request,revision_text,verify_revision_typography
from publishing.sudoku_typography import bind_typography


def test_old_plan_serialization_and_hash_are_unchanged(owned):
    root,context,*_=owned
    plan=revision_plan(root,'Change title to "Legacy Name"',context)
    raw=asdict(plan)
    assert type(plan) is ChatRevisionPlan and 'plan_schema_version' not in raw and 'typography_config' not in raw
    assert asdict(load_revision_plan(raw))==raw
    assert _hash(plan)==hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

@pytest.mark.parametrize('which,value',[('puzzle',34),('solution',22)])
def test_owned_sudoku_versioned_font_plan_roundtrip(owned,which,value):
    root,context,*_=owned;text=f'Set the {which} font size to {value} points'
    assert is_revision_request(text)
    plan=revision_plan(root,text,context)
    assert type(plan) is TypographyRevisionPlan and plan.plan_schema_version==2
    assert getattr(plan.typography,which+'_font_pt')==value
    assert asdict(load_revision_plan(asdict(plan)))==asdict(plan)
    assert 'Grid fonts:' in revision_text(plan)
    raw=asdict(plan);raw['plan_schema_version']=3
    with pytest.raises(ValueError):load_revision_plan(raw)
    raw=asdict(plan);raw['typography_config'][which+'_font_pt']=32 if which=='puzzle' else 20
    with pytest.raises(ValueError,match='does not match'):load_revision_plan(raw)

@pytest.mark.parametrize('text',['Set puzzle font size to 35','Set solution font size to 16','Set solution font size to 22 and export','Set puzzle font size to NaN'])
def test_invalid_font_commands_fail_closed(text):
    with pytest.raises(ValueError):_change(text)


def test_candidate_typography_and_puzzles_checked_independently(owned,tmp_path):
    from pathlib import Path
    from publishing.package_layout import initialize_package_layout,package_file
    root,context,*_=owned;plan=revision_plan(root,'Set puzzle font size to 34',context)
    folder=root/'data/studio_revision_candidates'/plan.revision_id/'fixture';initialize_package_layout(folder)
    pdf=package_file(folder,'interior.pdf',for_write=True);pdf.write_bytes(b'fixture PDF')
    original=package_file(Path(plan.source_snapshot['book']['package_path']),'interior.pdf').with_suffix('.puzzles.json')
    original.write_text(json.dumps({'puzzles':[{'answer':'preserved'}]}))
    pdf.with_suffix('.puzzles.json').write_bytes(original.read_bytes());bind_typography(pdf,plan.typography)
    source={'sudoku_typography':plan.typography.to_dict()}
    verify_revision_typography(plan,folder,source)
    with pytest.raises(ValueError,match='typography differs'):verify_revision_typography(plan,folder,{})
    pdf.with_suffix('.puzzles.json').write_text(json.dumps({'puzzles':[{'answer':'changed'}]}));bind_typography(pdf,plan.typography)
    with pytest.raises(ValueError,match='changed puzzles'):verify_revision_typography(plan,folder,source)


def test_font_revision_stage_adopt_and_chain_preserve_legacy_identity(owned,monkeypatch):
    import shutil
    from pathlib import Path
    from types import SimpleNamespace
    import puzzle_book_studio as studio
    from publishing.package_layout import package_file
    from publishing.studio_chat_revisions import save_revision_plan,confirm_revision_plan,stage_revision
    from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,_tree
    root,context,original,service,manifest=owned
    before=service.db.get_book(context['book_id']);original_hashes=_tree(original)
    plan=revision_plan(root,'Set puzzle font size to 34 points',context);save_revision_plan(root,plan);confirm_revision_plan(root,plan,context)
    def build(kind,title,subtitle,author,count,difficulty,seed,**kwargs):
        folder=kwargs['output_parent']/'candidate';shutil.copytree(original,folder)
        source=dict(manifest);source['sudoku_typography']=kwargs['sudoku_typography'].to_dict()
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(source))
        bind_typography(package_file(folder,'interior.pdf'),kwargs['sudoku_typography'])
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
    next_plan=revision_plan(root,'Set solution font size to 22',context)
    assert next_plan.typography.puzzle_font_pt==34 and next_plan.typography.solution_font_pt==22
    title_plan=revision_plan(root,'Change title to "Retained typography"',context)
    assert isinstance(title_plan,TypographyRevisionPlan) and title_plan.typography.puzzle_font_pt==34
    assert adopted['folder']==after['package_path']


def test_actual_offline_chat_proposes_versioned_font_revision(owned,monkeypatch):
    import gc,time,tkinter as tk
    import word_search_creator as desktop
    root,context,*_=owned
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',root,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.context=context;f.prompt.set('Set solution font size to 22 points');f.send();end=time.monotonic()+4
        while f.busy and time.monotonic()<end:app.update();time.sleep(.01)
        assert not f.busy and isinstance(f._chat_revision_plan,TypographyRevisionPlan)
        assert f._chat_revision_plan.typography.solution_font_pt==22
        assert f.proposal_button.cget('text')=='Create staged revision'
        assert 'solutions 22 pt' in f.proposal_text.get() and f.context==context
    finally:app.destroy();gc.collect()
