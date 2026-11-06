import json
import pytest
from publishing.database import PublishingDatabase

@pytest.fixture
def catalog(tmp_path):
    db = PublishingDatabase(tmp_path / 'catalog.sqlite')
    for i in range(25):
        db.upsert_book(str(i), f'source-{i}', {'title': f'Crème {i}', 'nested': {'values': [i]}}, f'package-{i}')
    with db._connect() as conn:
        conn.execute("UPDATE books SET updated_at='2099' WHERE book_id='7'")
        conn.execute("UPDATE books SET metadata_locked=1 WHERE book_id='7'")
        conn.execute("UPDATE marketplace_status SET status='Published' WHERE book_id='7' AND marketplace='amazon'")
        conn.execute("DELETE FROM marketplace_status WHERE book_id='0'")
    return db

def test_exact_shape_order_and_statuses(catalog):
    books = catalog.list_books()
    assert len(books) == 25
    assert books[0]['book_id'] == '7'
    for book in books:
        assert book == catalog.get_book(book['book_id'])
        assert book['statuses'] == catalog.statuses(book['book_id'])
        assert list(book['statuses']) == list(catalog.statuses(book['book_id']))
        assert 'metadata_json' not in book
    assert books[0]['metadata_locked'] == 1
    assert books[0]['source_key'] == 'source-7'
    assert books[0]['metadata'] == {'title': 'Crème 7', 'nested': {'values': [7]}}
    assert books[0]['statuses']['amazon'] == 'Published'
    assert catalog.get_book('0')['statuses'] == {}

@pytest.mark.parametrize('value', [None, 0, False, [], {}, 'missing', "' OR 1=1 --"])
def test_missing_and_invalid_identity(catalog, value):
    assert catalog.get_book(value) is None

def test_unrelated_invalid_metadata_is_isolated(catalog):
    with catalog._connect() as conn:
        conn.execute("UPDATE books SET metadata_json='broken' WHERE book_id='2'")
    assert catalog.get_book('7')['book_id'] == '7'
    with pytest.raises(json.JSONDecodeError):
        catalog.get_book('2')
    with pytest.raises(json.JSONDecodeError):
        catalog.list_books()

@pytest.mark.parametrize('method,args', [('get_book', ('7',)), ('list_books', ())])
def test_reads_have_one_connection_and_no_writes(catalog, monkeypatch, method, args):
    original = catalog._connect
    with original() as conn:
        before = {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table}')] for table in ('books', 'marketplace_status', 'marketplace_audit', 'approved_production_queue')}
    calls = []
    statements = []
    def connect():
        calls.append(True)
        conn = original()
        conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(catalog, '_connect', connect)
    getattr(catalog, method)(*args)
    assert len(calls) == 1
    assert len(statements) == 2
    assert all(sql.startswith('SELECT ') for sql in statements)
    with original() as conn:
        after = {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table}')] for table in before}
    assert before == after

def test_reads_are_fresh_and_return_independent_metadata(catalog):
    book = catalog.get_book('7')
    book['metadata']['nested']['values'].append('edited')
    book['statuses']['amazon'] = 'wrong'
    with catalog._connect() as conn:
        conn.execute("UPDATE marketplace_status SET status='Uploaded' WHERE book_id='7' AND marketplace='amazon'")
    assert catalog.get_book('7')['metadata']['nested']['values'] == [7]
    assert catalog.get_book('7')['statuses']['amazon'] == 'Uploaded'
    assert next(b for b in catalog.list_books() if b['book_id'] == '7')['statuses']['amazon'] == 'Uploaded'
