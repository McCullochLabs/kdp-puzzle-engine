"""Bounded non-Sudoku plans for the existing chat creation transaction.

This adapter supplies family-aware immutable plans, not another generator,
worker, catalog or approval service. The owning chat route dispatches here and
continues to use studio_chat_creation's exact-plan confirmation and worker.
"""
from dataclasses import asdict, dataclass, field
import re
import secrets
import uuid

from .studio_chat_creation import ChatBookPlan, _numeric_request

SUPPORTED_KINDS = ('Cryptogram', 'Word Scramble + Trivia', 'Mixed Brain Games')
_KIND_PATTERNS = {
    'Cryptogram': r'\bcryptograms?\b',
    'Word Scramble + Trivia': r'\b(?:word[ -]+)?scrambles?(?:\s*(?:\+|and|&)\s*trivia)?\b',
    'Mixed Brain Games': r'\bmixed\s+(?:brain\s+games?|puzzles?|books?)\b',
}
_THEME_ALIASES = {
    'general': 'General Starter', 'general knowledge': 'General Knowledge & Curiosity',
    'space': 'Space & Astronomy', 'astronomy': 'Space & Astronomy',
    'garden': 'Garden & Growing', 'gardening': 'Garden & Growing',
    'nature': 'Nature & Outdoors', 'travel': 'Travel & Adventure',
    'road trip': 'Road Trips & Highways', 'road trips': 'Road Trips & Highways',
    'winter holidays': 'Holidays & Seasons', 'holidays': 'Holidays & Seasons',
    'pets': 'Pets & Animal Life', 'history': 'History & Heritage',
    'food': 'Food & Home', 'school': 'School & Vocabulary', 'bible': 'Bible & Faith',
}


@dataclass(frozen=True)
class StudioChatBookPlan(ChatBookPlan):
    """Same serialized fields as the shared transaction's existing plan."""
    kind: str = 'Cryptogram'

    @property
    def subtitle(self):
        suffix = {
            'Cryptogram': 'Code-Breaking Puzzles with Complete Solutions',
            'Word Scramble + Trivia': 'Word Scrambles with Fact Clues and Answers',
            'Mixed Brain Games': 'Sudoku, Cryptograms and Word Scrambles with Fact Clues and Complete Answers',
        }
        return f'{self.count} {suffix[self.kind]}'


def _request_without_title(request):
    named = list(re.finditer(r'\b(?:called|titled)\s+["“]([^"”]+)["”]', request, re.I))
    outside = request
    for match in reversed(named):
        outside = outside[:match.start()] + ' ' + outside[match.end():]
    if re.search(r'\b(?:called|titled)\b', outside, re.I) or len(named) > 1:
        raise ValueError('Use one title in quotation marks after called or titled.')
    if not named:
        return request, None
    match = named[0]
    title = match.group(1).strip()
    if not 1 <= len(title) <= 110 or any(ord(c) < 32 for c in title):
        raise ValueError('Use a title of 1 to 110 printable characters.')
    return request[:match.start()] + ' ' + request[match.end():], title


@dataclass(frozen=True)
class CryptogramTypographyChatBookPlan(StudioChatBookPlan):
    plan_schema_version: int = 3
    typography_config: dict = field(default_factory=dict)

    def __post_init__(self):
        from .cryptogram_typography import CryptogramTypography
        if type(self.plan_schema_version) is not int or self.plan_schema_version != 3 or self.kind != 'Cryptogram':
            raise ValueError('Unsupported Cryptogram creation typography version or family.')
        CryptogramTypography.from_dict(self.typography_config)

    @property
    def typography(self):
        from .cryptogram_typography import CryptogramTypography
        return CryptogramTypography.from_dict(self.typography_config)


def check_family_content(plan):
    """Use the same checked library and safety buffer as the guided studio."""
    import puzzle_book_studio as studio
    checked, detail, capacity = studio.content_check(plan.kind, plan.topic)
    # Preserve the guided studio's stricter reviewed-library buffer as well as
    # the package builder's actual consumed-content requirement for Mixed.
    required = max(studio.buffered_capacity_needed(plan.count),
                   studio.required_content_for_book(plan.kind, plan.count))
    if not checked or capacity < required:
        raise ValueError(f'The {plan.topic} library is not ready for this plan: '
                         f'{required} reviewed entries are required; {capacity} are available. {detail}')
    studio.validate_scramble_promise(plan.kind, plan.topic, plan.title, plan.subtitle)


