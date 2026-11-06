import json
import tkinter as tk
import pytest
from tk_failure_diagnostics import wrap_initializer


def test_failure_is_recorded_once_and_same_exception_rethrown(tmp_path,monkeypatch):
    monkeypatch.setenv("UNRELATED_SECRET_SENTINEL","must-not-be-recorded")
    calls=[];error=tk.TclError("Cannot find usable init.tcl")
    def original(*args,**kwargs):calls.append((args,kwargs));raise error
    with pytest.raises(tk.TclError) as caught:wrap_initializer(original,tmp_path,"fixture-test")("self",flag=True)
    assert caught.value is error and len(calls)==1
    files=list(tmp_path.glob("*.json"));assert len(files)==1
    text=files[0].read_text(encoding="utf-8");record=json.loads(text)
    assert record["error"]==str(error) and set(record["library_environment"])=={"TCL_LIBRARY","TK_LIBRARY"}
    assert "must-not-be-recorded" not in text and "UNRELATED_SECRET_SENTINEL" not in text


def test_diagnostic_write_failure_does_not_mask_initializer_error(tmp_path):
    error=tk.TclError("original failure")
    def original():raise error
    def writer(*args):raise OSError("evidence unavailable")
    with pytest.raises(tk.TclError) as caught:wrap_initializer(original,tmp_path,writer=writer)()
    assert caught.value is error


def test_success_and_non_tcl_errors_are_unchanged(tmp_path):
    assert wrap_initializer(lambda value:value,tmp_path)(17)==17
    error=RuntimeError("other error")
    def original():raise error
    with pytest.raises(RuntimeError) as caught:wrap_initializer(original,tmp_path)()
    assert caught.value is error and not list(tmp_path.iterdir())


def test_opt_in_fixture_preserves_forced_tk_init_error(request,monkeypatch):
    from pathlib import Path
    directory=request.config.getoption("--tk-failure-diagnostics")
    before=set(Path(directory).glob("*.json")) if directory else set()
    error=tk.TclError("Synthetic initialization failure for instrumentation acceptance")
    def fail(*a,**k):raise error
    monkeypatch.setattr(tk._tkinter,"create",fail)
    with pytest.raises(tk.TclError) as caught:tk.Tk()
    assert caught.value is error
    if directory:
        added=set(Path(directory).glob("*.json"))-before
        assert len(added)==1
        record=json.loads(added.pop().read_text(encoding="utf-8"))
        assert record["error"]==str(error) and record["test"]==request.node.nodeid
