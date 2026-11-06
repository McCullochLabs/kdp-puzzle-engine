from dataclasses import FrozenInstanceError
import pytest
from publishing.sudoku_typography import SudokuTypography,resolve_typography

@pytest.mark.parametrize('values',[{'schema_version':2},{'schema_version':True},{'puzzle_font_pt':True},{'puzzle_font_pt':27},{'puzzle_font_pt':35},{'puzzle_font_pt':float('nan')},{'solution_font_pt':float('inf')},{'solution_font_pt':16},{'solution_font_pt':23},{'solution_font_pt':'20'}])
def test_invalid_config_rejected(values):
    with pytest.raises(ValueError):SudokuTypography(**values)

def test_versioned_roundtrip_is_exact_and_immutable():
    config=SudokuTypography(puzzle_font_pt=34,solution_font_pt=22)
    assert SudokuTypography.from_dict(config.to_dict())==config
    with pytest.raises(FrozenInstanceError):config.puzzle_font_pt=30
    for value in ({}, {'schema_version':1,'puzzle_font_pt':28,'solution_font_pt':17,'approved':True}):
        with pytest.raises(ValueError):SudokuTypography.from_dict(value)
    with pytest.raises(ValueError):resolve_typography(config.to_dict())
    assert resolve_typography()==SudokuTypography()

class CanvasSpy:
    def __init__(self):self.page=3
    def getPageNumber(self):return self.page
    def showPage(self):self.page+=1
    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return lambda *a,**k:None

def test_renderer_changes_only_text_sizes_preserving_grids_pages_and_shape_geometry(monkeypatch):
    import puzzle_book_studio as studio
    import sudoku
    calls=[]
    def draw(c,grid,x,y,cell,font,size,**kwargs):calls.append((grid,x,y,cell,size,kwargs))
    monkeypatch.setattr(sudoku,'draw_sudoku',draw)
    monkeypatch.setattr(studio,'font',lambda name:'Helvetica')
    for name in ('themed_running_header','themed_solution_header','footer','title'):
        monkeypatch.setattr(studio,name,lambda *a,**k:None)
    standard=CanvasSpy();standard_end=studio.sudoku_book(standard,3,'Easy',42)
    baseline=list(calls);calls.clear()
    larger=CanvasSpy();larger_end=studio.sudoku_book(larger,3,'Easy',42,typography=SudokuTypography(puzzle_font_pt=34,solution_font_pt=22))
    assert standard_end==larger_end and standard._puzzle_records==larger._puzzle_records
    assert [call[4] for call in baseline]==[28,28,28,17,17,17]
    assert [call[4] for call in calls]==[34,34,28,22,22,17]
    for before,after in zip(baseline,calls):
        assert before[:4]==after[:4] and before[5]==after[5]
    assert [c[5]['region_role'] for c in calls]==['puzzle']*3+['solution']*3

def test_invalid_renderer_config_fails_before_generation(monkeypatch):
    import puzzle_book_studio as studio
    import sudoku
    monkeypatch.setattr(sudoku,'make_solved',lambda *a:pytest.fail('Invalid config reached generation'))
    with pytest.raises(ValueError):studio.sudoku_book(CanvasSpy(),3,'Easy',42,typography={'puzzle_font_pt':99})
