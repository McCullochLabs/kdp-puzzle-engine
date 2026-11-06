"""Read-only activity planning shared by non-Tk clients of the Studio."""
from dataclasses import asdict
from functools import lru_cache
import json
from pathlib import Path

from .activity_packs import ActivityPackPlan, FORMATS, WORDS_PER_PAGE, validate_plan
from .studio_reader_profiles import BALANCES, check_reader_topic, reader_profile


@lru_cache(maxsize=2)
def _bank_names(path, stamp):
    bank = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return tuple(sorted(set(bank.get('topics', {})) | set(bank.get('topic_packs', {})), key=str.casefold))


def available_pack_themes(root):
    path = Path(root) / 'word_banks' / 'Guided_Builder_Master_Word_Bank.json'
    stat = path.stat()
    return _bank_names(str(path.resolve()), (stat.st_mtime_ns, stat.st_size))


def validate_pack_request(data, root):
    required = {'title', 'theme', 'reader_profile', 'activity_count', 'formats', 'theme_balance'}
    if not isinstance(data, dict) or not required <= set(data) or set(data) - required - {'source_groups'}:
        raise ValueError('Send only the activity-pack choices shown in the form.')
    groups = data.get('source_groups', [])
    if (not isinstance(groups, list) or len(groups) > 6 or
            any(not isinstance(group, str) or group not in available_pack_themes(root) for group in groups) or
            len(set(groups)) != len(groups)):
        raise ValueError('Choose up to six existing source groups.')
    title, theme = data['title'], data['theme']
    if (not isinstance(title, str) or not title.strip() or len(title) > 100 or
            any(ord(char) < 32 for char in title)):
        raise ValueError('Choose a plain-text pack name of 1 to 100 characters.')
    if not isinstance(theme, str) or not theme.strip() or len(theme) > 60 or any(ord(c) < 32 for c in theme) or (theme not in available_pack_themes(root) and not groups):
        raise ValueError('Choose an existing theme from the library.')
    profile = data['reader_profile']
    if not isinstance(profile, str):
        raise ValueError('Choose a supported reader profile.')
    reader_profile(profile)
    check_reader_topic(title + ' ' + theme, profile)
    for group in groups:
        check_reader_topic(group, profile)
    if not isinstance(data['theme_balance'], str) or data['theme_balance'] not in BALANCES:
        raise ValueError('Choose a supported theme balance.')
    kinds = data['formats']
    if (not isinstance(kinds, list) or not 1 <= len(kinds) <= len(FORMATS) or
            any(not isinstance(kind, str) or kind not in FORMATS for kind in kinds) or len(set(kinds)) != len(kinds)):
        raise ValueError('Choose one or more different supported activities.')
    count = data['activity_count']
    if type(count) is not int or not len(kinds) <= count <= 24:
        raise ValueError('Choose up to 24 pages, with at least one page for each activity type.')
    return dict(data, title=title.strip(), formats=list(kinds))


def prepare_pack_request(data, root):
    """Select real checked vocabulary; never generate output or save a bank."""
    data = validate_pack_request(data, root)
    formats = data['formats']
    kinds = [formats[index % len(formats)] for index in range(data['activity_count'])]
    word_pages = max(kinds.count('Word Search'), kinds.count('Word Scramble'))
    selection = {'words': [], 'group_counts': {}, 'warnings': []}
    if word_pages:
        from word_intelligence.pipeline import prepare_family_wordsearch
        selection = prepare_family_wordsearch(root, data['theme'], word_pages, WORDS_PER_PAGE,
            minimum_puzzles=1, max_word_length=18, seed=42,
            reader=data['reader_profile'], balance=data['theme_balance'], source_groups=data.get('source_groups', ()))
        if len(selection['words']) < word_pages * WORDS_PER_PAGE:
            raise ValueError('This theme cannot fill all the requested word activities with checked words. Choose fewer pages, another reader setting or another theme.')
    plan = validate_plan(ActivityPackPlan(title=data['title'], theme=data['theme'],
        words=tuple(selection['words']), formats=tuple(formats),
        activity_count=data['activity_count'], seed=42,
        reader_profile=data['reader_profile'], theme_balance=data['theme_balance']))
    notes = []
    for warning in selection.get('warnings', []):
        if 'mini-theme' in warning or 'coherence' in warning:
            note = 'Review the finished pages for variety and topic fit; automatic word checks do not replace editorial review.'
        else:
            note = warning
        if note not in notes:
            notes.append(note)
    return {'plan': asdict(plan), 'word_count': len(plan.words),
            'word_pages_per_type': word_pages, 'group_counts': selection.get('group_counts', {}),
            'notes': notes, 'inference_calls': 0, 'generated': False}
