from __future__ import annotations

from word_intelligence.pipeline import load_taxonomy
from word_intelligence.topic_routing import BUILT_IN_TOPIC_ALIASES


def test_phase5_legacy_theme_labels_resolve_to_reviewed_current_topics():
    taxonomy = load_taxonomy(".")
    for label, target_id in BUILT_IN_TOPIC_ALIASES.items():
        assert taxonomy.resolve(label) == target_id


def test_phase5_aliases_do_not_create_new_word_pool_or_claim_capacity():
    taxonomy = load_taxonomy(".")
    alias = "Cats, Dogs & Happy Pets"
    target = taxonomy.resolve(alias)
    assert target == "pets_animal_care"
    assert alias in taxonomy.topics[target].aliases
