import io
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from pypdf import PdfReader
import wordsearch as ws


def test_long_passport_heading_and_entries_stay_in_margins():
    ws.register_fonts()
    class CheckedCanvas(Canvas):
        def drawString(self,x,y,text,*args,**kwargs):
            width=pdfmetrics.stringWidth(text,self._fontname,self._fontsize)
            assert x >= ws.MARGIN-.1, (text,x)
            assert x+width <= ws.PAGE_W-ws.MARGIN+.1, (text,x+width)
            return super().drawString(x,y,text,*args,**kwargs)
    c=CheckedCanvas(io.BytesIO(),pagesize=(ws.PAGE_W,ws.PAGE_H),initialFontName='Sans')
    ws.signature_pages(c,[{'name':'A VERY LONG SEASONAL PASSPORT ENTRY NAME '*3} for _ in range(100)],'Fall',{'passport_title':'My Harvest Puzzle Passport'})
    c.save()


def test_wordsearch_title_fonts_are_embedded():
    ws.register_fonts();buffer=io.BytesIO()
    c=Canvas(buffer,pagesize=(ws.PAGE_W,ws.PAGE_H),initialFontName='Sans')
    ws.front_matter(c,'Thanksgiving & Fall Word Search - Signature Edition','Harvest, home, and gratitude','Jordan M. Slade',{'signature_edition':{'enabled':True}})
    c.save()
    for page in PdfReader(buffer).pages:
        for ref in page['/Resources']['/Font'].values():
            font=ref.get_object()
            descriptor=font.get('/FontDescriptor',{}).get_object()
            assert any(key in descriptor for key in ('/FontFile','/FontFile2','/FontFile3')),font.get('/BaseFont')
