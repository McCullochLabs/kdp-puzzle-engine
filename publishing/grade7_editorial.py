"""Book-scoped provisional editorial evidence; never grants human approval."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GLOSSARY=ROOT/'word_banks/grade7_review_glossary.json'

REFERENCES={
    'language':('Grade 7 language standards','https://www.thecorestandards.org/ELA-Literacy/L/7/'),
    'writing':('Grade 7 writing standards','https://www.thecorestandards.org/ELA-Literacy/W/7/'),
    'reading':('Grade 7 literature standards','https://www.thecorestandards.org/ELA-Literacy/RL/7/'),
    'math':('Illustrative Mathematics Grade 7 glossary','https://im.kendallhunt.com/MS/teachers/2/glossary.html'),
    'cells':('NGSS middle-school cells and organisms','https://www.nextgenscience.org/dci-arrangement/ms-ls1-molecules-organisms-structures-and-processes'),
    'matter':('NGSS middle-school matter','https://www.nextgenscience.org/dci-arrangement/ms-ps1-matter-and-its-interactions'),
    'motion':('NGSS middle-school forces and motion','https://www.nextgenscience.org/dci-arrangement/ms-ps2-motion-and-stability-forces-and-interactions'),
    'engineering':('NGSS middle-school engineering design','https://www.nextgenscience.org/dci-arrangement/ms-ets1-engineering-design'),
    'ecology':('NGSS middle-school ecosystems','https://www.nextgenscience.org/dci-arrangement/ms-ls2-ecosystems-interactions-energy-and-dynamics'),
    'earth':('USGS tectonic-plate explanation','https://pubs.usgs.gov/gip/dynamic/tectonic.html'),
    'history':('Smithsonian artifact-investigation lesson','https://www.smithsonianeducation.org/educators/lesson_plans/decoding_the_past/lesson1.html'),
    'digital':('FTC recognizing phishing','https://consumer.ftc.gov/articles/how-recognize-avoid-phishing-scams'),
    'art':('Getty elements and principles of art','https://www.getty.edu/education/teachers/building_lessons/formal_analysis.html'),
    'music':('MusicTheory.net introductory lessons','https://www.musictheory.net/lessons'),
    'timbre':('Carnegie Hall exploring sound qualities','https://www.carnegiehall.org/Education/Programs/Link-Up/National-Program/The-Orchestra-Rocks/Explore-Sounds-that-Rock'),
    'learning':('IES organizing instruction and study','https://ies.ed.gov/ncee/wwc/PracticeGuide/1'),
    'wordnet':('Princeton WordNet lexical reference','https://wordnet.princeton.edu/')}

TOPIC_REFERENCES=[['motion'],['cells'],['matter'],['motion'],['earth'],
    ['math'],['math'],['math'],['math'],['math','language'],
    ['reading'],['writing'],['language','reading'],['writing'],['language'],
    ['earth'],['history'],['writing'],['math'],['ecology'],
    ['engineering'],['digital'],['art'],['music','timbre'],['learning']]

PROMPT_GUIDANCE=[
    'Compare observations with the prediction. Explain whether the evidence supports it; a mismatch can lead to revision.',
    'Name a cell part and describe a simple job, such as a membrane controlling movement into and out of a cell.',
    'A mixture physically combines substances; a compound contains elements chemically bonded in fixed proportions.',
    'Examples include shoe grip, bicycle braking, and holding a pencil. Connect the example to resisting slipping.',
    'Erosion moves material; transported particles can become sediment deposited elsewhere.',
    'An expression represents a quantity. An equation states that two expressions have equal values.',
    'A unit rate compares a quantity with one of another, such as miles per hour or dollars per ticket.',
    'A diameter passes through the center and is twice the radius of the same circle.',
    'A very high or low value can change a mean and suggest checking the distribution or possible measurement errors.',
    'A universal statement claims every case works. One valid case that fails shows the universal statement is false.',
    'Use actions, dialogue, thoughts, and events as evidence; more than one inference may be defensible.',
    'Considering an opposing claim can reveal weaknesses and help a writer respond with stronger reasons and evidence.',
    'Accept an original comparison using like or as that meaningfully describes a place.',
    'Revision improves ideas, organization, and clarity; editing corrects wording and writing conventions.',
    'Accept a real prefix with an accurate example, such as re- in reread, meaning to read again.',
    'Latitude locates north/south position; longitude locates east/west position. Together they identify a location.',
    'An artifact can suggest past materials, activities, or technology; explain uncertainty and the need for context.',
    'Accept a practical community responsibility, explained with an example, without requiring a political opinion.',
    'Spending on one item leaves less money or another opportunity available. Identify a specific alternative forgone.',
    'Protecting a habitat can maintain food, shelter, and other conditions supporting its organisms.',
    'Testing prototypes can expose failures and compare improvements within criteria and constraints.',
    'Accept a sensible privacy action, such as sharing less personal information or checking account privacy controls.',
    'Differences in light, color, size, or texture can draw attention to an important part of an artwork.',
    'Changing the pace can suggest different energy or mood; accept examples tied to a particular performance.',
    'Useful feedback identifies a change to try. Explain how practice and a later check could show improvement.']


def lexical_index(root=ROOT):
    """Record lexical presence without copying definitions or asserting grade level."""
    words=set()
    base=Path(root)/'word_banks/source_data/definition_reference_wordnet_3_0'
    for name in ('noun','verb','adj','adv'):
        with (base/f'index.{name}').open(encoding='ascii') as source:
            for line in source:
                if line and not line.startswith(' '): words.add(line.split()[0])
    return words


def review_source(data,store,source_path,glossary_path=GLOSSARY):
    glossary_path=Path(glossary_path)
    glossary=json.loads(glossary_path.read_text(encoding='utf-8'))
    definitions=glossary['definitions']; lexicon=lexical_index()
    rows=[]; prompts=[]
    topics=[topic for chapter in data['chapters'] for topic in chapter['topics']]
    gaps=[]
    for i,topic in enumerate(topics):
        for word in topic['words'].split():
            record=store.get(word)
            gap=record is None or record.is_unclassified()
            if gap: gaps.append(word)
            if gap and not definitions.get(word):
                raise ValueError(f'Editorial review is missing an explanation for {word}.')
            display=glossary['display_forms'].get(word,word)
            lemma=display.lower().replace('-','_').replace(' ','_')
            aliases={'MITOCHONDRIA':'mitochondrion','BALANCED':'balanced','GEARS':'gear'}
            lookup=aliases.get(word,lemma)
            rows.append(dict(target=word,display=display,topic=topic['name'],
                disposition='retain_with_word_guide' if gap else 'retain_in_context',
                reviewer='Codex AI-assisted provisional review',teacher_approved=False,
                scope_references=TOPIC_REFERENCES[i],reference_scope='Subject context only; no prescribed grade-seven word-list claim.',
                lexical_reference='wordnet' if lookup in lexicon else None,
                definition=definitions.get(word),stretch_term=word in glossary['stretch_terms']))
        prompts.append(dict(topic=topic['name'],prompt=topic['prompt'],
            review='Open-ended, relevant to the topic, no personal disclosure required.',
            suggested_response=PROMPT_GUIDANCE[i],other_reasonable_answers_accepted=True))
    targets=[r['target'] for r in rows]
    if len(targets)!=300 or len(set(targets))!=300:
        raise ValueError('Editorial evidence must cover all 300 distinct targets.')
    return dict(schema_version=1,source_sha256=hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
        glossary_sha256=hashlib.sha256(glossary_path.read_bytes()).hexdigest(),
        review_method=glossary['review_method'],teacher_approval='pending',
        reviewed_targets=len(rows),previous_library_gaps=len(gaps),glossary_targets=sorted(gaps),
        references={key:dict(title=value[0],url=value[1]) for key,value in REFERENCES.items()},
        words=rows,prompts=prompts,
        decision='All terms retained for recreational enrichment; glossary support added for all library gaps. Stretch terms are optional vocabulary, not assessed mastery.')


def validate_review(review,data,source_path,glossary_path=GLOSSARY):
    errors=[]
    glossary=json.loads(Path(glossary_path).read_text(encoding='utf-8'))
    if review.get('source_sha256')!=hashlib.sha256(Path(source_path).read_bytes()).hexdigest(): errors.append('Editorial source fingerprint is stale.')
    if review.get('glossary_sha256')!=hashlib.sha256(Path(glossary_path).read_bytes()).hexdigest(): errors.append('Glossary fingerprint is stale.')
    expected={word for chapter in data['chapters'] for topic in chapter['topics'] for word in topic['words'].split()}
    actual=[row['target'] for row in review.get('words',[])]
    if set(actual)!=expected or len(actual)!=len(expected): errors.append('Editorial target coverage differs from the book.')
    if any(not row.get('scope_references') or row.get('teacher_approved') for row in review.get('words',[])):
        errors.append('Provisional evidence must cite its subject context and must not assert teacher approval.')
    for row in review.get('words',[]):
        if row.get('disposition')=='retain_with_word_guide' and not row.get('definition'):
            errors.append('A supported target has no word-guide explanation.')
        if row.get('definition')!=glossary['definitions'].get(row['target']):
            errors.append('An explanation differs from the fingerprinted glossary.')
        if any(ref not in REFERENCES for ref in row.get('scope_references',[])):
            errors.append('An editorial reference is unknown.')
    if len(review.get('prompts',[]))!=25: errors.append('Prompt review is incomplete.')
    return errors
