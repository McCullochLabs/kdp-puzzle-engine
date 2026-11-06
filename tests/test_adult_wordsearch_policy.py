"""Adult intent is explicit and path-scoped; it never approves source content."""
import copy
import random
import pytest
from publishing.puzzle_integrity import DENYLIST, verify_wordsearch
from wordsearch import generate_puzzle


def fixture(word):
    n=max(12,len(word))
    grid=[list('X'*n) for _ in range(n)]
    grid[0][:len(word)]=list(word)
    return grid,[[(0,c) for c in range(len(word))]],[word]


@pytest.mark.parametrize('word',['SHIT','BULLSHIT','MOTHERFUCKER'])
def test_only_explicit_adult_policy_accepts_intended_profanity(word):
    grid,paths,words=fixture(word)
    assert any('denylist' in e for e in verify_wordsearch(grid,paths,words,words))
    assert not verify_wordsearch(grid,paths,words,words,content_policy='adult_intended_profanity')


def test_adult_policy_still_rejects_filler_profanity():
    grid,paths,words=fixture('BULLSHIT')
    grid[3][:4]=list('FUCK')
    assert any('denylist' in e for e in verify_wordsearch(grid,paths,words,words,content_policy='adult_intended_profanity'))


@pytest.mark.parametrize('word',DENYLIST[-2:])
def test_hateful_slurs_cannot_be_whitelisted_as_intended_targets(word):
    grid,paths,words=fixture(word)
    assert any('denylist' in e for e in verify_wordsearch(grid,paths,words,words,content_policy='adult_intended_profanity'))


def test_unknown_policy_and_missing_intent_fail_closed():
    grid,paths,words=fixture('SHIT')
    assert verify_wordsearch(grid,paths,words,words,content_policy='allow_everything')
    assert verify_wordsearch(grid,paths,words,content_policy='adult_intended_profanity')
    with pytest.raises(ValueError,match='Unsupported'):
        generate_puzzle(['CAT'],content_policy='allow_everything')


def test_real_generator_retains_independent_path_and_occurrence_checks():
    expected=['BULLSHIT','DAMN','COCKTAIL']
    grid,paths,words=generate_puzzle(expected,rng=random.Random(20261102),content_policy='adult_intended_profanity')
    assert set(words)==set(expected)
    assert not verify_wordsearch(grid,paths,words,expected,content_policy='adult_intended_profanity')
    corrupted=copy.deepcopy(grid)
    r,c=paths[0][0];corrupted[r][c]='Z'
    assert verify_wordsearch(corrupted,paths,words,expected,content_policy='adult_intended_profanity')


def test_manifest_verification_preserves_explicit_policy_and_default_rejection(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    from publishing.puzzle_integrity import write_manifest,verify_manifest
    import json
    pdf=tmp_path/'fixture.pdf'; canvas=Canvas(str(pdf))
    canvas.drawString(54,700,'Test fixture');canvas.showPage()
    canvas.drawString(54,700,'Answer fixture');canvas.showPage();canvas.save()
    grid,paths,words=fixture('BULLSHIT')
    row=dict(number=1,type='word_search',grid=grid,placements=paths,words=words,intended_words=words,solution_grid=grid,solution_placements=paths,puzzle_page=1,solution_page=2,content_policy='adult_intended_profanity')
    manifest=json.loads(write_manifest(pdf,[row]).read_text())
    assert verify_manifest(pdf,manifest,2)==[]
    del manifest['puzzles'][0]['content_policy']
    assert any('denylist' in e for e in verify_manifest(pdf,manifest,2))
