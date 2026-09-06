"""Tiny conservative local production guard: one heavy build at a time."""
from __future__ import annotations
import json, os, tempfile, threading
from datetime import datetime, timedelta
from pathlib import Path

_LOCK = threading.RLock()

def _now(): return datetime.now().isoformat(timespec="seconds")

def _stale(active: dict) -> bool:
    """An interrupted desktop app must not permanently block the next build."""
    try:
        return datetime.fromisoformat(str(active.get("started"))) < datetime.now() - timedelta(hours=6)
    except (TypeError, ValueError):
        return True

class ProductionJobQueue:
    def __init__(self, project: Path): self.path = Path(project) / "data" / "production_job_queue.json"
    def _read(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return {"active": None, "history": []}
    def _save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True); handle, temp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".job.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream: json.dump(value, stream, indent=2); stream.write("\n")
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    def acquire(self, job_id: str, label: str) -> tuple[bool, str]:
        with _LOCK:
            state=self._read(); active=state.get("active")
            if active and _stale(active):
                active.update({"finished": _now(), "status": "interrupted", "note": "Recovered automatically after six hours with no completion record."})
                state.setdefault("history", []).insert(0, active); state["history"] = state["history"][:100]; state["active"] = None
                self._save(state); active = None
            if active and active.get("job_id") != job_id: return False, f"{active.get('label', 'Another book')} is already being built. Wait for it to finish before starting another heavy package."
            state["active"]={"job_id": job_id, "label": label, "started": _now(), "status": "running"}; self._save(state); return True, "Build started."
    def release(self, job_id: str, result: str) -> None:
        with _LOCK:
            state=self._read(); active=state.get("active")
            if active and active.get("job_id") == job_id:
                active.update({"finished": _now(), "status": result}); state.setdefault("history", []).insert(0, active); state["history"]=state["history"][:100]; state["active"]=None; self._save(state)
    def status(self) -> dict: return self._read()
