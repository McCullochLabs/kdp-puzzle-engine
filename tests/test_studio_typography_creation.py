from dataclasses import asdict
import hashlib,json
from types import SimpleNamespace
import pytest
from publishing.studio_chat_creation import sudoku_chat_plan,TypographyChatBookPlan,ChatBookPlan,_validated_saved_plan,_plan_hash,save_creation_plan,confirm_creation_plan,create_chat_book
from publishing.studio_assistant import guide_request

BASE='Create an easy 24-puzzle Sudoku book with seed 42'
def make(request):return sudoku_chat_plan(request,guide_request(request))

def test_legacy_creation_has_same_raw_shape_and_hash():
    p=make(BASE);raw=asdict(p)
    assert type(p) is ChatBookPlan and 'plan_schema_version' not in raw and 'typography_config' not in raw
    assert asdict(_validated_saved_plan({'plan':raw}))==raw
    assert _plan_hash(p)==hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

@pytest.mark.parametrize('suffix,expected',[('with puzzle font size 34 points',(34,17)),('with solution font size 22 pt',(28,22)),('with puzzle font size 34 points and solution font size 22 points',(34,22)),('with solution font size 20 pt and puzzle font size 30 pt',(30,20))])
def test_versioned_creation_roundtrip(suffix,expected):
    p=make(BASE+' '+suffix)
    assert type(p) is TypographyChatBookPlan and p.seed==42 and p.count==24 and p.request.endswith(suffix)
    assert (p.typography.puzzle_font_pt,p.typography.solution_font_pt)==expected
    assert asdict(_validated_saved_plan({'plan':asdict(p)}))==asdict(p)
    raw=asdict(p);raw['typography_config']['puzzle_font_pt']=31
    with pytest.raises(ValueError):_validated_saved_plan({'plan':raw})

@pytest.mark.parametrize('suffix',['with puzzle font size 35 points','with solution font size 16 pt','with puzzle font size 34 points and puzzle font size 30 points','with puzzle font size 34 points and export it','with font size 34 points','with puzzle font size NaN points'])
def test_invalid_or_compound_requests_held(suffix):
    with pytest.raises(ValueError):make(BASE+' '+suffix)


@pytest.mark.parametrize('drift',[False,True])
def test_real_service_propagates_fonts_and_new_owned_revision_retains_config(tmp_path,monkeypatch,drift):
    from pathlib import Path
    import puzzle_book_studio as studio
    from publishing.package_layout import initialize_package_layout,package_file
    from publishing.sudoku_typography import bind_typography
    from publishing.studio_chat_revisions import revision_plan
    from reportlab.pdfgen import canvas
    p=make(BASE+' with puzzle font size 34 points and solution font size 22 points');save_creation_plan(tmp_path,p);confirm_creation_plan(tmp_path,p)
    art=tmp_path/'cover_assets/fixture.png';art.parent.mkdir();art.write_bytes(b'approved fixture')
    folder=tmp_path/'out/fixture';initialize_package_layout(folder);seen=[]
    def build(kind,title,subtitle,author,count,difficulty,seed,**kwargs):
        seen.append(kwargs['sudoku_typography'])
        pdf=package_file(folder,'interior.pdf',for_write=True);c=canvas.Canvas(str(pdf))
        for _ in range(52):c.drawString(80,600,'Synthetic creation fixture');c.showPage()
        c.save();pdf.with_suffix('.puzzles.json').write_text(json.dumps({'puzzles':[]}))
        source={'title':title,'subtitle':subtitle,'author':author,'puzzle_type':kind,'theme':kwargs['theme'],'difficulty':difficulty,'puzzle_count':count,'puzzle_seed':seed,'sudoku_typography':kwargs['sudoku_typography'].to_dict(),'cover_art':str(art),'cover_art_sha256':hashlib.sha256(art.read_bytes()).hexdigest(),'cover_style':'photo','interior_style':'Calm Modern','title_page_style':'Automatic'}
        package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(source));bind_typography(pdf,kwargs['sudoku_typography']);return folder
    monkeypatch.setattr(studio,'APP',tmp_path);monkeypatch.setattr(studio,'create_package',build)
    monkeypatch.setattr('preflight.preflight',lambda *a:(True,[]));monkeypatch.setattr('publishing.package_layout.release_contract',lambda *a:{'ready':True})
    def qa(*a,**k):
        if drift:package_file(folder,'PACKAGE_SOURCE_RECORD.json').write_text('{}')
        return SimpleNamespace(blockers=[],to_dict=lambda:{'summary':{'blockers':0}})
    monkeypatch.setattr('publishing.product_qa.inspect_product',qa)
    monkeypatch.setattr('background_generation.index.BackgroundAssetIndex',lambda:SimpleNamespace(ledger_details=lambda *a:{'fixture':True},production_selectable=lambda *a:True))
    if drift:
        from publishing.database import PublishingDatabase
        with pytest.raises(ValueError,match='source changed during QA'):create_chat_book(tmp_path,p.draft_id)
        assert PublishingDatabase(tmp_path/'data/books.db').list_books()==[]
        return
    result=create_chat_book(tmp_path,p.draft_id)
    assert seen==[p.typography]
    next_plan=revision_plan(tmp_path,'Set solution font size to 20 points',{'book_id':result['book_id']})
    assert next_plan.typography.puzzle_font_pt==34 and next_plan.typography.solution_font_pt==20


def test_actual_offline_creation_proposal_shows_versioned_fonts(tmp_path,monkeypatch):
    import tkinter as tk,gc
    import word_search_creator as desktop
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False);monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.prompt.set(BASE+' with puzzle font size 34 points and solution font size 22 points');f.send();app.update()
        assert isinstance(f._chat_creation_plan,TypographyChatBookPlan)
        assert 'puzzles 34 pt, solutions 22 pt' in f.proposal_text.get()
        assert f.proposal_button.cget('text')=='Create this book' and not f.busy
    finally:app.destroy();gc.collect()
