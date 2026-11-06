import sqlite3
import pytest
from publishing.studio_recovery import StudioDraftStore


def test_drafts_survive_reopen_and_undo_retains_all_versions(tmp_path):
    path = tmp_path/'books.db'
    store = StudioDraftStore(path)
    key = store.save(None, 'activity_pack', {'title': 'First', 'count': ''})
    store.save(key, 'activity_pack', {'title': 'Second'})
    store.save(key, 'activity_pack', {'title': 'Third'})
    assert StudioDraftStore(path).load(key)['payload']['title'] == 'Third'
    assert store.undo(key)['payload']['title'] == 'Second'
    assert store.undo(key)['payload']['title'] == 'First'
    store.save(key, 'activity_pack', {'title': 'New branch'})
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM studio_draft_versions').fetchone()[0] == 4
    store.save(key, 'activity_pack', {'title': 'New branch'}, completed=True)
    assert store.pending() == []
    store.save(key, 'activity_pack', {'title': 'Another edit'})
    assert len(store.pending()) == 1


def test_invalid_save_preserves_previous_and_catalog_data(tmp_path):
    path = tmp_path/'books.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE books (book_id TEXT, status TEXT)')
        db.execute('INSERT INTO books VALUES (?, ?)', ('book', 'Published'))
    store = StudioDraftStore(path)
    key = store.save(None, 'book_plan', {'topic': 'Space'})
    with pytest.raises(ValueError): store.save(key, 'book_plan', {'topic': 'x'*300000})
    with pytest.raises(ValueError): store.save(key, 'activity_pack', {'topic': 'Garden'})
    assert store.load(key)['payload'] == {'topic': 'Space'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM books').fetchall() == [('book', 'Published')]
    revision = store.load(key)['revision']
    store.save(key, 'book_plan', {'topic': 'Space'})
    assert store.load(key)['revision'] == revision
