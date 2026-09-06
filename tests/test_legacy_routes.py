from pathlib import Path

from publishing.legacy_routes import RECOVERY_ONLY_SCRIPTS, recovery_script_inventory, unsupported_ui_routes

PROJECT = Path(__file__).resolve().parents[1]


def test_recovery_only_scripts_are_not_reachable_from_active_ui():
    assert unsupported_ui_routes(PROJECT) == []


def test_recovery_inventory_is_explicit_and_non_destructive():
    rows = recovery_script_inventory(PROJECT)
    assert {row["name"] for row in rows} == set(RECOVERY_ONLY_SCRIPTS)
    assert all(row["classification"] == "recovery_only" for row in rows)
