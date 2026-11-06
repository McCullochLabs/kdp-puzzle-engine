from dataclasses import asdict,replace
import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
import word_search_creator as studio
from publishing.studio_assistant import AssistantIntent
from publishing.studio_chat_creation import _plan_hash,save_creation_plan
from publishing.studio_recovery import StudioDraftStore
from publishing.studio_chat_wordsearch import (wordsearch_chat_plan,validate_saved_wordsearch_plan,
    wordsearch_plan_text,build_wordsearch_chat_plan)

REQUEST='Create a 48-puzzle Space word search book with seed 42'
INTENT=AssistantIntent(action='create_book',kind='Word Search',topic='Space')


@pytest.fixture
def library(tmp_path,monkeypatch):
    monkeypatch.setattr(studio,'APP_DIR',tmp_path);monkeypatch.setattr(studio,'OUTPUT_DIR',tmp_path/'out')
    for name in ('Guided_Builder_Master_Word_Bank.json','word_intelligence/word_store.json'):
        p=tmp_path/'word_banks'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    art=tmp_path/'cover_assets/approved.png';art.parent.mkdir();art.write_bytes(b'fixture approved artwork')
    record={'asset_id':'fixture','sha256':hashlib.sha256(art.read_bytes()).hexdigest(),'approval_revision':'one','production_approved':True}
    class Index:
        def ledger_details(self,path):return record
        @staticmethod
        def production_selectable(row):return row['production_approved']
    monkeypatch.setattr('publishing.studio_chat_wordsearch._ReadOnlyAssetIndex',Index)
    monkeypatch.setattr('publishing.studio_chat_wordsearch._select_art',lambda data:{'file':str(art),'focus':'center'})
    monkeypatch.setattr(studio,'photo_choice_palette',lambda *a:'nature')
    monkeypatch.setattr(studio,'recommend_theme_from_words',lambda *a:{'palette':'nature','style':'photo'})
    def word(i):
        return ''.join(chr(65+(i//26**n)%26) for n in range(4))
    selected={'topic':'Space','source_topics':['Space'],'groups':[{'name':f'Puzzle {i+1}','words':[word(i*12+j) for j in range(12)]} for i in range(48)]}
    calls=[]
    def prepare(root,topic,count,per,seed,**kwargs):calls.append((count,per,seed,kwargs));return selected
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch',prepare)
    return tmp_path,selected,record,calls


def confirm(root,plan):
    save_creation_plan(root,plan)
    store=StudioDraftStore(root/'data/books.db');draft=store.load(plan.draft_id)
    draft['payload']['chat_creation']['status']='confirmed'
    draft['payload']['chat_creation']['confirmation']={'source':'studio_chat.create_button','plan_sha256':_plan_hash(plan)}
    store.save(plan.draft_id,'book_plan',draft['payload'])


def test_plan_freezes_exact_checked_groups_sources_art_and_settings(library):
    root,selected,record,calls=library
    plan=wordsearch_chat_plan(REQUEST,INTENT,root)
    assert plan.count==48 and plan.seed==42 and plan.kind=='Word Search'
    assert json.loads(plan.checked_theme_json)['puzzles']==selected['groups']
    assert len(json.loads(plan.source_sha256_json))==4
    assert plan.art_sha256==record['sha256']
    assert calls[0]==(48,12,42,{'minimum_puzzles':24,'max_word_length':20,'source_groups':(),'reader':'standard','balance':'Balanced'})
    assert 'exactly 48' in wordsearch_plan_text(plan) and 'no exact page target' in wordsearch_plan_text(plan)
    assert not (root/'data').exists()
    assert validate_saved_wordsearch_plan({'plan':asdict(plan)},root)==plan


def test_shortened_checked_selection_is_never_confirmed(library):
    root,selected,record,calls=library;selected['groups']=selected['groups'][:36]
    with pytest.raises(ValueError,match='36 puzzles.*rather than 48'):wordsearch_chat_plan(REQUEST,INTENT,root)
    assert not (root/'data').exists()


@pytest.mark.parametrize('change',['seed','groups','settings','source','art','approval'])
def test_saved_plan_drift_fails_closed(library,change):
    root,selected,record,calls=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root)
    if change=='seed':plan=replace(plan,seed=43)
    if change=='groups':plan=replace(plan,checked_theme_json=plan.checked_theme_json.replace('AAAA','WRONG'))
    if change=='settings':plan=replace(plan,settings_json=plan.settings_json.replace('center','left'))
    if change=='source':(root/'word_banks/Guided_Builder_Master_Word_Bank.json').write_text('{"changed":true}')
    if change=='art':Path(plan.art_path).write_bytes(b'changed artwork')
    if change=='approval':record['production_approved']=False
    with pytest.raises(ValueError):validate_saved_wordsearch_plan({'plan':asdict(plan)},root)


@pytest.mark.parametrize('extra',['for seniors','large-print','100 pages','easy difficulty','Signature Edition','without answers','with blue cover','for kids','with 24 puzzles'])
def test_unsupported_requested_variants_are_honestly_rejected(library,extra):
    root,*_=library
    with pytest.raises(ValueError):wordsearch_chat_plan(REQUEST+' '+extra,INTENT,root)


def test_confirmation_required_before_gate_or_runner(library,monkeypatch):
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root)
    monkeypatch.setattr(studio,'prepare_wordsearch_production_gate',lambda *a:pytest.fail('Unconfirmed gate called'))
    with pytest.raises(ValueError,match='must be confirmed'):build_wordsearch_chat_plan(root,plan)
    assert not (root/'data/studio_wordsearch_drafts').exists()


def test_gate_failure_never_runs_or_acquires_job(library,monkeypatch):
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    events=[]
    pilot=SimpleNamespace(fail=lambda *a,**k:events.append(a))
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',staticmethod(lambda *a:(pilot,{})))
    monkeypatch.setattr(studio,'prepare_wordsearch_production_gate',lambda *a:(['production minimum failed'],['warning'],[]))
    monkeypatch.setattr(studio.WordSearchCreator,'_run_studio_package',lambda *a,**k:pytest.fail('Gate was bypassed'))
    with pytest.raises(ValueError,match='production minimum failed'):build_wordsearch_chat_plan(root,plan)
    assert events[0][0]=='validate' and not (root/'data/production_job_queue.json').exists()


def test_existing_pipeline_is_invoked_with_gate_job_and_scoped_identity(library,monkeypatch):
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    events=[]
    pilot=SimpleNamespace(fail=lambda *a,**k:None,complete=lambda *a:events.append('validated'),stage_fingerprint=lambda *a:'fingerprint',attach_orchestrator=lambda *a:events.append('attached'))
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',staticmethod(lambda *a:(pilot,{})))
    monkeypatch.setattr(studio,'prepare_wordsearch_production_gate',lambda *a:([],[],[]))
    def run(owner,settings,seed,folder,warnings,autopilot,facts,queue,job_id,**kwargs):
        assert events==['validated','attached'] and kwargs=={'sync_catalog':False}
        assert job_id==plan.draft_id and folder==root/'out/studio_wordsearch_drafts'/plan.draft_id
        assert settings['archive_after_package'] is False and settings['signature_edition'] is False
        assert queue.status()['active']['job_id']==job_id
        owner._studio_package_finished(True,folder,'complete')
    monkeypatch.setattr(studio.WordSearchCreator,'_run_studio_package',run)
    result=build_wordsearch_chat_plan(root,plan)
    assert result==root/'out/studio_wordsearch_drafts'/plan.draft_id
    assert json.loads((root/'data/production_job_queue.json').read_text())['active'] is None


def test_shared_gate_retains_production_errors_and_signature_minimum(library,monkeypatch):
    root,*_=library;path=root/'theme.json';path.write_text(json.dumps({'puzzles':[{}]*48}))
    calls=[]
    def gate(*a):calls.append(a);return ['existing error'],['existing warning'],['existing note']
    monkeypatch.setattr(studio,'production_stop_errors',gate)
    settings={'theme':str(path),'signature_edition':True}
    errors,warnings,notes=studio.prepare_wordsearch_production_gate(path,42,settings)
    assert calls==[(path,42,settings)]
    assert errors[0]=='existing error' and any('require 100 puzzles' in e for e in errors)
    assert warnings==['existing warning'] and notes==['existing note']
    calls.clear();errors,_,_=studio.prepare_wordsearch_production_gate(root/'other.json',42,settings)
    assert errors and not calls


def test_canonical_project_is_required(library):
    root,*_=library
    with pytest.raises(ValueError,match='does not match'):wordsearch_chat_plan(REQUEST,INTENT,root/'other')


def test_owned_theme_collision_is_preserved_before_production(library,monkeypatch):
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    source=Path(json.loads(plan.settings_json)['theme']);source.parent.mkdir(parents=True)
    source.write_text('existing owner content')
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',lambda *a:pytest.fail('Changed owned source reached production'))
    with pytest.raises(ValueError,match='owned checked theme changed'):build_wordsearch_chat_plan(root,plan)
    assert source.read_text()=='existing owner content'


def test_draft_directory_junction_is_rejected_without_writes(library,monkeypatch):
    import os,subprocess
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    outside=root.parent/(root.name+'_outside');outside.mkdir();marker=outside/'preserve.txt';marker.write_text('unchanged')
    namespace=root/'data/studio_wordsearch_drafts';namespace.parent.mkdir(exist_ok=True)
    try:namespace.symlink_to(outside,target_is_directory=True)
    except OSError:
        if os.name!='nt':pytest.skip('Directory links unavailable')
        command=subprocess.run(['cmd','/c','mklink','/J',str(namespace),str(outside)],capture_output=True,text=True)
        if command.returncode:pytest.skip('Temporary junction unavailable')
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',lambda *a:pytest.fail('Escaped source reached production'))
    with pytest.raises(ValueError,match='links or junctions'):build_wordsearch_chat_plan(root,plan)
    assert list(outside.iterdir())==[marker] and marker.read_text()=='unchanged'


@pytest.mark.parametrize('suffix',['in French','as CSV','with cartoon illustrations','using diagonal-only words','with 30 rows','with mirrored answers'])
def test_unknown_suffix_cannot_be_silently_ignored(library,suffix):
    root,*_=library
    with pytest.raises(ValueError):wordsearch_chat_plan(REQUEST+' '+suffix,INTENT,root)


@pytest.mark.parametrize('utterance',[
    'Create a 48-puzzle Space word search book with seed 42',
    'Create a word search book about Space with 48 puzzles and seed 42',
    'Create a 48-puzzle Space word search book called "Star Journal 2" with seed 42',
])
def test_supported_literal_topic_count_title_and_seed_forms(library,utterance):
    root,*_=library
    plan=wordsearch_chat_plan(utterance,INTENT,root)
    assert plan.count==48 and plan.seed==42
    if 'called' in utterance:assert plan.title=='Star Journal 2'


def test_unknown_topic_phrase_is_never_replaced_by_a_keyword_preset(library,monkeypatch):
    root,*_=library;seen=[]
    def unavailable(root,topic,*args,**kwargs):
        seen.append(topic);raise ValueError('Literal topic unavailable')
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch',unavailable)
    with pytest.raises(ValueError,match='Literal topic unavailable'):
        wordsearch_chat_plan('Create a 48-puzzle Quantum Space Weather word search book',INTENT,root)
    assert seen==['Quantum Space Weather']


def test_nature_is_sent_as_literal_topic_not_guide_preset(library,monkeypatch):
    root,selected,*_=library;seen=[]
    def prepare(root,topic,*args,**kwargs):seen.append(topic);return dict(selected,topic=topic)
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch',prepare)
    plan=wordsearch_chat_plan('Create a 48-puzzle Nature word search book',INTENT,root)
    assert seen==['Nature'] and plan.topic=='Nature'


@pytest.mark.parametrize('assets',[[],[{'asset_id':'legacy','path':'cover_assets/legacy.png'}]])
def test_readonly_art_index_never_audits_promotes_or_writes(tmp_path,monkeypatch,assets):
    import publishing.studio_chat_wordsearch as backend
    registry=tmp_path/'registry.json';registry.write_text(json.dumps({'assets':assets}))
    index=backend._ReadOnlyAssetIndex(registry)
    def forbidden(*a,**kw):pytest.fail('Read-only selection attempted approval migration/write')
    monkeypatch.setattr(index,'audit_legacy_library',forbidden)
    monkeypatch.setattr(index,'refresh_derived_metadata',forbidden)
    monkeypatch.setattr(index,'save',forbidden)
    before=registry.read_bytes()
    index.ensure_provenance_audited()
    assert index.ledger_details(tmp_path/'cover_assets/legacy.png') is None
    monkeypatch.setattr(backend,'_ReadOnlyAssetIndex',lambda:index)
    assert backend._select_art({'title':'Space Word Search','detected_topic':'Space'}) is None
    assert registry.read_bytes()==before


@pytest.mark.parametrize('state',['confirmed','running','failed','complete'])
def test_confirmed_art_survives_usage_recommendation_changes(library,monkeypatch,state):
    root,selected,record,calls=library
    plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    store=StudioDraftStore(root/'data/books.db');draft=store.load(plan.draft_id)
    draft['payload']['chat_creation']['status']=state;store.save(plan.draft_id,'book_plan',draft['payload'])
    # Production usage alters selection scores, but cannot change the approved
    # asset already shown and confirmed by the owner.
    record['usage']=[{'title':plan.title,'package':'built'}];record['updated_at']='later usage timestamp'
    monkeypatch.setattr('publishing.studio_chat_wordsearch._select_art',lambda *a:pytest.fail('Confirmed art was reselected'))
    saved=store.load(plan.draft_id)['payload']['chat_creation']
    assert validate_saved_wordsearch_plan(saved,root)==plan


@pytest.mark.parametrize('drift',['image','approval','source','groups','design'])
def test_confirmed_pinning_still_rejects_art_source_or_design_drift(library,monkeypatch,drift):
    root,selected,record,calls=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    store=StudioDraftStore(root/'data/books.db');saved=store.load(plan.draft_id)['payload']['chat_creation']
    if drift=='image':Path(plan.art_path).write_bytes(b'changed actual image')
    if drift=='approval':record['production_approved']=False
    if drift=='source':(root/'word_banks/Guided_Builder_Master_Word_Bank.json').write_text('{"new":true}')
    if drift=='groups':selected['groups'][0]['words'][0]='CHANGED'
    if drift=='design':record['approval_revision']='new revision'
    monkeypatch.setattr('publishing.studio_chat_wordsearch._select_art',lambda *a:pytest.fail('Drift must not autochoose replacement art'))
    with pytest.raises(ValueError):validate_saved_wordsearch_plan(saved,root)


def test_fabricated_unpersisted_confirmation_cannot_pin_an_asset(library,monkeypatch):
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root)
    fake={'plan':asdict(plan),'status':'complete','confirmation':{'source':'studio_chat.create_button','plan_sha256':_plan_hash(plan)}}
    calls=[]
    monkeypatch.setattr('publishing.studio_chat_wordsearch._select_art',lambda *a:(calls.append(True),None)[1])
    with pytest.raises(ValueError,match='No approved matching'):validate_saved_wordsearch_plan(fake,root)
    assert calls and not (root/'data/books.db').exists()


