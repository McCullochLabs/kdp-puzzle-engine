"""Read-only theme remediation queues; never edits themes or approval decisions.

Uses the existing word-search normalization and placement preconditions. Exact
set duplicates are objective; plural and high-overlap pairs are review hints,
not claims of equivalent meaning, incorrect spelling, or automatic repair.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import wordsearch


def historical_category(message: str) -> tuple[str, str]:
    """Classify every historical finding without silently dropping unknown ones."""
    low = message.casefold()
    if 'review/exclusion' in low:
        return 'editorial', 'existing_review_or_exclusion_gate'
    if 'embedded in multiple' in low:
        return 'structural', 'embedded_target_conflict'
    if 'unique uppercase' in low:
        return 'structural', 'target_format_duplicate_or_fit'
    if 'duplicate' in low or 'appears more than once' in low:
        return 'structural', 'duplicate_target'
    if 'no words' in low or 'no puzzles' in low or 'expected format' in low:
        return 'structural', 'missing_or_invalid_container'
    if 'word' in low and ('blank' in low or 'longer' in low or 'a-z' in low):
        return 'structural', 'invalid_target'
    return 'review', 'other_historical_finding'


def _flag(code, puzzle=None, **evidence):
    return {'code': code, 'puzzle': puzzle, 'evidence': evidence,
            'status': 'REVIEW_REQUIRED', 'automatic_repair': False}


def inspect_theme(data, review_terms=frozenset()):
    """Audit parsed theme data without generating grids or mutating data."""
    structural, editorial, duplicates, normalization = [], [], [], []
    puzzle_sets = []
    if not isinstance(data, dict):
        return {'structural': [_flag('invalid_theme_container')], 'editorial': [],
                'duplicate_inventory': [], 'normalization_observations': [], 'puzzle_sets': []}
    puzzles = data.get('puzzles')
    if not isinstance(puzzles, list) or not puzzles:
        return {'structural': [_flag('missing_or_invalid_puzzles')], 'editorial': [],
                'duplicate_inventory': [], 'normalization_observations': [], 'puzzle_sets': []}
    all_locations = defaultdict(list)
    names = defaultdict(list)
    for number, puzzle in enumerate(puzzles, 1):
        if not isinstance(puzzle, dict):
            structural.append(_flag('invalid_puzzle_container', number)); continue
        names[str(puzzle.get('name', '')).strip().casefold()].append(number)
        source = puzzle.get('words')
        if not isinstance(source, list) or not source:
            structural.append(_flag('missing_or_invalid_words', number)); continue
        if not 12 <= len(source) <= 25:
            editorial.append(_flag('production_word_count', number, actual=len(source), minimum=12, maximum=25))
        clean, by_key = [], defaultdict(list)
        for index, raw in enumerate(source, 1):
            if not isinstance(raw, str):
                structural.append(_flag('non_string_target', number, position=index, value=raw)); continue
            try:
                key = wordsearch.clean_words([raw])[0]
            except ValueError as exc:
                structural.append(_flag('invalid_target', number, position=index, raw=raw, error=str(exc))); continue
            clean.append(key);by_key[key].append({'position': index, 'raw': raw})
            all_locations[key].append(number)
            if key != raw:
                normalization.append({'puzzle': number, 'position': index, 'raw': raw, 'normalized': key,
                                      'note': 'Existing engine normalization; source spelling preserved.'})
        for key, entries in sorted(by_key.items()):
            if len(entries) > 1:
                structural.append(_flag('normalized_duplicate', number, normalized=key, entries=entries))
                duplicates.append({'kind': 'within_puzzle_normalized_duplicate', 'puzzle': number,
                                   'normalized': key, 'entries': entries})
        valid = len(clean) == len(source) and len(clean) == len(set(clean))
        if valid:
            try:
                wordsearch.validate_word_set(clean, wordsearch.grid_size_for(clean))
            except ValueError as exc:
                structural.append(_flag('placement_precondition', number, error=str(exc), targets=clean))
        for word in sorted(set(clean) & set(review_terms)):
            editorial.append(_flag('existing_review_or_exclusion_gate', number, normalized=word))
        if valid:
            puzzle_sets.append({'number': number, 'words': sorted(set(clean))})
            # A deliberately narrow review signal, never semantic deduplication.
            for word in sorted(set(clean)):
                if word.endswith('S') and len(word) > 3 and word[:-1] in clean:
                    editorial.append(_flag('possible_singular_plural_pair', number, words=[word[:-1], word]))
    for name, locations in sorted(names.items()):
        if len(locations) > 1:
            editorial.append(_flag('repeated_puzzle_name', locations=locations, name=name))
    for word, locations in sorted(all_locations.items()):
        distinct = sorted(set(locations))
        if len(distinct) > 1:
            duplicates.append({'kind': 'across_puzzle_reused_target', 'normalized': word, 'puzzles': distinct})
            if data.get('no_repeat_words') is True:
                editorial.append(_flag('no_repeat_claim_conflict', normalized=word, puzzles=distinct))
    for first, second in itertools.combinations(puzzle_sets, 2):
        a, b = set(first['words']), set(second['words'])
        similarity = len(a & b) / len(a | b)
        if similarity >= .8:
            duplicates.append({'kind': 'exact_puzzle_set' if a == b else 'near_puzzle_set',
                               'puzzles': [first['number'], second['number']],
                               'jaccard': round(similarity, 4), 'shared_words': sorted(a & b),
                               'review_only': True})
    return {'structural': structural, 'editorial': editorial, 'duplicate_inventory': duplicates,
            'normalization_observations': normalization, 'puzzle_sets': puzzle_sets}


def build_report(root: Path, baseline: Path):
    baseline_data = json.loads(baseline.read_text(encoding='utf-8-sig'))
    from word_search_creator import REVIEW_REQUIRED_TERMS
    historical, themes, cross_sets, inputs = [], [], defaultdict(list), {}
    for entry in baseline_data['themes']:
        relative = Path(entry['file'].replace('\\', '/'))
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or relative.is_absolute():
            raise ValueError('Theme reference must stay within project root.')
        for message in entry.get('issues', []):
            queue, category = historical_category(message)
            historical.append({'file': relative.as_posix(), 'queue': queue, 'category': category, 'message': message})
        try:
            content = path.read_bytes();inputs[relative.as_posix()] = hashlib.sha256(content).hexdigest()
            data = json.loads(content.decode('utf-8-sig'))
            result = inspect_theme(data, REVIEW_REQUIRED_TERMS)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            result = {'structural': [_flag('unreadable_json', error=str(exc))], 'editorial': [],
                      'duplicate_inventory': [], 'normalization_observations': [], 'puzzle_sets': []}
        for puzzle in result.pop('puzzle_sets'):
            cross_sets[tuple(puzzle['words'])].append({'file': relative.as_posix(), 'puzzle': puzzle['number']})
        themes.append({'file': relative.as_posix(), **result})
    exact_sets = [{'words': list(words), 'locations': locations} for words, locations in cross_sets.items()
                  if len({x['file'] for x in locations}) > 1]
    summary = {
        'theme_files': len(themes),
        'historical_themes_with_issues': sum(bool(t.get('issues')) for t in baseline_data['themes']),
        'historical_findings': len(historical),
        'historical_root_causes': dict(Counter(x['category'] for x in historical)),
        'current_themes_with_structural_findings': sum(bool(t['structural']) for t in themes),
        'current_structural_findings': sum(len(t['structural']) for t in themes),
        'current_themes_with_editorial_findings': sum(bool(t['editorial']) for t in themes),
        'current_editorial_findings': sum(len(t['editorial']) for t in themes),
        'current_structural_codes': dict(Counter(x['code'] for t in themes for x in t['structural'])),
        'current_editorial_codes': dict(Counter(x['code'] for t in themes for x in t['editorial'])),
        'cross_theme_exact_puzzle_sets': len(exact_sets),
        'source_files_changed': 0,
        'approval_changes': 0,
        'automatic_repairs': 0,
        'status': 'REVIEW_REQUIRED',
    }
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'summary': summary, 'historical_classification': historical, 'themes': themes,
            'cross_theme_exact_sets': exact_sets, 'input_sha256': inputs,
            'baseline_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
            'limitations': ['No full grid generation, spelling certification, semantic relevance or approval is inferred.',
                           'Structural detection does not authorize deleting/replacing reviewed targets or lowering word counts.',
                           'Near-duplicate puzzle inventory uses within-theme Jaccard >= 0.8; plural pairs are review hints.',
                           'Cross-theme exact sets may be intentional revisions or archives, not automatic originality failures.',
                           'Existing engine normalization observations are informational, not source defects.']}


def write_report(report, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    def dump(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    dump('summary.json', {k: report[k] for k in ['summary', 'limitations', 'input_sha256', 'baseline_sha256']})
    dump('historical_classification.json', report['historical_classification'])
    dump('structural_review_queue.json', [{'file': t['file'], **x} for t in report['themes'] for x in t['structural']])
    dump('editorial_review_queue.json', [{'file': t['file'], **x} for t in report['themes'] for x in t['editorial']])
    dump('duplicate_inventory.json', {'within_theme': [{'file': t['file'], **x} for t in report['themes'] for x in t['duplicate_inventory']],
                                    'cross_theme_exact_sets': report['cross_theme_exact_sets']})
    dump('normalization_observations.json', [{'file': t['file'], **x} for t in report['themes'] for x in t['normalization_observations']])
    (output / 'README.md').write_text('# Content remediation checkpoint\n\nRead-only deterministic audit. No themes, words, approvals, or books were modified.\n\n'
        + json.dumps(report['summary'], indent=2) + '\n\nThe queues contain objectively detectable defects and separate editorial choices. '
        'Replacement vocabulary, removal of duplicates, and conflict repartition need source-specific review; none are automatically applied. '
        'The complete input hashes permit verification that review sources remain unchanged.\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--baseline', type=Path, default=ROOT / 'audits/system_20261101/content_integrity_report.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.root, args.baseline)
    write_report(report, args.output)
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
