from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sudoku_symbols import PACKS, draw_symbol, pack_label


def main():
    target = ROOT / "reports" / "sudoku_symbol_pack_sampler.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(target), pagesize=letter)
    width, height = letter
    for pack, names in PACKS.items():
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(width / 2, height - 55, pack_label(pack))
        c.setFont("Helvetica", 10)
        c.drawCentredString(width / 2, height - 75, "The same nine symbols appear consistently on puzzle and solution pages.")
        for index, name in enumerate(names):
            row, col = divmod(index, 3)
            x = 135 + col * 170
            y = height - 175 - row * 190
            c.roundRect(x - 55, y - 55, 110, 110, 8, stroke=1, fill=0)
            draw_symbol(c, pack, index + 1, x, y, 105)
            c.setFont("Helvetica", 10)
            c.drawCentredString(x, y - 76, name.replace("_", " ").title())
        c.showPage()
    c.save()
    print(target)


if __name__ == "__main__":
    main()
