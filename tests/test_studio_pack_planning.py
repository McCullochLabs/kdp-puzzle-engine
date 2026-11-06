from pathlib import Path
import hashlib

import pytest

from publishing.studio_pack_planning import available_pack_themes, prepare_pack_request, validate_pack_request

ROOT = Path(__file__).resolve().parents[1]


def choices(**changes):
    return dict(title='Family test', theme='Homesteading', reader_profile='standard',
                activity_count=6, formats=['Word Search', 'Word Scramble', 'Sudoku'],
                theme_balance='Balanced', **changes) if not changes else choices() | changes


def test_exposes_all_bank_groups():
    import json
    bank = json.loads((ROOT/'word_banks/Guided_Builder_Master_Word_Bank.json').read_text(encoding='utf-8-sig'))
    assert set(available_pack_themes(ROOT)) == set(bank['topics']) | set(bank['topic_packs'])


@pytest.mark.parametrize('change', [
    {'activity_count': True}, {'activity_count': 25}, {'activity_count': 1},
    {'formats': []}, {'formats': ['Word Search', 'Word Search']}, {'formats': [{}]},
    {'theme': '../../data/books.db'}, {'reader_profile': []}, {'theme_balance': []},
    {'title': 'bad\nname'}, {'words': ['UNREVIEWED']},
])
def test_rejects_invalid_or_unreviewed_input(change):
    with pytest.raises(ValueError): validate_pack_request(choices(**change), ROOT)


def test_adult_group_rejected_even_for_number_activities():
    with pytest.raises(ValueError, match='adult topic'):
        prepare_pack_request(choices(theme='Cocktail Hour, Nightlife & Social Club',
            reader_profile='ages_6_8', formats=['Sudoku']), ROOT)


def test_number_only_does_not_load_word_sorter(monkeypatch):
    import word_intelligence.pipeline
    monkeypatch.setattr(word_intelligence.pipeline, 'prepare_family_wordsearch', lambda *a, **k: pytest.fail('No word selection needed'))
    result = prepare_pack_request(choices(formats=['Sudoku']), ROOT)
    assert result['word_count'] == 0 and result['generated'] is False


def test_short_selection_never_claims_ready(monkeypatch):
    import word_intelligence.pipeline
    monkeypatch.setattr(word_intelligence.pipeline, 'prepare_family_wordsearch', lambda *a, **k: {'words':['MOON']})
    with pytest.raises(ValueError, match='fewer pages'):
        prepare_pack_request(choices(), ROOT)


def test_actual_child_and_composite_plans_preserve_bank_files():
    from publishing.studio_reader_profiles import word_suits_reader
    paths = [ROOT/'word_banks'/name for name in ('Guided_Builder_Master_Word_Bank.json',
        'word_intelligence/word_store.json', 'editorial_wordsearch_topic_overlay.json', 'family_group_content_reviews.json')]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    child = prepare_pack_request(choices(theme='Space & Astronomy', reader_profile='ages_6_8'), ROOT)
    assert child['word_count'] == 16
    assert all(word_suits_reader(word,'ages_6_8') for word in child['plan']['words'])
    home = prepare_pack_request(choices(), ROOT)
    assert home['word_count'] == len(set(home['plan']['words'])) == 16
    assert len(home['group_counts']) == 2
    assert home['inference_calls'] == child['inference_calls'] == 0
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
