"""Opt-in diagnostics only; never retry or alter Tk initialization results."""
import json,os,sys,threading,uuid
from pathlib import Path


def write_failure(directory,error,nodeid=""):
    import tkinter as tk
    candidates=[Path(sys.base_prefix)/"tcl/tcl8.6/init.tcl",Path(sys.base_prefix)/"tcl/tk8.6/tk.tcl"]
    for name,filename in (("TCL_LIBRARY","init.tcl"),("TK_LIBRARY","tk.tcl")):
        if os.environ.get(name):candidates.append(Path(os.environ[name])/filename)
    files=[]
    for path in candidates:
        try:files.append({"path":str(path),"is_file":path.is_file(),"bytes":path.stat().st_size if path.is_file() else None})
        except OSError as exc:files.append({"path":str(path),"stat_error":type(exc).__name__})
    record={"test":nodeid,"exception_type":type(error).__name__,"error":str(error)[:2000],"tcl_version":tk.TclVersion,"tk_version":tk.TkVersion,"library_environment":{key:os.environ.get(key) for key in ("TCL_LIBRARY","TK_LIBRARY")},"library_files":files,"thread_count":threading.active_count(),"on_main_thread":threading.current_thread() is threading.main_thread()}
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/("tk_init_failure_"+uuid.uuid4().hex+".json")
    with path.open("x",encoding="utf-8") as stream:json.dump(record,stream,indent=2)
    return path


def wrap_initializer(original,directory,nodeid="",writer=write_failure):
    import tkinter as tk
    def initialize(*args,**kwargs):
        try:return original(*args,**kwargs)
        except tk.TclError as error:
            try:writer(directory,error,nodeid)
            except Exception:pass  # Evidence failure must never mask the original exception.
            raise
    return initialize
