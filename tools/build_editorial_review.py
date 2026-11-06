"""Build source-linked human editorial packets from preserved production records."""
from pathlib import Path
import json,hashlib,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from publishing.package_layout import package_file
from pypdf import PdfReader
import puzzle_book_studio as studio

def norm(text):return re.sub(r'[^a-z0-9]+','',text.casefold())

def build(output):
 output=Path(output)
 if output.exists():raise FileExistsError('Preserve prior editorial packets; choose a new version.')
 portfolio=json.loads((ROOT/'audits/system_20261101/portfolio_current.json').read_text());results=[]
 for book in portfolio:
  folder=Path(book['folder']);source=package_file(folder,'PACKAGE_SOURCE_RECORD.json');meta=json.loads(source.read_text(encoding='utf-8-sig'))
  pdf=package_file(folder,'interior.pdf');reader=PdfReader(pdf);manifest=pdf.with_suffix('.puzzles.json')
  if not manifest.exists():raise ValueError('Missing puzzle manifest: '+str(manifest))
  puzzles=json.loads(manifest.read_text())['puzzles'];theme=meta.get('theme') or meta.get('detected_topic')
  lookup={}
  if any(x['type']=='scramble_trivia' for x in puzzles):
   lookup={word:(question,answer) for word,question,answer in studio.themed_trivia(theme)}
  fact_rows=[];crypto=[];words=[]
  for puzzle in puzzles:
   if puzzle['type']=='scramble_trivia':
    word=puzzle['word'];words.append(word);question,answer=lookup.get(word,('',''))
    printed=reader.pages[puzzle['puzzle_page']-1].extract_text() or ''
    fact_rows.append({'number':puzzle['number'],'word':word,'question':question,'answer':puzzle.get('fact_answer'),'source_answer':answer,'question_found_in_actual_pdf':bool(question) and norm(question) in norm(printed),'source_answer_matches_manifest':norm(answer)==norm(puzzle.get('fact_answer','')),'page':puzzle['puzzle_page'],'review_status':'PENDING_EDITORIAL_SOURCE_VERIFICATION','source':'puzzle_book_studio.themed_trivia('+str(theme)+')','external_factual_source':None})
   elif puzzle['type']=='cryptogram':crypto.append({k:puzzle.get(k) for k in ['number','plaintext','puzzle_page','solution_page']})
   elif puzzle['type']=='word_search':words.extend(puzzle.get('words',[]))
  unique=sorted(set(words));near=[{'a':a,'b':b,'reason':'substring/concept-family review; not automatic duplicate'} for i,a in enumerate(unique) for b in unique[i+1:] if len(a)>=4 and a in b or len(b)>=4 and b in a]
  results.append({'family':book['family'],'title':book['title'],'folder':str(folder),'interior_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'source_record_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'instructions_excerpt':'\n'.join(reader.pages[i].extract_text() or '' for i in range(min(3,len(reader.pages)))),'fact_clue_review':fact_rows,'cryptogram_copy_review':crypto,'near_word_review':near,'human_testing':{'status':'NOT_PERFORMED','protocol':['Read instructions without coaching and describe task.','Solve three early, three middle, three final puzzles; record completion time, hints, errors and frustration.','Find answers using page references; record lookup time and ambiguity.','Assess print contrast, grid/symbol distinction and type at actual size.','For each difficulty label record experience; do not infer empirical calibration from model votes.']},'owner_gates':['Rights/AI disclosure','Factual/editorial source review','Audience and difficulty testing','KDP Print Previewer','Physical proof']})
 output.mkdir(parents=True);(output/'editorial_packets.json').write_text(json.dumps({'schema_version':1,'source_code_sha256':hashlib.sha256((ROOT/'puzzle_book_studio.py').read_bytes()).hexdigest(),'books':results},indent=2),encoding='utf-8')
 lines=['# Owner editorial review packets','','No factual, rights, difficulty, Print Previewer, or physical-proof approval is inferred.']
 for b in results:
  lines+=['', '## '+b['title'],'',f"Fact clues: {len(b['fact_clue_review'])}; crypto prompts: {len(b['cryptogram_copy_review'])}; near-word pairs: {len(b['near_word_review'])}.",'','- [ ] Instructions and answer lookup tested','- [ ] Audience/difficulty testing recorded','- [ ] Rights and AI disclosure reviewed','- [ ] Print Previewer and physical proof inspected']
  for f in b['fact_clue_review']:lines+=['',f"Puzzle {f['number']}, p{f['page']}: {f['question']} → {f['answer']}",'External source: ______  Reviewer/date: ______  Decision: ______']
 (output/'OWNER_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 summary={'books':len(results),'fact_clues':sum(len(b['fact_clue_review']) for b in results),'questions_confirmed_in_pdf':sum(f['question_found_in_actual_pdf'] for b in results for f in b['fact_clue_review']),'answers_matched':sum(f['source_answer_matches_manifest'] for b in results for f in b['fact_clue_review']),'crypto_prompts':sum(len(b['cryptogram_copy_review']) for b in results),'book_changes':0,'factual_approvals':0}
 (output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))

if __name__=='__main__':build(sys.argv[1])
