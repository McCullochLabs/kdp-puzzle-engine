from io import BytesIO
import pytest
from reportlab.pdfgen import canvas
from publishing.pdf_print_screen import scan_pdf, selftest
from publishing.title_pages import TitlePageSpec, render_title_page, STYLE_LABELS


def assert_print_screen(buffer):
    result=scan_pdf(buffer)
    assert not [s for s in result['strokes'] if s['status']!='AT_OR_ABOVE_MINIMUM']
    assert not result['font_below_7pt_samples']
    assert not result['unsupported']


def test_transformed_painted_paths_and_unused_widths():
    selftest()


@pytest.mark.parametrize('style',list(STYLE_LABELS))
def test_title_page_strokes_and_compass_text_meet_minimum(style):
    buffer=BytesIO();c=canvas.Canvas(buffer,pagesize=(612,792))
    render_title_page(c,TitlePageSpec('Roadside Word Discoveries',puzzle_type='Word Scramble + Trivia',topic='Travel & Adventure',style=style))
    c.save();buffer.seek(0);assert_print_screen(buffer)


def test_word_grid_print_strokes():
    import wordsearch
    wordsearch.register_fonts();buffer=BytesIO();c=canvas.Canvas(buffer,pagesize=(612,792))
    wordsearch.draw_grid(c,[list('AB'),list('CD')],80,700,24,14)
    c.save();buffer.seek(0);assert_print_screen(buffer)


def test_product_qa_blocks_actual_thin_stroke_and_small_text(tmp_path):
    from publishing.package_layout import initialize_package_layout, package_file
    from publishing.product_qa import inspect_product
    initialize_package_layout(tmp_path)
    target=package_file(tmp_path,'interior.pdf',for_write=True)
    c=canvas.Canvas(str(target),pagesize=(612,792));c.setLineWidth(.5);c.line(80,500,400,500)
    c.setFont('Helvetica',6);c.drawString(80,600,'Small print');c.save()
    report=inspect_product(tmp_path,tmp_path,{'trim_size':'8.5x11'})
    checks={row.check_id:row for row in report.findings}
    assert not checks['interior.print_strokes'].passed
    assert not checks['interior.minimum_font'].passed
    assert checks['interior.print_strokes'] in report.blockers
    assert checks['interior.minimum_font'] in report.blockers


def test_scaled_form_text_uses_parent_transform():
    buffer=BytesIO();c=canvas.Canvas(buffer)
    c.beginForm('small');c.setFont('Helvetica',5);c.drawString(10,10,'Scaled readable text');c.endForm()
    c.saveState();c.scale(2,2);c.doForm('small');c.restoreState();c.save();buffer.seek(0)
    result=scan_pdf(buffer)
    assert not result['font_below_7pt_samples']
    assert result['font_min_effective_height_pt']==10


def test_invisible_text_is_not_a_print_font_failure():
    buffer=BytesIO();c=canvas.Canvas(buffer)
    t=c.beginText(80,700);t.setFont('Helvetica',5);t.setTextRenderMode(3);t.textOut('Invisible search text');c.drawText(t)
    c.save();buffer.seek(0);result=scan_pdf(buffer)
    assert not result['font_below_7pt_samples']
    assert result['font_min_effective_height_pt'] is None


def test_empty_move_only_path_is_not_a_painted_thin_line():
    buffer=BytesIO();c=canvas.Canvas(buffer);c.setLineWidth(.5)
    path=c.beginPath();path.moveTo(80,700);c.drawPath(path,stroke=1,fill=0)
    c.save();buffer.seek(0);assert not scan_pdf(buffer)['strokes']
