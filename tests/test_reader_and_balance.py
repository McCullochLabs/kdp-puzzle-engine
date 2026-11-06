from dataclasses import replace
from pathlib import Path
import json
import random
import pytest
from publishing.studio_reader_profiles import reader_profile, reader_from_request, word_suits_reader, check_reader_topic, allocation_targets
from publishing.activity_packs import ActivityPackPlan, validate_plan, generate_activities
from publishing.studio_family_trial import save_trial, TASKS


@pytest.mark.parametrize('text,expected',[('for an eight-year-old','ages_6_8'),('for a 10 year old','ages_9_12'),('age 14','standard'),('make a pack',None)])
def test_explicit_age_is_parsed_without_inference(text,expected):
    assert reader_from_request(text)==expected


def test_younger_profile_requires_short_familiar_words_and_blocks_adult_topics():
    assert word_suits_reader('GARDEN','ages_6_8')
    assert not word_suits_reader('PHOTOSYNTHESIS','ages_6_8')
    assert not word_suits_reader('XYZZY','ages_6_8')
    with pytest.raises(ValueError,match='adult topic'): check_reader_topic('Cocktail Hour','ages_6_8')
    with pytest.raises(ValueError,match='age 6'): reader_from_request('for a 4-year-old')


@pytest.mark.parametrize('profile', ['ages_6_8','ages_9_12'])
def test_reader_changes_real_placements_and_answers(profile):
    words=tuple('GARDEN SOIL SEED ROOT LEAF STEM PLANT TREE'.split())
    plan=ActivityPackPlan('Garden practice',words,theme='Garden',formats=('Word Search',),activity_count=1,seed=42,reader_profile=profile)
    first=generate_activities(plan);assert first==generate_activities(plan)
    item=first[0];allowed=reader_profile(profile)['directions']
    assert len(item['grid'])==reader_profile(profile)['grid']
    for word,cells in zip(item['words'],item['placements']):
        assert ''.join(item['grid'][r][c] for r,c in cells)==word
        assert (cells[1][0]-cells[0][0],cells[1][1]-cells[0][1]) in allowed


def test_reader_validation_cannot_be_bypassed_by_manual_vocabulary():
    with pytest.raises(ValueError,match='reader profile'):
        validate_plan(ActivityPackPlan('Practice',('PHOTOSYNTHESIS',)*8,formats=('Word Search',),activity_count=1,reader_profile='ages_6_8'))


def test_theme_emphasis_assigns_a_larger_share_without_extra_ai():
    names=['homesteading','home_household','gardening']
    targets=allocation_targets(names,30,'More household')
    assert targets['home_household']==18 and targets['gardening']==6
    assert allocation_targets(names,30,'Balanced')==dict.fromkeys(names,10)


def test_family_practice_preserves_each_actual_observation(tmp_path):
    observations=[{'result':'Not tried','note':''} for _ in TASKS]
    a=save_trial(tmp_path,observations);b=save_trial(tmp_path,observations)
    assert a!=b and a.is_file() and b.is_file()
    data=json.loads(a.read_text());assert data['inference_calls']==0
    assert all(row['result']=='Not tried' for row in data['observations'])


def test_reviewed_memberships_never_override_rejection_or_invent_dictionary_words(tmp_path):
    from word_intelligence.family_content_reviews import apply_store_reviews
    from word_intelligence.store import WordIntelligenceStore
    from word_intelligence.records import WordRecord, TopicLink, REJECTED
    class Taxonomy:
        def resolve(self,name): return 'cats'
    folder=tmp_path/'word_banks';folder.mkdir()
    (folder/'family_group_content_reviews.json').write_text(json.dumps({'schema_version':1,'review_type':'owner_requested_editorial_membership','reviews':{'Cats & Pets':{'words':['CAT','KITTEN','XYZZY']}}}))
    store=WordIntelligenceStore();store.dictionary_words={'CAT','KITTEN'}
    record=WordRecord('CAT','CAT');record.topics=[TopicLink('cats',REJECTED,0)]
    store.records['CAT']=record
    apply_store_reviews(store,Taxonomy(),tmp_path)
    assert record.link_for('cats').status==REJECTED
    assert 'XYZZY' not in store.records
    assert store.records['KITTEN'].link_for('cats').status=='trusted'
