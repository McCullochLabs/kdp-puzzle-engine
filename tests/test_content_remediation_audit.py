import copy
import json
from pathlib import Path

import pytest

from tools.audit_content_remediation import historical_category, inspect_theme, build_report, write_report


def test_normalized_duplicates_report_sources_without_mutation():
    theme = {'production_readiness': 'APPROVED', 'puzzles': [{'name': 'Cold', 'words': ['ICE CREAM', 'ICE-CREAM', 12, '', 'éclair']} ]}
    before = copy.deepcopy(theme)
    report = inspect_theme(theme)
    assert theme == before
    codes = [x['code'] for x in report['structural']]
    assert codes.count('normalized_duplicate') == 1
    assert 'non_string_target' in codes and codes.count('invalid_target') == 2
    duplicate = next(x for x in report['structural'] if x['code'] == 'normalized_duplicate')
    assert duplicate['evidence']['normalized'] == 'ICECREAM'
    assert not duplicate['automatic_repair']


def test_embedded_targets_reuse_real_placement_contract():
    result = inspect_theme({'puzzles': [{'words': ['FAN', 'FANBELT', 'FANCLUB']}]})
    assert any(x['code'] == 'placement_precondition' and 'embedded' in x['evidence']['error'] for x in result['structural'])


def test_display_normalization_is_informational_and_not_defect():
    result = inspect_theme({'puzzles': [{'words': ['ICE CREAM', 'FROZEN YOGURT', 'SORBET']}]})
    assert not result['structural']
    assert result['normalization_observations'][0]['normalized'] == 'ICECREAM'


def test_near_duplicate_sets_and_no_repeat_claim_are_review_only():
    words = ['ALPHA', 'BETA', 'GAMMA', 'DELTA', 'OMEGA', 'SIGMA']
    result = inspect_theme({'no_repeat_words': True, 'puzzles': [{'words': words}, {'words': words}]}, {'BETA'})
    assert any(x['kind'] == 'exact_puzzle_set' for x in result['duplicate_inventory'])
    assert any(x['code'] == 'no_repeat_claim_conflict' for x in result['editorial'])
    assert sum(x['code'] == 'existing_review_or_exclusion_gate' for x in result['editorial']) == 2


def test_historical_findings_never_disappear():
    assert historical_category('Puzzle 1: 1 existing review/exclusion terms') == ('editorial', 'existing_review_or_exclusion_gate')
    assert historical_category('New unknown defect') == ('review', 'other_historical_finding')


def test_report_guards_paths_and_refuses_to_overwrite(tmp_path):
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'themes': [{'file': '../outside.json', 'issues': []}]}))
    with pytest.raises(ValueError, match='within project root'):
        build_report(tmp_path, baseline)
    baseline.write_text(json.dumps({'themes': []}))
    report = build_report(tmp_path, baseline)
    output = tmp_path / 'review'
    write_report(report, output)
    with pytest.raises(FileExistsError):
        write_report(report, output)


def test_exact_set_inventory_never_silently_drops_invalid_targets():
    result = inspect_theme({'puzzles': [{'words': ['ALPHA', '']}, {'words': ['ALPHA']}]})
    assert len(result['puzzle_sets']) == 1
    assert not any(x['kind'] == 'exact_puzzle_set' for x in result['duplicate_inventory'])
