import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from reportlab.pdfgen.canvas import Canvas

from publishing.studio_assistant import guide_request
from publishing.studio_book_checks import check_saved_book, book_check_text
from publishing.studio_codex import RequestCancelled


@pytest.fixture
def saved_book(tmp_path):
    folder = tmp_path / 'package'; folder.mkdir()
    canvas = Canvas(str(folder / 'interior.pdf'), pagesize=(612, 792))
    for page in range(24):
        canvas.drawString(72, 720, 'SOLUTION 1' if page == 23 else 'PUZZLE 1')
        canvas.showPage()
    canvas.save()
    canvas = Canvas(str(folder / 'kdp_full_wrap.pdf'), pagesize=((17.25 + 24 * .002252) * 72, 810))
    canvas.drawString(72, 720, 'Fixture'); canvas.showPage(); canvas.save()
    (tmp_path / 'data').mkdir()
    db = sqlite3.connect(tmp_path / 'data/books.db')
    db.execute('CREATE TABLE books(book_id TEXT PRIMARY KEY, metadata_json TEXT, package_path TEXT)')
    db.execute('INSERT INTO books VALUES(?,?,?)', ('selected', json.dumps({'title': 'Fixture', 'author': 'Audit', 'kind': 'Word Search', 'approval_status': 'Awaiting owner'}), str(folder)))
    db.commit(); db.close()
    return tmp_path


@pytest.mark.parametrize('text', ['Check this book for KDP', 'Run preflight', 'Check the selected book', 'Verify its answers', 'Show me what still needs fixing', 'Show QA findings'])
def test_checks_require_saved_identity(text):
    assert guide_request(text, context={'book_id': 'selected'}).action == 'check_book'
    assert guide_request(text).action == 'clarify'
    assert guide_request(text, context={'action': 'create_pack'}).action == 'clarify'


def test_check_is_real_and_read_only(saved_book):
    files = list(saved_book.rglob('*'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    result = check_saved_book(saved_book, 'selected')
    assert result['preflight']['passed']
    assert result['qa']['summary']['blockers'] > 0
    assert 'Product QA:' in book_check_text(result)
    assert 'no approval or marketplace status was changed' in book_check_text(result)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in saved_book.rglob('*') if p.is_file()}


def test_missing_catalog_and_cancel_are_safe(tmp_path):
    with pytest.raises(ValueError, match='catalog'):
        check_saved_book(tmp_path, 'missing')
    assert not (tmp_path / 'data').exists()
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(RequestCancelled):
        check_saved_book(tmp_path, 'missing', cancelled)


def test_actual_family_submit_and_accept(saved_book, monkeypatch):
    import tkinter as tk
    import word_search_creator as studio
    monkeypatch.setattr(studio, 'load_app_preferences', lambda: {})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models', lambda self: [])
    try:
        app = studio.WordSearchCreator()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    try:
        app.withdraw(); app.APP_DIR = saved_book
        family = app.family_studio
        family.context = {'book_id': 'selected', 'title': 'Fixture', 'kind': 'Word Search', 'topic': 'Space'}
        captured = []
        original = family._say
        def capture(role, text):
            captured.append(text); original(role, text)
        monkeypatch.setattr(family, '_say', capture)
        family.prompt.set('Check this book for KDP'); family.send()
        deadline = time.monotonic() + 30
        while family.busy and time.monotonic() < deadline:
            app.update(); time.sleep(.01)
        assert not family.busy
        assert any('PDF preflight: passed' in text and 'Product QA:' in text for text in captured)
        assert not (saved_book / 'package/PRODUCT_QA.json').exists()
    finally:
        app.destroy()


def test_stale_selection_discards_check(saved_book, monkeypatch):
    import tkinter as tk
    import word_search_creator as studio
    monkeypatch.setattr(studio, 'load_app_preferences', lambda: {})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models', lambda self: [])
    started = threading.Event(); release = threading.Event(); identities = []
    def delayed(project, identity, cancel):
        identities.append(identity); started.set(); release.wait(5)
        return {'title': 'STALE RESULT'}
    monkeypatch.setattr('publishing.studio_book_checks.check_saved_book', delayed)
    try:
        app = studio.WordSearchCreator()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    try:
        app.withdraw(); app.APP_DIR = saved_book
        family = app.family_studio
        family.context = {'book_id': 'selected', 'title': 'Fixture'}
        captured = []; monkeypatch.setattr(family, '_say', lambda role, text: captured.append(text))
        family.prompt.set('Run preflight'); family.send()
        assert started.wait(3)
        family.context = {'book_id': 'other', 'title': 'Other'}
        release.set()
        deadline = time.monotonic() + 5
        while family.busy and time.monotonic() < deadline:
            app.update(); time.sleep(.01)
        assert identities == ['selected']
        assert not family.busy
        assert not any('STALE RESULT' in text for text in captured)
        assert any('selected project changed' in text for text in captured)
    finally:
        release.set(); app.destroy()


def test_page_target_is_transparent_in_actual_guide(saved_book, monkeypatch):
    import tkinter as tk
    import word_search_creator as studio
    monkeypatch.setattr(studio, 'load_app_preferences', lambda: {})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models', lambda self: [])
    def forbidden(*args, **kwargs):
        raise AssertionError('Guide must not invoke model interpretation')
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.interpret', forbidden)
    try:
        app = studio.WordSearchCreator()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    try:
        app.withdraw(); app.APP_DIR = saved_book
        family = app.family_studio
        assert family.provider == 'Guide'
        family.prompt.set('Create a 100-page large-print birdwatching word search book for seniors')
        family.send(); app.update()
        assert family.intent.action == 'create_book'
        assert family.intent.topic.casefold() == 'birdwatching'
        text = family.proposal_text.get()
        assert 'requested 100 pages' in text
        assert 'does not yet enforce an exact page count' in text
        assert 'front matter, and answers' in text
        assert not family.busy
    finally:
        app.destroy()
