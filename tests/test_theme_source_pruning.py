import json
from pathlib import Path
import pytest
from publishing.database import PublishingDatabase


def bare(database,tmp_path,identity='keep',**kwargs):
    database.upsert_book(identity,kwargs.get('source',str(tmp_path/f'{identity}.json')),kwargs.get('metadata',{'title':identity}),kwargs.get('package',''))
    return identity


@pytest.mark.parametrize('protection',['package_source','generated_source','package_path','metadata_lock','Ready','Uploaded','Published',
 'external_id','integration_state','metadata_isbn','metadata_files','metadata_review'])
def test_theme_prune_preserves_tracked_or_generated_work(tmp_path,protection):
    db=PublishingDatabase(tmp_path/'catalog.db');bare(db,tmp_path);bare(db,tmp_path,'stale')
    with db._connect() as con:
        if protection=='package_source':con.execute('UPDATE books SET source_key=? WHERE book_id=?',('package:'+str(tmp_path/'missing_package'),'keep'))
        elif protection=='generated_source':con.execute('UPDATE books SET source_key=? WHERE book_id=?',('generated:Sudoku:draft','keep'))
        elif protection=='package_path':con.execute('UPDATE books SET package_path=? WHERE book_id=?',(str(tmp_path/'missing_package'),'keep'))
        elif protection=='metadata_lock':con.execute('UPDATE books SET metadata_locked=1 WHERE book_id=?',('keep',))
        elif protection in ['Ready','Uploaded','Published']:con.execute('UPDATE marketplace_status SET status=? WHERE book_id=? AND marketplace=?',(protection,'keep','amazon'))
        elif protection in ['external_id','integration_state']:con.execute('UPDATE marketplace_status SET '+protection+'=? WHERE book_id=? AND marketplace=?',('persisted-state','keep','amazon'))
        else:
            meta={'title':'keep'}
            meta.update({'metadata_isbn':{'isbn':'9780000000000'},'metadata_files':{'files':{'interior_pdf':'missing.pdf'}},'metadata_review':{'content_plan_approval':{'source':'owner'}}}[protection])
            con.execute('UPDATE books SET metadata_json=? WHERE book_id=?',(json.dumps(meta),'keep'))
        before=con.execute('SELECT * FROM books WHERE book_id=?',('keep',)).fetchone()
        statuses=con.execute('SELECT * FROM marketplace_status WHERE book_id=?',('keep',)).fetchall()
    assert db.prune_sources(set())==1
    with db._connect() as con:
        assert tuple(con.execute('SELECT * FROM books WHERE book_id=?',('keep',)).fetchone())==tuple(before)
        assert [tuple(r) for r in con.execute('SELECT * FROM marketplace_status WHERE book_id=?',('keep',))]==[tuple(r) for r in statuses]
    assert db.get_book('stale') is None


LINKS={
 'isbn':('INSERT INTO isbns(isbn,book_id) VALUES(?,?)',('9780000000000','keep')),
 'release':('INSERT INTO release_locks(book_id,revision,package_path,snapshot_json,snapshot_sha256,locked_at) VALUES(?,?,?,?,?,?)',('keep',1,'package','{}','fingerprint','now')),
 'revision':('INSERT INTO book_package_revisions(book_id,prior_package_path,package_path,evidence_json,adopted_at) VALUES(?,?,?,?,?)',('keep','old','new','{}','now')),
 'review':('INSERT INTO final_local_reviews(book_id,reviewed_at) VALUES(?,?)',('keep','now')),
 'history':('INSERT INTO marketplace_audit(book_id,marketplace,changed_at) VALUES(?,?,?)',('keep','amazon','now')),
 'integration':('INSERT INTO integration_log(book_id,marketplace,event,created_at) VALUES(?,?,?,?)',('keep','etsy','draft','now')),
 'queue':('INSERT INTO approved_production_queue(book_id,added_at,updated_at) VALUES(?,?,?)',('keep','now','now')),
 'cover_concept':('INSERT INTO cover_concepts(book_id,label,direction_json,created_at) VALUES(?,?,?,?)',('keep','Owner design','{}','now')),
 'bundle':('INSERT INTO bundles(bundle_id,title,book_ids_json,metadata_json,output_path,created_at) VALUES(?,?,?,?,?,?)',('bundle','Bundle','["keep"]','{}','output','now')),
}


