import copy
import json
import random

import pytest
from reportlab.pdfgen.canvas import Canvas

import sudoku
import wordsearch
from publishing.puzzle_integrity import occurrences, verify_wordsearch, write_manifest, verify_manifest, wordsearch_difficulty
from publishing.sudoku_difficulty import rate_sudoku
from publishing.product_qa import _text_metrics, rendered_page_metrics
from publishing.puzzle_integrity import verify_rendered_grids
from pypdf import PdfReader


def test_every_grid_has_all_unique_answers_across_short_word_seeds():
    words=['CAT','DOG','SUN','MAP','PEN','CUP']
    for seed in range(100):
        grid,cells,placed=wordsearch.generate_puzzle(words,rng=random.Random(seed))
        assert sorted(placed)==sorted(words)
        assert not verify_wordsearch(grid,cells,placed,words)


def test_impossible_or_duplicate_targets_stop_generation():
    with pytest.raises(ValueError,match='fits|fit'):
        wordsearch.generate_puzzle(['IMPOSSIBLE'],N=3)
    with pytest.raises(ValueError,match='unique'):
        wordsearch.generate_puzzle(['CAT','CAT'])
    with pytest.raises(ValueError,match='multiple'):
        wordsearch.generate_puzzle(['CAT','CATCH','CATTLE'])
    with pytest.raises(ValueError,match='duplicate'):
        wordsearch.clean_words(['ice cream','ice-cream'])


def test_embedded_single_target_and_palindrome_have_one_physical_path():
    grid,cells,words=wordsearch.generate_puzzle(['CAT','CATCH','EYE'],rng=random.Random(4))
    assert all(len(occurrences(grid,w))==1 for w in words)


def test_independent_checker_rejects_corruption_and_accidental_terms():
    grid,cells,words=wordsearch.generate_puzzle(['PENCIL','RULER'],rng=random.Random(3))
    bad=copy.deepcopy(grid); r,c=cells[0][0]; bad[r][c]='Z'
    assert verify_wordsearch(bad,cells,words)
    bad[0][:4]=list('SHIT')
    assert any('denylist' in e for e in verify_wordsearch(bad,cells,words))


def test_manifest_round_trip_detects_missing_answer_and_pdf_change(tmp_path):
    pdf=tmp_path/'interior.pdf'; c=Canvas(str(pdf)); c.drawString(54,700,'PUZZLE 1'); c.showPage(); c.drawString(54,700,'SOLUTION 1'); c.showPage(); c.save()
    grid,paths,words=wordsearch.generate_puzzle(['PENCIL','RULER'],directions=((0,1),(1,0)),rng=random.Random(2))
    row=dict(number=1,type='word_search',grid=grid,placements=paths,words=words,intended_words=words,
             directions=((0,1),(1,0)),solution_grid=grid,solution_placements=paths,puzzle_page=1,solution_page=2)
    path=write_manifest(pdf,[row]); data=json.loads(path.read_text())
    assert verify_manifest(pdf,data,2)==[]
    changed=copy.deepcopy(data); changed['puzzles'][0]['solution_page']=3
    assert verify_manifest(pdf,changed,2)
    changed=copy.deepcopy(data); changed['puzzles'][0]['solution_grid'][0][0]='Z'
    assert verify_manifest(pdf,changed,2)
    pdf.write_bytes(pdf.read_bytes()+b'\n% changed')
    assert any('current PDF' in e for e in verify_manifest(pdf,data,2))


def test_pdf_grid_readback_detects_a_wrong_render_even_with_valid_math(tmp_path):
    pdf=tmp_path/'interior.pdf'; wordsearch.register_fonts()
    grid,paths,words=wordsearch.generate_puzzle(['PENCIL','RULER'],rng=random.Random(2))
    c=Canvas(str(pdf)); wordsearch.draw_grid(c,grid,80,700,25,18); c.showPage()
    wordsearch.draw_grid(c,grid,80,700,25,18,highlights=paths); c.showPage(); c.save()
    row=dict(number=1,type='word_search',grid=grid,placements=paths,words=words,solution_grid=grid,
             solution_placements=paths,puzzle_page=1,solution_page=2)
    data=json.loads(write_manifest(pdf,[row],c._puzzle_text_regions).read_text())
    metrics=rendered_page_metrics(pdf)
    result=verify_rendered_grids(data,metrics)
    assert not result['errors'] and result['grids_checked']==2
    data['puzzles'][0]['grid'][0][0]='Z' if grid[0][0]!='Z' else 'Y'
    assert verify_rendered_grids(data,metrics)['errors']


def test_sudoku_rating_reports_logic_and_preserves_input():
    puzzle=[[int(c) for c in line] for line in ['530070000','600195000','098000060','800060003','400803001','700020006','060000280','000419005','000080079']]
    before=copy.deepcopy(puzzle); rating=rate_sudoku(puzzle)
    assert puzzle==before and rating['label']=='easy'
    assert rating['solved_by_supported_logic']
    assert rate_sudoku([[0]*9 for _ in range(9)])['label']=='hard'
    with pytest.raises(ValueError,match='conflicting'):
        rate_sudoku([[1]*9 for _ in range(9)])


