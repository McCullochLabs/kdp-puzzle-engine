import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from publishing.sudoku_typography import SudokuTypography,package_typography,typography_facts,bind_typography,verify_typography_binding

def test_default_identity_and_custom_identity_are_distinct():
    facts={'fingerprint':'legacy','title':'Test'}
    assert package_typography('Sudoku',SudokuTypography()) is None
    assert typography_facts(facts,None) is facts
    a=typography_facts(facts,SudokuTypography(puzzle_font_pt=34,solution_font_pt=22))
    b=typography_facts(facts,SudokuTypography(puzzle_font_pt=30,solution_font_pt=20))
    assert len({facts['fingerprint'],a['fingerprint'],b['fingerprint']})==3
    assert facts=={'fingerprint':'legacy','title':'Test'}
    with pytest.raises(ValueError):package_typography('Cryptogram',SudokuTypography())

@pytest.mark.parametrize('drift',['pdf','manifest','config','unknown'])
def test_artifact_binding_detects_drift(tmp_path,drift):
    pdf=tmp_path/'interior.pdf';pdf.write_bytes(b'fixture PDF');pdf.with_suffix('.puzzles.json').write_bytes(b'fixture manifest')
    config=SudokuTypography(puzzle_font_pt=34,solution_font_pt=22);bind_typography(pdf,config);verify_typography_binding(pdf,config)
    if drift=='pdf':pdf.write_bytes(b'edited PDF')
    elif drift=='manifest':pdf.with_suffix('.puzzles.json').write_bytes(b'edited manifest')
    elif drift=='config':config=SudokuTypography(puzzle_font_pt=30,solution_font_pt=20)
    else:
        path=pdf.with_suffix('.typography.json');value=json.loads(path.read_text());value['approved']=True;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='binding changed'):verify_typography_binding(pdf,config)


def test_wrapper_preserves_legacy_kwargs_and_rejects_unsupported_before_work(tmp_path,monkeypatch):
    import puzzle_book_studio as studio
    monkeypatch.setattr(studio,'APP',tmp_path);calls=[]
    wrapped=studio._record_package_failure(lambda *a,**k:calls.append(k) or 'fixture')
    assert wrapped('Sudoku','Test','Subtitle','Author',24,'Easy',42)=='fixture'
    assert calls==[{'sync_catalog':True}]
    wrapped('Sudoku','Test','Subtitle','Author',24,'Easy',42,sudoku_typography=SudokuTypography())
    assert calls[-1]==calls[0]
    with pytest.raises(ValueError):wrapped('Cryptogram','Test','Subtitle','Author',24,'Easy',42,sudoku_typography=SudokuTypography())
    assert len(calls)==2 and not (tmp_path/'data').exists()

@pytest.mark.parametrize('drift',[None,'pdf','source'])
def test_complete_package_reuse_requires_config_and_exact_artifact_binding(tmp_path,monkeypatch,drift):
    import puzzle_book_studio as studio
    import publishing.production_autopilot as auto
    from publishing.package_layout import initialize_package_layout,package_file
    config=SudokuTypography(puzzle_font_pt=34,solution_font_pt=22);folder=tmp_path/'out/cached';initialize_package_layout(folder)
    pdf=package_file(folder,'interior.pdf',for_write=True);pdf.write_bytes(b'fixture PDF');pdf.with_suffix('.puzzles.json').write_bytes(b'fixture manifest');bind_typography(pdf,config)
    source=package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True);source.write_text(json.dumps({'sudoku_typography':config.to_dict()}))
    if drift=='pdf':pdf.write_bytes(b'changed PDF')
    if drift=='source':source.write_text(json.dumps({'sudoku_typography':SudokuTypography().to_dict()}))
    base={'fingerprint':'base'};facts=typography_facts(base,config)
    stage=auto.ProductionAutopilot.stage_fingerprint
    prior={'status':'complete','artifact':str(folder),'fingerprint':stage(facts,'package')}
    pilot=SimpleNamespace(begin=lambda *a:None,complete=lambda *a,**k:None,fail=lambda *a,**k:None,attach_orchestrator=lambda *a:None,record=lambda:{'stages':{'package':prior}},stage_fingerprint=stage)
    monkeypatch.setattr(studio,'APP',tmp_path);monkeypatch.setattr(auto,'canonical_facts',lambda *a:base);monkeypatch.setattr(auto,'ProductionAutopilot',lambda *a:pilot)
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda *a:{'ready':True})
    monkeypatch.setattr(studio,'make_interior',lambda *a,**k:pytest.fail('Cached/held package regenerated'))
    if drift:
        with pytest.raises(ValueError):studio.create_package('Sudoku','Test','Subtitle','Jordan M. Slade',24,'Easy',42,sudoku_typography=config,sync_catalog=False)
    else:assert studio.create_package('Sudoku','Test','Subtitle','Jordan M. Slade',24,'Easy',42,sudoku_typography=config,sync_catalog=False)==folder


@pytest.mark.parametrize('config',[None,SudokuTypography(),SudokuTypography(puzzle_font_pt=34,solution_font_pt=22)])
def test_make_interior_forwards_only_nondefault_typography(tmp_path,monkeypatch,config):
    import puzzle_book_studio as studio
    calls=[]
    def render(*args,**kwargs):calls.append(kwargs);raise RuntimeError('renderer boundary reached')
    monkeypatch.setattr(studio,'sudoku_book',render)
    with pytest.raises(RuntimeError,match='renderer boundary reached'):
        studio.make_interior('Sudoku','Test','Subtitle','Author',3,'Easy',42,tmp_path/'fixture.pdf',sudoku_typography=config)
    assert calls==[{} if config in (None,SudokuTypography()) else {'typography':config}]


def test_fresh_package_forwards_config_to_interior(tmp_path,monkeypatch):
    import puzzle_book_studio as studio
    import publishing.production_autopilot as auto
    config=SudokuTypography(puzzle_font_pt=34,solution_font_pt=22);calls=[]
    stage=auto.ProductionAutopilot.stage_fingerprint
    pilot=SimpleNamespace(begin=lambda *a:None,complete=lambda *a,**k:None,fail=lambda *a,**k:None,attach_orchestrator=lambda *a:None,record=lambda:{'stages':{}},current_artifact=lambda *a:None,stage_fingerprint=stage)
    monkeypatch.setattr(studio,'APP',tmp_path);monkeypatch.setattr(auto,'ProductionAutopilot',lambda *a:pilot)
    def render(*args,**kwargs):calls.append(kwargs);raise RuntimeError('interior boundary reached')
    monkeypatch.setattr(studio,'make_interior',render)
    with pytest.raises(RuntimeError,match='interior boundary reached'):
        studio.create_package('Sudoku','Test','Subtitle','Jordan M. Slade',24,'Easy',42,sudoku_typography=config,sync_catalog=False)
    assert calls==[{'sudoku_typography':config}]
