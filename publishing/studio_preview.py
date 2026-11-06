"""Actual PDF/image previews; rendering runs outside the Tk event loop."""
from dataclasses import asdict
import json
import hashlib
from pathlib import Path
from queue import Empty, Queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk
import pypdfium2 as pdfium

from .activity_packs import generate_activities, render_pdfs, validate_plan


def render_pack_preview(plan):
    plan = validate_plan(plan)
    activities = generate_activities(plan)
    with tempfile.TemporaryDirectory(prefix='studio_preview_') as folder:
        root = Path(folder)
        render_pdfs(root, plan, activities)
        output = []
        for name, page in (('ACTIVITIES.pdf', 0), ('ACTIVITIES.pdf', 1), ('ANSWERS.pdf', 1)):
            output.append((name + (' · Introduction' if page == 0 else ' · Activity 1'), render_document(root / name, page)))
        return output


_PDF_LOCK = threading.RLock()


def render_document(path, page=0):
    # PDFium rendering must not run concurrently in separate preview windows.
    with _PDF_LOCK:
        return _render_document(path, page)


def _render_document(path, page=0):
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        return _render_pdf_page(str(path),page)[0]
    with Image.open(path) as image:
        return image.convert('RGB').copy()


def _render_pdf_page(source,page):
    with pdfium.PdfDocument(source) as document:
        count=len(document)
        if not count:raise ValueError('This PDF has no pages.')
        index=max(0,min(int(page),count-1));pdf_page=document[index]
        try:
            bitmap=pdf_page.render(scale=1.1)
            try:return bitmap.to_pil().convert('RGB').copy(),count,index
            finally:bitmap.close()
        finally:pdf_page.close()


def render_saved_documents(documents):
    """Render one requested PDF page, never preload an entire book."""
    if len(documents)==1 and Path(documents[0][1]).suffix.lower()=='.pdf':
        label,path,*rest=documents[0]
        with _PDF_LOCK:
            source=str(path)
            if len(rest)>1:
                digest=rest[1]
                if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                    raise ValueError('Invalid saved PDF fingerprint.')
                source=Path(path).read_bytes()
                if hashlib.sha256(source).hexdigest()!=digest:
                    raise ValueError('The PDF changed after its answer-page index was read. Reopen the saved solutions.')
            image,count,page=_render_pdf_page(source,int(rest[0]) if rest else 0)
        return [(f'{label} · PDF page {page+1} of {count}',image)],(count,page)
    return [(item[0],render_document(item[1],item[2] if len(item)>2 else 0)) for item in documents],None


