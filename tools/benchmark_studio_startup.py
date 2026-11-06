"""Reproducible fresh-process Guide startup baseline, without network/model calls."""
from pathlib import Path
import argparse,json,subprocess,sys,time,statistics,ctypes
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def peak_working_set():
    if sys.platform!='win32':return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.GetCurrentProcess.restype=wintypes.HANDLE
    query=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];query.restype=wintypes.BOOL
    ok=query(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb)
    return round(counters.PeakWorkingSetSize/1048576,2) if ok else None

def child(duration=2):
    start=time.perf_counter()
    import word_search_creator as studio
    import_seconds=time.perf_counter()-start
    studio.load_app_preferences=lambda:{'assistant_provider':'Guide','local_ai_enabled':False}
    studio.save_app_preferences=lambda *args,**kwargs:None
    app=studio.WordSearchCreator();app.withdraw();app.update()
    ready=time.perf_counter()-start
    callback_errors=[];app.report_callback_exception=lambda *args:callback_errors.append(str(args[1]))
    latencies=[]
    for method in ['show_create','show_home','show_settings','show_home']:
        tick=time.perf_counter();getattr(app.family_studio,method)();app.update();latencies.append({'action':method,'elapsed_ms':round((time.perf_counter()-tick)*1000,2)})
    samples=[]
    until=time.perf_counter()+duration
    while time.perf_counter()<until:
        tick=time.perf_counter();app.update();samples.append((time.perf_counter()-tick)*1000);time.sleep(.02)
    peak=peak_working_set();app.destroy()
    print(json.dumps({'import_seconds':round(import_seconds,3),'first_update_seconds':round(ready,3),'peak_process_working_set_mb':peak,'navigation':latencies,'sample_duration_seconds':duration,'idle_update_max_ms':round(max(samples),2),'callback_errors':callback_errors}))

def run(output,trials,duration=2):
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a fresh checkpoint file.')
    rows=[]
    for _ in range(trials):
        start=time.perf_counter();p=subprocess.run([sys.executable,__file__,'--child','--duration',str(duration)],cwd=ROOT,capture_output=True,text=True,timeout=max(90,duration+30))
        if p.returncode:raise RuntimeError(p.stderr[-1500:])
        row=json.loads(p.stdout.strip().splitlines()[-1]);row['process_elapsed_seconds']=round(time.perf_counter()-start,3);rows.append(row)
    data={'mode':'Fresh-process actual Tk/FamilyStudio startup, deterministic Guide, window withdrawn after construction','trials':rows,'median_first_update_seconds':statistics.median(r['first_update_seconds'] for r in rows),'maximum_observed_process_working_set_mb':max(r['peak_process_working_set_mb'] or 0 for r in rows),'limitations':['Fresh process does not flush Windows filesystem cache.','Model loading is excluded; no network or model call requested.','A bounded idle sample and four navigation actions do not establish leak freedom or responsiveness under generation load.','Guide preferences were scoped to the benchmark process; user settings not rewritten.','Peak working set excludes unrelated processes and local-model RAM.']}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--trials',type=int,default=3);p.add_argument('--duration',type=int,default=2);a=p.parse_args()
    if a.child:child(a.duration)
    elif a.output:run(a.output,a.trials,a.duration)
    else:p.error('--output required')
