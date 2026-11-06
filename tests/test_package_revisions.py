"""Catalog transactions/scans; artifact QA itself is exercised by existing QA tests."""
import json
from pathlib import Path
import pytest
from publishing.manager import PublishingService
from publishing import package_revisions as revisions

@pytest.fixture
def catalog(tmp_path,monkeypatch):
    service=PublishingService(tmp_path)
    old=tmp_path/'out/old';new=tmp_path/'out/revision'
    source={'title':'Owned Book','author':'Jordan M. Slade','puzzle_type':'Sudoku','puzzle_count':1,'seed':9}
    for folder in [old,new]:
        folder.mkdir(parents=True)
        for name in ['interior.pdf','kdp_full_wrap.pdf','front_cover.png']:(folder/name).write_bytes(b'fixture')
        (folder/'interior.puzzles.json').write_text(json.dumps({'puzzles':[{'number':1}]}))
        (folder/'PACKAGE_SOURCE_RECORD.json').write_text(json.dumps(source))
    key='package:'+str(old.resolve());book_id=service._id(key)
    service.db.upsert_book(book_id,key,{'title':'Owned Book','author':'Jordan M. Slade','description':'Owner copy','price':{'amazon':15.99},'files':{'print_interior':str(old/'interior.pdf')}},str(old))
    service.db.save_metadata(book_id,service.db.get_book(book_id)['metadata'],locked=True)
    with service.db._connect() as db:db.execute("UPDATE marketplace_status SET status='Published',external_id='existing-ASIN',url='https://example.test/book' WHERE book_id=? AND marketplace='amazon'",(book_id,))
    monkeypatch.setattr(revisions,'validate_revision',lambda service,book,target:{'file_sha256':revisions.fingerprint(target),'previous_file_sha256':revisions.fingerprint(Path(book['package_path'])),'qa_blockers':0,'preflight_passed':True})
    return service,book_id,old,new

def test_adoption_preserves_identity_locked_owner_copy_and_external_states(catalog):
    service,book_id,old,new=catalog;before=service.db.get_book(book_id);external=service.db.marketplace_records(book_id)
    result=service.adopt_print_revision(book_id,new);after=service.db.get_book(book_id)
    assert result['book_id']==book_id and after['source_key']==before['source_key']
    assert after['package_path']==str(new.resolve()) and after['metadata_locked']==1
    for key in ['title','author','description','price']:assert after['metadata'][key]==before['metadata'][key]
    assert after['metadata']['files']['print_interior']==str(new/'interior.pdf')
    assert service.db.marketplace_records(book_id)==external
    assert after['metadata']['local_print_revision']['owner_review']=='pending'
    assert service.db.release_locks(book_id)==[]

def test_owner_change_during_validation_is_not_overwritten(catalog,monkeypatch):
    service,book_id,old,new=catalog
    def check(service,book,target):
        metadata=dict(book['metadata']);metadata['description']='Concurrent owner edit';service.db.save_metadata(book_id,metadata)
        return {'file_sha256':revisions.fingerprint(target),'previous_file_sha256':revisions.fingerprint(Path(book['package_path'])),'qa_blockers':0,'preflight_passed':True}
    monkeypatch.setattr(revisions,'validate_revision',check)
    with pytest.raises(ValueError,match='changed during validation'):service.adopt_print_revision(book_id,new)
    after=service.db.get_book(book_id);assert after['package_path']==str(old) and after['metadata']['description']=='Concurrent owner edit'
    assert not service.db.has_print_revision(book_id)

def test_failed_quality_evidence_cannot_commit(catalog,monkeypatch):
    service,book_id,old,new=catalog
    monkeypatch.setattr(revisions,'validate_revision',lambda *args:{'qa_blockers':1,'preflight_passed':True})
    with pytest.raises(ValueError,match='Passing revision'):service.adopt_print_revision(book_id,new)
    assert service.db.get_book(book_id)['package_path']==str(old)

def test_files_changed_after_quality_check_cannot_commit(catalog,monkeypatch):
    service,book_id,old,new=catalog
    def check(service,book,target):
        proof=revisions.fingerprint(target);(target/'interior.pdf').write_bytes(b'changed');return {'file_sha256':proof,'previous_file_sha256':revisions.fingerprint(Path(book['package_path'])),'qa_blockers':0,'preflight_passed':True}
    monkeypatch.setattr(revisions,'validate_revision',check)
    with pytest.raises(ValueError,match='files changed'):service.adopt_print_revision(book_id,new)
    assert not service.db.has_print_revision(book_id)