class StudioPreview(tk.Toplevel):
    def __init__(self, parent, plan_getter=None, documents=()):
        super().__init__(parent)
        self._closed=False
        self.title('Actual page preview')
        from word_search_creator import fit_dialog_to_screen
        fit_dialog_to_screen(self, 690, 760, 500, 450)
        self.get_plan, self.documents = plan_getter, tuple(documents)
        self.document_navigation=not plan_getter and len(self.documents)==1 and Path(self.documents[0][1]).suffix.lower()=='.pdf'
        self.document_page=int(self.documents[0][2]) if self.document_navigation and len(self.documents[0])>2 else 0
        self.document_page_count=None
        self.results = Queue()
        self.fingerprint = None
        self.busy = False
        self.images = []
        self.index = 0
        self.note = tk.StringVar(self, 'Preparing an actual page preview…')
        ttk.Label(self, textvariable=self.note, wraplength=600, padding=12).pack(fill='x')
        self.image_label = ttk.Label(self, anchor='center')
        self.image_label.pack(fill='both', expand=True)
        buttons = ttk.Frame(self, padding=12)
        buttons.pack(fill='x')
        self.previous_button=ttk.Button(buttons,text='Previous',command=lambda:self.navigate(-1))
        self.previous_button.pack(side='left')
        self.next_button=ttk.Button(buttons,text='Next',command=lambda:self.navigate(1))
        self.next_button.pack(side='left',padx=8)
        self.page_number=tk.StringVar(self,str(self.document_page+1))
        if self.document_navigation:
            self.page_entry=ttk.Entry(buttons,textvariable=self.page_number,width=5)
            self.page_entry.pack(side='left')
            self.page_entry.bind('<Return>',lambda event:self.go_to_page())
            self.page_button=ttk.Button(buttons,text='Go to PDF page',command=self.go_to_page)
            self.page_button.pack(side='left',padx=5)
        self._update_navigation()
        ttk.Button(buttons, text='Close', command=self.destroy).pack(side='right')
        self._job = self.after(50, self._watch)
        self.bind('<Destroy>', self._destroyed, add='+')
        self.bind('<Configure>', lambda event: self.show(0) if event.widget == self else None)

    def _destroyed(self, event):
        if event.widget == self:
            self._closed=True
            try:self.after_cancel(self._job)
            except tk.TclError:pass
            # Destroyed widget attributes can retain Python cycles until a
            # worker triggers GC. Drop owned Tk objects here on the UI thread.
            self.note=None
            self.page_number=None
            self.photo=None
            self.images=[]
            self.get_plan=None

    def _watch(self):
        if self._closed:return
        try:
            while True:
                fingerprint, images, error, page_info = self.results.get_nowait()
                self.busy = False
                if error:
                    self.images = []
                    self.image_label.configure(image='')
                    self.document_page_count=None
                    self.note.set('Preview could not be rendered: ' + error)
                else:
                    self.images = images
                    if page_info:
                        self.document_page_count,self.document_page=page_info
                        self.page_number.set(str(self.document_page+1))
                    self.index = 0
                    self.show(0)
                self._update_navigation()
        except Empty: pass
        if not self.busy:
            try:
                plan = self.get_plan() if self.get_plan else None
                documents=self.documents
                if self.document_navigation:
                    documents=((documents[0][0],documents[0][1],self.document_page,*documents[0][3:]),)
                fingerprint = json.dumps(asdict(plan), sort_keys=True) if plan else str([
                    (str(item[1]), Path(item[1]).stat().st_mtime_ns, Path(item[1]).stat().st_size, item[2:]) for item in documents])
                if fingerprint != self.fingerprint:
                    self.fingerprint = fingerprint
                    self.busy = True
                    self.images = []
                    self.image_label.configure(image='')
                    self.note.set('Rendering actual pages…')
                    self._update_navigation()
                    results=self.results
                    def work(plan=plan,documents=documents,fingerprint=fingerprint):
                        try:
                            images,page_info=(render_pack_preview(plan),None) if plan else render_saved_documents(documents)
                            results.put((fingerprint,images,'',page_info))
                        except Exception as exc:results.put((fingerprint,[],str(exc),None))
                    threading.Thread(target=work, daemon=True).start()
            except (ValueError, OSError, tk.TclError):
                self.images = []
                self.image_label.configure(image='')
                self.fingerprint = None
                self.note.set('The plan changed. Correct its inputs to refresh the preview.')
        if not self._closed:self._job = self.after(700, self._watch)

    def _update_navigation(self):
        if self._closed or not self.document_navigation:return
        ready=not self.busy and self.document_page_count is not None
        self.previous_button.configure(state='normal' if ready and self.document_page>0 else 'disabled')
        self.next_button.configure(state='normal' if ready and self.document_page<self.document_page_count-1 else 'disabled')
        self.page_entry.configure(state='normal' if ready else 'disabled')
        self.page_button.configure(state='normal' if ready else 'disabled')

    def navigate(self,delta):
        if self._closed:return
        if not self.document_navigation:
            self.show(delta)
            return
        if self.busy or self.document_page_count is None:return
        target=max(0,min(self.document_page+delta,self.document_page_count-1))
        self.page_number.set(str(target+1))
        self.go_to_page()

    def go_to_page(self):
        if self._closed:return
        if self.busy or self.document_page_count is None:return
        raw=self.page_number.get().strip()
        if len(raw)>9 or not raw.isascii() or not raw.isdigit() or not 1<=int(raw)<=self.document_page_count:
            self.note.set(f'Choose a page from 1 to {self.document_page_count}.')
            return
        target=int(raw)-1
        if target==self.document_page:return
        self.document_page=target
        # Restart the existing poller, rather than creating parallel renderers.
        try:self.after_cancel(self._job)
        except tk.TclError:pass
        self._watch()

    def show(self, delta):
        if self._closed:return
        if not self.images: return
        self.index = (self.index + delta) % len(self.images)
        label, image = self.images[self.index]
        image = image.copy()
        image.thumbnail((max(100, self.winfo_width()-30), max(100, self.winfo_height()-130)))
        self.photo = ImageTk.PhotoImage(image, master=self)
        self.image_label.configure(image=self.photo)
        self.note.set((f'{label}' if self.document_navigation else f'{label} · {self.index+1}/{len(self.images)}')+' · Preview is not final print approval')
