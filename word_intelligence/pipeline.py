"""End-to-end intelligence pipeline runner.

One entry point used by the GUI, future CLI and validation probes so the
classification flow stays identical everywhere:

    build taxonomy -> build store -> prepare indexes -> classify -> stats
"""

from __future__ import annotations

import json
from pathlib import Path

from .ambiguity import AmbiguityRegistry, scan_for_ambiguity
from .analysis import coverage_summary
from .classifier import Classifier, RunStats, scope_records
from .store import DEFAULT_STATE_DIR, WordIntelligenceStore, _load_json
from .taxonomy import TopicTaxonomy


def load_taxonomy(project_root=".") -> TopicTaxonomy:
    bank = _load_json(Path(project_root) / "word_banks"
                      / "Guided_Builder_Master_Word_Bank.json") or {}
    from .editorial_overlay import merge_master_bank
    bank = merge_master_bank(bank, project_root)
    taxonomy = TopicTaxonomy.from_master_bank(bank)
    # Shared legacy aliases must resolve in capacity checks and audits too,
    # not only inside the Book Planner's optional saved-route flow.
    from .topic_routing import apply_builtin_aliases
    apply_builtin_aliases(taxonomy)
    return taxonomy


def load_or_build_store(taxonomy, project_root=".", state_dir=DEFAULT_STATE_DIR):
    """Reuse the persisted store when present, else rebuild from sources."""
    try:
        store = WordIntelligenceStore.load(state_dir)
        from .editorial_overlay import apply_store_overlay
        apply_store_overlay(store, taxonomy, project_root)
        return store
    except FileNotFoundError:
        from .store import build_store
        store, report = build_store(project_root, taxonomy)
        from .editorial_overlay import apply_store_overlay
        report["editorial_overlay"] = apply_store_overlay(store, taxonomy, project_root)
        return store, report


def run_classification(store, taxonomy, catalog=None, themes_dir=None,
                       scope: str = "proven",
                       ambiguity_registry: AmbiguityRegistry | None = None,
                       detect_ambiguous: bool = True):
    """Classify the requested scope; returns (classifier, RunStats)."""
    registry = ambiguity_registry if ambiguity_registry is not None \
        else AmbiguityRegistry.load(DEFAULT_STATE_DIR)
    classifier = Classifier(store, taxonomy, registry)
    prepared = classifier.prepare(catalog=catalog, themes_dir=themes_dir)

    families = {cid: t.family for cid, t in taxonomy.topics.items()}
    detected = scan_for_ambiguity(store, families, registry) if detect_ambiguous else []

    stats = RunStats()
    records = sorted(scope_records(store, scope),
                     key=lambda r: r.normalized)
    classifier.classify_many(records, stats)
    summary = {
        "prepared": prepared,
        "scope": scope,
        "ambiguity_detected": detected,
        "stats": stats.to_dict(),
        "coverage": coverage_summary(store),
    }
    return classifier, stats, summary


def load_candidate_catalog(project_root=".") -> dict:
    return _load_json(Path(project_root) / "word_banks" / "source_data"
                      / "dwyl_topic_candidate_catalog.json") or {}


def save_store_quietly(store, state_dir=DEFAULT_STATE_DIR):
    try:
        path = store.save(state_dir)
        return {"saved": True, "path": str(path)}
    except OSError as exc:
        return {"saved": False, "error": str(exc)}


from functools import lru_cache


@lru_cache(maxsize=1)
def _family_wordsearch_runtime(root_path, stamps):
    from .editorial_overlay import merge_master_bank
    root = Path(root_path)
    bank = merge_master_bank(_load_json(root / 'word_banks' / 'Guided_Builder_Master_Word_Bank.json') or {}, root)
    taxonomy = load_taxonomy(root)
    loaded = load_or_build_store(taxonomy, root, root / 'word_banks' / 'word_intelligence')
    store = loaded[0] if isinstance(loaded, tuple) else loaded
    return bank, taxonomy, store