def test_build_reuses_actual_confirmation_state_before_validation(library,monkeypatch):
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    monkeypatch.setattr('publishing.studio_chat_wordsearch._select_art',lambda *a:pytest.fail('Build discarded actual confirmed state'))
    pilot=SimpleNamespace(fail=lambda *a,**k:None)
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',staticmethod(lambda *a:(pilot,{})))
    monkeypatch.setattr(studio,'prepare_wordsearch_production_gate',lambda *a:(['stop after confirmed validation'],[],[]))
    with pytest.raises(ValueError,match='stop after confirmed validation'):build_wordsearch_chat_plan(root,plan)


def test_real_ws_pipeline_stops_after_interior_checkpoint_before_cover(library,monkeypatch):
    import threading
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    stop=threading.Event();events=[];commands=[]
    pilot=SimpleNamespace(fail=lambda stage,*a,**k:events.append(('failed',stage)),complete=lambda stage,*a,**k:events.append(('completed',stage)),stage_fingerprint=lambda *a:'fingerprint',attach_orchestrator=lambda *a:None,current_artifact=lambda *a:None)
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',staticmethod(lambda *a:(pilot,{'fingerprint':'fixture'})))
    monkeypatch.setattr(studio,'prepare_wordsearch_production_gate',lambda *a:([],[],[]))
    monkeypatch.setattr(studio,'BackgroundAssetIndex',lambda:SimpleNamespace(ledger_details=lambda *a:{'approved':True}))
    monkeypatch.setattr(studio,'log_plain_error',lambda *a:None)
    from publishing.package_layout import package_file
    def run(command,**kwargs):
        commands.append(command)
        target=Path(command[command.index('--out')+1]);target.write_bytes(b'preserve checked interior fixture')
        stop.set()
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(studio.subprocess,'run',run)
    with pytest.raises(ValueError,match='safe boundary'):
        build_wordsearch_chat_plan(root,plan,stop_event=stop)
    assert len(commands)==1 and commands[0][1]==str(studio.ENGINE)
    assert ('completed','generate') in events and ('failed','cover') in events
    folder=root/'out/studio_wordsearch_drafts'/plan.draft_id
    assert package_file(folder,'interior.pdf').read_bytes()==b'preserve checked interior fixture'
    assert not package_file(folder,'front_cover.png').exists()
    queue=json.loads((root/'data/production_job_queue.json').read_text())
    assert queue['active'] is None