def studio_family_chat_plan(request, intent, *, draft_id=None):
    """Derive supported settings from original text, never model-filled fields."""
    from .studio_assistant import guide_request, requested_book_topic
    import puzzle_book_studio as studio
    if not isinstance(request, str) or not request.strip() or len(request) > 1000:
        raise ValueError('Use a book request of 1 to 1000 characters.')
    if any(ord(c) < 32 for c in request):
        raise ValueError('Use a single printable book request.')
    if getattr(intent, 'action', None) != 'create_book' or getattr(intent, 'kind', None) not in SUPPORTED_KINDS:
        raise ValueError('This route supports explicit new Cryptogram, Word Scramble + Trivia or Mixed Brain Games books.')
    if getattr(intent, 'kind', None)=='Cryptogram':
        from .studio_chat_creation import _font_creation_suffix
        from .cryptogram_typography import CryptogramTypography
        parsed=_font_creation_suffix(request,CryptogramTypography)
        if parsed:
            clean_request,config=parsed
            base=studio_family_chat_plan(clean_request,guide_request(clean_request),draft_id=draft_id)
            values=asdict(base);values['request']=request
            return CryptogramTypographyChatBookPlan(**values,typography_config=config.to_dict())
    clean, named_title = _request_without_title(request)
    explicit = guide_request(clean)
    if explicit.action != 'create_book' or explicit.kind != intent.kind:
        raise ValueError('State the new puzzle-book family explicitly; model/context guesses cannot create it.')
    kind = explicit.kind
    if not re.search(_KIND_PATTERNS[kind], clean, re.I):
        raise ValueError('State the supported puzzle-book family explicitly.')
    if kind != 'Mixed Brain Games' and (re.search(r'\bsudoku\b', clean, re.I) or
            any(re.search(pattern, clean, re.I) for family, pattern in _KIND_PATTERNS.items() if family != kind)):
        raise ValueError('Choose one puzzle family, or request Mixed Brain Games explicitly.')
    if re.search(r'\b(?:large[ -]print|seniors?|kids?|children|teens?|ages?|beginners?|font|bleed|hardcover|paperback|landscape|portrait|trim|signature\s+edition|numbers?[- ]only|only numbers?)\b|\b\d+\s*[x×]\s*\d+', clean, re.I):
        raise ValueError('This direct route uses the standard 8.5 × 11 layout. Requested reader, edition, print or symbol variants need the guided plan.')
    if re.search(r'\b(?:covers?|colou?rs?|author|by|only|classic|bonus(?:es)?|interior\s+style|title\s+page|(?:without|no|omit|exclude)\s+(?:answers?|solutions?)|answerless|separate\s+(?:trivia|quiz)|standalone\s+(?:trivia|quiz))\b', clean, re.I):
        raise ValueError('This route uses the shown default author, existing automatic approved cover, layout and complete answers. Requested overrides need the guided plan.')
    counts, pages, requested_seed = _numeric_request(clean)
    if pages:
        raise ValueError('Exact page targets are not supported for these layouts; request a puzzle count. Actual pages are checked after generation.')
    if len(set(counts)) > 1:
        raise ValueError('Specify one puzzle count.')
    count = int(counts[0]) if counts else int(studio.DEFAULTS[kind][2])
    if not 24 <= count <= 150:
        raise ValueError('This production route supports 24 to 150 puzzles.')
    settings_text = re.sub(_KIND_PATTERNS[kind], ' ', clean, flags=re.I)
    if re.search(r'\b(?:medium|intermediate|expert|very\s+hard|challenging)\b', settings_text, re.I):
        raise ValueError('That difficulty claim is unsupported. Mixed books support Easy, Hard or Mixed for Sudoku only; the two word families are not rated.')
    levels = [level for level in ('Easy', 'Hard', 'Mixed')
              if re.search(r'\b' + level + r'\b', settings_text, re.I)]
    if kind in ('Cryptogram', 'Word Scramble + Trivia'):
        if levels or re.search(r'\bdifficulty\b', settings_text, re.I):
            raise ValueError('Cryptograms and word scrambles are not difficulty-rated. Remove the difficulty request or use the guided plan.')
        difficulty = studio.DEFAULTS[kind][3]
    else:
        if len(levels) > 1 or re.search(r'\bstandard\s+difficulty\b', settings_text, re.I):
            raise ValueError('Choose Easy, Hard or Mixed for the Sudoku section.')
        if re.search(r'\b(?:easy|hard|mixed)\s+(?:cryptograms?|(?:word\s+)?scrambles?|trivia)\b', settings_text, re.I):
            raise ValueError('Only the Sudoku section is difficulty-rated; the word families are not rated.')
        difficulty = levels[0] if levels else studio.DEFAULTS[kind][3]
    # Remove only settings already validated, then use the shared literal-topic
    # parser. This does not allow a model to silently replace an unknown topic.
    topic_request = re.sub(r'\b(?:with\s+)?seed\b(?:\s*[:=]\s*|\s+)\S+', '', clean, flags=re.I)
    topic_request = re.sub(r'\b(?:easy|hard|standard|mixed)\s+difficulty\b', '', topic_request, flags=re.I)
    topic_request = re.sub(r'\b(?:with\s+)?\d+[ -]*puzzles?\b', '', topic_request, flags=re.I)
    # A numeral without a recognized count/seed unit must not be ignored.
    if re.search(r'\d', topic_request):
        raise ValueError('Write settings as an unsigned puzzle count or seed.')
    raw_topic = requested_book_topic(re.sub(r'\bscrambles\b', 'scramble', topic_request, flags=re.I)).strip()
    topic = next((name for name in studio.AVAILABLE_THEMES if name.casefold() == raw_topic.casefold()),
                 _THEME_ALIASES.get(raw_topic.casefold())) if raw_topic else 'General Starter'
    if not topic:
        raise ValueError(f'The topic {raw_topic!r} has no supported checked design here. Choose an existing theme; it will not be replaced silently.')
    residue = re.sub(_KIND_PATTERNS[kind], ' ', topic_request, flags=re.I)
    if kind == 'Mixed Brain Games':
        residue = re.sub(r'\b(?:sudoku|cryptograms?|(?:word\s+)?scrambles?(?:\s*(?:and|\+)\s*trivia)?)\b', ' ', residue, flags=re.I)
    if raw_topic:
        residue = re.sub(r'\b' + r'\s+'.join(map(re.escape, raw_topic.split())) + r'\b', ' ', residue, flags=re.I)
    residue = re.sub(r'\b(?:create|make|build|want|new|can|could|would|you|i|me|please|a|an|the|book|books|puzzle|puzzles|with|and|about|on|themed|around|easy|hard|mixed|standard|difficulty|complete|full|answers|solutions|fact|clues)\b', ' ', residue, flags=re.I)
    if re.search(r'[^\s.,!?\"“”\'’&+\-]', residue):
        raise ValueError('The request contains unsupported settings. Use one supported family, theme, puzzle count, seed and optional quoted title; other variants need the guided plan.')
    identity = draft_id or uuid.uuid4().hex
    if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{32}', identity):
        raise ValueError('Invalid creation draft identity.')
    title = named_title or f'{topic} {kind} — {identity[:8]}'
    seed = requested_seed if requested_seed is not None else secrets.randbelow(2**31 - 1) + 1
    if not 1 <= seed < 2**31:
        raise ValueError('Seed must be from 1 to 2147483647.')
    plan = StudioChatBookPlan(identity, request, title, topic, count, difficulty, seed, None, kind=kind)
    check_family_content(plan)
    return plan