def prepare_family_wordsearch(project_root, topic, puzzle_count=48, words_per_puzzle=12, seed=42, *, minimum_puzzles=24, max_word_length=None, source_groups=(), reader="standard", balance="Balanced"):
    """Sort existing groups into checked puzzles without modifying source data."""
    import copy
    from .pool_builder import PoolRequest, build_word_pool, collect_eligible_words
    from .production_gate import evaluate_book
    from .editorial_overlay import merge_master_bank
    root = Path(project_root)
    sources = [root / 'word_banks' / name for name in ('Guided_Builder_Master_Word_Bank.json', 'word_intelligence/word_store.json', 'editorial_wordsearch_topic_overlay.json', 'family_group_content_reviews.json')]
    stamps = tuple((path.stat().st_mtime_ns, path.stat().st_size) if path.is_file() else None for path in sources)
    bank, taxonomy, store = _family_wordsearch_runtime(str(root.resolve()), stamps)
    aliases = {'space': 'Space & Astronomy', 'garden': 'Gardening',
               'garden & growing': 'Gardening', 'travel & adventure': 'Travel and Geography'}
    requested = str(topic).strip()
    from publishing.studio_theme_recipes import THEME_RECIPES
    selected_groups = tuple(source_groups) or THEME_RECIPES.get(requested.casefold(), ())
    if len(selected_groups) > 6:
        raise ValueError('Choose at most six source groups.')
    packs = bank.get('topic_packs') or {}
    pack = next((name for name in packs if name.casefold() == requested.casefold()), None)
    if selected_groups:
        target_names = [source for name in selected_groups for source in packs.get(name, [name])]
        if any(not taxonomy.resolve(name) for name in target_names):
            raise ValueError('One of the proposed groups is not in your library. Choose existing groups in Browse all topics; nothing was substituted.')
        targets = list(dict.fromkeys(taxonomy.resolve(name) for name in target_names))
    else:
        target = taxonomy.resolve(requested) or taxonomy.resolve(aliases.get(requested.casefold(), ''))
        targets = list(dict.fromkeys(filter(None, (taxonomy.resolve(name) for name in packs[pack])))) if pack else ([target] if target else [])
    if not targets:
        raise ValueError('Choose a topic from Browse all topics. The owner can add new topics in Advanced tools.')
    from publishing.studio_reader_profiles import reader_profile, word_suits_reader, check_reader_topic, allocation_targets, group_weights
    reader_profile(reader)
    check_reader_topic(requested, reader)
    for key in targets: check_reader_topic(taxonomy.topics[key].display_name, reader)
    quotas = allocation_targets(targets, puzzle_count, balance)
    weights = group_weights(targets, balance)
    profiles = bank.get('word_profiles') or {}
    views = {}
    source_topics = []
    for target_id in targets:
        definition = taxonomy.topics[target_id]
        sources = [name for name in definition.aliases if name in bank.get('topics', {})]
        source_topics.extend(sources)
        roles = collect_eligible_words(store, taxonomy, PoolRequest(target_id, 1, words_per_puzzle, seed=seed))
        eligible = set().union(*roles.values())
        # Require agreement with the independent profile evidence as well as
        # the store. Old broad imports must not silently override topic fit.
        eligible = {word for word in eligible if set(sources).intersection(profiles.get(word, {}).get('topics', []))
                    and (max_word_length is None or 2 <= len(word) <= max_word_length)
                    and word_suits_reader(word, reader)}
        view = copy.copy(store)
        view.records = {word: store.records[word] for word in eligible}
        views[target_id] = view
    available = set().union(*(set(view.records) for view in views.values()))
    multiple = 12 if minimum_puzzles >= 24 else 1
    count = min(puzzle_count, (len(available) // words_per_puzzle // multiple) * multiple)
    if count < minimum_puzzles:
        from publishing.studio_theme_recipes import group_unavailable
        raise ValueError(group_unavailable(requested, short=minimum_puzzles < 24))
    groups, used, warnings = [], set(), []
    allocations = {key: 0 for key in targets}
    while len(groups) < count:
        progressed = False
        for target_id in sorted(targets, key=lambda key: (allocations[key] / weights[key], -weights[key])):
            if len(groups) >= count: break
            if len(targets)>1 and balance != 'Use available content' and allocations[target_id] >= quotas[target_id]: continue
            view = views[target_id]
            if len(set(view.records) - used) < words_per_puzzle: continue
            pool = build_word_pool(view, taxonomy, PoolRequest(target_id, 1, words_per_puzzle,
                series_context=list(used), seed=seed + len(groups)))
            if pool.shortfall or not pool.puzzles: continue
            words = pool.puzzles[0]
            truth = evaluate_book(view, taxonomy, target_id, [words], required_puzzles=1, min_words_per_puzzle=words_per_puzzle)
            if not truth.ready:
                continue
            groups.append({'name': f"{taxonomy.topics[target_id].display_name} Puzzle {len(groups)+1:03d}",
                           'words': list(words), 'topic_id': target_id})
            allocations[target_id] += 1
            used.update(words); warnings.extend(truth.warnings)
            progressed = True
        if not progressed:
            if len(groups) < minimum_puzzles:
                raise ValueError('This reader profile and theme balance cannot fill a checked book. Choose a shorter activity pack, Standard readers, or Use available content.')
            warnings.append('The plan was shortened to honor theme balance and available checked words.')
            break
    final_count = (len(groups) // multiple) * multiple
    while len(groups) > final_count:
        key = max(allocations, key=lambda key: allocations[key] / weights[key])
        index = max(i for i, group in enumerate(groups) if group['topic_id'] == key)
        groups.pop(index); allocations[key] -= 1
    for index, group in enumerate(groups, 1):
        group['name'] = f"{taxonomy.topics[group['topic_id']].display_name} Puzzle {index:03d}"
    if len(targets)>1:
        for key in targets:
            if allocations[key] < quotas[key]: warnings.append(f'{taxonomy.topics[key].display_name}: {allocations[key]} puzzle(s) available; requested share was up to {quotas[key]}.')
    # Each source group is assessed against its own existing topic evidence.
    for target_id in targets:
        allocated = [group['words'] for group in groups if group['topic_id'] == target_id]
        if allocated:
            truth = evaluate_book(views[target_id], taxonomy, target_id, allocated, required_puzzles=len(allocated), min_words_per_puzzle=words_per_puzzle)
            if not truth.ready: raise ValueError('The topic check stopped this plan: ' + ' '.join(truth.errors[:2]))
            warnings.extend(truth.warnings)
    used_ids = list(dict.fromkeys(group['topic_id'] for group in groups))
    unavailable = [taxonomy.topics[key].display_name for key in targets if key not in used_ids]
    source_topics = [source for key in used_ids for source in taxonomy.topics[key].aliases if source in bank.get('topics', {})]
    if unavailable: warnings.append('Not included in this plan: ' + ', '.join(unavailable) + '. A short plan may have too few word activities for every group.')
    display = requested if selected_groups else (pack or taxonomy.topics[targets[0]].display_name)
    return {'topic': display, 'source_topics': list(dict.fromkeys(source_topics)), 'groups': groups,
            'words': [word for group in groups for word in group['words']],
            'warnings': list(dict.fromkeys(warnings)), 'seed': seed, 'unavailable_groups': unavailable, 'reader_profile': reader, 'theme_balance': balance,
            'group_counts': {taxonomy.topics[key].display_name: value for key,value in allocations.items() if value}}
