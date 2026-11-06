from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
import puzzle_book_studio as studio
from test_studio_chat_revisions import owned
from publishing.studio_chat_revisions import revision_plan,save_revision_plan,confirm_revision_plan,stage_revision,_source_snapshot
from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,reject_revision,_tree
from publishing.studio_recovery import StudioDraftStore


@pytest.fixture
def staged(owned,monkeypatch):
    from publishing.package_layout import initialize_package_layout,package_file
    from reportlab.pdfgen import canvas
    root,context,original,service,manifest=owned
    plan=revision_plan(root,'Make it harder',context);save_revision_plan(root,plan);confirm_revision_plan(root,plan,context)
    def build(kind,title,subtitle,author,count,difficulty,seed,**kw):
        folder=Path(kw['output_parent'])/'candidate';initialize_package_layout(folder)
        c=canvas.Canvas(str(package_file(folder,'interior.pdf',for_write=True)))
        for _ in range(count*2+4):c.drawString(80,600,'Candidate fixture');c.showPage()
        c.save()
        updated=dict(manifest,title=title,subtitle=subtitle,author=author,puzzle_count=count,difficulty=difficulty,puzzle_seed=seed)
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(updated))
        package_file(folder,'interior.pdf').with_suffix('.puzzles.json').write_bytes(package_file(original,'interior.pdf').with_suffix('.puzzles.json').read_bytes())
        return folder
    monkeypatch.setattr(studio,'create_package',build)
    monkeypatch.setattr('preflight.preflight',lambda p:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda p:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    result=stage_revision(root,plan.revision_id)
    pending={**context,'pending_semantic_revision':{'revision_id':plan.revision_id,'title':plan.title}}
    return root,context,original,service,plan,result,pending


def test_adoption_same_identity_preserves_original_and_supports_chain(staged):
    root,context,original,service,plan,result,pending=staged
    before=service.db.get_book(context['book_id']);hashes=_tree(original)
    confirm_adoption(root,plan.revision_id,pending)
    adopted=adopt_revision(root,plan.revision_id)
    after=service.db.get_book(context['book_id'])
    assert len(service.db.list_books())==1
    assert after['book_id']==before['book_id'] and after['source_key']==before['source_key']
    assert after['statuses']==before['statuses'] and after['metadata_locked']==before['metadata_locked']
    assert after['metadata']['difficulty_label']=='Hard'
    assert _tree(original)==hashes and Path(result['folder']).is_dir()
    assert after['package_path']==adopted['folder'] and Path(adopted['folder']).is_relative_to(root/'out')
    assert adopt_revision(root,plan.revision_id)==adopted
    updated={**context,'title':adopted['title']}
    next_plan=revision_plan(root,'Change puzzle count to 36',updated)
    assert next_plan.difficulty=='Hard' and next_plan.count==36


def test_unconfirmed_and_stale_context_cannot_adopt(staged):
    root,context,original,service,plan,result,pending=staged
    with pytest.raises(ValueError,match='Accept this exact'):adopt_revision(root,plan.revision_id)
    with pytest.raises(ValueError,match='exact staged'):confirm_adoption(root,plan.revision_id,{**pending,'book_id':'wrong'})


@pytest.mark.parametrize('drift',['source','candidate','lock','status','plan'])
def test_adoption_drift_never_updates_catalog(staged,drift):
    root,context,original,service,plan,result,pending=staged
    confirm_adoption(root,plan.revision_id,pending)
    if drift=='source':(original/'owner_note.txt').write_text('changed')
    if drift=='candidate':(Path(result['folder'])/'changed.txt').write_text('tampered')
    if drift=='lock':service.db.save_metadata(context['book_id'],service.db.get_book(context['book_id'])['metadata'],locked=True)
    if drift=='status':
        with service.db._connect() as db:db.execute("UPDATE marketplace_status SET status='Prepared' WHERE book_id=?",(context['book_id'],))
    if drift=='plan':
        store=StudioDraftStore(root/'data/books.db');draft=store.load(plan.revision_id)
        draft['payload']['chat_revision']['plan']['count']=36;store.save(plan.revision_id,'book_plan',draft['payload'])
    before=service.db.get_book(context['book_id'])
    with pytest.raises(ValueError):adopt_revision(root,plan.revision_id)
    assert service.db.get_book(context['book_id'])==before


def test_rejection_retains_candidate_and_never_changes_book(staged):
    root,context,original,service,plan,result,pending=staged
    before=service.db.list_books();files=_tree(Path(result['folder']))
    assert reject_revision(root,plan.revision_id,pending)==context
    assert reject_revision(root,plan.revision_id,pending)==context
    assert service.db.list_books()==before and _tree(Path(result['folder']))==files
    with pytest.raises(ValueError,match='completed'):confirm_adoption(root,plan.revision_id,pending)


def test_transaction_failure_rolls_back_catalog_and_recovery_then_retries(staged,monkeypatch):
    import publishing.studio_revision_adoption as adoption
    root,context,original,service,plan,result,pending=staged;confirm_adoption(root,plan.revision_id,pending)
    before=service.db.list_books();save=adoption._save_version;calls=[]
    def fail(db,draft,payload,completed=False):
        calls.append(True)
        if len(calls)==2:raise OSError('Simulated recovery save failure')
        return save(db,draft,payload,completed)
    monkeypatch.setattr(adoption,'_save_version',fail)
    with pytest.raises(OSError,match='recovery save'):adopt_revision(root,plan.revision_id)
    assert service.db.list_books()==before
    assert StudioDraftStore(root/'data/books.db').load(plan.revision_id)['payload']['chat_revision']['status']=='complete'
    monkeypatch.setattr(adoption,'_save_version',save)
    adopted=adopt_revision(root,plan.revision_id)
    assert adopted['book_id']==context['book_id']


def test_candidate_path_escape_is_rejected(staged):
    root,context,original,service,plan,result,pending=staged
    store=StudioDraftStore(root/'data/books.db');draft=store.load(plan.revision_id)
    draft['payload']['chat_revision']['result']['folder']=str(original)
    store.save(plan.revision_id,'book_plan',draft['payload']);confirm_adoption(root,plan.revision_id,pending)
    with pytest.raises(ValueError,match='outside'):adopt_revision(root,plan.revision_id)


def test_generic_sync_does_not_reimport_source_or_adopted_aliases(staged):
    root,context,original,service,plan,result,pending=staged
    # The initial owned record is protected too, before any semantic adoption.
    before=service.db.list_books();service.sync_output_packages()
    assert service.db.list_books()==before
    confirm_adoption(root,plan.revision_id,pending);adopt_revision(root,plan.revision_id)
    before=service.db.list_books();service.sync_output_packages()
    assert service.db.list_books()==before


@pytest.mark.parametrize('accept',[True,False])
def test_actual_tk_revision_decision_flow(staged,monkeypatch,accept):
    import time,tkinter as tk
    import word_search_creator as app_module
    root,context,original,service,plan,result,pending=staged
    monkeypatch.setattr(app_module,'load_app_preferences',lambda:{})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    try:app=app_module.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.withdraw();app.APP_DIR=root
        ui=app.family_studio;ui.context=dict(context)
        ui._receive_staged_revision(result)
        assert ui.proposal_button.cget('text')=='Accept staged revision'
        if accept:ui.proposal_button.invoke()
        else:ui.reject_revision_button.invoke()
        deadline=time.monotonic()+15
        while ui.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
        assert not ui.busy
        assert ui.context['book_id']==context['book_id'] and 'pending_semantic_revision' not in ui.context
        saved=StudioDraftStore(root/'data/books.db').load(plan.revision_id)['payload']['chat_revision']
        assert saved['status']==('adopted' if accept else 'rejected')
        if accept:assert service.db.get_book(context['book_id'])['metadata']['difficulty_label']=='Hard'
        else:assert service.db.get_book(context['book_id'])['package_path']==str(original)
    finally:app.destroy()
