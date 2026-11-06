from dataclasses import replace
import hashlib
import json
import random
import zipfile

from pypdf import PdfReader
import pytest

from publishing import activity_packs as packs
from publishing.activity_packs import ActivityPackPlan, PRESETS, build_activity_pack, generate_activities, parse_words, validate_plan
import sudoku
import wordsearch


def plan(**changes):
    return replace(ActivityPackPlan(title="Road Trip Fun", words=tuple(PRESETS["Road Trip"].split()), theme="Road Trip", seed=42), **changes)


def test_generation_is_reproducible_without_changing_global_random_state():
    state = random.getstate()
    first = generate_activities(plan())
    assert random.getstate() == state
    assert first == generate_activities(plan())
    assert first != generate_activities(plan(seed=43))
    for item in first:
        if item['kind'] == 'Word Search':
            for word, cells in zip(item['words'], item['placements']):
                assert ''.join(item['grid'][r][c] for r, c in cells) == word
        elif item['kind'] == 'Word Scramble':
            for word, shown in zip(item['words'], item['scrambled']):
                assert word != shown and sorted(word) == sorted(shown)
        else:
            assert sudoku.count_solutions([row[:] for row in item['grid']]) == 1
            assert all(value == 0 or value == item['solution'][r][c] for r, row in enumerate(item['grid']) for c, value in enumerate(row))
    for kind in ('Word Search', 'Word Scramble'):
        words = [word for item in first if item['kind'] == kind for word in item['words']]
        assert len(words) == len(set(words))


def test_custom_vocabulary_is_normalized_without_dropping_entries():
    words = parse_words('Jordan, birthday cake; road-trip\nfamily')
    assert words == ('Jordan', 'birthday cake', 'road-trip', 'family')
    result = validate_plan(plan(words=words + ('friends', 'party', 'music', 'smiles'), activity_count=1, formats=('Word Search',)))
    assert result.words[:3] == ('JORDAN', 'BIRTHDAYCAKE', 'ROADTRIP')


@pytest.mark.parametrize('changes, message', [
    ({'title': ''}, 'title'), ({'title': 'a'*101}, 'Title'),
    ({'formats': ()}, 'activity types'), ({'formats': ('Maze',)}, 'activity types'),
    ({'activity_count': 2}, 'at least one'), ({'activity_count': 25}, '1 to 24'),
    ({'activity_count': True}, '1 to 24'), ({'seed': -1}, 'seed'),
    ({'difficulty': 'extreme'}, 'difficulty'),
    ({'words': ('CAT',)}, 'at least 16'),
    ({'words': ('HELLO1',)*20}, 'English letters'),
    ({'words': ('LEGO',)*20}, 'content review'),
    ({'words': ('Harry Potter',)*20}, 'content review'),
    ({'words': ('cat', 'CAT')}, 'duplicates'),
    ({'words': ('AAAA',)*20}, 'meaningful word scramble'),
])
def test_invalid_plan_is_rejected(changes, message):
    with pytest.raises(ValueError, match=message):
        validate_plan(plan(**changes))


def test_sudoku_only_needs_no_vocabulary():
    result = generate_activities(plan(words=(), activity_count=1, formats=('Sudoku',)))
    assert len(result) == 1 and result[0]['kind'] == 'Sudoku'


def test_partial_word_placement_aborts_without_output(tmp_path, monkeypatch):
    monkeypatch.setattr(wordsearch, 'generate_puzzle', lambda *args, **kwargs: ([['A']], [], []))
    with pytest.raises(ValueError, match='every word'):
        build_activity_pack(plan(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_render_failure_cleans_up_and_preserves_existing_files(tmp_path, monkeypatch):
    existing = tmp_path / 'existing.txt'
    existing.write_text('keep')
    def fail(folder, *args):
        (folder / 'partial.pdf').write_text('partial')
        raise RuntimeError('render failed')
    monkeypatch.setattr(packs, 'render_pdfs', fail)
    with pytest.raises(RuntimeError, match='render failed'):
        build_activity_pack(plan(), tmp_path)
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_text() == 'keep'


def test_complete_pack_has_separate_answers_verified_manifest_and_customer_zip(tmp_path):
    folder = build_activity_pack(plan(recipient='Made for Jordan'), tmp_path)
    activities = PdfReader(folder / 'ACTIVITIES.pdf')
    answers = PdfReader(folder / 'ANSWERS.pdf')
    assert len(activities.pages) == len(answers.pages) == 7
    for reader in (activities, answers):
        assert all(tuple(float(v) for v in page.mediabox) == (0, 0, 612, 792) for page in reader.pages)
        assert all((page.extract_text() or '').strip() for page in reader.pages)
        assert 'Made for Jordan' in reader.pages[0].extract_text()
    assert 'ANSWER SHEETS' not in activities.pages[0].extract_text()
    assert 'ANSWER SHEETS' in answers.pages[0].extract_text()
    manifest = json.loads((folder / 'PACK_MANIFEST.json').read_text())
    assert manifest['proof']['human_review'] == 'required'
    assert manifest['plan']['seed'] == 42
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(folder / 'PRINTABLE_PACK.zip') as archive:
        assert set(archive.namelist()) == {'ACTIVITIES.pdf', 'ANSWERS.pdf', 'READ_ME.txt'}
        assert archive.testzip() is None
    original = (folder / 'ACTIVITIES.pdf').read_bytes()
    second = build_activity_pack(plan(recipient='Made for Jordan'), tmp_path)
    assert second != folder
    assert (folder / 'ACTIVITIES.pdf').read_bytes() == original
    assert (second / 'ACTIVITIES.pdf').read_bytes() == original
