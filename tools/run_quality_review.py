"""Run each test module in isolation to avoid cumulative Windows Tk handles.

All temporary files stay in the project; no publishing or external account actions.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import time
import argparse

ROOT=Path(__file__).resolve().parents[1]


def main(output='.quality-isolated-20261022'):
    folder=(ROOT/output).resolve()
    if ROOT not in folder.parents:
        raise ValueError('Test scratch output must stay inside the project.')
    folder.mkdir(exist_ok=True)
    temporary=folder/'temp'; temporary.mkdir(exist_ok=True)
    env={**os.environ,'TEMP':str(temporary),'TMP':str(temporary)}
    reports=[]; started=time.perf_counter()
    for path in sorted((ROOT/'tests').glob('test_*.py')):
        command=[sys.executable,'-m','pytest',str(path),'-q','-p','no:cacheprovider','--tb=short',
                 '--basetemp',str(folder/('tmp-'+path.stem))]
        try:
            result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=600)
            output=result.stdout+result.stderr; code=result.returncode
        except subprocess.TimeoutExpired:
            output='Module exceeded the 600-second limit.'; code=124
        (folder/(path.stem+'.log')).write_text(output,encoding='utf-8')
        counts={kind:int(re.findall(r'(\d+) '+kind,output)[-1]) if re.findall(r'(\d+) '+kind,output) else 0
                for kind in ('passed','failed','skipped','error')}
        reports.append(dict(module=path.name,exit_code=code,counts=counts,
                            failures=[line for line in output.splitlines() if line.startswith('FAILED ')],
                            native_crash='fatal exception' in output.lower()))
        summary=dict(modules_completed=len(reports),elapsed_seconds=round(time.perf_counter()-started,2),
                     totals={key:sum(r['counts'][key] for r in reports) for key in counts},modules=reports)
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(path.name,code,counts,flush=True)
    print(json.dumps(summary['totals']),flush=True)
    if any(row['exit_code'] for row in reports):
        raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='.quality-isolated-20261022')
    main(parser.parse_args().output)
