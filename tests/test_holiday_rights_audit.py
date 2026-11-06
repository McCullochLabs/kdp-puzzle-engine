from pathlib import Path
from holiday_combo import _write_rights_ledger
from publishing.package_layout import initialize_package_layout, package_file

def test_rights_ledger_preserves_existing_approval(tmp_path):
    initialize_package_layout(tmp_path)
    approval = {"asset_id": "existing-approved", "asset_sha256": "abc", "provenance": {"provider": "existing"}}
    _write_rights_ledger(tmp_path, Path("approved.png"), approval)
    text = package_file(tmp_path, "COVER_ART_RIGHTS_LEDGER.txt").read_text(encoding="utf-8")
    assert "existing-approved" in text and "abc" in text
    assert "not newly granted" in text and "Owner review" in text

def test_build_writes_ledger_but_refresh_does_not_use_build_locals():
    import ast, inspect, holiday_combo
    tree = ast.parse(inspect.getsource(holiday_combo.build))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert any(isinstance(n.func, ast.Name) and n.func.id == "_write_rights_ledger" for n in calls)
    refresh = inspect.getsource(holiday_combo.refresh_listing)
    assert "_write_rights_ledger(output" not in refresh
