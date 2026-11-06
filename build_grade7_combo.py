"""Reproducible 25-word-search / 25-number-Sudoku book and production evidence.

Uses existing engines, approved cover assets, print geometry, and local gates.
No catalog approvals, uploads, or publishing operations are performed.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time

from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

import wordsearch
import sudoku
from publishing.package_layout import initialize_package_layout, package_file
from publishing.puzzle_integrity import write_manifest, verify_manifest, wordsearch_difficulty
from publishing.sudoku_difficulty import rate_sudoku
from publishing.product_qa import inspect_product, write_product_qa_report
from preflight import preflight

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'word_banks/grade7_wordsearch_sudoku_50.json'


def load_source(path=SOURCE):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    topics=[t for chapter in data['chapters'] for t in chapter['topics']]
    if len(data['chapters'])!=5 or len(topics)!=25:
        raise ValueError('Exactly five chapters with five word searches each are required.')
    words=[w for t in topics for w in wordsearch.clean_words(t['words'].split())]
    if len(words)!=300 or len(set(words))!=300:
        raise ValueError('The book must contain 300 distinct targets.')
    if any(len(t['words'].split())!=12 for t in topics) or any(len(w)>15 for w in words):
        raise ValueError('Each search requires twelve words fitting the 15 x 15 grid.')
    return data


def plan_book(data, seed):
    records=[]; seen=set(); audit=[]
    from publishing.grade7_editorial import GLOSSARY
    display_forms=json.loads(GLOSSARY.read_text(encoding='utf-8'))['display_forms']
    for chapter_index,chapter in enumerate(data['chapters']):
        searches=[]; numbers=[]
        for offset,topic in enumerate(chapter['topics']):
            rng=random.Random(seed+chapter_index*10000+offset)
            words=wordsearch.clean_words(topic['words'].split()); rng.shuffle(words)
            # Earlier chapters avoid reverse directions. The final three allow all eight.
            directions=((0,1),(1,0),(1,1),(1,-1)) if chapter_index<2 else None
            grid,placements,placed=wordsearch.generate_puzzle(words,15,directions=directions,rng=rng)
            searches.append(dict(type='word_search',name=topic['name'],prompt=topic['prompt'],
                grid=grid,placements=placements,words=placed,display_words=[display_forms.get(w,w) for w in words],intended_words=words,directions=directions,
                solution_grid=grid,solution_placements=placements,
                difficulty=wordsearch_difficulty(grid,placements,placed)))
            # Singles-only first chapter, then introduce box/line and pair deductions.
            requested='easy' if chapter_index==0 or offset<2 else 'medium'
            for attempt in range(400):
                srng=random.Random(seed+500000+chapter_index*10000+offset*400+attempt)
                solution=sudoku.make_solved(srng)
                puzzle=sudoku.make_puzzle(solution,'easy' if requested=='easy' else 'hard',srng)
                rating=rate_sudoku(puzzle)
                digest=hashlib.sha256(json.dumps(puzzle).encode()).hexdigest()
                if rating['label']==requested and rating['solved_by_supported_logic'] and digest not in seen:
                    seen.add(digest); break
            else:
                raise ValueError(f'No unique {requested} Sudoku after 400 candidates; no difficulty substitution was made.')
            numbers.append(dict(type='sudoku',name='Logic Lab',grid=puzzle,solution_grid=solution,
                difficulty=rating,display_style='numbers',generation_attempts=attempt+1))
        # Measured progression within each chapter, with stable ordering on ties.
        searches.sort(key=lambda r:r['difficulty']['score'])
        for item in searches+numbers:
            item['number']=len(records)+1; item['chapter']=chapter_index+1
            records.append(item)
        audit.append(dict(chapter=chapter['title'],word_searches=5,sudokus=5,
                          sudoku_candidate_attempts=sum(r['generation_attempts'] for r in numbers)))
    return records,audit


def text(c, content, x, top, width=504, size=13, leading=20, font='Sans', bottom=54):
    c.setFont(font,size); c.setFillGray(.14)
    y=top
    for paragraph in content.split('\n'):
        line=''
        for word in paragraph.split():
            if stringWidth(word,font,size)>width: raise ValueError('Unbreakable text exceeds available width.')
            candidate=(line+' '+word).strip()
            if line and stringWidth(candidate,font,size)>width:
                if y<bottom: raise ValueError('Text overflow.')
                c.drawString(x,y,line); y-=leading; line=word
            else: line=candidate
        if line:
            if y<bottom: raise ValueError('Text overflow.')
            c.drawString(x,y,line); y-=leading
        y-=8
    return y


def end_page(c):
    wordsearch.footer(c,c.getPageNumber()); c.showPage()


def heading(c,eyebrow,title,subtitle=''):
    text(c,eyebrow.upper(),54,738,size=10,font='SansB')
    text(c,title,54,692,size=26,leading=32,font='SansB')
    c.setStrokeGray(.25); c.setLineWidth(2); c.line(54,658,126,658)
    if subtitle: text(c,subtitle,54,627,size=13)


def render_interior(path,data,records):
    wordsearch.register_fonts(); sudoku.register_fonts()
    c=canvas.Canvas(str(path),pagesize=(612,792),pageCompression=1,invariant=1)
    c.setTitle(data['title']); c.setAuthor(data['author'])
    text(c,'THE SEVENTH-GRADE PUZZLE LAB',54,700,size=12,font='SansB')
    text(c,'Think,\nSearch,\nSolve',54,620,size=54,leading=66,font='SansB')
    text(c,'50 Word Search & Sudoku Puzzles\nfor Seventh Graders',54,350,size=21,leading=30)
    text(c,'25 themed word searches / 25 number Sudoku\nComplete solutions / Cross-subject thinking prompts',54,245,size=13)
    text(c,data['author']+'\nSladePuzzleCo',54,130,size=14); end_page(c)
    heading(c,'Welcome','A little curiosity. A lot to discover.')
    text(c,'Move from science and math to language, history, art, and design. Each chapter has five word searches and five number Sudoku puzzles. Take breaks, try a new strategy, and check your work in the solutions.',54,605,size=14,leading=22)
    text(c,'How to use this book\nWord searches: find all twelve targets in a straight line. The first two chapters use rightward, downward, or downward-diagonal paths. Later chapters also allow upward and backward words. Spaces and punctuation are omitted in the grid.\nSudoku: place digits 1 through 9 so each row, column, and 3 x 3 box contains each digit exactly once.\nDifficulty labels describe puzzle mechanics. Easy Sudoku uses singles; Medium introduces locked candidates or naked pairs. This book does not require guessing.\nThinking prompts are optional and open-ended. They are for discussion and do not have a single answer in the solution section.',54,475,size=13,leading=20)
    text(c,'Copyright 2026 '+data['author']+'. All rights reserved.\nPublished by SladePuzzleCo.',54,105,size=9,leading=13); end_page(c)
    heading(c,'Solve with a strategy','Your logic toolkit')
    text(c,'WORD SEARCH\nStart with a distinctive letter. Trace one straight direction at a time. Shared letters are allowed. Every target has one physical answer in its grid.\nNAKED SINGLE\nIf a cell has only one possible digit after checking its row, column, and box, place it.\nHIDDEN SINGLE\nIf a digit can go in only one cell within a row, column, or box, place it there.\nLOCKED CANDIDATE\nIf all possible places for a digit in a box lie in one row or column, remove that digit as a possibility elsewhere along that row or column. The reverse works too.\nNAKED PAIR\nIf exactly two cells in a row, column, or box share the same two possible digits, those digits cannot appear in any other cell of that unit.',54,610,size=13,leading=20)
    text(c,'Write small candidate digits lightly. Recheck the row, column, and box after every placement.',54,155,size=13); end_page(c)
    heading(c,'Find your next challenge','Five chapters. Fifty puzzles.')
    for i,ch in enumerate(data['chapters']):
        start=i*10+1
        text(c,f"0{i+1}  {ch['title']}\nPuzzles {start}-{start+9}  |  page {5+i*10}",54,605-i*83,size=16,leading=23,font='SansB')
    text(c,'Complete solutions begin on page 55. The Word Guide begins on page 85.\nPage numbers match the printed page footer.',54,145,size=12); end_page(c)
    for row in records:
        number=row['number']; chapter=data['chapters'][row['chapter']-1]
        row['puzzle_page']=c.getPageNumber()
        heading(c,f"Chapter {row['chapter']} / {chapter['title']}",f"Puzzle {number}: {row['name']}")
        label=row['difficulty']['label'].upper()
        if row['type']=='word_search':
            text(c,'WORD SEARCH  /  '+label,54,627,size=11,font='SansB')
            c.setFont('Sans',10); c.drawRightString(558,627,'FORWARD ONLY' if row['directions'] else 'ALL EIGHT DIRECTIONS')
            wordsearch.draw_grid(c,row['grid'],96,598,28,18)
            wordsearch.draw_word_list(c,row['display_words'],54,151,504,cols=3,heading_font=10,word_font=14,row_step=20)
            # Optional prompt is retained in the chapter reflection page/answer label records.
        else:
            text(c,'NUMBER SUDOKU  /  '+label,54,627,size=11,font='SansB')
            sudoku.draw_sudoku(c,row['grid'],90,595,48,'MonoB',27)
            description='Try singles: one candidate in a cell, or one place for a digit.' if label=='EASY' else 'Start with singles. Look for locked candidates or a naked pair when stuck.'
            text(c,description,54,125,size=13)
        end_page(c)
    for start in range(0,50,2):
        for slot,row in enumerate(records[start:start+2]):
            row['solution_page']=c.getPageNumber()
            top=731-slot*346
            text(c,f"SOLUTION {row['number']} / {row['name']}",54,top,size=13,font='SansB')
            if row['type']=='word_search':
                wordsearch.draw_grid(c,row['grid'],174,top-24,17.6,11,highlights=row['placements'])
            else:
                sudoku.draw_sudoku(c,row['solution_grid'],176.4,top-24,28.8,'MonoB',15)
        end_page(c)
    for chapter in data['chapters']:
        heading(c,'Take it further',chapter['title'])
        text(c,'Choose a prompt. Explain your thinking here, in a notebook, or in a conversation.',54,610,size=13)
        for i,topic in enumerate(chapter['topics']):
            top=547-i*92
            bottom=text(c,topic['name']+'\n'+topic['prompt'],54,top,size=12,leading=17)
            c.setStrokeGray(.7); c.setLineWidth(.5); c.line(54,bottom-3,558,bottom-3)
        end_page(c)
    from publishing.grade7_editorial import GLOSSARY
    glossary=json.loads(GLOSSARY.read_text(encoding='utf-8'))
    entries=sorted(glossary['definitions'].items())
    for start in range(0,len(entries),10):
        heading(c,'Word guide','Explore a word, then use it')
        text(c,'Short explanations for selected vocabulary. A * marks optional stretch vocabulary.',54,625,size=12)
        y=583
        for word,meaning in entries[start:start+10]:
            label=glossary['display_forms'].get(word,word)
            if word in glossary['stretch_terms']: label+=' *'
            y=text(c,label+': '+meaning,54,y,size=12,leading=17)-8
        end_page(c)
    c.save()
    return write_manifest(path,records,getattr(c,'_puzzle_text_regions',[]))


def run_engine(script,args,log):
    result=subprocess.run([sys.executable,str(ROOT/script),*args],cwd=ROOT,capture_output=True,text=True)
    log.append(dict(engine=script,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)


def build(destination,seed=20261022):
    destination=Path(destination)
    if destination.exists(): raise FileExistsError('Choose a new output directory; existing books are never overwritten.')
    initialize_package_layout(destination)
    stages=[]; started=time.perf_counter(); data=load_source()
    records,planning=plan_book(data,seed)
    from word_intelligence.store import WordIntelligenceStore
    store=WordIntelligenceStore.load(ROOT/'word_banks/word_intelligence')
    targets=sorted({w for row in records if row['type']=='word_search' for w in row['words']})
    unknown=[w for w in targets if store.get(w) is None]
    unreviewed=[w for w in targets if store.get(w) is not None and store.get(w).is_unclassified()]
    coverage=dict(total_targets=len(targets),unknown_words=unknown,unreviewed_words=unreviewed,
        reviewed_library_coverage=round((len(targets)-len(unknown)-len(unreviewed))/len(targets),4),
        basis='Existing trusted or approved library links; this does not certify grade suitability or cross-subject topic fit.',
        editorial_review='Teacher review pending')
    from publishing.grade7_editorial import review_source,validate_review,GLOSSARY
    editorial=review_source(data,store,SOURCE)
    editorial_errors=validate_review(editorial,data,SOURCE)
    if editorial_errors: raise ValueError('; '.join(editorial_errors))
    review_path=package_file(destination,'EDITORIAL_REFERENCE_REVIEW.json',for_write=True)
    review_path.write_text(json.dumps(editorial,indent=2),encoding='utf-8')
    checklist=['# Teacher and physical-proof review','',
        'Status: pending human review. The following suggested responses are discussion aids, not an exhaustive answer key.','',
        '- [ ] Review all 300 target words in EDITORIAL_REFERENCE_REVIEW.json for your students.',
        '- [ ] Check the 97 Word Guide explanations and the eight optional stretch terms.',
        '- [ ] Confirm topic names, prompts, instructions, and Easy/Medium progression suit the intended readers.',
        '- [ ] Print representative word searches, Sudoku puzzles, solutions, and a Word Guide page at Actual Size.',
        '- [ ] Inspect letters, numbers, highlights, line weights, contrast, writing space, gutter, and trim.',
        '- [ ] Inspect a printer-produced bound proof and the marketplace preview before publication.',
        '- [ ] Record reviewer name, date, corrections, and approval decision.','',
        'Reviewer: __________________  Date: ______________  Decision: __________________','',
        '## Prompt review and suggested responses','']
    for prompt in editorial['prompts']:
        checklist.extend(['### '+prompt['topic'],prompt['prompt'],'',prompt['suggested_response'],''])
    package_file(destination,'TEACHER_AND_PRINT_REVIEW.md',for_write=True).write_text('\n'.join(checklist),encoding='utf-8')
    coverage.update(provisional_reference_reviewed_targets=editorial['reviewed_targets'],
                    provisional_reference_reviewed_coverage=editorial['reviewed_targets']/len(targets),
                    teacher_approval='pending',editorial_reference_path=str(review_path.resolve()),
                    editorial_reference_sha256=hashlib.sha256(review_path.read_bytes()).hexdigest())
    stages.append(dict(stage='planning',seconds=round(time.perf_counter()-started,3),chapters=planning))
    interior=package_file(destination,'interior.pdf',for_write=True)
    manifest=render_interior(interior,data,records)
    reader=PdfReader(interior); pages=len(reader.pages)
    issues=verify_manifest(interior,json.loads(manifest.read_text()),pages)
    if issues: raise ValueError('; '.join(issues))
    stages.append(dict(stage='independent_puzzle_verification',puzzles=len(records),errors=issues,pages=pages))
    # Use an already approved reading-themed asset; do not grant new artwork approval.
    art=ROOT/'cover_assets/background_photos/school_middle_learning_v1.png'
    from background_generation.index import require_production_approved_cover_asset
    asset=require_production_approved_cover_asset(art)
    front=package_file(destination,'front_cover.png',for_write=True)
    sample_word=''.join(''.join(r) for r in records[0]['grid'])
    first_sudoku=next(r for r in records if r['type']=='sudoku')
    sample_sudoku=''.join(str(v) if v else '.' for r in first_sudoku['grid'] for v in r)
    run_engine('cover.py',['--title',data['title'],'--subtitle',data['subtitle'],'--author',data['author'],
        '--badge','50 PUZZLES','--format-label','WORD SEARCH + SUDOKU','--puzzle-type','Word Search + Sudoku',
        '--puzzle-count','50','--sample-wordsearch',sample_word,'--sample-sudoku',sample_sudoku,
        '--palette','ocean','--style','photo','--art',str(art),'--out',str(front)],stages)
    blurb='Explore five chapters of science, math, language, people, and creative thinking. Solve 25 themed word searches and 25 number Sudoku puzzles, with complete solutions and optional thinking prompts. Designed for seventh-grade recreational enrichment.'
    run_engine('wrap_cover.py',['--front',str(front),'--pages',str(pages),'--palette','ocean',
        '--title',data['title'],'--author',data['author'],'--back-heading','CURIOSITY MEETS LOGIC',
        '--back',blurb,'--puzzle-type','Word Search + Sudoku','--puzzle-count','50','--sample-sudoku',sample_sudoku,
        '--out',str(package_file(destination,'kdp_full_wrap.pdf',for_write=True)),
        '--preview-out',str(package_file(destination,'kdp_full_wrap_preview.png',for_write=True))],stages)
    metadata={**data,'puzzle_type':'Word Search + Sudoku','puzzle_type_id':'mixed','puzzle_count':50,
        'page_count':pages,'trim_size':'8.5x11','detected_topic':'Grade 7 / middle school','require_puzzle_manifest':True,'cover_art':str(art),
        'cover_puzzle_type':'Word Search + Sudoku','difficulty':'Easy to Medium','seed':seed,'vocabulary_coverage':coverage,
        'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'glossary_sha256':hashlib.sha256(GLOSSARY.read_bytes()).hexdigest(),
        'editorial_source_path':str(SOURCE),'cover_asset_id':asset['asset_id']}
    package_file(destination,'PACKAGE_SOURCE_RECORD.json',for_write=True).write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    package_file(destination,'COVER_ART_RIGHTS_LEDGER.txt',for_write=True).write_text('Existing approved project asset: '+str(art)+'\nAsset ID: '+asset['asset_id']+'\nNo new rights or aesthetic approval was granted by this build.\n',encoding='utf-8')
    ok,lines=preflight(destination)
    package_file(destination,'PUBLISHER_PREFLIGHT.txt',for_write=True).write_text('\n'.join(lines),encoding='utf-8')
    package_file(destination,'KDP_LISTING_KIT.txt',for_write=True).write_text(data['title']+'\n'+data['subtitle']+'\nAuthor: '+data['author']+'\n\n'+blurb+f'\n\n{pages} pages. 8.5 x 11 inches. 300 distinct targets. Full solutions.\nTeacher/editorial review and physical proof remain pending.\n',encoding='utf-8')
    package_file(destination,'PRODUCTION_PROOF_GATE.txt',for_write=True).write_text('LOCAL AUTOMATED PROOF\n50/50 puzzles independently verified against the PDF-bound manifest.\nHuman editorial, aesthetic and physical proof review remain pending.\n',encoding='utf-8')
    report=inspect_product(ROOT,destination,metadata)
    write_product_qa_report(package_file(destination,'PRODUCT_QA.txt',for_write=True),report)
    audit=dict(context7_role='Documentation reference, not an autonomous production observer.',
        documentation=['https://pypdf.readthedocs.io/en/stable/user/extract-text.html','https://docs.reportlab.com/reportlab/userguide/ch2_graphics/','https://docs.reportlab.com/reportlab/userguide/ch3_fonts/'],
        stages=stages,seed=seed,puzzles=50,word_searches=25,sudokus=25,unique_targets=300,pages=pages,vocabulary_coverage=coverage,
        difficulty_counts=dict(Counter((r['type']+':'+r['difficulty']['label']) for r in records)),
        preflight_passed=ok,qa=report.to_dict(),human_editorial_review='pending',physical_proof='not inspected')
    audit['editorial_reference_review']=dict(reviewed_targets=300,glossary_entries=len(editorial['glossary_targets']),
        reviewed_prompts=25,teacher_approval='pending',source_fingerprint=editorial['source_sha256'])
    package_file(destination,'PRODUCTION_AUDIT.json',for_write=True).write_text(json.dumps(audit,indent=2),encoding='utf-8')
    if not ok or report.blockers: raise ValueError('Production audit found blockers; inspect the saved reports.')
    print(json.dumps(dict(output=str(destination),pages=pages,qa=report.status,difficulty=audit['difficulty_counts'])))
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',required=True); parser.add_argument('--seed',type=int,default=20261022)
    args=parser.parse_args(); build(args.out,args.seed)
