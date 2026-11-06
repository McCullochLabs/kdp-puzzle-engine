import pytest
import sudoku

class CanvasSpy:
    def getPageNumber(self):return 1
    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return lambda *a,**k:None

@pytest.mark.parametrize('size,role',[(28,'puzzle'),(20,'solution'),(28,'solution'),(13,'puzzle')])
def test_explicit_region_role_is_independent_of_font_size(size,role):
    c=CanvasSpy();sudoku.draw_sudoku(c,[[0]*9 for _ in range(9)],60,720,40,'Helvetica',size,region_role=role)
    assert c._puzzle_text_regions==[{'page':1,'role':role,'bounds':[60,360,420,720],'font_pt':size}]

@pytest.mark.parametrize('size,role',[(28,'puzzle'),(20,'puzzle'),(17,'solution')])
def test_legacy_default_is_unchanged(size,role):
    c=CanvasSpy();sudoku.draw_sudoku(c,[[0]*9 for _ in range(9)],60,720,40,'Helvetica',size)
    assert c._puzzle_text_regions[0]['role']==role

def test_invalid_role_fails_before_any_region_record():
    c=CanvasSpy()
    with pytest.raises(ValueError,match='region role'):sudoku.draw_sudoku(c,[[0]*9 for _ in range(9)],60,720,40,'Helvetica',20,region_role='answer-ish')
    assert not hasattr(c,'_puzzle_text_regions')
