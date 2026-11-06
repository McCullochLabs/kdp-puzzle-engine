"""Add definition-backed review candidates without modifying approved vocabulary."""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque, Counter
import argparse, hashlib, json, re, sys
CAMPAIGN_ID="phase2_20261101"
CAMPAIGN_DIRECTORY_PREFIX="phase2_definition_niches_20261101"
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from word_intelligence.content_contracts import content_record_from_dict, deterministic_content_id

def noun_reference(directory):
    senses={}; lemmas=defaultdict(list)
    for line in (directory/'data.noun').read_text(encoding='utf-8').splitlines():
        if not line or not line[0].isdigit(): continue
        raw, _, gloss=line.partition('|'); parts=raw.split(); count=int(parts[3],16)
        words=[parts[4+2*i] for i in range(count)]; at=4+2*count; pointers=int(parts[at]); at+=1
        parents=[parts[at+4*i+1] for i in range(pointers) if parts[at+4*i] in ('@','@i') and parts[at+4*i+2]=='n']
        senses[parts[0]]={'definition':gloss.strip(),'words':words,'parents':parents}
        for word in words: lemmas[word.casefold()].append(parts[0])
    return senses,lemmas

def nearest_anchors(start,senses,anchors):
    queue=deque([(start,0)]); seen=set(); found=[]; distance=None
    while queue:
        node,depth=queue.popleft()
        if node in seen or (distance is not None and depth>distance): continue
        seen.add(node)
        if node in anchors:
            found.extend(anchors[node]);distance=depth
        else:
            queue.extend((parent,depth+1) for parent in senses.get(node,{}).get('parents',[]))
    return list({(x['name'],x['parent_topic_id']):x for x in found}.values())

def prior_candidate_words(root):
    """Exclude established campaigns, not earlier versions of this campaign.

    Current canonical candidates have no campaign_id field, so the campaign
    directory prefix is also required. Including v1 here would make v2 empty.
    """
    base=Path(root)/'word_banks/research_briefs'
    prior=set(); prior_files=[]; skipped_current=[]
    for path in sorted(base.rglob('*candidates.json')):
        relative=path.relative_to(base)
        if any(part.startswith(CAMPAIGN_DIRECTORY_PREFIX) for part in relative.parts[:-1]):
            skipped_current.append(path); continue
        payload=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(payload,dict):continue
        prior_files.append(path)
        for record in payload.get('records',payload.get('candidates',[])):
            if not isinstance(record,dict) or record.get('campaign_id')==CAMPAIGN_ID:continue
            word=record.get('normalized',record.get('source_content_id',''))
            if isinstance(word,str) and word:
                prior.add(word)
    return prior,prior_files,skipped_current


def _hashes(paths):
    return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


# These are campaign-specific semantic review holds, not taxonomy edits.
# Provenance: independent review of v3 exact WordNet gloss/group/parent pairs.
SEMANTIC_REVIEW_PROVENANCE = "phase2_definition_niches_20261101_v3/independent_verification.json"
SEMANTIC_REVIEW_RULES = (
    ({"ALB", "CHALICE", "PEW"}, "home_household", "religious_object_parent_context"),
    ({"HOURGLASS"}, "sports_hobbies", "timepiece_parent_mismatch"),
    ({"BOARDROOM"}, "home_household", "corporate_room_parent_mismatch"),
    ({"MINA"}, None, "uncommon_bird_spelling_review"),
    ({"CHRYSALIS"}, None, "cocoon_gloss_requires_entomology_review"),
    ({"COASTGUARD"}, None, "regional_service_spelling_context"),
    ({"LAVA", "MAGMA"}, "science_discovery", "molten_material_rock_type_context"),
    ({"FORMALITIES"}, "holiday_seasonal_life", "etiquette_not_necessarily_holiday"),
)


def candidate_review_hold(word, group):
    """Do not turn a valid lexical niche into a misleading parent proposal."""
    for words, parent, rule in SEMANTIC_REVIEW_RULES:
        if word in words and (parent is None or group['parent_topic_id'] == parent):
            return {'rule': rule, 'reason': 'semantic_parent_or_definition_review',
                    'group': group['name'], 'inherited_parent_topic_id': group['parent_topic_id'],
                    'provenance': SEMANTIC_REVIEW_PROVENANCE}
    return None