def test_outside_output_path_is_rejected(catalog,tmp_path):
    service,book_id,old,new=catalog
    with pytest.raises(ValueError,match='local output'):service.adopt_print_revision(book_id,tmp_path)

def test_output_scan_never_reimports_adopted_old_or_new_package(catalog):
    service,book_id,old,new=catalog;service.adopt_print_revision(book_id,new)
    assert service.sync_output_packages()==0
    assert [b['book_id'] for b in service.db.list_books()]==[book_id]
    assert service.db.get_book(book_id)['package_path']==str(new.resolve())

def test_duplicate_pruning_retains_managed_identity(catalog):
    service,book_id,old,new=catalog;service.adopt_print_revision(book_id,new)
    service.db.save_metadata(book_id,service.db.get_book(book_id)['metadata'],locked=False)
    with service.db._connect() as db:db.execute("UPDATE marketplace_status SET status='Not Prepared',external_id='',url='' WHERE book_id=?",(book_id,))
    other=service.output/'another';other.mkdir()
    service.db.upsert_book('other','package:'+str(other),{'title':'Owned Book'},str(other))
    service.db.save_metadata('other',{'title':'Owned Book'},locked=True)
    service.db.prune_duplicate_unpublished_package_titles()
    assert service.db.get_book(book_id) is not None

def test_changed_puzzle_records_are_rejected_before_adoption(catalog):
    service,book_id,old,new=catalog
    (new/'interior.puzzles.json').write_text(json.dumps({'puzzles':[{'number':2}]}))
    with pytest.raises(ValueError,match='every puzzle'):revisions.compare_revision(old,new)

def test_catalog_identity_change_during_validation_is_rejected(catalog,monkeypatch):
    service,book_id,old,new=catalog
    def check(service,book,target):
        with service.db._connect() as db:db.execute("UPDATE books SET source_key='owner-changed-source' WHERE book_id=?",(book_id,))
        return {'file_sha256':revisions.fingerprint(target),'previous_file_sha256':revisions.fingerprint(Path(book['package_path'])),'qa_blockers':0,'preflight_passed':True}
    monkeypatch.setattr(revisions,'validate_revision',check)
    with pytest.raises(ValueError,match='changed during validation'):service.adopt_print_revision(book_id,new)
    assert not service.db.has_print_revision(book_id)


def test_theme_refresh_keeps_explicit_adopted_package(catalog,monkeypatch):
    service,unused,old,new=catalog
    source=service.project/'theme.json';source.write_text(json.dumps({'title':'Owned Book','author':'Jordan M. Slade','puzzles':[{'words':'ALPHA BETA'}]}))
    key=str(source.resolve());book_id=service._id(key)
    service.db.upsert_book(book_id,key,service.db.get_book(unused)['metadata'],str(old))
    service.adopt_print_revision(book_id,new)
    def forbidden(*args):raise AssertionError('Must not replace an explicitly adopted package with a title search')
    monkeypatch.setattr(service,'_find_package_for_title',forbidden)
    assert service.sync_theme(source)==book_id
    assert service.db.get_book(book_id)['package_path']==str(new.resolve())


def test_revision_claimed_by_another_book_is_not_adopted(catalog):
    service,book_id,old,new=catalog
    service.db.upsert_book('other','package:'+str(new),{'title':'Owned Book'},str(new))
    with pytest.raises(ValueError,match='another catalog book'):service.adopt_print_revision(book_id,new)
    assert service.db.get_book(book_id)['package_path']==str(old)
    assert not service.db.has_print_revision(book_id)


def test_cover_alpha_change_is_a_real_cover_change(catalog):
    from PIL import Image
    from pypdf import PdfWriter
    import hashlib
    service,book_id,old,new=catalog
    for folder,alpha in [(old,255),(new,0)]:
        writer=PdfWriter();writer.add_blank_page(612,792);writer.write(folder/'interior.pdf')
        digest=hashlib.sha256((folder/'interior.pdf').read_bytes()).hexdigest()
        (folder/'interior.puzzles.json').write_text(json.dumps({'pdf_sha256':digest,'puzzles':[{'number':1}]}))
        Image.new('RGBA',(20,20),(100,100,100,alpha)).save(folder/'front_cover.png')
        (folder/'front_cover.approval.json').write_text(json.dumps({'asset_id':'fixture','asset_sha256':'fixture-asset-hash'}))
    with pytest.raises(ValueError,match='front-cover pixels'):revisions.compare_revision(old,new)


def test_unrelated_title_lookup_cannot_claim_managed_revision(catalog):
    service,book_id,old,new=catalog;service.adopt_print_revision(book_id,new)
    assert service._find_package_for_title('Owned Book') is None
