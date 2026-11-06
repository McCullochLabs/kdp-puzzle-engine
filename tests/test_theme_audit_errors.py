import json
from pathlib import Path
import word_search_creator as studio

def test_unplaceable_theme_reports_content_error_without_crashing(tmp_path,monkeypatch):
    theme=tmp_path/"invalid.json"
    theme.write_text(json.dumps({"title":"Invalid fixture","puzzles":[{"name":"One","words":["ALPINE","ALPINEBIRD","ALPINEPLANT"]}]}))
    errors,_,_=studio.audit_theme(theme,42)
    assert any("embedded in multiple" in e for e in errors)

def test_duplicate_normalized_entries_are_reported_without_crashing(tmp_path):
    theme=tmp_path/"invalid.json"
    theme.write_text(json.dumps({"title":"Invalid fixture","puzzles":[{"name":"One","words":["ICE CREAM","ICE-CREAM"]}]}))
    errors,_,_=studio.audit_theme(theme,42)
    assert any("duplicate" in e.lower() for e in errors)