@pytest.mark.parametrize('kind',LINKS)
def test_linked_history_review_and_approvals_survive_prune(tmp_path,kind):
    db=PublishingDatabase(tmp_path/'catalog.db');bare(db,tmp_path);bare(db,tmp_path,'stale')
    with db._connect() as con:con.execute(*LINKS[kind])
    assert db.prune_sources(set())==1
    assert db.get_book('keep') is not None and db.get_book('stale') is None


def test_only_exact_untracked_alias_or_vanished_theme_is_pruned(tmp_path):
    db=PublishingDatabase(tmp_path/'catalog.db')
    first=tmp_path/'active.json';alias=tmp_path/'alias.json';variant=tmp_path/'variant.json';broken=tmp_path/'broken.json'
    content={'title':'Same title','puzzles':[{'words':['APPLE']} ]}
    first.write_text(json.dumps(content));alias.write_text(json.dumps(content,indent=4));variant.write_text(json.dumps(dict(content,puzzles=[])));broken.write_text('{broken')
    for identity,path in [('active',first),('alias',alias),('variant',variant),('broken',broken)]:bare(db,tmp_path,identity,source=str(path))
    bare(db,tmp_path,'vanished')
    before={str(p):p.read_bytes() for p in [first,alias,variant,broken]}
    assert db.prune_sources({str(first)})==2
    assert {b['book_id'] for b in db.list_books()}=={'active','variant','broken'}
    assert all(Path(p).read_bytes()==value for p,value in before.items())


def test_opaque_metadata_is_not_assumed_disposable(tmp_path):
    db=PublishingDatabase(tmp_path/'catalog.db');bare(db,tmp_path)
    with db._connect() as con:con.execute('UPDATE books SET metadata_json=? WHERE book_id=?',('{broken','keep'))
    assert db.prune_sources(set())==0
    with db._connect() as con:assert con.execute('SELECT1 FROM books WHERE book_id=?'.replace('SELECT1','SELECT 1'),('keep',)).fetchone()


def test_versioned_chat_draft_source_reference_is_preserved(tmp_path):
    db=PublishingDatabase(tmp_path/'catalog.db');bare(db,tmp_path);bare(db,tmp_path,'stale')
    with db._connect() as con:
        con.execute('CREATE TABLE studio_draft_versions(draft_id TEXT,revision INTEGER,payload TEXT)')
        con.execute('INSERT INTO studio_draft_versions VALUES(?,?,?)',('draft',1,json.dumps({'selected_context':{'book_id':'keep'}})))
    assert db.prune_sources(set())==1
    assert db.get_book('keep') is not None


def test_opaque_bundle_references_stop_destructive_guessing(tmp_path):
    db=PublishingDatabase(tmp_path/'catalog.db');bare(db,tmp_path)
    with db._connect() as con:con.execute('INSERT INTO bundles VALUES(?,?,?,?,?,?)',('bundle','Bundle','{broken','{}','output','now'))
    assert db.prune_sources(set())==0
    assert db.get_book('keep') is not None


def test_unknown_relative_source_identity_is_not_assumed_stale(tmp_path):
    db=PublishingDatabase(tmp_path/'catalog.db');bare(db,tmp_path,source='legacy_relative.json')
    assert db.prune_sources(set())==0
    assert db.get_book('keep') is not None


def test_equivalent_active_path_spelling_preserves_identity(tmp_path):
    from publishing.database import PublishingDatabase
    import json
    theme=tmp_path/'theme.json';theme.write_text(json.dumps({'title':'Keep','puzzles':[]}),encoding='utf-8')
    child=tmp_path/'child';child.mkdir()
    db=PublishingDatabase(tmp_path/'catalog.db')
    db.upsert_book('keep',str(theme),{'title':'Keep'},'')
    equivalent=str(child/'..'/'theme.json')
    assert db.prune_sources({equivalent})==0
    assert db.get_book('keep') is not None
