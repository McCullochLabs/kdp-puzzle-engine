from dataclasses import asdict
import hashlib,json,uuid
from pathlib import Path
from types import SimpleNamespace
import pytest
import puzzle_book_studio as studio
from publishing.studio_chat_creation import sudoku_chat_plan,save_creation_plan,confirm_creation_plan,_checkpoint,_plan_hash
from publishing.studio_assistant import guide_request,AssistantIntent
from publishing.studio_chat_revisions import _change,revision_plan,save_revision_plan,confirm_revision_plan,stage_revision


def test_default_scope_is_unchanged_and_staging_is_uuid_bound(tmp_path,monkeypatch):
    monkeypatch.setattr(studio,'APP',tmp_path);monkeypatch.setattr(studio,'OUT',tmp_path/'out')
    expected=hashlib.sha1(b'Sudoku|Same title').hexdigest()[:12]
    assert studio._production_scope('Sudoku','Same title')==(expected,tmp_path/'out')
    run=uuid.uuid4().hex;target=tmp_path/'data/studio_revision_candidates'/run
    assert studio._production_scope('Sudoku','Same title',run,target)==(run,target)
    for identity,path in [('bad',target),(uuid.uuid1().hex,target),(run,tmp_path/'out'),(run,target/'..')]:
        with pytest.raises(ValueError):studio._production_scope('Sudoku','Same title',identity,path)
    with pytest.raises(ValueError):studio._production_scope('Sudoku','Same title',None,target)


def test_failure_wrapper_preserves_default_and_revision_identity(tmp_path,monkeypatch):
    monkeypatch.setattr(studio,'APP',tmp_path)
    seen=[];failures=[]
    class Pilot:
        def __init__(self,root,identity):self.identity=identity
        def fail(self,*args,**kwargs):failures.append(self.identity)
    monkeypatch.setattr('publishing.production_autopilot.ProductionAutopilot',Pilot)
    def fail(*args,**kwargs):seen.append(kwargs);raise RuntimeError('fixture')
    wrapped=studio._record_package_failure(fail);run=uuid.uuid4().hex
    with pytest.raises(RuntimeError):wrapped('Sudoku','Title','Subtitle','Author',24,'Easy',42,sync_catalog=False,production_run_id=run)
    assert failures==[run] and seen[0]['production_run_id']==run and seen[0]['sync_catalog'] is False
    with pytest.raises(RuntimeError):wrapped('Sudoku','Title','Subtitle','Author',24,'Easy',42)
    assert failures[-1]==hashlib.sha1(b'Sudoku|Title').hexdigest()[:12]


@pytest.mark.parametrize('text,expected',[('Make it easier',('difficulty','Easy')),('Change difficulty to Hard',('difficulty','Hard')),
 ('Change puzzle count to 36',('count',36)),('Change title to "New Name"',('title','New Name'))])
def test_bounded_revision_commands(text,expected):assert _change(text)==expected


@pytest.mark.parametrize('text',['Change difficulty to expert','Change puzzle count to -24','Change puzzle count to 24.5',
 'Change title to Unquoted','Change puzzle count to 24 and title to "Other"','Add12puzzles','Change cover to blue'])
def test_unsupported_revision_is_not_silently_accepted(text):
    with pytest.raises(ValueError):_change(text)


