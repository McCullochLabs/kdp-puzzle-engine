import gc,hashlib,time,tkinter as tk
from pathlib import Path
import pytest
from reportlab.pdfgen import canvas
from publishing.studio_preview import StudioPreview,render_document,render_saved_documents

@pytest.fixture
def pdf(tmp_path):
    path=tmp_path/'book.pdf';c=canvas.Canvas(str(path))
    for i in range(3):
        c.setFillColorRGB(i/3,.2,.7-i/5);c.rect(40,40,400,600,fill=1);c.showPage()
    c.save();return path

@pytest.mark.parametrize('page,expected',[(0,0),(1,1),(2,2),(99,2),(-1,0)])
def test_single_pdf_renders_only_requested_page_and_reports_count(pdf,page,expected):
    before=pdf.read_bytes();images,info=render_saved_documents([('Interior',pdf,page)])
    assert info==(3,expected) and len(images)==1
    assert f'PDF page {expected+1} of 3' in images[0][0]
    assert images[0][1].tobytes()==render_document(pdf,expected).tobytes()
    assert pdf.read_bytes()==before


def pump(root,predicate,seconds=5):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        root.update()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Preview did not finish')


def test_actual_pdf_controls_navigate_all_pages_without_preloading(pdf):
    gc.collect()
    try:root=tk.Tk()
    except tk.TclError as exc:pytest.skip(str(exc))
    errors=[];root.report_callback_exception=lambda *a:errors.append(a)
    before=pdf.read_bytes()
    try:
        window=StudioPreview(root,documents=[('Interior',pdf,0)])
        pump(root,lambda:window.document_page_count==3 and not window.busy and bool(window.images))
        assert window.previous_button.instate(['disabled'])
        window.next_button.invoke();pump(root,lambda:not window.busy and window.document_page==1)
        assert len(window.images)==1 and window.images[0][1].tobytes()==render_document(pdf,1).tobytes()
        window.page_number.set('3');window.page_button.invoke();pump(root,lambda:not window.busy and window.document_page==2)
        assert window.next_button.instate(['disabled']) and 'PDF page 3 of 3' in window.note.get()
        for bad in ['0','4','x','1.5','9'*5000]:
            window.page_number.set(bad);window.page_button.invoke();root.update()
            assert window.document_page==2 and 'Choose a page' in window.note.get()
        window.previous_button.invoke();pump(root,lambda:not window.busy and window.document_page==1)
        assert len(window.images)==1 and pdf.read_bytes()==before and not errors
    finally:root.destroy();gc.collect()


def test_multiple_document_images_keep_existing_preview_cycle(tmp_path):
    from PIL import Image
    paths=[]
    for n,color in enumerate(['red','blue']):
        p=tmp_path/f'{n}.png';Image.new('RGB',(200,300),color).save(p);paths.append(p)
    gc.collect()
    try:root=tk.Tk()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        window=StudioPreview(root,documents=[('Front',paths[0],0),('Back',paths[1],0)])
        pump(root,lambda:len(window.images)==2 and not window.busy)
        assert not window.document_navigation
        window.next_button.invoke();root.update();assert window.index==1
        window.previous_button.invoke();root.update();assert window.index==0
    finally:root.destroy();gc.collect()


def test_closed_preview_releases_owned_tk_objects_on_main_thread(pdf):
    import threading,weakref
    gc.collect()
    try:root=tk.Tk()
    except tk.TclError as exc:pytest.skip(str(exc))
    main=threading.get_ident();released=[]
    try:
        window=StudioPreview(root,documents=[('Interior',pdf,0)])
        pump(root,lambda:window.images and not window.busy)
        refs=[weakref.ref(window.note),weakref.ref(window.page_number),weakref.ref(window.photo)]
        finalizers=[weakref.finalize(obj,lambda:released.append(threading.get_ident())) for obj in [window.note,window.page_number,window.photo]]
        window.destroy();root.update()
        assert all(ref() is None for ref in refs) and released==[main]*3
        assert window._closed and window.note is None and window.page_number is None
        worker=threading.Thread(target=gc.collect);worker.start();worker.join(timeout=2);assert not worker.is_alive()
        window._watch();window.show(0);window.navigate(1)
    finally:root.destroy();gc.collect()
