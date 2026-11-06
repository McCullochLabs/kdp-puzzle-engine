import json
import pytest
import puzzle_book_studio as studio
from publishing.difficulty_claims import difficulty_description, cover_difficulty


@pytest.mark.parametrize('kind', ['Cryptogram', 'Word Scramble + Trivia'])
def test_unimplemented_level_does_not_change_puzzles_or_public_claim(kind, tmp_path):
    manifests=[]
    for level in ('Easy', 'Hard'):
        target=tmp_path/(level+'.pdf')
        studio.make_interior(kind,'Fixture','Fixture','Audit',2,level,42,target)
        manifests.append(json.loads(target.with_suffix('.puzzles.json').read_text()))
        listing=studio.listing(kind,'Fixture','Fixture','Audit',2,level,24)
        back=studio.back_cover_copy(kind,'General Starter',2,level)[1]
        assert 'not difficulty-rated' in listing.lower()
        assert 'not difficulty-rated' in back.lower()
        assert level+' difficulty' not in back
        assert 'a '+level.lower()+' level' not in listing
        assert cover_difficulty(kind,level)==''
    assert manifests[0]['puzzles']==manifests[1]['puzzles']


def test_mixed_claim_scopes_only_sudoku_and_omits_whole_book_chip():
    listing=studio.listing('Mixed Brain Games','Fixture','Fixture','Audit',24,'Hard',24)
    back=studio.back_cover_copy('Mixed Brain Games','General Starter',24,'Hard')[1]
    assert 'Sudoku section uses hard difficulty' in listing
    assert 'Cryptograms and word scrambles are not difficulty-rated' in listing
    assert 'Sudoku: Hard;' in back
    assert cover_difficulty('Mixed Brain Games','Hard')==''
    assert cover_difficulty('Sudoku','Easy')=='Easy'
    assert difficulty_description('Sudoku','Easy')=='Easy'


def test_actual_difficulty_widget_disables_and_restores_without_changing_raw_value():
    import tkinter as tk
    from tkinter import ttk
    from types import SimpleNamespace
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    try:
        root.withdraw()
        raw=tk.StringVar(root,'Hard');kind=tk.StringVar(root,'Cryptogram')
        widget=ttk.Combobox(root,textvariable=raw,values=('Easy','Mixed','Standard','Hard'),state='readonly')
        owner=SimpleNamespace(kind=kind,difficulty_box=widget)
        for family in ('Cryptogram','Word Scramble + Trivia','Sudoku','Mixed Brain Games'):
            kind.set(family)
            studio.PuzzleBookStudio._sync_difficulty_control(owner)
            root.update()
            assert str(widget.cget('state'))==('disabled' if family in ('Cryptogram','Word Scramble + Trivia') else 'readonly')
            assert raw.get()=='Hard'
    finally:
        root.destroy()
