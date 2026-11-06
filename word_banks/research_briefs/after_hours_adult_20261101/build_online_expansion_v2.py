from pathlib import Path
import json,re,unicodedata,random,collections,sys,hashlib
sys.path.insert(0,str(Path.cwd()))
from wordsearch import validate_word_set,grid_size_for
root=Path(__file__).parent
out=root/'v2_online_expansion';out.mkdir(exist_ok=True)
def norm(s):return re.sub('[^A-Z]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().upper())
rows=json.loads((root/'candidate_pool.json').read_text(encoding='utf8'))
held=json.loads((root/'held_candidates.json').read_text(encoding='utf8'))
seen={r['normalized'] for r in rows};sources=[];exclusions=[]
def add_terms(niche,text,url,kind='primary industry name reference'):
 sources.append({'url':url,'niche':niche,'evidence_kind':kind,'retrieved':'2026-11-01','used':'Names and generic terms only; no source prose or instructions'})
 for display in text.split('|'):
  k=norm(display)
  if k in seen:continue
  if not 3<=len(k)<=21:exclusions.append({'display':display,'reason':'outside 3..21 normalized A-Z letters','source':url});continue
  seen.add(k)
  prior=next((r for r in held if r['normalized']==k),None)
  row=dict(prior or {})
  row.update({'display':display.upper(),'normalized':k,'niche':niche,'status':'pending_review','external_reference':url,'reference_kind':kind,'topic_fit_review':'curated direct fit; pending independent editorial approval','brand_review':'generic term/name screened; pending final review','editorial_origin':'online primary-source gap research','wordnet_evidence':row.get('wordnet_evidence',[])})
  row.pop('hold_reason',None);rows.append(row)
add_terms('profanity and minced oaths','heck|crikey|cripes|gosh|golly|blimey|jeez|geez|strewth|jeepers|bejesus','https://www.wordwebonline.com/en/HECK','primary dictionary entry/synonym labels')
add_terms('lingerie and adult accessories','cock ring|anal beads|butt plug|bullet vibrator|wand vibrator|rabbit vibrator|clitoral vibrator|g spot stimulator|vibrating egg|finger massager|external vibrator|internal vibrator|anal vibrator|g spot vibrator|vibrating ring|personal massager|silicone|glass|plastic','https://www.trojan.ca/en-ca/sexual-information/types-of-vibrators')
add_terms('lingerie and adult accessories','handcuffs|cuffs|restraints|wrist cuffs|ankle cuffs|bed restraints|bondage rope|bondage tape|spreader bar|nipple clamps|under bed restraint|over door restraint|chain lead','https://www.lovehoney.com/bondage/handcuffs-restraints/')
add_terms('lingerie and adult accessories','ball gag|bondage hood|bit gag|ring gag|gag|mask|faux leather|metal|vinyl|neoprene|polyester|wax|pinwheel|nipple sucker','https://www.lovehoney.com/bondage/blindfolds-masks-gags/')
add_terms('lingerie and adult accessories','stainless steel|ABS plastic','https://www.lelo.com/blog/faq-choosing-the-right-toy-tc/')
# Source-corrected apostrophes/accents use the official permalink as evidence.
fix={'bees-knees':"Bee's Knees",'horses-neck':"Horse's Neck",'vieux-carre':'Vieux Carre'}
blocked={'chartreuse-swizzle':'protected product/liqueur brand','dark-n-stormy':'protected cocktail name','hemingway-special':'celebrity name','mary-pickford':'celebrity name','corpse-reviver-2':'official numeric identity incompatible with A-Z-only target','french-75':'official numeric identity incompatible with A-Z-only target','iba-tiki':'organization acronym/protected identity','grand-margarita':'potential brand association needs review','dons-special-daiquiri':'eponym association held','tommys-margarita':'named establishment association held','ve-n-to':'punctuation-dependent identity held','missionarys-downfall':'defer sensitivity review','porn-star-martini':'defer marketplace wording review','sex-on-the-beach':'defer marketplace wording review'}
for item in json.loads((root/'iba_name_evidence_unreviewed.json').read_text(encoding='utf8')):
 slug=item['url'].strip('/').split('/')[-1]
 if slug in blocked:exclusions.append({'display':item['name'],'reason':blocked[slug],'source':item['url']});continue
 display=fix.get(slug,item['name'])
 if '\ufffd' in display:exclusions.append({'display':display,'reason':'source encoding requires correction','source':item['url']});continue
 add_terms('named cocktails',display,item['url'])
# Real named beer styles, not manufactured beverage + adjective combinations.
add_terms('beer styles','American Light Lager|American Lager|Cream Ale|American Wheat Beer|International Pale Lager|Czech Pale Lager|Czech Amber Lager|Czech Dark Lager|Munich Helles|Festbier|Helles Bock|German Leichtbier|Kolsch|German Pils|Marzen|Rauchbier|Dunkles Bock|Vienna Lager|Altbier|Kellerbier|Munich Dunkel|Schwarzbier|Doppelbock|Eisbock|Baltic Porter|Weissbier|Dunkles Weissbier|Weizenbock|Ordinary Bitter|Best Bitter|Strong Bitter|British Golden Ale|English IPA|Dark Mild|British Brown Ale|English Porter|Scottish Light|Scottish Heavy|Scottish Export|Irish Red Ale|Irish Stout|Irish Extra Stout|Sweet Stout|Oatmeal Stout|Tropical Stout|Foreign Extra Stout|British Strong Ale|Old Ale|Wee Heavy|English Barleywine|Blonde Ale|American Pale Ale|American Amber Ale|California Common|American Brown Ale|American Porter|American Stout|Imperial Stout|American IPA|Belgian IPA|Black IPA|Brown IPA|Brut IPA|Red IPA|Rye IPA|White IPA|Hazy IPA|Double IPA|American Strong Ale|American Barleywine|Wheatwine|Berliner Weisse|Flanders Red Ale|Oud Bruin|Lambic|Gueuze|Fruit Lambic|Gose|Witbier|Belgian Pale Ale|Biere de Garde|Belgian Blond Ale|Saison|Belgian Dubbel|Belgian Tripel|Kentucky Common|Lichtenhainer|London Brown Ale|Piwo Grodziskie|Roggenbier|Sahti','https://www.bjcp.org/beer-styles/beer-style-guidelines/')
add_terms('wine grape varieties','Aligote|Arinto de Bucelas|Albarino|Assyrtiko|Bianco d Alessano|Bourboulenc|Chardonnay|Chenin Blanc|Clairette|Colombard|Cortese|Fiano|Friulano|Furmint|Garganega|Grenache Blanc|Grillo|Gruener Veltliner|Harslevelu|Inzolia|Kerner|Malvasia Istriana|Marsanne|Moscato Giallo|Pecorino|Petit Manseng|Picolit|Pinot Blanc|Pinot Grigio|Prosecco|Riesling|Roussanne|Sauvignon Blanc|Savagnin|Semillon|Traminer|Verdelho|Verdejo|Vermentino|Viognier|Alicante Bouschet|Barbera|Blaufrankisch|Bonvedro|Cabernet Franc|Cabernet Sauvignon|Carignan|Cinsaut|Corvina|Counoise|Dolcetto|Durif|Gamay|Graciano|Grenache|Lagrein|Lambrusco Maestri|Malbec|Marzemino|Mataro|Mencia|Merlot|Montepulciano|Negro Amaro|Nero d Avola|Petit Verdot|Pinot Noir|Pinotage|Ruby Cabernet|Sagrantino|Sangiovese|Saperavi|Schioppettino|Shiraz|Souzao|Tannat|Tempranillo|Teroldego|Tinto Cao|Trincadeira','https://www.awri.com.au/industry_support/viticulture/grapevine-varieties/')
# Canonical display normalization is ASCII/transliteration, never concatenated display phrases.
for r in rows:r['normalized']=norm(r['display'])
assert len({r['normalized'] for r in rows})==len(rows)
counts=collections.Counter(r['niche'] for r in rows)
# Choose only real attested vocabulary; broad niche labels are research grouping axes.
allocation={'profanity and minced oaths':4,'cheeky flirtation':7,'lingerie and adult accessories':6,'bar equipment and service':5,'alcoholic drinks':12,'named cocktails':6,'beer styles':4,'wine grape varieties':4}
# Exclude especially short embed-heavy targets, broad padding and questionable sense-fit.
selection_holds={'ASS':'embedded in too many profanity words','SHIT':'embedded in many profanity words','SOD':'very short embed risk','SWITCH':'too generic without adult context','CHEMISTRY':'broad topic fit','BOLD':'broad adjective','BRAZEN':'broad adjective','IMPISH':'broad adjective','SIZZLING':'broad adjective','BALLYHOO':'off-topic commotion sense','BUNKUM':'weak profanity connection','TOMFOOLERY':'weak adult-topic fit','FOOLERY':'weak adult-topic fit','BLOOMERS':'weak adult lingerie fit','PETTICOAT':'weak adult lingerie fit','PLASTIC':'generic material','GLASS':'generic material','POLYESTER':'generic material','WAX':'ambiguous material','MASK':'generic object','METAL':'generic material','FEATHER':'generic object','ROBE':'broad clothing','CRAP':'reserve short embed target','DRAUGHT':'spelling alias of draft','BREWAGE':'obscure alias','KIR':'short embedded target','CORNLIQUOR':'same spirit as corn whiskey','JULEP':'same drink as mint julep','HOMEBREW':'context broad','SWIZZLE':'bar tool ambiguity','SOUR':'generic category','COLLINS':'same family as John Collins','PUNCH':'broad embedded target','GIN':'embedded in many drink names','RUM':'embedded in many drink names','ALE':'embedded in many styles','BEER':'embedded in many styles','WINE':'embedded in many wine names','WHISKEY':'embedded in many spirit names','BOOZE':'reserve broad slang','ALCOHOL':'reserve broad term','COCKTAIL':'embedded in drink names','SPRUCEBEER':'obscure historical beverage reserve'}
for k in ['ASS','SHIT','SOD','CRAP','KIR','GIN','RUM','ALE','BEER','WINE','WHISKEY','BOOZE','ALCOHOL','COCKTAIL']:
 selection_holds.pop(k,None)
by={n:[r for r in rows if r['niche']==n and r['normalized'] not in selection_holds] for n in allocation}
# Seeded greedy with restarts distributes embedded targets and leaves surplus out.
groups=[]
for niche,num in allocation.items():
 pool=by[niche];best=[]
 for attempt in range(500):
  rng=random.Random(20261101+attempt);ordered=pool[:];rng.shuffle(ordered)
  priorities={'FUCK','SHIT','DAMN','HELL','BLOODY','BOLLOCKS','BUGGER','BASTARD','ASSHOLE','BULLSHIT','CRAP','PISS','WANKER','TWAT','VIBRATOR','DILDO','COCKRING','BUTTPLUG','ANALBEADS','BULLETVIBRATOR','WANDVIBRATOR','RABBITVIBRATOR','GIN','RUM','VODKA','TEQUILA','WHISKEY','BEER','WINE','ALE'}
  ordered.sort(key=lambda r:r['normalized'] not in priorities)
  bins=[[] for _ in range(num)]
  for r in ordered:
   options=list(range(num));rng.shuffle(options);options.sort(key=lambda j:len(bins[j]))
   for j in options:
    if len(bins[j])>=12:continue
    try:validate_word_set([x['normalized'] for x in bins[j]]+[r['normalized']],21)
    except ValueError:continue
    bins[j].append(r);break
  if sum(map(len,bins))>sum(map(len,best)):best=bins
  if all(len(g)==12 for g in bins):break
 assert all(len(g)==12 for g in best),(niche,len(pool),list(map(len,best)))
 for i,g in enumerate(best,1):
  words=[r['normalized'] for r in g];validate_word_set(words,grid_size_for(words))
  groups.append({'id':'after_hours_%02d'%(len(groups)+1),'title':niche.title()+' '+str(i),'niche':niche,'status':'pending_review','display_words':[r['display'] for r in g],'words':words,'grid_size':grid_size_for(words),'source_records':[{'normalized':r['normalized'],'reference':r.get('external_reference') or 'Princeton WordNet 3.0 offsets in candidate_pool.json'} for r in g]})
flat=[w for g in groups for w in g['words']]
assert len(groups)==48 and len(flat)==len(set(flat))==576
selected=set(flat)
remaining_holds=[r for r in held if r['normalized'] not in seen]
validation={'status':'pending_review_not_approved','candidate_pool_count':len(rows),'new_attested_terms_since_v1':len(rows)-418,'counts_by_niche':dict(counts),'standard_candidate_groups':48,'selected_globally_unique_words':576,'all_groups_exactly_12':all(len(g['words'])==12 for g in groups),'core_validate_word_set_passed':48,'max_normalized_length':max(map(len,flat)),'length_limit':21,'standard_candidate_complete':True,'standard_production_ready':False,'signature_required':1200,'signature_shortfall_from_entire_pool':max(0,1200-len(rows)),'signature_ready':False,'grid_placement_and_integrity':'not run in this research task','approval_changes':0,'production_file_changes':0,'curated_selection_holds':selection_holds,'prior_hold_terms_now_attested':sorted({r['normalized'] for r in held}&seen),'remaining_prior_lexical_holds':len(remaining_holds),'allocation_groups':allocation,'local_model_suggestions_accepted':0}
for name,obj in [('candidate_pool.json',rows),('standard_48_group_candidates.json',groups),('validation.json',validation),('source_manifest.json',sources),('source_exclusions.json',exclusions),('remaining_prior_holds.json',remaining_holds),('unselected_attested_candidates.json',[r for r in rows if r['normalized'] not in selected])]:
 (out/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf8')
print(json.dumps(validation,indent=2))
