"""Controlled child-process interruption; never terminates unrelated processes."""
from pathlib import Path
import json,subprocess,sys,time
from publishing.phone_pack_service import PackService
ROOT=Path(__file__).resolve().parents[1]


def test_actual_process_termination_preserves_project_and_marks_job_interrupted(tmp_path):
    child='''from pathlib import Path
import sys,json,time
from publishing.phone_pack_service import PackService
root,work=map(Path,sys.argv[1:]);service=PackService(root,work/'catalog.db',work/'packs',start_worker=False)
request={'title':'Recovery Fixture','theme':'Space & Astronomy','reader_profile':'ages_6_8','activity_count':3,'formats':['Word Search','Word Scramble','Sudoku'],'theme_balance':'Balanced'}
project=service.save(request);job=service.enqueue(project['id'],1);service.update(job,status='running',stage='Controlled test interruption')
(work/'ready.json').write_text(json.dumps({'project':project['id'],'job':job}))
time.sleep(120)
'''
    process=subprocess.Popen([sys.executable,'-c',child,str(ROOT),str(tmp_path)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+15
        while not (tmp_path/'ready.json').exists() and time.monotonic()<deadline and process.poll() is None:time.sleep(.05)
        assert (tmp_path/'ready.json').exists(), process.communicate(timeout=1) if process.poll() is not None else 'Child did not checkpoint'
        ids=json.loads((tmp_path/'ready.json').read_text());process.terminate();process.wait(timeout=10)
        recovered=PackService(ROOT,tmp_path/'catalog.db',tmp_path/'packs',start_worker=False)
        try:
            project=recovered.project(ids['project']);job=recovered.job(ids['job'])
            assert project['revision']==1 and project['request']['title']=='Recovery Fixture'
            assert job['status']=='interrupted'
            assert recovered.enqueue(ids['project'],1)!=ids['job']
            assert recovered.job(ids['job'])['status']=='interrupted'
        finally:recovered.close()
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=10)
        if process.stdout:process.stdout.close()
        if process.stderr:process.stderr.close()