@pytest.mark.parametrize('level',['easy','medium','hard'])
def test_requested_sudoku_band_is_matched_and_unique(level):
    rng=random.Random(41); solution=sudoku.make_solved(rng)
    puzzle,rating=sudoku.make_rated_puzzle(solution,level,rng)
    assert rating['label']==level
    assert sudoku.count_solutions([r[:] for r in puzzle],2)==1
    assert all(not puzzle[r][c] or puzzle[r][c]==solution[r][c] for r in range(9) for c in range(9))


def test_sudoku_manifest_rejects_corrupt_givens(tmp_path):
    pdf=tmp_path/'interior.pdf'; pdf.write_bytes(b'fixture')
    rng=random.Random(1); solution=sudoku.make_solved(rng); puzzle=sudoku.make_puzzle(solution,'easy',rng)
    row=dict(number=1,type='sudoku',grid=puzzle,solution_grid=solution,puzzle_page=1,solution_page=2)
    data=json.loads(write_manifest(pdf,[row]).read_text())
    assert verify_manifest(pdf,data,2)==[]
    data['puzzles'][0]['grid'][0][0]=10
    assert verify_manifest(pdf,data,2)


def test_pdf_transform_and_glyph_extents_include_right_edge(tmp_path):
    pdf=tmp_path/'scaled.pdf'; c=Canvas(str(pdf)); c.translate(100,200); c.scale(.5,.5)
    c.setFont('Helvetica',20); c.drawString(20,40,'MEASURE'); c.showPage(); c.save()
    metrics=_text_metrics(PdfReader(pdf).pages[0])
    assert metrics['positions'][0][:2]==pytest.approx((110,220))
    assert metrics['font_sizes'][0]==pytest.approx(10)
    glyphs=rendered_page_metrics(pdf)[0]['glyphs']
    assert min(g[1] for g in glyphs)>100
    assert max(g[3] for g in glyphs)>min(g[1] for g in glyphs)+30


def test_grade7_source_and_measured_progression():
    from build_grade7_combo import load_source,plan_book
    data=load_source(); rows,_=plan_book(data,20261022)
    assert len(rows)==50
    assert sum(r['type']=='word_search' for r in rows)==25
    assert all(r['difficulty']['solved_by_supported_logic'] for r in rows if r['type']=='sudoku')
    assert {r['difficulty']['label'] for r in rows if r['type']=='sudoku'}=={'easy','medium'}
    assert rows==plan_book(data,20261022)[0]


@pytest.mark.parametrize('kind',['Sudoku','Cryptogram','Word Scramble + Trivia','Mixed Brain Games'])
def test_studio_writes_complete_pdf_bound_answers(kind,tmp_path):
    from puzzle_book_studio import make_interior
    pdf=tmp_path/'interior.pdf'
    make_interior(kind,'Test book','Puzzles with answers','Jordan M. Slade',6,'Easy',9124,pdf)
    data=json.loads(pdf.with_suffix('.puzzles.json').read_text())
    assert data['puzzle_count']==6
    assert verify_manifest(pdf,data,len(PdfReader(pdf).pages))==[]


@pytest.mark.parametrize('kind',['Cryptogram','Word Scramble + Trivia','Mixed Brain Games'])
def test_final_qa_checks_actual_text_game_questions_and_answers(kind,tmp_path):
    from puzzle_book_studio import make_interior
    from publishing.product_qa import inspect_product
    pdf=tmp_path/'interior.pdf'
    make_interior(kind,'Test book','Games with answers','Jordan M. Slade',6,'Easy',9124,pdf)
    report=inspect_product(tmp_path,tmp_path,{'puzzle_count':6})
    assert next(r for r in report.findings if r.check_id=='puzzle.answer_integrity').passed


def test_cover_combined_preview_draws_all_nine_sudoku_rows(monkeypatch):
    import cover
    class Drawing:
        def __init__(self): self.strings=[]; self.lines=[]
        def textlength(self,text,**kwargs): return len(text)*10
        def text(self,point,text,**kwargs): self.strings.append(text)
        def line(self,points,**kwargs): self.lines.append(points)
    monkeypatch.setattr(cover,'COVER_PUZZLE_TYPE','Word Search + Sudoku')
    monkeypatch.setattr(cover,'COVER_SAMPLE_WORDSEARCH','A'*225)
    monkeypatch.setattr(cover,'COVER_SAMPLE_SUDOKU','123456789'*9)
    drawing=Drawing(); cover.puzzle_type_hero(drawing,1000,1000,100,'#777777','#111111','#ffffff')
    assert len([s for s in drawing.strings if s.isdigit()])==81
    assert 'WORD SEARCH EXCERPT' in drawing.strings


def test_quality_policy_invalidates_cached_generation(monkeypatch):
    from publishing.production_orchestrator import component_fingerprints
    from publishing.production_autopilot import ProductionAutopilot
    import publishing.puzzle_integrity as integrity
    first=component_fingerprints({'book_id':'quality-test'})
    first_auto=ProductionAutopilot.stage_fingerprint({'fingerprint':'fixture'},'interior')
    monkeypatch.setattr(integrity,'POLICY_REVISION','future-policy')
    second=component_fingerprints({'book_id':'quality-test'})
    assert first['generation']!=second['generation']
    assert first['cover']!=second['cover']
    assert first_auto!=ProductionAutopilot.stage_fingerprint({'fingerprint':'fixture'},'interior')