def test_persisted_ws_stop_keeps_completed_interior_and_cover_checkpoints(library,monkeypatch):
    import threading
    from publishing.production_autopilot import ProductionAutopilot
    from publishing.package_layout import package_file
    from reportlab.pdfgen import canvas
    root,*_=library;plan=wordsearch_chat_plan(REQUEST,INTENT,root);confirm(root,plan)
    stop=threading.Event();facts={'fingerprint':'safe-stop-fixture'};commands=[]
    def begin(*args):
        pilot=ProductionAutopilot(root,plan.draft_id);pilot.begin(facts)
        # Persisted local checkpoint store is real; canonical orchestrator is outside this fixture.
        pilot.attach_orchestrator=lambda *a:None
        return pilot,facts
    monkeypatch.setattr(studio.WordSearchCreator,'_begin_wordsearch_autopilot',staticmethod(begin))
    monkeypatch.setattr(studio,'prepare_wordsearch_production_gate',lambda *a:([],[],[]))
    monkeypatch.setattr(studio,'BackgroundAssetIndex',lambda:SimpleNamespace(ledger_details=lambda *a:{'approved':True}))
    monkeypatch.setattr(studio,'log_plain_error',lambda *a:None)
    def run(command,**kwargs):
        commands.append(command);target=Path(command[command.index('--out')+1])
        if command[1]==str(studio.ENGINE):
            c=canvas.Canvas(str(target));c.drawString(80,600,'Synthetic interior checkpoint');c.showPage();c.save()
        else:target.write_bytes(b'preserved cover fixture');stop.set()
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(studio.subprocess,'run',run)
    with pytest.raises(ValueError,match='safe boundary'):build_wordsearch_chat_plan(root,plan,stop_event=stop)
    pilot=ProductionAutopilot(root,plan.draft_id);stages=pilot.record()['stages']
    assert stages['generate']['status']=='complete'
    assert stages['cover']['status']=='complete'
    assert stages['listing']['status']=='failed'
    folder=root/'out/studio_wordsearch_drafts'/plan.draft_id
    before={name:package_file(folder,name).read_bytes() for name in ('interior.pdf','front_cover.png')}
    # A fresh checkpoint-store instance must retain both artifacts even when the next run is stopped before subprocess work.
    monkeypatch.setattr(studio.subprocess,'run',lambda *a,**k:pytest.fail('Completed artifact was regenerated'))
    with pytest.raises(ValueError,match='safe boundary'):build_wordsearch_chat_plan(root,plan,stop_event=stop)
    fresh=ProductionAutopilot(root,plan.draft_id)
    for stage,name in [('generate','interior.pdf'),('cover','front_cover.png')]:
        assert fresh.current_artifact(stage,fresh.stage_fingerprint(facts,stage))==package_file(folder,name)
        assert package_file(folder,name).read_bytes()==before[name]
    assert len(commands)==2
    assert json.loads((root/'data/production_job_queue.json').read_text())['active'] is None
