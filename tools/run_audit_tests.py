"""Sequential isolated pytest modules with a durable checkpoint and actual totals."""
from pathlib import Path
import argparse,json,subprocess,sys,time,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

def run(output):
 output=Path(output)
 if output.exists():raise FileExistsError('Use a new acceptance-run directory.')
 output.mkdir(parents=True);rows=[];start=time.perf_counter()
 for module in sorted((ROOT/'tests').glob('test_*.py')):
  xml=output/(module.stem+'.xml');log=output/(module.stem+'.log');tick=time.perf_counter();timeout=False
  try:p=subprocess.run([sys.executable,'-m','pytest',str(module),'-q','--junitxml='+str(xml.resolve())],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300);code=p.returncode;text=p.stdout+'\n'+p.stderr
  except subprocess.TimeoutExpired as exc:code=124;timeout=True;text=str(exc)
  log.write_text(text,encoding='utf-8');counts={'passed':0,'failed':0,'skipped':0,'error':0}
  if xml.exists():
   tree=ET.parse(xml)
   for case in tree.iter('testcase'):
    key='failed' if case.find('failure') is not None else 'error' if case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed';counts[key]+=1
   if code and not counts['failed'] and not counts['error']:counts['error']+=1
  elif code:counts['error']=1
  rows.append({'module':module.name,'exit_code':code,'counts':counts,'timeout':timeout,'elapsed_seconds':round(time.perf_counter()-tick,2)})
  totals={k:sum(r['counts'][k] for r in rows) for k in counts}
  summary={'modules_completed':len(rows),'modules_expected':len(list((ROOT/'tests').glob('test_*.py'))),'elapsed_seconds':round(time.perf_counter()-start,2),'totals':totals,'modules':rows}
  (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(module.name,counts,flush=True)
 print('TOTALS',json.dumps(totals),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output)
