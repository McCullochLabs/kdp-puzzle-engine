import hashlib
import json
from pathlib import Path

import pytest

from tools.extend_word_review import nearest_anchors, prior_candidate_words, run
from word_intelligence.content_contracts import content_record_from_dict


def test_nearest_anchor_keeps_equal_distance_ambiguity_and_terminates_cycles():
    a={'name':'Garden Tools','parent_topic_id':'gardening'}
    b={'name':'Workshop Tools','parent_topic_id':'tools_workshop'}
    senses={'start':{'parents':['left','right']}, 'left':{'parents':['start']}, 'right':{'parents':['left']}}
    assert nearest_anchors('start',senses,{'left':[a],'right':[b]})==[a,b]
    assert nearest_anchors('start',senses,{})==[]


def test_nearest_anchor_does_not_merge_farther_niches():
    a={'name':'Near','parent_topic_id':'gardening'}
    b={'name':'Far','parent_topic_id':'tools_workshop'}
    senses={'start':{'parents':['left','detour']},'detour':{'parents':['far']}}
    assert nearest_anchors('start',senses,{'left':[a],'far':[b]})==[a]


def test_prior_candidates_exclude_current_versions_and_current_record_ids(tmp_path):
    base=tmp_path/'word_banks/research_briefs'
    old=base/'previous_campaign';old.mkdir(parents=True)
    (old/'canonical_candidates.json').write_text(json.dumps({'records':[{'normalized':'OLD'},{'normalized':'CURRENT','campaign_id':'phase2_20261101'}]}))
    current=base/'phase2_definition_niches_20261101_v1';current.mkdir()
    (current/'canonical_candidates.json').write_text(json.dumps({'records':[{'normalized':'ABACUS'}]}))
    words,paths,skipped=prior_candidate_words(tmp_path)
    assert words=={'OLD'}
    assert paths==[old/'canonical_candidates.json']
    assert skipped==[current/'canonical_candidates.json']


def _fixture(root):
    bank=root/'word_banks'; briefs=bank/'research_briefs';old=briefs/'definition_backed_word_organization_2026_10_09'
    old.mkdir(parents=True)
    (old/'semantic_roots.txt').write_text('Calculating Tools|Math|abacus|0\n')
    (old/'semantic_word_groups.json').write_text(json.dumps({'groups':[{'name':'Calculating Tools','kind':'focused_niche','parent_topic_id':'math_logic'}]}))
    state=bank/'word_intelligence';state.mkdir()
    (state/'word_store.json').write_text(json.dumps({'records':[
        {'normalized':'ABACUS','frequency':2.65,'topics':[]},
        {'normalized':'ABALONE','frequency':2.65,'topics':[{'topic_id':'ocean','status':'approved'}]},
    ]}))
    (bank/'Guided_Builder_Master_Word_Bank.json').write_text('{"preserve":"master"}')
    data=root/'data';data.mkdir();(data/'content_approval_decisions.json').write_text('{"preserve":"owner approvals"}')
    reference=bank/'source_data/definition_reference_wordnet_3_0';reference.mkdir(parents=True)
    (reference/'data.noun').write_text('00000001 06 n 01 abacus 0 000 | a manual calculating frame\n')
    (reference/'index.noun').write_text('abacus n 1 0 1 1 00000001\n')
    for part in ('verb','adj','adv'):(reference/f'index.{part}').write_text('  no entries\n')
    (reference/'LICENSE').write_text('Fixture lexical reference license')
    current=briefs/'phase2_definition_niches_20261101_v1';current.mkdir()
    (current/'canonical_candidates.json').write_text(json.dumps({'records':[{'normalized':'ABACUS'}]}))
    return briefs


def test_run_retains_pending_proposals_and_preserves_sources(tmp_path):
    briefs=_fixture(tmp_path)
    before={str(p.relative_to(tmp_path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    output=briefs/'phase2_definition_niches_20261101_v3'
    summary=run(tmp_path,output)
    assert summary['new_unique_candidates']==1
    assert summary['source_preservation_verified']
    for name,digest in before.items():assert hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()==digest
    payload=json.loads((output/'canonical_candidates.json').read_text())
    record=payload['records'][0];content_record_from_dict(record)
    assert record['normalized']=='ABACUS'
    assert record['quality']['editorial_status']=='pending_review'
    assert record['topics'][0]['status']=='proposed'
    assert record['payload']['definition']=='a manual calculating frame'
    assert record['payload']['parent_topic_review_required']
    candidates=json.loads((output/'grouping_review_candidates.json').read_text())['candidates']
    assert candidates[0]['status']=='generated_unreviewed'
    with pytest.raises(FileExistsError):run(tmp_path,output)
    with pytest.raises(ValueError,match='within word_banks'):run(tmp_path,tmp_path/'unsafe')


def test_misleading_inherited_parent_is_held_without_rewriting_taxonomy():
    from tools.extend_word_review import candidate_review_hold
    group={'name':'Clocks and Timepieces','parent_topic_id':'sports_hobbies'}
    before=dict(group)
    hold=candidate_review_hold('HOURGLASS',group)
    assert hold['rule']=='timepiece_parent_mismatch'
    assert hold['reason']=='semantic_parent_or_definition_review'
    assert group==before
    assert candidate_review_hold('HOURGLASS',{'name':'Clocks and Timepieces','parent_topic_id':'science_discovery'}) is None
    assert candidate_review_hold('AQUIFER',{'name':'Geological Formations','parent_topic_id':'nature'}) is None
    assert candidate_review_hold('CHRYSALIS',{'name':'Insects and Entomology','parent_topic_id':'nature'})['rule']=='cocoon_gloss_requires_entomology_review'
