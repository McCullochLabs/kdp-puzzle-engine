import hashlib
import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from publishing.studio_title_page_candidate import _resource_digest,_resource_digester,protected_pages


def test_shared_resource_decoded_once_and_objects_retained():
    class Stream(dict):
        calls=0
        def get_data(self):self.calls+=1;return b"font stream"
    obj=Stream({"/FontName":"Example"});digest=_resource_digester()
    expected=_resource_digest(obj);obj.calls=0
    assert digest(obj)==expected and digest(obj)==expected and obj.calls==1
    # The memo owns the object; a new check has no stale cached value.
    obj["/FontName"]="Changed"
    assert _resource_digest(obj)!=expected
    import gc,weakref
    reference=weakref.ref(obj);del obj;gc.collect()
    assert reference() is not None
    del digest;gc.collect();assert reference() is None


def test_cycles_still_fail_closed():
    value={};value["self"]=value
    with pytest.raises(ValueError,match="Cyclic"):_resource_digest(value)


def test_shared_page_digests_match_independent_page_reference(tmp_path):
    path=tmp_path/"fixture.pdf";pdf=canvas.Canvas(str(path))
    for i in range(5):pdf.drawString(80,600,f"Page {i}");pdf.showPage()
    pdf.save();reader=PdfReader(path);expected=[]
    for page in reader.pages[1:]:
        contents=page.get_contents()
        expected.append({"media":[float(v) for v in page.mediabox],"crop":[float(v) for v in page.cropbox],"rotation":page.rotation,"content_sha256":hashlib.sha256(contents.get_data() if contents else b"").hexdigest(),"resources_sha256":_resource_digest(page.get("/Resources",{}))})
    assert protected_pages(path)==expected
