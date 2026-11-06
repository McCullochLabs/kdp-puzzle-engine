import json,sqlite3,threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from publishing.studio_assistant import guide_request
from publishing.studio_book_checks import export_saved_book
from publishing.studio_codex import RequestCancelled

@pytest.mark.parametrize('text',['Export this book','Prepare the KDP files','Prepare an export package'])
def test_export_requires_canonical_selection(text):
 assert guide_request(text,context={'book_id':'selected'}).action=='export_book'
 assert guide_request(text).action=='clarify'
 assert guide_request('Upload this export package',context={'book_id':'selected'}).action=='help'

@pytest.fixture
def fixture(tmp_path,monkeypatch):
 import publishing.studio_book_checks as checks
 folder=tmp_path/'out/book';folder.mkdir(parents=True);artifact=folder/'interior.pdf';artifact.write_bytes(b'fixture')
 data=tmp_path/'data';data.mkdir();db=sqlite3.connect(data/'books.db');db.execute('CREATE TABLE books(book_id TEXT,metadata_json TEXT,package_path TEXT)');db.execute('INSERT INTO books VALUES(?,?,?)',('selected',json.dumps({'title':'Fixture'}),str(folder)));db.commit();db.close()
 from integrations.product import ArtifactPurpose
 product=SimpleNamespace(artifacts=[SimpleNamespace(path=str(artifact),purpose=ArtifactPurpose.PRINT_INTERIOR)])
 monkeypatch.setattr('integrations.factory.MasterProductFactory.from_book_record',lambda *a,**k:product)
 evidence={'title':'Fixture','preflight':{'passed':True},'qa':{'summary':{'blockers':0}}}
 monkeypatch.setattr(checks,'check_saved_book',lambda *a:evidence)
 calls=[]
 def export(product,destination):
  calls.append(destination);destination.mkdir(parents=True);(destination/'files').mkdir();(destination/'files/artifact.pdf').write_bytes(artifact.read_bytes())
  return SimpleNamespace(success=True,recovery={'export_path':str(destination)})
 monkeypatch.setattr('integrations.registry.get_export_integration',lambda key:SimpleNamespace(export_package=export))
 return tmp_path,artifact,evidence,calls

def test_versioned_local_exports_preserve_catalog(fixture):
 root,artifact,evidence,calls=fixture;before=(root/'data/books.db').read_bytes()
 first=export_saved_book(root,'selected');second=export_saved_book(root,'selected')
 assert first['export_path']!=second['export_path'] and len(calls)==2
 assert (root/'data/books.db').read_bytes()==before and artifact.read_bytes()==b'fixture'

def test_failed_qa_and_preflight_never_export(fixture):
 root,artifact,evidence,calls=fixture;evidence['qa']['summary']['blockers']=1
 with pytest.raises(ValueError,match='blocked'):export_saved_book(root,'selected')
 evidence['qa']['summary']['blockers']=0;evidence['preflight']['passed']=False
 with pytest.raises(ValueError,match='blocked'):export_saved_book(root,'selected')
 assert not calls

def test_cancelled_request_never_exports(fixture):
 root,artifact,evidence,calls=fixture;cancel=threading.Event();cancel.set()
 with pytest.raises(RequestCancelled):export_saved_book(root,'selected',cancel)
 assert not calls

def test_files_changed_during_validation_fail_closed(fixture,monkeypatch):
 root,artifact,evidence,calls=fixture
 def mutate(*a):artifact.write_bytes(b'changed');return evidence
 monkeypatch.setattr('publishing.studio_book_checks.check_saved_book',mutate)
 with pytest.raises(ValueError,match='files changed'):export_saved_book(root,'selected')
 assert not calls


def test_corrupt_export_copy_never_reports_success(fixture,monkeypatch):
 root,artifact,evidence,calls=fixture
 def broken(product,destination):
  destination.mkdir(parents=True);(destination/'files').mkdir();(destination/'files/bad.pdf').write_bytes(b'corrupt')
  return SimpleNamespace(success=True,recovery={'export_path':str(destination)})
 monkeypatch.setattr('integrations.registry.get_export_integration',lambda key:SimpleNamespace(export_package=broken))
 with pytest.raises(ValueError,match='integrity changed'):export_saved_book(root,'selected')


