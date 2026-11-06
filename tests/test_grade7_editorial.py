import copy
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from build_grade7_combo import ROOT,SOURCE,load_source,plan_book,render_interior
from publishing.grade7_editorial import GLOSSARY,review_source,validate_review
from word_intelligence.store import WordIntelligenceStore


@pytest.fixture(scope='module')
def evidence():
    data=load_source(); store=WordIntelligenceStore.load(ROOT/'word_banks/word_intelligence')
    return data,store,review_source(data,store,SOURCE)


def test_all_words_and_prompts_have_provisional_scoped_review(evidence):
    data,store,review=evidence
    assert review['reviewed_targets']==300 and review['previous_library_gaps']==97
    assert len(review['prompts'])==25
    assert len([r for r in review['words'] if r['definition']])==97
    assert review['teacher_approval']=='pending'
    assert not any(r['teacher_approved'] for r in review['words'])
    assert not validate_review(json.loads(json.dumps(review)),data,SOURCE)
    assert store.get('RIBOSOME') is None


@pytest.mark.parametrize('change',['remove_word','remove_prompts','teacher_claim','change_definition','unknown_reference'])
def test_incomplete_or_forged_review_is_rejected(evidence,change):
    data,_store,original=evidence; review=copy.deepcopy(original)
    row=next(r for r in review['words'] if r['definition'])
    if change=='remove_word': review['words'].pop()
    elif change=='remove_prompts': review['prompts']=[]
    elif change=='teacher_claim': row['teacher_approved']=True
    elif change=='change_definition': row['definition']='A different explanation.'
    else: row['scope_references']=['not-a-reference']
    assert validate_review(review,data,SOURCE)


def test_source_or_glossary_change_invalidates_evidence(evidence,tmp_path):
    data,_store,review=evidence
    changed=tmp_path/'source.json'; changed.write_bytes(SOURCE.read_bytes()+b'\n')
    assert any('source fingerprint' in e for e in validate_review(review,data,changed))
    glossary=tmp_path/'glossary.json'; glossary.write_bytes(GLOSSARY.read_bytes()+b'\n')
    assert any('Glossary fingerprint' in e for e in validate_review(review,data,SOURCE,glossary))


def test_revised_book_preserves_puzzles_and_adds_all_glossary_entries(evidence,tmp_path):
    data,_store,review=evidence
    records,_=plan_book(data,20261022)
    unit=next(r for r in records if 'UNITRATE' in r.get('words',[]))
    assert 'UNIT RATE' in unit['display_words']
    pdf=tmp_path/'interior.pdf'; render_interior(pdf,data,records)
    reader=PdfReader(pdf)
    assert len(reader.pages)==94
    guide=' '.join((page.extract_text() or '') for page in reader.pages[84:])
    glossary=json.loads(GLOSSARY.read_text())
    assert all(glossary['display_forms'].get(word,word) in guide for word in review['glossary_targets'])
    assert 'optional stretch vocabulary' in guide
    assert len(records)==50
