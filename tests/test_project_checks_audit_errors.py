import json
import pytest
from project_checks import audit_theme

@pytest.mark.parametrize('words,message', [
    (['ICE CREAM', 'ICE-CREAM'], 'normalize to the same'),
    (['FAN', 'FANBELT', 'FANCLUB'], 'embedded in multiple'),
    (['ALPHA', None], 'must be text'),
    (['ALPHA', ''], 'A-Z letters'),
])
def test_invalid_targets_are_findings_not_exceptions(tmp_path, words, message):
    source = tmp_path / 'invalid.json'
    source.write_text(json.dumps({'puzzles': [{'name': 'Bad targets', 'words': words}]}))
    errors, _, _ = audit_theme(source, 42)
    assert any(message in error for error in errors)

def test_audit_continues_after_invalid_puzzle(tmp_path):
    source = tmp_path / 'invalid.json'
    source.write_text(json.dumps({'puzzles': [
        {'name': 'First', 'words': ['ICE CREAM', 'ICE-CREAM']},
        {'name': 'Second', 'words': ['FAN', 'FANBELT', 'FANCLUB']},
    ]}))
    errors, _, notes = audit_theme(source, 42)
    assert any(error.startswith('First:') for error in errors)
    assert any(error.startswith('Second:') for error in errors)
    assert any('Checked 2 puzzle(s)' in note for note in notes)
