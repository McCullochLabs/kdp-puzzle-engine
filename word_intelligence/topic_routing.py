"""Saved, explainable topic-to-library connections for user-created topics."""
from __future__ import annotations

import json
from pathlib import Path

from .normalization import clean_surface
from .taxonomy import TopicDef


# Legacy saved themes use these buyer-friendly labels while the current Master
# Library uses concise canonical topic IDs.  This is routing metadata only:
# it does not add words, merge word pools, or make an under-capacity theme
# ready.  Keeping it here means every caller of ``load_taxonomy`` can resolve
# the same known labels before a plan, audit, or capacity check begins.
BUILT_IN_TOPIC_ALIASES: dict[str, str] = {
    "Birdwatching, Backyards & Wildlife": "birdwatching",
    "Cats, Dogs & Happy Pets": "pets_animal_care",
    "Christmas & Winter": "christmas",
    "Classic Literature & Reading": "books_reading_libraries",
    "Farm Animals & Country Life": "farm_country_rural_life",
    "Fishing, Lakes & Outdoor Adventure": "outdoor_adventure",
    "Food, Drinks & Kitchen Life": "baking_food",
    "Gardening and Homesteading": "gardening",
    "Halloween & Autumn": "halloween",
    "Holidays and Celebrations": "seasonal_celebrations",
    "Horses, Farm & Country Life": "farm_country_rural_life",
    "Pets & Animal Care": "pets_animal_care",
    "Reptiles, Amphibians & Wild Habitats": "nature",
    "Travel & Geography": "travel_geography",
    "Vehicles and Automotive": "vehicles_automotive",
    "World War II & American History": "world_war_ii_history",
}


def apply_builtin_aliases(taxonomy) -> None:
    """Attach reviewed legacy labels in memory without rewriting the library."""
    for label, target_id in BUILT_IN_TOPIC_ALIASES.items():
        if target_id not in taxonomy.topics:
            continue
        # Never displace an existing first-party taxonomy alias.
        if taxonomy.resolve(label) not in (None, target_id):
            continue
        taxonomy.alias_to_id[label] = target_id
        aliases = taxonomy.topics[target_id].aliases
        if label not in aliases:
            aliases.append(label)


class TopicRouter:
    """Suggests related canonical topics and stores only explicit user choices."""
    def __init__(self, root: Path | str, taxonomy) -> None:
        self.root, self.taxonomy = Path(root), taxonomy

    @property
    def path(self) -> Path:
        return self.root / "data" / "topic_routes.json"

    def load(self) -> dict[str, dict]:
        try:
            return dict(json.loads(self.path.read_text(encoding="utf-8-sig")).get("routes") or {})
        except (OSError, json.JSONDecodeError):
            return {}

    def suggestions(self, topic: str) -> list[str]:
        key = clean_surface(topic)
        if key == "SUMMERACTIVITIES":
            preferred = ("outdoor_adventure", "weather_climate", "coastal_lake_river_life", "travel_geography", "sports_hobbies")
            return [item for item in preferred if item in self.taxonomy.topics]
        tokens = set(key.split())
        scored = []
        for item, definition in self.taxonomy.topics.items():
            overlap = len(tokens & set(clean_surface(definition.display_name).split()))
            if overlap:
                scored.append((overlap, item))
        return [item for _, item in sorted(scored, reverse=True)[:5]]

    def save(self, topic: str, related_ids: list[str]) -> None:
        routes = self.load(); route_id = "_".join(str(topic).casefold().split())
        routes[route_id] = {"display_name": str(topic).strip(), "related_topics": [item for item in related_ids if item in self.taxonomy.topics]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema_version": 1, "routes": routes}, indent=2) + "\n", encoding="utf-8")

    def apply_saved(self) -> None:
        apply_builtin_aliases(self.taxonomy)
        for route_id, row in self.load().items():
            if route_id in self.taxonomy.topics:
                continue
            name = str(row.get("display_name") or route_id.replace("_", " ").title())
            related = [item for item in row.get("related_topics") or [] if item in self.taxonomy.topics]
            self.taxonomy.topics[route_id] = TopicDef(route_id, name, [name], related=related, description="Saved topic connection")
            self.taxonomy.alias_to_id[name] = route_id
            self.taxonomy.trusted_words[route_id] = set()