@pytest.fixture
def owned(tmp_path,monkeypatch):
    from publishing.package_layout import initialize_package_layout,package_file
    from publishing.manager import PublishingService
    from publishing.metadata_service import build_metadata
    from reportlab.pdfgen import canvas
    monkeypatch.setattr(studio,'APP',tmp_path);monkeypatch.setattr(studio,'OUT',tmp_path/'out')
    request='Create an easy 24-puzzle Sudoku book with seed 42';plan=sudoku_chat_plan(request,guide_request(request))
    save_creation_plan(tmp_path,plan);confirm_creation_plan(tmp_path,plan)
    folder=tmp_path/'out/owned_source';initialize_package_layout(folder)
    art=tmp_path/'cover_assets/approved.png';art.parent.mkdir();art.write_bytes(b'approved fixture')
    c=canvas.Canvas(str(package_file(folder,'interior.pdf',for_write=True)))
    for _ in range(52):c.drawString(80,600,'Source fixture');c.showPage()
    c.save();package_file(folder,'interior.pdf').with_suffix('.puzzles.json').write_text('{"puzzles":[{"fixture":"same puzzle records"}]}')
    manifest={'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':'Sudoku','theme':plan.topic,'puzzle_count':24,
      'difficulty':'Easy','puzzle_seed':42,'cover_art':str(art),'cover_art_sha256':hashlib.sha256(art.read_bytes()).hexdigest(),
      'cover_style':'photo','interior_style':'Calm Modern','title_page_style':'Automatic'}
    package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(manifest))
    service=PublishingService(tmp_path);key='package:'+str(folder);identity=service._id(key)
    meta=build_metadata({'title':plan.title,'subtitle':plan.subtitle,'author':plan.author,'puzzle_type':'Sudoku','detected_topic':plan.topic,'puzzle_count':24,'difficulty_label':'Easy'})
    meta.update(book_id=identity,trim_size='8.5x11',page_count=52,files=service._package_files(folder),production_status='Needs owner and platform review',puzzle_seed=42,
                studio_chat_creation={'draft_id':plan.draft_id,'plan_sha256':_plan_hash(plan)})
    service.db.upsert_book(identity,key,meta,str(folder))
    _checkpoint(tmp_path,plan,'complete',result={'book_id':identity,'folder':str(folder),'pages':52})
    monkeypatch.setattr('background_generation.index.BackgroundAssetIndex',lambda:SimpleNamespace(ledger_details=lambda p:{'fixture':True},production_selectable=lambda p:True))
    context={'book_id':identity,'title':plan.title,'topic':plan.topic,'kind':'Sudoku'}
    return tmp_path,context,folder,service,manifest


def test_source_owner_changes_and_locks_fail_closed(owned):
    root,context,folder,service,manifest=owned
    plan=revision_plan(root,'Make it harder',context);assert plan.difficulty=='Hard'
    changed=dict(service.db.get_book(context['book_id'])['metadata']);changed['subtitle']='Owner edit';service.db.save_metadata(context['book_id'],changed)
    with pytest.raises(ValueError,match='metadata was edited'):revision_plan(root,'Make it harder',context)
    service.db.save_metadata(context['book_id'],changed,locked=True)
    with pytest.raises(ValueError,match='Locked'):revision_plan(root,'Make it harder',context)


def test_unconfirmed_or_changed_revision_source_never_generates(owned):
    root,context,folder,service,manifest=owned;p=revision_plan(root,'Make it harder',context);save_revision_plan(root,p)
    with pytest.raises(ValueError,match='not confirmed'):stage_revision(root,p.revision_id)
    save_revision_plan(root,p);confirm_revision_plan(root,p,context)
    (folder/'owner_note.txt').write_text('changed source')
    with pytest.raises(ValueError,match='Source or revision plan changed'):stage_revision(root,p.revision_id)


def test_staged_candidate_preserves_source_catalog_and_has_provenance(owned,monkeypatch):
    from publishing.package_layout import initialize_package_layout,package_file
    from reportlab.pdfgen import canvas
    root,context,folder,service,manifest=owned
    plan=revision_plan(root,'Change title to "New Candidate"',context);save_revision_plan(root,plan);confirm_revision_plan(root,plan,context)
    before=service.db.list_books();calls=[]
    def build(kind,title,subtitle,author,count,difficulty,seed,**kwargs):
        calls.append(kwargs);target=kwargs['output_parent']/'new_candidate';initialize_package_layout(target)
        c=canvas.Canvas(str(package_file(target,'interior.pdf',for_write=True)))
        for _ in range(count*2+4):c.drawString(80,600,'Candidate');c.showPage()
        c.save();updated=dict(manifest,title=title,subtitle=subtitle,puzzle_count=count,difficulty=difficulty,puzzle_seed=seed)
        package_file(target,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(updated))
        package_file(target,'interior.pdf').with_suffix('.puzzles.json').write_bytes(package_file(folder,'interior.pdf').with_suffix('.puzzles.json').read_bytes())
        return target
    monkeypatch.setattr(studio,'create_package',build)
    monkeypatch.setattr('preflight.preflight',lambda p:(True,[]))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda p:{'ready':True})
    monkeypatch.setattr('publishing.product_qa.inspect_product',lambda *a,**k:SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}}))
    result=stage_revision(root,plan.revision_id)
    assert result['status']=='STAGED_NOT_ADOPTED' and result['source_book_id']==context['book_id']
    assert service.db.list_books()==before and result['source_unchanged']
    assert Path(result['folder']).is_relative_to(root/'data/studio_revision_candidates')
    assert (Path(result['folder'])/'STAGED_REVISION_PROVENANCE.json').is_file()
    assert calls[0]['production_run_id']==plan.revision_id and calls[0]['sync_catalog'] is False
    assert stage_revision(root,plan.revision_id)==result and len(calls)==1


