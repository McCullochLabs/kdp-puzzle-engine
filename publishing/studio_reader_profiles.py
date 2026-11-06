"""Deterministic reader mechanics; these are aids, not reading-age certification."""
from functools import lru_cache
import re

READER_PROFILES = {
    'grade_7': {'label':'Grade 7 / cross-subject enrichment','max_length':15,'minimum_frequency':None,'grid':15,
                'minimum_grid_font_pt':16,'minimum_word_font_pt':14,
                'directions':None,'instructions':'Words may run across, down, diagonally or backwards. Spaces are omitted.'},
    'standard': {'label': 'Standard / adults & teens', 'max_length': 18, 'minimum_frequency': None, 'grid': 15,
                 'directions': None, 'instructions': 'Words may run across, down, diagonally or backwards.'},
    'ages_6_8': {'label': 'Ages 6–8 / simpler words', 'max_length': 8, 'minimum_frequency': 3.8, 'grid': 12,
                 'minimum_grid_font_pt':18,'minimum_word_font_pt':16,
                 'directions': ((0, 1), (1, 0)), 'instructions': 'Words run left to right or top to bottom. No diagonal or backwards words.'},
    'ages_9_12': {'label': 'Ages 9–12 / growing readers', 'max_length': 12, 'minimum_frequency': 3.2, 'grid': 15,
                 'minimum_grid_font_pt':16,'minimum_word_font_pt':14,
                 'directions': ((0, 1), (1, 0), (1, 1), (1, -1)), 'instructions': 'Words run forwards across, down or diagonally down. No backwards words.'},
}
READER_LABELS = {value['label']: key for key, value in READER_PROFILES.items()}
ADULT_GROUPS = ('cannabis', 'cocktail', 'nightlife', 'romance', 'relationship fun', 'firearms')


def reader_profile(key='standard'):
    if key not in READER_PROFILES: raise ValueError('Choose a supported reader profile.')
    return READER_PROFILES[key]


@lru_cache(maxsize=8192)
def familiar_word(word):
    from wordfreq import zipf_frequency
    return zipf_frequency(word.casefold(), 'en')


def word_suits_reader(word, key='standard', frequency=None):
    profile = reader_profile(key)
    if len(word) > profile['max_length']: return False
    if profile['minimum_frequency'] is None: return True
    score = familiar_word(word) if frequency is None else frequency
    return score >= profile['minimum_frequency']


def check_reader_topic(topic, key):
    reader_profile(key)
    if key != 'standard' and any(term in str(topic).casefold() for term in ADULT_GROUPS):
        raise ValueError('This adult topic is unavailable with a child reader profile. Choose another topic.')


def reader_from_request(text):
    # Explicit ages are parsed locally, without another model request.
    words = {'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
    match = re.search(r'\b(\d{1,2}|six|seven|eight|nine|ten|eleven|twelve)[ -]+year[ -]+old\b|\bage[sd]?\s+(\d{1,2})\b', text, re.I)
    if not match: return None
    raw=(match.group(1) or match.group(2)).casefold()
    age=words[raw] if raw in words else int(raw)
    if 6 <= age <= 8: return 'ages_6_8'
    if 9 <= age <= 12: return 'ages_9_12'
    if age >= 13: return 'standard'
    raise ValueError('Reader profiles start at age 6. An adult should choose and review an appropriate activity for younger children.')


BALANCES = ('Balanced', 'More household', 'More gardening', 'More farm', 'More food', 'Use available content')


def group_weights(names, balance):
    if balance not in BALANCES: raise ValueError('Choose a supported theme balance.')
    keywords = {'More household': ('home','household'), 'More gardening': ('garden',),
                'More farm': ('farm','rural'), 'More food': ('food','baking')}.get(balance, ())
    return {name: (3 if any(re.search(r'\b' + term + (r'\b' if term == 'home' else ''), name.casefold().replace('_', ' ')) for term in keywords) else 1) for name in names}


def allocation_targets(names, total, balance='Balanced'):
    import math
    weights=group_weights(names,balance)
    return {name: math.ceil(total * weight / sum(weights.values())) for name,weight in weights.items()}
