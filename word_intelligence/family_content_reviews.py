"""Small owner-requested editorial repairs, separate from generated inventories.

These are vocabulary membership reviews, not artwork or publishing approvals.
Rejected links and safety flags remain authoritative.
"""
import json
from pathlib import Path
from .normalization import clean_surface

FILENAME = 'family_group_content_reviews.json'


def load_reviews(root):
    path = Path(root) / 'word_banks' / FILENAME
    try:
        if path.stat().st_size > 128_000: return {}
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError): return {}
    if doc.get('schema_version') != 1 or doc.get('review_type') != 'owner_requested_editorial_membership': return {}
    result = {}
    for topic, review in doc.get('reviews', {}).items():
        if not isinstance(topic,str) or len(topic)>80 or not isinstance(review,dict): continue
        words = review.get('words', [])
        if not isinstance(words,list) or len(words)>100: continue
        result[topic] = tuple(dict.fromkeys(clean_surface(word) for word in words if isinstance(word,str)
            and clean_surface(word).isascii() and clean_surface(word).isalpha() and 2 <= len(clean_surface(word)) <= 18))
    return result


def merge_bank_reviews(bank, root):
    for topic, words in load_reviews(root).items():
        if topic not in bank.get('topics', {}): continue
        bank['topics'][topic] = sorted(set(bank['topics'][topic]) | set(words))
        bank['words'] = sorted(set(bank.get('words', [])) | set(words))
        for word in words:
            profile = bank.setdefault('word_profiles', {}).setdefault(word, {})
            profile['topics'] = sorted(set(profile.get('topics', [])) | {topic})
            profile['sources'] = sorted(set(profile.get('sources', [])) | {'family_editorial_membership_review'})
    return bank


def apply_store_reviews(store, taxonomy, root):
    from .records import TopicLink, EvidenceItem, TRUSTED, SIGNAL_EXISTING
    from wordfreq import zipf_frequency
    for topic, words in load_reviews(root).items():
        topic_id = taxonomy.resolve(topic)
        if not topic_id: continue
        for word in words:
            # A curated topic list cannot invent dictionary words or override a veto.
            if word not in store.dictionary_words: continue
            record = store.records.get(word)
            if record is not None:
                link = record.link_for(topic_id)
                if record.trademark_review or record.safety_review or (link and link.status == 'rejected'): continue
            else:
                record = store.ensure_record(word, word)
                link = None
            if record.frequency is None: record.frequency = zipf_frequency(word.casefold(),'en')
            if link is None:
                record.topics.append(TopicLink(topic_id, TRUSTED, 100.0,
                    [EvidenceItem(SIGNAL_EXISTING, 'Owner-requested explicit editorial membership review; dictionary-backed vocabulary', 30)]))
            if 'family_editorial_membership_review' not in record.sources:
                record.sources.append('family_editorial_membership_review')