def test_pending_candidate_cannot_check_or_export_old_original():
    from publishing.family_studio import FamilyStudio
    messages=[];started=[]
    fake=SimpleNamespace(context={'book_id':'original','pending_semantic_revision':{'revision_id':'new'}},
        _last_request='Export this book',proposal_button=SimpleNamespace(configure=lambda **kw:None),
        _say=lambda role,text:messages.append(text),_check_selected_book=lambda *a,**k:started.append(True))
    FamilyStudio._receive_intent(fake,AssistantIntent(action='export_book'))
    assert not started and 'did not check or export the old original' in messages[-1]
    fake._last_request='Check this book';FamilyStudio._receive_intent(fake,AssistantIntent(action='check_book'))
    assert not started
    fake._last_request="Check this candidate's original artwork";FamilyStudio._receive_intent(fake,AssistantIntent(action='check_book'))
    assert not started
    fake._last_request='Export this candidate, not the original';FamilyStudio._receive_intent(fake,AssistantIntent(action='export_book'))
    assert not started
    with pytest.raises(ValueError,match='staged candidate is still pending'):revision_plan(Path('.'),'Make it harder',fake.context)


@pytest.mark.parametrize('link_position',['staging_parent','uuid_child'])
def test_revision_staging_rejects_temp_junction_escape(tmp_path,monkeypatch,link_position):
    import os,subprocess
    project=tmp_path/'project';project.mkdir();(project/'data').mkdir()
    monkeypatch.setattr(studio,'APP',project)
    run=uuid.uuid4().hex;staging=project/'data/studio_revision_candidates'
    target=tmp_path/'outside' if link_position=='staging_parent' else project/'out'
    target.mkdir();marker=target/'preserve.txt';marker.write_text('canonical data unchanged')
    if link_position=='staging_parent':link=staging
    else:staging.mkdir();link=staging/run
    try:link.symlink_to(target,target_is_directory=True)
    except OSError:
        if os.name!='nt':pytest.skip('Directory symlinks unavailable')
        completed=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True)
        if completed.returncode:pytest.skip('Temporary junction creation unavailable: '+completed.stderr)
    with pytest.raises(ValueError,match='symlinks or junctions|inside this project|local staging folder'):
        studio._production_scope('Sudoku','Original title',run,staging/run)
    assert marker.read_text()=='canonical data unchanged'
    assert list(target.iterdir())==[marker]


def test_revision_confirmation_rejects_a_different_selected_project(owned):
    root,context,folder,service,manifest=owned
    p=revision_plan(root,'Make it harder',context);save_revision_plan(root,p)
    with pytest.raises(ValueError,match='Selected project changed'):
        confirm_revision_plan(root,p,{**context,'book_id':'another-book'})


@pytest.mark.parametrize('raw,action',[("Don't export this book",'export_book'),('Never check this book','check_book'),('Do not create a Sudoku book','create_book')])
def test_model_proposal_cannot_override_raw_action_negation(raw,action):
    from publishing.family_studio import FamilyStudio
    messages=[];started=[]
    fake=SimpleNamespace(_last_request=raw,_say=lambda role,text:messages.append(text),
                         _check_selected_book=lambda *a,**k:started.append(True))
    FamilyStudio._receive_intent(fake,AssistantIntent(action=action,kind='Sudoku',topic='Space'))
    assert not started and fake.intent.action=='help'
    assert 'explicitly says not' in messages[0]


def test_cover_commands_keep_existing_cover_workshop_route():
 from publishing.studio_chat_revisions import is_revision_request
 from publishing.studio_assistant import guide_request
 for text in ('Change its cover','Change the cover to blue','Set its cover background'):
  assert not is_revision_request(text)
  assert guide_request(text,context={'book_id':'selected','topic':'Garden'}).action=='covers'
