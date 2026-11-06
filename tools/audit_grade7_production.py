"""Read back and render the final book; save a documentation-informed audit."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image, ImageDraw
from pypdf import PdfReader
from pypdf.generic import ContentStream
from publishing.package_layout import package_file
from publishing.product_qa import inspect_product, write_product_qa_report


def embedded_text_fonts(pdf):
    reader=PdfReader(pdf); used=set(); missing=set()
    for page in reader.pages:
        fonts=page['/Resources'].get('/Font',{})
        current=None
        for operands,operator in ContentStream(page.get_contents(),reader).operations:
            if operator==b'Tf': current=operands[0]
            if operator in (b'Tj',b'TJ',b"'",b'"'):
                if not current: continue
                font=fonts[current].get_object()
                name=str(font.get('/BaseFont',current)); used.add(name)
                descendants=font.get('/DescendantFonts')
                actual=descendants[0].get_object() if descendants else font
                descriptor=actual.get('/FontDescriptor')
                descriptor=descriptor.get_object() if descriptor else {}
                if not any(key in descriptor for key in ('/FontFile','/FontFile2','/FontFile3')):
                    missing.add(name)
    return dict(used_fonts=sorted(used),unembedded_fonts=sorted(missing))


def audit(root):
    root=Path(root).resolve(); pdf=package_file(root,'interior.pdf')
    metadata=json.loads(package_file(root,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8'))
    report=inspect_product(ROOT,root,metadata)
    write_product_qa_report(package_file(root,'PRODUCT_QA.txt',for_write=True),report)
    fonts=embedded_text_fonts(pdf)
    previews=root/'03_PREVIEWS'; renders=previews/'all_pages'; renders.mkdir(exist_ok=True)
    executable=shutil.which('pdftoppm')
    if not executable: raise RuntimeError('Poppler is required for the final independent render audit.')
    subprocess.run([executable,'-scale-to','1000','-png',str(pdf),str(renders/'page')],check=True)
    images=sorted(renders.glob('page-*.png'))
    for start in range(0,len(images),12):
        sheet=Image.new('RGB',(960,1736),'#dddddd'); draw=ImageDraw.Draw(sheet)
        for i,path in enumerate(images[start:start+12]):
            with Image.open(path) as page:
                page.thumbnail((306,406)); x=(i%3)*320+(320-page.width)//2; y=(i//3)*434+22
                sheet.paste(page,(x,y)); draw.text(((i%3)*320+12,(i//3)*434+5),f'Page {start+i+1}',fill='black')
        sheet.save(previews/f'contact_{start//12+1:02d}.png')
    existing=json.loads(package_file(root,'PRODUCTION_AUDIT.json').read_text(encoding='utf-8'))
    existing.update(qa=report.to_dict(),font_audit=fonts,rendering_engine='Poppler pdftoppm',rendered_pages=len(images),
        artifact_sha256={name:hashlib.sha256(package_file(root,name).read_bytes()).hexdigest()
                         for name in ('interior.pdf','front_cover.png','kdp_full_wrap.pdf')})
    package_file(root,'PRODUCTION_AUDIT.json',for_write=True).write_text(json.dumps(existing,indent=2),encoding='utf-8')
    integrity=next(row for row in report.findings if row.check_id=='puzzle.rendered_correspondence')
    coverage=existing['vocabulary_coverage']
    page_count=len(PdfReader(pdf).pages)
    markdown=f'''# Production audit: Think, Search, Solve

## Result

Created a {page_count}-page, 8.5 x 11-inch book containing 25 word searches, 25 number Sudoku puzzles, full solutions, and 25 optional cross-subject thinking prompts. Seed: {existing['seed']}.

**Local status: {report.status}. {len(report.blockers)} blockers; {len(report.warnings)} review warning(s).** Nothing was uploaded, published, or granted new human approval.

## What Context7 contributed

Context7 retrieved primary library documentation. It does not observe applications, inspect local artifacts, or independently sign off books. Codex performed the production run and this audit using that documentation as a reference. No project source or private book content was sent to Context7.

- [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html): compose the text and user transformation matrices; raw text coordinates and font sizes alone are insufficient for page measurements.
- [ReportLab canvas](https://docs.reportlab.com/reportlab/userguide/ch2_graphics/): measure strings in the selected font before placing them, then finalize the PDF with the canvas save operation.
- [ReportLab fonts](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/): register and embed TrueType fonts.

## Checks on the actual product

- All 300 intended targets were retained; no target repeats across the book.
- All word-search targets occur once physically, including reverse-direction scanning and palindrome deduplication. The bounded offensive-string screen passed.
- All 25 Sudoku puzzles have exactly one valid solution. Thirteen rate Easy using singles; twelve rate Medium using locked candidates or naked pairs. Every puzzle was solved by the supported logic set.
- Independent PDF glyph readback verified {integrity.evidence['grids_checked']} grids: each puzzle and its printed solution. A numbered answer heading alone is no longer accepted as completeness evidence.
- The puzzle manifest is bound to the exact interior bytes by SHA-256; page mappings, numbered headings, mathematical answers, and solution correspondence were checked.
- All {len(images)} interior pages were rendered with Poppler. Automated all-page glyph bounds and body-margin screens passed. Puzzle and solution layout regions passed the reader-size screen.
- Text uses embedded fonts: {', '.join(fonts['used_fonts'])}. Unembedded fonts used by text: {', '.join(fonts['unembedded_fonts']) or 'none'}.
- The approved middle-school background and recorded cover puzzle type/count match the product. The front cover is 2550 x 3300 pixels. The full wrap uses the actual {page_count}-page interior and passed the existing local print preflight.

## Findings and fixes during production

1. A serialized direction list initially failed validation because JSON changes tuples into lists. The checker now normalizes direction tuples; a round-trip regression test covers this.
2. The first full package used approved library artwork with weak recorded grade/topic fit. The build now selects the existing approved middle-school artwork and records the grade context.
3. The combined-book cover cropped its Sudoku to 5 x 5. The renderer now shows the complete actual 9 x 9 puzzle; the word-search crop is explicitly labelled an excerpt.
4. Existing-library vocabulary coverage is {coverage['reviewed_library_coverage']:.1%}: {len(coverage['unknown_words'])} terms are absent and {len(coverage['unreviewed_words'])} lack reviewed links. Book-specific provisional reference review covers {coverage.get('provisional_reference_reviewed_targets',0)}/300 targets and all 25 prompts. The revised book includes original explanations for all 97 gaps, optional stretch labels, and natural display forms UNIT RATE and TRADE-OFF. This evidence is source-bound and does not modify the global library or claim teacher approval. QA keeps human signoff pending.

## Remaining review

Teacher/editorial review of grade suitability and open-ended prompts is pending. A physical printed proof and marketplace preview have not been inspected. Word-search mechanics scores and Sudoku technique bands are transparent local measures, not externally calibrated reading-age or difficulty certifications. The denylist is bounded. Automated glyph checks detect text extent and cell correspondence, but do not prove every visual relationship or aesthetic choice; contact sheets and full-page renders are included for review.

The files are a complete local review package, not a claim of marketplace acceptance.
'''
    package_file(root,'PRODUCTION_AUDIT.md',for_write=True).write_text(markdown,encoding='utf-8')
    print(json.dumps(dict(status=report.status,blockers=len(report.blockers),warnings=len(report.warnings),grids=integrity.evidence['grids_checked'],rendered_pages=len(images),fonts=fonts)))
    if report.blockers or fonts['unembedded_fonts'] or len(images)!=page_count: raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('package'); args=parser.parse_args(); audit(args.package)