def validate_saved_family_plan(saved):
    """Reconstruct and recheck a saved family plan before confirm or creation."""
    from .studio_assistant import AssistantIntent
    try:
        plan = CryptogramTypographyChatBookPlan(**saved['plan']) if 'plan_schema_version' in saved['plan'] else StudioChatBookPlan(**saved['plan'])
    except (KeyError, TypeError) as exc:
        raise ValueError('Saved creation parameters are incomplete or unsupported.') from exc
    if plan.kind not in SUPPORTED_KINDS or type(plan.count) is not int or type(plan.seed) is not int or not 1 <= plan.seed < 2**31:
        raise ValueError('Saved creation parameters are invalid.')
    expected = studio_family_chat_plan(plan.request, AssistantIntent(action='create_book', kind=plan.kind), draft_id=plan.draft_id)
    expected_data = asdict(expected)
    if _numeric_request(_request_without_title(plan.request)[0])[2] is None:
        expected_data['seed'] = plan.seed
    if asdict(plan) != expected_data:
        raise ValueError('Saved creation parameters do not match the original request.')
    return plan


def family_plan_text(plan):
    from .difficulty_claims import difficulty_description
    check_family_content(plan)
    detail = difficulty_description(plan.kind, plan.difficulty)
    if plan.kind == 'Mixed Brain Games':
        sudoku_count = plan.count // 3 + bool(plan.count % 3)
        crypto_count = plan.count // 3 + bool(plan.count % 3 > 1)
        split = f'{sudoku_count} Sudoku, {crypto_count} Cryptograms and {plan.count - sudoku_count - crypto_count} word scrambles with fact clues'
    else:
        split = f'{plan.count} ' + ('Cryptograms' if plan.kind == 'Cryptogram' else 'word scrambles with fact clues')
    return (f'Create {plan.title!r}: {split}, {plan.topic}. Difficulty: {detail}. '
            f'8.5 × 11 inches, existing automatic layout and approved-art routing. Author: {plan.author}. '+
            (f'Text fonts: puzzles {plan.typography.puzzle_font_pt:g} pt, solutions {plan.typography.solution_font_pt:g} pt. ' if plan.typography else '')+
            'Actual page count is measured after generation. The existing checked-library, artwork and production gates apply. '
            'Create this book confirms this exact plan and starts local generation; nothing is published.')
