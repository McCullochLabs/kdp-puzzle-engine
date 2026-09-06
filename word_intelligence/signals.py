"""Evidence signals A-I for word->topic classification.

Every signal produces explainable EvidenceItems; the classifier combines
them deterministically.  Nothing here mutates project data - signals read
the store/taxonomy/theme index and return evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from .normalization import clean_surface, split_tokens
from .records import (
    SIGNAL_ALIAS,
    SIGNAL_AMBIGUITY,
    SIGNAL_COOCCURRENCE,
    SIGNAL_FAMILIARITY,
    SIGNAL_LEXICON,
    SIGNAL_NEGATIVE,
    SIGNAL_PHRASE_TOKEN,
    SIGNAL_SOURCE_SUGGESTION,
    SIGNAL_TAXONOMY,
    SIGNAL_THEME_HISTORY,
    EvidenceItem,
)


# Signal point values (before diminishing-corroboration damping).
# Exact lexicon membership lands at 92: HIGH on its own (audited), crossing
# into VERY_HIGH only with corroborating familiarity/context - conservative
# by design so auto-linking stays precise.
POINTS_LEXICON_EXACT = 92.0
# Curated research suggestions are strong single-source evidence: two
# independent curated/published sources agreeing reaches VERY_HIGH, one
# alone lands in the audited HIGH band.
POINTS_ALIAS_IN_LEXICON = 60.0
POINTS_SOURCE_SUGGESTION = 70.0
POINTS_TAXONOMY_RELATION = 22.0
POINTS_PHRASE_TOKEN = 14.0
MAX_POINTS_PHRASE_TOKEN = 28.0
POINTS_THEME_HISTORY = 20.0
MAX_POINTS_THEME_HISTORY = 40.0
POINTS_SOURCE_SUGGESTION = 70.0
POINTS_TAXONOMY_RELATION = 22.0
POINTS_PHRASE_TOKEN = 14.0
MAX_POINTS_PHRASE_TOKEN = 28.0
POINTS_THEME_HISTORY = 18.0
MAX_POINTS_THEME_HISTORY = 36.0
POINTS_CO_OCCURRENCE = 10.0
MAX_POINTS_CO_OCCURRENCE = 30.0
BONUS_FAMILIARITY_STRONG = 6.0   # zipf >= 3.2
BONUS_FAMILIARITY_OK = 3.0       # zipf >= 2.6
PENALTY_NEGATIVE = -35.0

# Diminishing returns: strongest signal full value, later corroborating
# signals contribute a shrinking share (deterministic, order-independent
# because weights are sorted before applying).
CORROBORATION_FACTORS = (1.0, 0.65, 0.45, 0.30, 0.20, 0.15)
CORROBORATION_FACTOR_TAIL = 0.10


def damped_total(weights) -> float:
    """Sum weights with diminishing corroboration; negatives always full."""
    positives = sorted((w for w in weights if w > 0), reverse=True)
    negative_sum = sum(w for w in weights if w <= 0)
    total = 0.0
    for i, w in enumerate(positives):
        factor = CORROBORATION_FACTORS[i] if i < len(CORROBORATION_FACTORS) else CORROBORATION_FACTOR_TAIL
        total += w * factor
    return total + negative_sum


def familiarity_bonus(frequency) -> tuple[float, EvidenceItem | None]:
    if frequency is None:
        return 0.0, None
    if frequency >= 3.2:
        return BONUS_FAMILIARITY_STRONG, EvidenceItem(
            SIGNAL_FAMILIARITY, f"Common word (zipf {frequency:.1f})", BONUS_FAMILIARITY_STRONG)
    if frequency >= 2.6:
        return BONUS_FAMILIARITY_OK, EvidenceItem(
            SIGNAL_FAMILIARITY, f"Familiar word (zipf {frequency:.1f})", BONUS_FAMILIARITY_OK)
    return 0.0, None


class TopicSignalIndex:
    """Inverted indexes over topic lexicons + production theme history."""

    def __init__(self, store, taxonomy) -> None:
        self.store = store
        self.taxonomy = taxonomy
        self._token_to_topics: dict[str, set[str]] = {}
        self._exact_topics: dict[str, set[str]] = {}
        self._root_suggestions: dict[str, list[str]] = {}
        self.theme_word_counts: dict[str, dict[str, int]] = {}   # word -> {topic: n}
        self.themes_scanned = 0

        for cid, words in store.topic_lexicon.items():
            for word in words:
                self._exact_topics.setdefault(word, set()).add(cid)
                for token in split_tokens(word):
                    self._token_to_topics.setdefault(token, set()).add(cid)

    # ------------------------------------------------------------------

    def attach_root_suggestions(self, catalog: dict, resolve) -> int:
        """dwyl proven root suggestions (already screened zipf>=2.6 upstream)."""
        count = 0
        for raw_word, suggested in (catalog.get("root_suggestions") or {}).items():
            norm = clean_surface(raw_word)
            if not norm:
                continue
            cids = []
            for name in suggested if isinstance(suggested, list) else [suggested]:
                cid = resolve(name)
                if cid:
                    cids.append(cid)
            if cids:
                self._root_suggestions[norm] = cids
                count += 1
        return count

    def build_theme_index(self, themes_dir, max_files: int | None = None) -> int:
        """Count word usage inside VALIDATED themes (those carrying an explicit
        source_word_bank topic anchor).  Only anchored themes vote - freeform
        user files must not silently reshape the taxonomy."""
        themes_dir = Path(themes_dir)
        if not themes_dir.exists():
            return 0
        counts: dict[str, dict[str, int]] = {}
        scanned = 0
        for path in sorted(themes_dir.rglob("*.json")):
            if max_files is not None and scanned >= max_files:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            anchor = data.get("source_word_bank") or {}
            raw_topics = anchor.get("topics") or []
            if isinstance(raw_topics, str):
                raw_topics = [raw_topics]
            cids = [self.taxonomy.resolve(t) for t in raw_topics]
            cids = [c for c in cids if c]
            if not cids:
                continue
            scanned += 1
            seen_words: set[str] = set()
            for puzzle in data.get("puzzles") or []:
                for raw in puzzle.get("words") or []:
                    norm = clean_surface(raw)
                    if norm and norm not in seen_words:
                        seen_words.add(norm)
            for norm in seen_words:
                bucket = counts.setdefault(norm, {})
                for cid in cids:
                    bucket[cid] = bucket.get(cid, 0) + 1
        self.theme_word_counts = counts
        self.themes_scanned = scanned
        return scanned

    # ------------------------------------------------------------------
    # Candidate discovery
    # ------------------------------------------------------------------

    def candidate_topics(self, normalized: str) -> set[str]:
        """Topics worth scoring for this word (cheap superset)."""
        candidates: set[str] = set()
        candidates |= self._exact_topics.get(normalized, set())
        for neighbor in self.store.variant_neighbors(normalized):
            candidates |= self._exact_topics.get(neighbor, set())
        candidates |= set(self._root_suggestions.get(normalized, ()))
        for token in split_tokens(normalized):
            candidates |= self._token_to_topics.get(token, set())
            for neighbor in self.store.variant_neighbors(token):
                candidates |= self._token_to_topics.get(neighbor, set())
        for cid in self.theme_word_counts.get(normalized, {}):
            candidates.add(cid)
        return candidates

    # ------------------------------------------------------------------
    # Evidence collection for one (word, topic) pair
    # ------------------------------------------------------------------

    def evaluate(self, record, topic_id: str) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        norm = record.normalized
        lex_words = self.store.topic_lexicon.get(topic_id, set())

        if norm in lex_words:
            evidence.append(EvidenceItem(
                SIGNAL_LEXICON, f"Exact entry in '{self.taxonomy.display_name(topic_id)}' lexicon",
                POINTS_LEXICON_EXACT))
        else:
            for neighbor in sorted(self.store.variant_neighbors(norm)):
                if neighbor in lex_words:
                    evidence.append(EvidenceItem(
                        SIGNAL_ALIAS,
                        f"Spelling variant '{neighbor}' belongs to "
                        f"'{self.taxonomy.display_name(topic_id)}'", POINTS_ALIAS_IN_LEXICON))
                    break

        suggested = self._root_suggestions.get(norm, [])
        if topic_id in suggested:
            evidence.append(EvidenceItem(
                SIGNAL_SOURCE_SUGGESTION,
                "Listed as vocabulary candidate for this topic in curated research",
                POINTS_SOURCE_SUGGESTION))

        # Phrase tokens: multi-word items whose parts appear in the lexicon
        # ("NATIONALPARK": NATIONAL + PARK both common in National Parks words).
        tokens = split_tokens(norm)
        if len(tokens) > 1:
            matched = [t for t in tokens if t in self._token_to_topics.get(topic_id, ())]
            if matched:
                weight = min(POINTS_PHRASE_TOKEN * len(matched), MAX_POINTS_PHRASE_TOKEN)
                evidence.append(EvidenceItem(
                    SIGNAL_PHRASE_TOKEN,
                    f"Component word(s) {'/'.join(matched)} used in this topic",
                    weight))

        # Taxonomy relation: candidate is a declared neighbour of a topic the
        # word already matches exactly.
        related = self.taxonomy.related_closure(topic_id, hops=1)
        for other_cid in sorted(related):
            if norm in self.store.topic_lexicon.get(other_cid, ()):
                evidence.append(EvidenceItem(
                    SIGNAL_TAXONOMY,
                    f"Related to '{self.taxonomy.display_name(topic_id)}' via "
                    f"'{self.taxonomy.display_name(other_cid)}'", POINTS_TAXONOMY_RELATION))
                break

        history_counts = self.theme_word_counts.get(norm, {})
        history = history_counts.get(topic_id, 0)
        if history:
            # Specificity dampening (WI2 Phase 3): repetition inside themes
            # is only strong evidence when THIS topic dominates the word's
            # whole usage distribution.  A word sprinkled evenly across
            # unrelated themes carries almost no topical signal.
            total_uses = sum(history_counts.values()) or 1
            specificity = history / total_uses
            weight = min(POINTS_THEME_HISTORY * history,
                         MAX_POINTS_THEME_HISTORY) * specificity
            evidence.append(EvidenceItem(
                SIGNAL_THEME_HISTORY,
                f"Used in {history} published theme(s) for this topic "
                f"(specificity {specificity:.0%} of {total_uses})", weight))
            if total_uses >= 5 and specificity < 0.4:
                evidence.append(EvidenceItem(
                    SIGNAL_NEGATIVE,
                    f"Broadly distributed across themes "
                    f"({len(history_counts)} topics, dominance "
                    f"{specificity:.0%})",
                    -0.3 * MAX_POINTS_THEME_HISTORY))

        co_occurrence = 0
        for cid, hits in self.theme_word_counts.get(norm, {}).items():
            if cid != topic_id and hits and cid in related:
                co_occurrence += hits
        if co_occurrence:
            weight = min(POINTS_CO_OCCURRENCE * co_occurrence, MAX_POINTS_CO_OCCURRENCE)
            evidence.append(EvidenceItem(
                SIGNAL_COOCCURRENCE,
                f"Frequently appears beside this topic's family ({co_occurrence}x)",
                weight))

        _, fam = familiarity_bonus(record.frequency)
        if fam is not None:
            evidence.append(fam)

        return evidence


def detect_ambiguity(candidates: list[tuple[str, float]], families: dict[str, str]):
    """Flag when two UNRELATED topics both claim a word strongly.

    Returns (EvidenceItem | None, competing_topic_id | None).
    """
    if len(candidates) < 2:
        return None, None
    ordered = sorted(candidates, key=lambda pair: (-pair[1], pair[0]))
    (a, sa), (b, sb) = ordered[0], ordered[1]
    if sa >= 70 and sb >= 70 and families.get(a) != families.get(b):
        return EvidenceItem(
            SIGNAL_AMBIGUITY,
            f"Strongly matches unrelated topics too ('{b}')",
            0.0), b
    return None, None


def negative_evidence(record, topic_id: str, taxonomy) -> EvidenceItem | None:
    """Exclusion pressure: safety flags, rejected senses, blocked pairs."""
    if record.safety_review:
        return EvidenceItem(SIGNAL_NEGATIVE, "Word carries an exclusion flag", PENALTY_NEGATIVE)
    if record.trademark_review and topic_id not in getattr(record, "trademark_allowed_topics", set()):
        return EvidenceItem(SIGNAL_NEGATIVE, "Trademark-review term", PENALTY_NEGATIVE * 0.5)
    return None

