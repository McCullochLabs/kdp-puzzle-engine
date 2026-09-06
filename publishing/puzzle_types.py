"""Small, lazy puzzle-type capability registry.

This is a compatibility layer around the established generators.  It does not
load a generator, initialise an AI provider, or introduce a plugin runtime.
Its job is to give planning, capability reporting, content intelligence, and
future UI discovery one truthful description of each puzzle format.

Display names remain backward-compatible with existing package records.  The
stable ``type_id`` is the value new integrations should store alongside the
existing display label.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


LIFECYCLE_STATES = frozenset({"planned", "experimental", "beta", "production_ready", "disabled", "deprecated"})


@dataclass(frozen=True)
class PuzzleTypeCapability:
    """Declarative facts for one format; service names are intentionally lazy."""
    type_id: str
    display_name: str
    category: str
    lifecycle: str
    aliases: tuple[str, ...] = ()
    generator_service: str = ""
    validator_service: str = ""
    solution_service: str = ""
    content_requirements: tuple[str, ...] = ()
    content_record_types: tuple[str, ...] = ()
    minimum_content_capacity: int | None = None
    difficulty_support: tuple[str, ...] = ("standard",)
    large_print_compatible: bool = True
    themed_content_compatible: bool = True
    digital_compatible: bool = True
    print_compatible: bool = True
    mixed_book_compatible: bool = False
    readiness_planning_supported: bool = True
    human_review_requirements: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()
    visual_content_supported: bool = False

    def __post_init__(self) -> None:
        if not self.type_id or self.type_id.casefold() != self.type_id or not self.type_id.replace("_", "").isalnum():
            raise ValueError("Puzzle type IDs must use lowercase letters, numbers, and underscores.")
        if self.lifecycle not in LIFECYCLE_STATES:
            raise ValueError(f"Unknown puzzle-type lifecycle: {self.lifecycle}")

    @property
    def production_available(self) -> bool:
        return self.lifecycle == "production_ready" and bool(self.generator_service and self.validator_service)

    @property
    def deterministic_solution_support(self) -> bool:
        return bool(self.solution_service)

    def to_dict(self) -> dict[str, object]:
        return {
            "type_id": self.type_id, "display_name": self.display_name,
            "category": self.category, "lifecycle": self.lifecycle,
            "aliases": list(self.aliases), "production_available": self.production_available,
            "generator_available": bool(self.generator_service),
            "validator_available": bool(self.validator_service),
            "solution_support": self.deterministic_solution_support,
            "content_requirements": list(self.content_requirements),
            "content_record_types": list(self.content_record_types),
            "minimum_content_capacity": self.minimum_content_capacity,
            "difficulty_support": list(self.difficulty_support),
            "large_print_compatible": self.large_print_compatible,
            "themed_content_compatible": self.themed_content_compatible,
            "digital_compatible": self.digital_compatible,
            "print_compatible": self.print_compatible,
            "mixed_book_compatible": self.mixed_book_compatible,
            "readiness_planning_supported": self.readiness_planning_supported,
            "human_review_requirements": list(self.human_review_requirements),
            "known_limitations": list(self.known_limitations),
            "visual_content_supported": self.visual_content_supported,
        }


class PuzzleTypeRegistry:
    """In-memory registry with explicit registration and safe unknown lookup."""
    def __init__(self, capabilities: Iterable[PuzzleTypeCapability] = ()) -> None:
        self._items: dict[str, PuzzleTypeCapability] = {}
        self._aliases: dict[str, str] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: PuzzleTypeCapability, *, replace: bool = False) -> PuzzleTypeCapability:
        current = self._items.get(capability.type_id)
        if current and not replace:
            raise ValueError(f"Puzzle type is already registered: {capability.type_id}")
        names = (capability.type_id, capability.display_name, *capability.aliases)
        for name in names:
            key = _key(name)
            owner = self._aliases.get(key)
            if owner and owner != capability.type_id and not replace:
                raise ValueError(f"Puzzle type alias already belongs to {owner}: {name}")
        if current:
            for key, owner in list(self._aliases.items()):
                if owner == capability.type_id:
                    del self._aliases[key]
        self._items[capability.type_id] = capability
        for name in names:
            self._aliases[_key(name)] = capability.type_id
        return capability

    def resolve(self, value: object) -> PuzzleTypeCapability | None:
        return self._items.get(self._aliases.get(_key(value), ""))

    def require(self, value: object) -> PuzzleTypeCapability:
        result = self.resolve(value)
        if result is None:
            raise ValueError(f"Unknown puzzle type: {value or '(blank)'}. Choose a registered puzzle type.")
        return result

    def all(self, *, include_nonproduction: bool = True) -> tuple[PuzzleTypeCapability, ...]:
        values = tuple(self._items.values())
        return values if include_nonproduction else tuple(item for item in values if item.production_available)

    def ids_for_readiness_ui(self) -> tuple[str, ...]:
        """Existing readiness UI values, derived from registered capabilities."""
        return tuple(item.type_id for item in self._items.values()
                     if item.production_available and item.readiness_planning_supported)


def _key(value: object) -> str:
    return " ".join(str(value or "").replace("_", " ").casefold().split())


REGISTRY = PuzzleTypeRegistry((
    PuzzleTypeCapability("word_search", "Word Search", "word", "production_ready",
        aliases=("word search", "word-search", "word find"), generator_service="wordsearch.generate",
        validator_service="wordsearch.validate", solution_service="wordsearch.solution_render",
        content_requirements=("themed_word_sets",), content_record_types=("word", "phrase"),
        minimum_content_capacity=576, difficulty_support=("easy", "standard", "challenging"), mixed_book_compatible=True,
        human_review_requirements=("topic fit", "rights review when flagged")),
    PuzzleTypeCapability("sudoku", "Sudoku", "logic", "production_ready",
        aliases=("symbol sudoku",), generator_service="sudoku.generate", validator_service="sudoku.unique_solution",
        solution_service="sudoku.solution_render", content_requirements=("algorithmic_grid",),
        difficulty_support=("easy", "standard", "challenging"), themed_content_compatible=False, mixed_book_compatible=True,
        human_review_requirements=("final print review",)),
    PuzzleTypeCapability("cryptogram", "Cryptogram", "word_logic", "production_ready",
        aliases=("cipher", "cryptograms"), generator_service="cryptogram.generate", validator_service="cryptogram.prompt_validate",
        solution_service="cryptogram.solution_render", content_requirements=("reviewed_prompts",),
        content_record_types=("cryptogram_prompt",), minimum_content_capacity=96,
        difficulty_support=("easy", "standard", "challenging"), mixed_book_compatible=True,
        human_review_requirements=("prompt originality", "topic fit")),
    PuzzleTypeCapability("scramble_trivia", "Word Scramble + Trivia", "word_trivia", "production_ready",
        aliases=("word scramble", "scramble trivia", "word scramble and trivia"), generator_service="scramble_trivia.generate",
        validator_service="scramble_trivia.answer_validate", solution_service="scramble_trivia.solution_render",
        content_requirements=("answers", "questions", "verified_facts"), content_record_types=("trivia",),
        minimum_content_capacity=96, difficulty_support=("easy", "standard", "challenging"), mixed_book_compatible=True,
        human_review_requirements=("factual verification", "topic fit")),
    PuzzleTypeCapability("mixed", "Mixed Brain Games", "mixed", "production_ready",
        aliases=("mixed brain games", "mixed puzzle", "mixed puzzles"), generator_service="mixed_brain_games.compose",
        validator_service="mixed_brain_games.component_validate", solution_service="mixed_brain_games.section_solutions",
        content_requirements=("component_recipes",), readiness_planning_supported=True,
        difficulty_support=("easy", "standard", "challenging"), mixed_book_compatible=False,
        human_review_requirements=("all included component formats must pass",),
        known_limitations=("Capacity is evaluated by the selected component formats, not as one interchangeable word pool.")),
    PuzzleTypeCapability("crossword", "Crossword", "word_logic", "planned",
        content_requirements=("answers", "clues", "grid"), content_record_types=("word", "phrase"),
        known_limitations=("No generator, clue validator, or deterministic solver is registered yet.")),
    PuzzleTypeCapability("word_fill_in", "Word Fill-In", "word", "planned",
        aliases=("fill in", "fill-in"), content_requirements=("word_bank", "grid"), content_record_types=("word", "phrase"),
        known_limitations=("No generator or placement validator is registered yet.")),
    PuzzleTypeCapability("missing_letters", "Missing Letters", "word", "planned",
        aliases=("missing vowels",), content_requirements=("word_sets",), content_record_types=("word", "phrase"),
        known_limitations=("No generator or answer validator is registered yet.")),
    PuzzleTypeCapability("anagram", "Anagram", "word", "planned",
        content_requirements=("answer_words",), content_record_types=("word", "phrase"),
        known_limitations=("No generator or answer validator is registered yet.")),
    PuzzleTypeCapability("word_ladder", "Word Ladder", "word_logic", "planned",
        content_requirements=("start_end_words", "valid_steps"), content_record_types=("word",),
        known_limitations=("No ladder generator or deterministic step verifier is registered yet.")),
    PuzzleTypeCapability("codeword", "Codeword", "code_logic", "planned",
        content_requirements=("answer_words", "code_mapping"), content_record_types=("word", "phrase"),
        known_limitations=("No codeword generator, validator, or solver is registered yet.")),
    PuzzleTypeCapability("logic_grid", "Logic Grid", "logic", "planned",
        content_requirements=("entities", "attributes", "clues", "solution"),
        known_limitations=("No clue generator or unique-solution solver is registered yet.")),
    PuzzleTypeCapability("number_search", "Number Search", "number", "planned",
        content_requirements=("number_sets", "grid"), known_limitations=("No generator or grid validator is registered yet.")),
    PuzzleTypeCapability("maze", "Maze", "visual", "planned",
        content_requirements=("geometry", "start_end", "path"), visual_content_supported=True,
        known_limitations=("No maze renderer or path validator is registered yet.")),
    PuzzleTypeCapability("spot_the_difference", "Spot-the-Difference", "visual", "planned",
        aliases=("spot the difference",), content_requirements=("image_assets", "difference_map"),
        visual_content_supported=True, known_limitations=("No image-pair renderer or difference-map validator is registered yet.")),
))


def resolve_puzzle_type(value: object) -> PuzzleTypeCapability | None:
    return REGISTRY.resolve(value)


def require_puzzle_type(value: object) -> PuzzleTypeCapability:
    return REGISTRY.require(value)


def registered_puzzle_types(*, include_nonproduction: bool = True) -> tuple[PuzzleTypeCapability, ...]:
    return REGISTRY.all(include_nonproduction=include_nonproduction)

