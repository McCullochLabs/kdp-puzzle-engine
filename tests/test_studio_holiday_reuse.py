import json,sqlite3,threading
from dataclasses import replace
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas
import holiday_combo
from publishing.studio_holiday_reuse import prepare_holiday_reuse,confirm_holiday_reuse,_request


@pytest.fixture
def saved(tmp_path,monkeypatch):
    folder=tmp_path/'out/holiday';folder.mkdir(parents=True)
    for name in ('interior.pdf','kdp_full_wrap.pdf'):
        pdf=canvas.Canvas(str(folder/name));pdf.drawString(50,700,'Fixture');pdf.save()
    (folder/'front_cover.png').write_bytes(b'fixture')
    (folder/'interior.puzzles.json').write_text('{}')
    manifest={'title':holiday_combo.TITLE,'subtitle':holiday_combo.SUBTITLE,'author':holiday_combo.AUTHOR,
              'puzzle_type':holiday_combo.TYPE,'puzzle_count':200}
    (folder/'PACKAGE_SOURCE_RECORD.json').write_text(json.dumps(manifest),encoding='utf-8')
    database=tmp_path/'data/books.db';database.parent.mkdir()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE books(book_id TEXT,source_key TEXT,metadata_json TEXT,package_path TEXT)')
        db.execute('INSERT INTO books VALUES(?,?,?,?)',('holiday','source',json.dumps(manifest),str(folder)))
    monkeypatch.setattr('publishing.package_layout.release_contract',lambda folder:{'ready':True})
    monkeypatch.setattr('publishing.studio_book_checks.check_saved_book',lambda *a,**k:{'preflight':{'passed':True},'qa':{'summary':{'blockers':0}}})
    return tmp_path,folder,database


@pytest.mark.parametrize('text',[
    'Create a 100-puzzle holiday word search and Sudoku book',
    'Create a 200.5-puzzle holiday word search and Sudoku book',
    'Create a holiday word search and Sudoku book with seed 42',
    'Create a holiday word search and Sudoku book for seniors',
    'Create a large-print holiday word search and Sudoku book',
    'Create a birdwatching word search and Sudoku book',
    'Create a holiday word search and Sudoku book called "New Title"',
    'Do not create a holiday word search and Sudoku book',
    'Create a holiday word search and Sudoku book and upload it',
])
def test_custom_or_negated_recipe_not_silently_substituted(text):
    with pytest.raises(ValueError):_request(text)


def test_explicit_reuse_preserves_bytes_and_identity(saved):
    root,folder,database=saved;before=database.read_bytes();files={p.name:p.read_bytes() for p in folder.iterdir()}
    plan=prepare_holiday_reuse(root,'Create a 200-puzzle holiday word search and Sudoku book',{'book_id':'prior'})
    result=confirm_holiday_reuse(root,plan)
    assert result['book_id']=='holiday' and result['kind']=='Word Search + Sudoku' and result['reused_existing']
    assert database.read_bytes()==before and files=={p.name:p.read_bytes() for p in folder.iterdir()}
    assert json.loads(plan.selected_context_json)=={'book_id':'prior'}


def test_drift_and_blockers_fail_without_selecting_or_writing(saved,monkeypatch):
    root,folder,database=saved
    plan=prepare_holiday_reuse(root,'Create a holiday word search and Sudoku book')
    (folder/'front_cover.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):confirm_holiday_reuse(root,plan)
    plan=prepare_holiday_reuse(root,'Create a holiday word search and Sudoku book')
    monkeypatch.setattr('publishing.studio_book_checks.check_saved_book',lambda *a,**k:{'preflight':{'passed':False},'qa':{'summary':{'blockers':1}}})
    with pytest.raises(ValueError,match='blockers'):confirm_holiday_reuse(root,plan)
    cancel=threading.Event();cancel.set()
    with pytest.raises(ValueError,match='cancelled'):confirm_holiday_reuse(root,plan,cancel)


def test_ambiguous_book_identity_requires_explicit_selection(saved):
    root,folder,database=saved
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO books SELECT ?,source_key,metadata_json,package_path FROM books',('alias',))
    with pytest.raises(ValueError,match='Choose'):prepare_holiday_reuse(root,'Create a holiday word search and Sudoku book')
    assert prepare_holiday_reuse(root,'Create a holiday word search and Sudoku book',{'book_id':'holiday'}).book_id=='holiday'


def test_page_target_cannot_be_ignored(saved):
    root,folder,database=saved
    with pytest.raises(ValueError,match='page target'):
        prepare_holiday_reuse(root,'Create a holiday word search and Sudoku book with 316 pages')