def run(root,output):
    root=Path(root).resolve(); output=Path(output).resolve()
    if not output.is_relative_to(root/'word_banks/research_briefs'):
        raise ValueError('Review output must stay within word_banks/research_briefs.')
    if output.exists(): raise FileExistsError('Use a new versioned output directory; prior review evidence is preserved.')
    old=root/'word_banks/research_briefs/definition_backed_word_organization_2026_10_09'
    inputs=[root/'word_banks/word_intelligence/word_store.json',old/'semantic_roots.txt',old/'semantic_word_groups.json']
    store=json.loads(inputs[0].read_text(encoding='utf-8-sig'))['records']
    groups=json.loads(inputs[2].read_text())['groups']; group_map={g['name']:g for g in groups if g['kind']=='focused_niche'}
    directory=root/'word_banks/source_data/definition_reference_wordnet_3_0';senses,lemmas=noun_reference(directory)
    other_pos=set()
    for part in ('verb','adj','adv'):
        for line in (directory/f'index.{part}').read_text().splitlines():
            if line and not line.startswith(' '):other_pos.add(line.split()[0].casefold())
    explicit_holds={'THERMOS':'potential_brand_review','GASKET':'anchor_is_seal_not_a_fastener','DEC':'abbreviation_and_audience_review','ARE':'function_word_and_unit_ambiguity','BROTHEL':'adult_content_review','ASHTRAY':'tobacco_audience_review','BENEDICTINE':'alcohol_and_proper_name_review','BOURBON':'alcohol_audience_review','MACON':'alcohol_and_proper_name_review','MEAD':'alcohol_audience_review','MEN':'broad_person_label_not_a_focused_niche'}
    prior, prior_files, skipped_current_files = prior_candidate_words(root)
    anchors=defaultdict(list)
    # index.noun ordering, not data.noun ordering, defines the documented sense number.
    index={}
    for line in (directory/'index.noun').read_text().splitlines():
        if not line or line.startswith(' '):continue
        parts=line.split();n=int(parts[2]);index[parts[0]]=parts[-n:]
    for line in inputs[1].read_text().splitlines():
        if not line or line.startswith('#'):continue
        label,parent,lemma,sense=line.split('|')
        if label not in group_map:continue
        offsets=index.get(lemma,[])
        if int(sense)<len(offsets):anchors[offsets[int(sense)]].append(group_map[label])
    # Keep complete reference and prior-campaign provenance, not only the noun
    # files. These sources must remain unchanged throughout candidate creation.
    source_paths=inputs+[directory/name for name in ('data.noun','index.noun','index.verb','index.adj','index.adv','LICENSE')]+prior_files
    protected_paths=[root/name for name in ('word_banks/Guided_Builder_Master_Word_Bank.json','data/content_approval_decisions.json','word_banks/word_intelligence/approved_topic_links.json') if (root/name).exists()]
    before_hashes=_hashes(source_paths+protected_paths)
    from word_search_creator import REVIEW_REQUIRED_TERMS
    candidate_rows=[];canonical=[];holds=[];by_group=defaultdict(list);untrusted=0
    for record in store:
        if any(t['status'] in ('trusted','approved') for t in record.get('topics',[])):continue
        untrusted+=1;word=record['normalized']
        if word in prior:continue
        reason='';semantic_hold=None;offsets=lemmas.get(word.lower(),[])
        if record.get('trademark_review') or record.get('safety_review') or word in REVIEW_REQUIRED_TERMS:reason='existing_review_gate'
        elif word in explicit_holds:reason=explicit_holds[word]
        elif word.lower() in other_pos:reason='alternate_part_of_speech_requires_context'
        elif not re.fullmatch('[A-Z]{3,15}',word):reason='outside_exact_3_to_15_letter_scope'
        elif len(offsets)!=1:reason='no_unique_exact_noun_sense'
        else:
            sense=senses[offsets[0]]
            if any(w[:1].isupper() for w in sense['words']):reason='named_or_capitalized_synset'
            elif re.search(r'\b(obsolete|archaic|derogatory|offensive|vulgar|slang|sexual|genital|penis|vagina|excrement|racist|prostitut\w*|whore\w*)\b',sense['definition'],re.I):reason='sensitive_or_dated_definition'
            else:
                matches=nearest_anchors(offsets[0],senses,anchors)
                if len(matches)!=1:reason='no_unique_specific_niche_anchor'
                elif (semantic_hold := candidate_review_hold(word,matches[0])):reason=semantic_hold['reason']
                elif record.get('frequency',0)<2.0:reason='low_familiarity_specialist_review'
                elif any(t['status']=='rejected' and t['topic_id']==matches[0]['parent_topic_id'] for t in record.get('topics',[])):reason='rejected_topic_link'
        if reason:
            hold={'normalized':word,'reason':reason}
            if semantic_hold:hold['semantic_review']=semantic_hold
            holds.append(hold);continue
        group=matches[0];synset='n:'+offsets[0];topic=group['parent_topic_id'];definition=senses[offsets[0]]['definition']
        cid=hashlib.sha256((word+'|'+topic+'|phase2_20261101').encode()).hexdigest()[:24]
        candidate_rows.append({'candidate_id':cid,'campaign_id':'phase2_20261101','source_content_id':word,'display':word.lower(),'normalized':word,'topic_id':topic,'puzzle_type':'word_search','tier':'Review Carefully','reasons':['Definition-backed exact noun lemma',group['name'],synset,'Inherited parent-topic fit and alternate parts of speech require editorial review'],'provenance':'dictionary:Princeton_WordNet_3.0','status':'generated_unreviewed'})
        item={'schema_version':1,'id':deterministic_content_id('word',word),'type':'word','display':word.lower(),'normalized':word,'topics':[{'topic_id':topic,'relationship':'primary','confidence':55,'status':'proposed'}],'audiences':[],'difficulty':'standard','format_rules':{'word_search_max_letters':15,'safe_for_cover':False},'quality':{'editorial_status':'pending_review','factual_status':'not_applicable','trademark_review':False,'safety_review':False},'provenance':{'source_type':'dictionary','source_id':'Princeton_WordNet_3.0:'+synset,'reviewed_at':''},'payload':{'word_group':group['name'],'definition':definition,'definition_synset':synset,'frequency':record.get('frequency'),'ambiguity_review_required':True,'parent_topic_review_required':True,'alternate_parts_of_speech_not_resolved':True,'definition_is_not_trivia':True}}
        content_record_from_dict(item);canonical.append(item);by_group[group['name']].append(word)
    if _hashes(source_paths+protected_paths)!=before_hashes:
        raise RuntimeError('Review input or protected approval source changed during candidate selection.')
    output.mkdir(parents=True)
    def save(name,data):(output/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    save('grouping_review_candidates.json',{'schema_version':1,'candidates':candidate_rows});save('canonical_candidates.json',{'schema_version':1,'records':canonical});save('niche_word_groups.json',{'schema_version':1,'status':'REVIEW_REQUIRED','groups':dict(sorted(by_group.items()))});save('review_holds.json',{'status':'UNASSIGNED','reason_counts':dict(Counter(r['reason'] for r in holds)),'records':holds})
    summary={'source_untrusted_records':untrusted,'new_unique_candidates':len(canonical),'new_niche_groups':len(by_group),'held_not_forced':len(holds),'semantic_review_holds':sum(h['reason']=='semantic_parent_or_definition_review' for h in holds),'semantic_review_rule_provenance':SEMANTIC_REVIEW_PROVENANCE,'prior_candidate_words_excluded':len(prior),'approval_changes':0,'source_changes':0,'input_sha256':{str(Path(p).relative_to(root)):h for p,h in before_hashes.items()},'prior_candidate_files':[str(p.relative_to(root)) for p in prior_files],'current_campaign_versions_skipped':[str(p.relative_to(root)) for p in skipped_current_files],'source_preservation_verified':True,'limitations':['Single noun sense does not exclude other parts of speech or specialist/parent-topic ambiguity. All remain proposed and pending review.','No master/store/taxonomy or existing campaign was changed. No book capacity or trivia verification is inferred.']}
    save('validation.json',summary);(output/'WORDNET_LICENSE.txt').write_bytes((directory/'LICENSE').read_bytes());print(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.root,args.output)
