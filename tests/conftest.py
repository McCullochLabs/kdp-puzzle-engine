"""Optional failure evidence; disabled in ordinary test runs."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--tk-failure-diagnostics",default=None,metavar="DIRECTORY",help="Capture Tk init errors without retries or result changes.")


@pytest.fixture(autouse=True)
def optional_tk_failure_capture(request,monkeypatch):
    directory=request.config.getoption("--tk-failure-diagnostics")
    if directory:
        import tkinter as tk
        from tk_failure_diagnostics import wrap_initializer
        monkeypatch.setattr(tk.Tk,"__init__",wrap_initializer(tk.Tk.__init__,directory,request.node.nodeid))
