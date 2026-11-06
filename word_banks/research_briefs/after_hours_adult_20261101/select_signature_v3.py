from pathlib import Path
import json,random,sys,collections,re,hashlib
sys.path.insert(0,str(Path.cwd()))
from wordsearch import validate_word_set,grid_size_for
root=Path(__file__).parent
out=root/'v3_cannabis_signature_research'
rows=json.loads((out/'candidate_pool.json').read_text(encoding='utf8'))
base=json.loads((root/'v2_online_expansion/standard_48_group_candidates.json').read_text(encoding='utf8'))
baseflat={w for g in base for w in g['words']}
allocation={'cannabis vocabulary':2,'cannabis anatomy':3,'cannabis chemistry':5,'glass smoking accessories':5,'tobacco pipe shapes and parts':6,'cigar lounge vocabulary':9,'lighters and ignition':2,'vaporizer vocabulary':3,'wine cellar vocabulary':7,'named wines and spirits':4,'casino lounge vocabulary':6}
# These authentic but unsuitable/alias/generic source labels are withheld from Signature selection.
selection_holds={
 'ROACH':'needs direct slang source review','DOOBIE':'needs direct slang source review','STONER':'needs direct slang source review','STONED':'needs direct slang source review','TOKE':'needs direct slang source review','SINSEMILLA':'needs direct slang source review',
 'ATOMISER':'spelling alias of ATOMIZER already globally present','HEADY':'generic adjective','COLLAB':'generic collaboration term','BOROHEAD':'niche slang; independent review required','PIECE':'overly broad slang','DIFFUSION':'broad process word','PRECOOLER':'same object as ash catcher',
 'AUTHOR':'pipe shape but overly generic display','FILL':'overly generic pipe term','STRAIGHT':'overly generic display','STAIN':'overly generic display','POT':'already cannabis slang; do not use twice','ORIENTAL':'ambiguous style label held','PRINCE':'eponymous pipe name; defer review','HEATH':'plant material not central to accessories',
 'FINISH':'overly generic display','GLASSJAR':'overly generic accessory','JAR':'overly generic accessory','AMARILLO':'color descriptor also hop product association','CIGARMAKER':'craft role lower priority','CIGARCASE':'reserve generic accessory','CIGARBAR':'reserve venue','CIGARLOUNGE':'reserve venue','CASE':'overly generic display',
 'BODY':'overly generic component','BASE':'overly generic component','BALL':'overly generic component','FORK':'overly generic component','GUARD':'overly generic component',
 'MOD':'very broad shortened name','VAPOR':'generic physical state','VAPING':'act label reserve','OHM':'generic measurement unit',
 'AVA':'acronym not preferred','ABV':'acronym not preferred','AROMACOMPOUNDS':'broad chemistry descriptor','ESTERS':'broad chemistry class','GLYCEROL':'broad chemical label','PHENOLS':'broad chemical class','SUSS':'ASCII spelling loses distinctive German identity','JENNIE':'generic name/reserve bottle term',
 'CABERNET':'shorthand alias of existing grape name','MUSCADEL':'overlapping muscatel alias','MUSCADELLE':'wine/grape sense needs review','RYEWHISKEY':'overlapping rye spirit','PORTWINE':'same wine as PORT','VARIETALWINE':'overlapping VARIETAL','ETHYLALCOHOL':'not a named drink','STRONGDRINK':'generic classification','INEBRIANT':'broad alias','INTOXICANT':'broad alias','ARDENTSPIRITS':'broad alias','AQUAVITAE':'broad alias','LACING':'ambiguous added-alcohol sense',
 'CARDPLAYER':'overly broad role','DIE':'very short ambiguous target','PAIR':'overly broad short target','BET':'very short ambiguous target','CHECK':'broad action','CALL':'broad action','HIT':'broad action','STAND':'broad action','FOLD':'broad action','RAISE':'broad action','SWEEPSTAKES':'outside nightlife table-game focus','LOTTERY':'outside nightlife table-game focus','BINGO':'outside intended nightlife focus','PACHINKO':'outside selected nightlife focus','LONGSHOT':'broad metaphor','CARD SHARPER':'reserve spelling alias'
}
# Provisional capacities are quality-trimmed, not forced. Relax no production validation.
priorities={'CANNABIS','MARIJUANA','HEMP','WEED','GANJA','BUD','HASHISH','JOINT','BLUNT','SPLIFF','REEFER','BONG','PIPE','LIGHTER','POCKETLIGHTER','FLINT','WICK','TORCHLIGHTER','BUTANE','CARBCAP','CHILLUM','DABRIG','DOWNSTEM','GRINDER','ONEHITTER','ROLLINGPAPER','VAPEPEN','VAPORIZER','CANNABIDIOL','CANNABINOL','CANNABIGEROL','TETRAHYDROCANNABINOL'}
groups=[dict(g) for g in base];errors=[];sizes={}
for niche,num in allocation.items():
 pool=[r for r in rows if r['niche']==niche and r['normalized'] not in baseflat and r['normalized'] not in selection_holds and not r.get('selection_hold')]
 sizes[niche]={'available_after_holds':len(pool),'requested_groups':num}
 best=[]
 for attempt in range(1000):
  rng=random.Random(20261103+attempt);order=pool[:];rng.shuffle(order);order.sort(key=lambda r:r['normalized'] not in priorities)
  bins=[[] for _ in range(num)]
  for r in order:
   ix=list(range(num));rng.shuffle(ix);ix.sort(key=lambda j:len(bins[j]))
   for j in ix:
    if len(bins[j])>=12:continue
    try:validate_word_set([x['normalized'] for x in bins[j]]+[r['normalized']],21)
    except ValueError:continue
    bins[j].append(r);break
  if sum(map(len,bins))>sum(map(len,best)):best=bins
  if all(len(g)==12 for g in bins):break
 if not all(len(g)==12 for g in best):errors.append({'niche':niche,'group_sizes':list(map(len,best)),'pool':len(pool)});continue
 for i,g in enumerate(best,1):
  words=[r['normalized'] for r in g];N=grid_size_for(words);validate_word_set(words,N)
  groups.append({'id':'after_hours_signature_%03d'%(len(groups)+1),'title':niche.title()+' '+str(i),'niche':niche,'status':'pending_review','display_words':[r['display'] for r in g],'words':words,'grid_size':N,'source_records':[{'normalized':r['normalized'],'reference':r.get('external_reference') or 'Princeton WordNet 3.0 evidence in candidate_pool.json'} for r in g]})
