from pathlib import Path
import pytest
from pypdf import PdfWriter
from preflight import preflight


def make_package(folder, count=24, wrong_page=None, wrap_pages=1):
    interior=PdfWriter()
    for i in range(count):
        interior.add_blank_page(width=432 if i==wrong_page else 612,height=792)
    interior.add_metadata({"/Author":"Audit Author"})
    with (folder/"interior.pdf").open("wb") as stream: interior.write(stream)
    wrap=PdfWriter()
    for _ in range(wrap_pages):wrap.add_blank_page(width=(17.25+count*.002252)*72,height=810)
    with (folder/"kdp_full_wrap.pdf").open("wb") as stream:wrap.write(stream)


def test_valid_uniform_package_passes(tmp_path):
    make_package(tmp_path)
    assert preflight(tmp_path)[0]


def test_later_wrong_trim_page_is_rejected(tmp_path):
    make_package(tmp_path,wrong_page=12)
    ok,notes=preflight(tmp_path)
    assert not ok
    assert any("13" in line and line.startswith("FAIL") for line in notes)


def test_oversize_interior_is_rejected(tmp_path):
    make_package(tmp_path,count=592)
    assert not preflight(tmp_path)[0]


@pytest.mark.parametrize("count,wrap_pages",[(0,1),(24,0),(24,2)])
def test_empty_or_multiple_page_print_components_fail_without_crashing(tmp_path,count,wrap_pages):
    make_package(tmp_path,count=count,wrap_pages=wrap_pages)
    ok,notes=preflight(tmp_path)
    assert not ok and any(line.startswith("FAIL") for line in notes)

@pytest.mark.parametrize("mutation",["rotate","encrypt","spine"])
def test_geometry_and_protection_fail_closed(tmp_path,mutation):
    from pypdf import PdfReader
    make_package(tmp_path)
    target=tmp_path/("kdp_full_wrap.pdf" if mutation=="spine" else "interior.pdf")
    writer=PdfWriter(clone_from=str(target))
    if mutation=="rotate": writer.pages[12].rotate(90)
    elif mutation=="encrypt": writer.encrypt("test-only-password")
    else: writer.pages[0].mediabox.upper_right=((17.25+48*.002252)*72,810)
    with target.open("wb") as stream:writer.write(stream)
    assert not preflight(tmp_path)[0]