def test_cross_book_artifact_map_cannot_export_unchecked_files(fixture,monkeypatch):
 from integrations.product import ArtifactPurpose
 root,artifact,evidence,calls=fixture
 other=root/'out/other';other.mkdir();bad=other/'interior.pdf';bad.write_bytes(b'unchecked')
 monkeypatch.setattr('integrations.factory.MasterProductFactory.from_book_record',lambda *a,**k:SimpleNamespace(artifacts=[SimpleNamespace(path=str(bad),purpose=ArtifactPurpose.PRINT_INTERIOR)]))
 with pytest.raises(ValueError,match="selected book's package"):export_saved_book(root,'selected')
 assert not calls


def test_noncanonical_pdf_inside_same_package_is_not_qa_validated(fixture,monkeypatch):
 from integrations.product import ArtifactPurpose
 root,artifact,evidence,calls=fixture;wrong=artifact.parent/'old_interior.pdf';wrong.write_bytes(b'old')
 monkeypatch.setattr('integrations.factory.MasterProductFactory.from_book_record',lambda *a,**k:SimpleNamespace(artifacts=[SimpleNamespace(path=str(wrong),purpose=ArtifactPurpose.PRINT_INTERIOR)]))
 with pytest.raises(ValueError,match='must match'):export_saved_book(root,'selected')
 assert not calls


@pytest.mark.parametrize('text',["Do not export this book","Don't prepare the KDP files","Never export the original book"])
def test_negated_export_never_runs(text):
 assert guide_request(text,context={'book_id':'selected'}).action=='help'


def organized_typography_fixture(fixture):
 from publishing.package_layout import initialize_package_layout,package_file
 from publishing.sudoku_typography import SudokuTypography,bind_typography
 from integrations.factory import MasterProductFactory
 root,old,evidence,calls=fixture;folder=old.parent;initialize_package_layout(folder)
 interior=package_file(folder,'interior.pdf',for_write=True);interior.write_bytes(old.read_bytes())
 MasterProductFactory.from_book_record({}).artifacts[0].path=str(interior)
 manifest=interior.with_suffix('.puzzles.json');manifest.write_text('{"puzzles":[]}')
 source=package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True)
 config=SudokuTypography(puzzle_font_pt=34,solution_font_pt=22)
 source.write_text(json.dumps({'puzzle_type':'Sudoku','sudoku_typography':config.to_dict()}))
 bind_typography(interior,config)
 return root,interior,manifest,source,calls


def test_organized_export_tracks_and_copies_canonical_evidence(fixture):
 import hashlib
 root,pdf,manifest,source,calls=organized_typography_fixture(fixture)
 (pdf.parent.parent/'PACKAGE_SOURCE_RECORD.json').write_text('stale flat alias')
 result=export_saved_book(root,'selected');exported=Path(result['export_path'])
 validation=json.loads((exported/'LOCAL_VALIDATION.json').read_text())
 for name,path in [('PACKAGE_SOURCE_RECORD.json',source),('interior.puzzles.json',manifest),('interior.typography.json',pdf.with_suffix('.typography.json'))]:
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  assert validation['source_sha256'][str(path.resolve())]==digest
  assert validation['local_source_evidence_sha256'][name]==digest
  assert (exported/'LOCAL_SOURCE_EVIDENCE'/name).read_bytes()==path.read_bytes()
 assert len(calls)==1


def test_organized_manifest_mutation_during_qa_blocks_export(fixture,monkeypatch):
 root,pdf,manifest,source,calls=organized_typography_fixture(fixture);evidence=fixture[2]
 def mutate(*a):manifest.write_text('{"puzzles":["changed"]}');return evidence
 monkeypatch.setattr('publishing.studio_book_checks.check_saved_book',mutate)
 with pytest.raises(ValueError,match='files changed'):export_saved_book(root,'selected')
 assert not calls


def test_typography_binding_required_when_source_declares_fonts(fixture):
 root,pdf,manifest,source,calls=organized_typography_fixture(fixture)
 pdf.with_suffix('.typography.json').unlink()
 with pytest.raises(ValueError,match='binding changed or is missing'):export_saved_book(root,'selected')
 assert not calls


def test_corrupted_source_evidence_copy_is_not_reported_as_success(fixture,monkeypatch):
 import shutil
 root,pdf,manifest,source,calls=organized_typography_fixture(fixture);original=shutil.copy2
 def corrupt(src,dst,*a,**k):
  result=original(src,dst,*a,**k)
  if 'LOCAL_SOURCE_EVIDENCE' in str(dst):Path(dst).write_bytes(b'corrupt evidence')
  return result
 monkeypatch.setattr(shutil,'copy2',corrupt)
 with pytest.raises(ValueError,match='source evidence integrity changed'):export_saved_book(root,'selected')
