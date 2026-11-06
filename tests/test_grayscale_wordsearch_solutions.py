from io import BytesIO
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader
from pypdf.generic import ContentStream
import wordsearch as ws


def test_grayscale_solution_option_preserves_grid_and_uses_neutral_highlights():
 ws.register_fonts();stream=BytesIO();canvas=Canvas(stream)
 ws.draw_grid(canvas,[list('CAT'),list('XXX'),list('XXX')],70,600,30,18,highlights=[[(0,0),(0,1),(0,2)]],grayscale=True)
 canvas.save();reader=PdfReader(stream);page=reader.pages[0]
 assert 'CATXXXXXX'==''.join(page.extract_text().split())
 operations=ContentStream(page.get_contents(),reader).operations
 colors=[list(map(float,args)) for args,op in operations if op==b'RG']
 assert all(abs(row[0]-row[1])<1e-8 and abs(row[1]-row[2])<1e-8 for row in colors)
 assert any(op==b'G' and abs(float(args[0])-.65)<1e-8 for args,op in operations)