print('CAPACITIES',json.dumps(sizes));print('ERRORS',json.dumps(errors))
if errors:raise SystemExit(2)
flat=[w for g in groups for w in g['words']]
assert len(groups)==100 and len(flat)==len(set(flat))==1200
idx={r['normalized']:r for r in rows}
for g in groups:
 validate_word_set(g['words'],g['grid_size'])
 assert len(g['words'])==12
 for w in g['words']:assert re.fullmatch('[A-Z]{3,21}',w) and (idx[w].get('wordnet_evidence') or idx[w].get('external_reference'))
summary={'status':'pending_editorial_and_production_review_not_approved','pool_count':len(rows),'added_since_v2':len(rows)-722,'signature_group_count':len(groups),'globally_unique_selected_targets':len(set(flat)),'group_size':12,'all_100_core_word_set_contracts_pass':True,'max_selected_target_length':max(map(len,flat)),'length_limit':21,'v2_standard_groups_preserved_exactly':groups[:48]==base,'selection_counts_by_niche':dict(collections.Counter(g['niche'] for g in groups)),'new_niche_capacities':sizes,'signature_candidate_source_sufficient':True,'signature_production_ready':False,'actual_grid_generation_and_ambiguity_checks':'not performed by research subtask','approval_changes':0,'production_bank_changes':0,'model_calls_v3':0,'selection_holds':selection_holds,'candidate_pool_sha256':hashlib.sha256((out/'candidate_pool.json').read_bytes()).hexdigest()}
for name,obj in [('signature_100_group_candidates.json',groups),('validation.json',summary),('unselected_pool.json',[r for r in rows if r['normalized'] not in set(flat)])]:
 (out/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf8')
print(json.dumps(summary,indent=2))
