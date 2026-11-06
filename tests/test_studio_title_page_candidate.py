import hashlib,json,uuid
from pathlib import Path
import pytest
from PIL import Image
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject
from reportlab.pdfgen.canvas import Canvas
from publishing.package_layout import initialize_package_layout,package_file
from publishing.studio_revision_adoption import _tree
from publishing.studio_title_page_candidate import build_title_page_candidate,protected_pages

@pytest.fixture
def source(tmp_path):
    folder=tmp_path/'out/source';initialize_package_layout(folder)
    pdf=package_file(folder,'interior.pdf',for_write=True);c=Canvas(str(pdf))
    for text in ['Original title','Original puzzle page','Original solution page']:c.drawString(60,600,text);c.showPage()
    c.save();records={'schema_version':1,'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzles':[{'fixture':'unchanged puzzle and answer'}],'layout_regions':[]}
    pdf.with_suffix('.puzzles.json').write_text(json.dumps(records))
    raw={'title':'Fixture Word Search','subtitle':'Complete puzzles','author':'Fixture Author','puzzle_type':'Word Search','puzzle_count':1,'cover_style':'photo'}
    package_file(folder,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(raw))
    art=package_file(folder,'front_cover.png',for_write=True);Image.new('RGB',(100,120),'black').save(art)
    art.with_suffix('.approval.json').write_text(json.dumps({'asset_id':'unit-fixture','asset_sha256':hashlib.sha256(art.read_bytes()).hexdigest()}))
    package_file(folder,'kdp_full_wrap.pdf',for_write=True).write_bytes(pdf.read_bytes())
    (folder/'interior_handoff.pdf').write_bytes(pdf.read_bytes());(folder/'keep.txt').write_text('preserve this')
    return tmp_path,folder


def test_copy_changes_only_title_and_pdf_bindings_and_preserves_original(source):
    root,folder=source;frozen=_tree(folder);before=protected_pages(package_file(folder,'interior.pdf'))
    target,proof=build_title_page_candidate(root,folder,uuid.uuid4().hex,'Modern Minimal',frozen)
    assert _tree(folder)==frozen and proof['protected_pages']==2 and proof['puzzles_preserved']
    assert protected_pages(package_file(target,'interior.pdf'))==before
    assert package_file(target,'interior.pdf').read_bytes()==(target/'interior_handoff.pdf').read_bytes()
    assert package_file(target,'kdp_full_wrap.pdf').read_bytes()==package_file(folder,'kdp_full_wrap.pdf').read_bytes()
    assert not (root/'data/books.db').exists()
    assert 'NOT_ADOPTED' in proof['status']
    assert json.loads(package_file(target,'PACKAGE_SOURCE_RECORD.json').read_text())['title_page_style']=='Modern Minimal'


@pytest.mark.parametrize('fault',['source','uuid','style','kind'])
def test_bad_or_changed_inputs_never_copy(source,fault):
    root,folder=source;frozen=_tree(folder);identity=uuid.uuid4().hex;style='Modern Minimal'
    if fault=='source':(folder/'owner_change.txt').write_text('preserved')
    if fault=='uuid':identity='bad'
    if fault=='style':style='unknown'
    if fault=='kind':
        p=package_file(folder,'PACKAGE_SOURCE_RECORD.json');raw=json.loads(p.read_text());raw['puzzle_type']='Sudoku';p.write_text(json.dumps(raw));frozen=_tree(folder)
    with pytest.raises(ValueError):build_title_page_candidate(root,folder,identity,style,frozen)
    assert not (root/'data/studio_revision_candidates').exists()


def test_existing_candidate_not_overwritten(source):
    root,folder=source;identity=uuid.uuid4().hex;frozen=_tree(folder)
    candidate,_=build_title_page_candidate(root,folder,identity,'Modern Minimal',frozen);before=_tree(candidate)
    with pytest.raises(ValueError,match='preserved'):build_title_page_candidate(root,folder,identity,'Modern Minimal',frozen)
    assert _tree(candidate)==before and _tree(folder)==frozen


def test_resource_only_font_change_is_detected(source):
    root,folder=source;pdf=package_file(folder,'interior.pdf');reader=PdfReader(pdf);writer=PdfWriter()
    for page in reader.pages:writer.add_page(page)
    fonts=writer.pages[1]['/Resources']['/Font'];font=next(iter(fonts.values())).get_object();font[NameObject('/BaseFont')]=NameObject('/Courier')
    changed=root/'resource_changed.pdf'
    with changed.open('wb') as stream:writer.write(stream)
    old=PdfReader(pdf);new=PdfReader(changed)
    assert old.pages[1].get_contents().get_data()==new.pages[1].get_contents().get_data()
    assert protected_pages(pdf)!=protected_pages(changed)


def test_recovery_reuses_only_complete_unchanged_copy_without_rendering(source,monkeypatch):
    root,folder=source;identity=uuid.uuid4().hex;frozen=_tree(folder)
    candidate,proof=build_title_page_candidate(root,folder,identity,'Modern Minimal',frozen);before=_tree(candidate)
    monkeypatch.setattr('publishing.studio_title_page_candidate.render_title_page',lambda *a,**k:pytest.fail('Completed copy was rendered again'))
    again,reused=build_title_page_candidate(root,folder,identity,'Modern Minimal',frozen,recover=True)
    assert again==candidate and reused['recovery_reused'] and _tree(candidate)==before and _tree(folder)==frozen


def test_incomplete_copy_is_preserved_while_recovery_uses_fresh_sibling(source):
    root,folder=source;identity=uuid.uuid4().hex;partial=root/'data/studio_revision_candidates'/identity/'candidate';partial.mkdir(parents=True)
    (partial/'owner_note.txt').write_text('preserve incomplete work');before=_tree(partial)
    candidate,proof=build_title_page_candidate(root,folder,identity,'Modern Minimal',_tree(folder),recover=True)
    assert candidate.name=='candidate_recovery_001' and _tree(partial)==before and proof['puzzles_preserved']


def test_changed_complete_copy_is_held_not_replaced(source):
    root,folder=source;identity=uuid.uuid4().hex;frozen=_tree(folder)
    candidate,_=build_title_page_candidate(root,folder,identity,'Modern Minimal',frozen)
    (candidate/'keep.txt').write_text('owner change');before=_tree(candidate)
    with pytest.raises(ValueError,match='files changed'):build_title_page_candidate(root,folder,identity,'Modern Minimal',frozen,recover=True)
    assert _tree(candidate)==before and not (candidate.parent/'candidate_recovery_001').exists()


def test_recovery_attempts_bounded_without_deleting_partial_work(source):
    root,folder=source;identity=uuid.uuid4().hex;base=root/'data/studio_revision_candidates'/identity
    for name in ['candidate','candidate_recovery_001','candidate_recovery_002','candidate_recovery_003']:
        path=base/name;path.mkdir(parents=True);(path/'keep.txt').write_text(name)
    before=_tree(base)
    with pytest.raises(ValueError,match='attempts are held'):build_title_page_candidate(root,folder,identity,'Modern Minimal',_tree(folder),recover=True)
    assert _tree(base)==before
