"""Multi-anchor compatibility engine (Word Intelligence 2.0).

The single-anchor audit flagged every word whose only topic memberships sat
outside the target topic plus its direct taxonomy neighbours.  Because the
master bank's ``related`` links are empty for every canonical topic, that
neighbourhood was always empty and tens of thousands of legitimately themed
words were reported as off_topic.

This layer adds the missing semantic bridge:

*   CURATED_ANCHOR_LINKS - hand-curated, symmetric pairs of canonical topics
    that legitimately share vocabulary (``gardening`` <-> ``garden_to_table``).
*   compatibility_closure() - target + taxonomy neighbours + curated anchors.
*   family_sibling_ids() - sibling topics inside the same family.

Compatibility NEVER makes an unrelated word usable: MINECRAFT still points
only at gaming topics and stays flagged inside a Christmas book.  It just
stops punishing words that were always thematically correct.
"""

from __future__ import annotations

# Curated symmetric anchor pairs over canonical topic ids from
# TopicTaxonomy.from_master_bank().  Unknown ids are ignored defensively so
# a renamed topic cannot break audits.
CURATED_ANCHOR_LINKS: dict[str, set[str]] = {
    "christmas": {"holidays", "seasonal_celebrations"},
    "thanksgiving": {"holidays", "seasonal_celebrations", "homesteading"},
    "halloween": {"holidays", "seasonal_celebrations", "homesteading"},
    "easter_spring": {"holidays", "seasonal_celebrations",
                      "gardening", "nature"},
    "holidays": {"seasonal_celebrations", "christmas",
                 "thanksgiving", "halloween"},
    "seasonal_celebrations": {"holidays", "christmas",
                              "thanksgiving", "halloween"},
    "gardening": {"nature", "garden_to_table", "signature_gardening",
                  "homesteading", "outdoor_adventure"},
    "signature_gardening": {"gardening", "garden_to_table", "nature",
                            "homesteading"},
    "garden_to_table": {"gardening", "signature_gardening", "homesteading",
                        "baking_food", "homesteading"},
    "homesteading": {"gardening", "garden_to_table",
                     "home_household"},
    "national_parks": {"forest_wildlife_outdoors", "outdoor_adventure", "nature",
                       "birdwatching", "us_geography_landmarks",
                       "travel_geography", "travel_road_trips_getaways"},
    "outdoor_adventure": {"national_parks", "forest_wildlife_outdoors", "nature",
                          "sports_hobbies", "travel_road_trips_getaways",
                          "weather_climate"},
    "nature": {"national_parks", "forest_wildlife_outdoors", "outdoor_adventure",
               "birdwatching", "ocean_life", "coastal_lake_river_life",
               "weather_climate", "gardening"},
    "birdwatching": {"nature", "forest_wildlife_outdoors", "national_parks",
                     "ocean_life", "coastal_lake_river_life"},
    "ocean_life": {"coastal_lake_river_life", "nature", "birdwatching",
                   "travel_geography"},
    "coastal_lake_river_life": {"ocean_life", "nature", "birdwatching"},
    "us_geography_landmarks": {"travel_geography", "travel_road_trips_getaways",
                               "national_parks", "american_history",
                               "american_heritage"},
    "travel_geography": {"us_geography_landmarks", "travel_road_trips_getaways",
                         "national_parks", "nature"},
    "travel_road_trips_getaways": {"travel_geography", "us_geography_landmarks",
                                   "vehicles_automotive", "outdoor_adventure",
                                   "national_parks"},
    "vehicles_automotive": {"travel_road_trips_getaways",
                            "careers_community_everyday_life"},
    "nostalgia_through_decades": {"pop_culture_entertainment",
                                  "video_games_gaming", "music_instruments",
                                  "arts_creativity_making"},
    "pop_culture_entertainment": {"nostalgia_through_decades",
                                  "video_games_gaming", "music_instruments"},
    "video_games_gaming": {"pop_culture_entertainment",
                           "nostalgia_through_decades"},
    "music_instruments": {"arts_creativity_making", "pop_culture_entertainment",
                          "nostalgia_through_decades"},
    "arts_creativity_making": {"music_instruments", "books_reading_libraries",
                               "pop_culture_entertainment"},
    "american_history": {"american_heritage", "world_war_ii_history",
                         "us_geography_landmarks", "bible_faith"},
    "world_war_ii_history": {"american_history", "american_heritage"},
    "american_heritage": {"american_history", "world_war_ii_history",
                          "us_geography_landmarks"},
    "bible_faith": {"faith_encouragement",
                    "american_history"},
    "faith_encouragement": {"bible_faith",
                            "mindfulness"},
    "mindfulness": {"wellness_self_care", "faith_encouragement",
                    "positive_parenting"},
    "wellness_self_care": {"mindfulness", "positive_parenting",
                           "careers_community_everyday_life"},
    "positive_parenting": {"wellness_self_care", "mindfulness",
                           "careers_community_everyday_life"},
    "dogs_pets": {"pets_animal_care", "cat_lover", "cats_pets"},
    "cats_pets": {"pets_animal_care", "cat_lover", "dogs_pets"},
    "cat_lover": {"cats_pets", "pets_animal_care", "dogs_pets"},
    "pets_animal_care": {"dogs_pets", "cats_pets", "cat_lover",
                         "homesteading"},
    "science_discovery": {"space_astronomy", "weather_climate", "nature"},
    "space_astronomy": {"science_discovery", "weather_climate"},
    "weather_climate": {"nature", "science_discovery", "outdoor_adventure",
                        "space_astronomy"},
    "baking_food": {"garden_to_table", "home_household", "homesteading"},
    "home_household": {"baking_food", "homesteading",
                       "careers_community_everyday_life"},
    "careers_community_everyday_life": {"general_interest", "home_household",
                                        "wellness_self_care"},
    "general_interest": {"careers_community_everyday_life",
                         "word_skills_brain_games"},
    "sports_hobbies": {"outdoor_adventure", "pop_culture_entertainment"},
    "books_reading_libraries": {"arts_creativity_making",
                                "word_skills_brain_games"},
    "word_skills_brain_games": {"books_reading_libraries", "general_interest",
                                "grade_vocabulary"},
}


_LINK_CACHE: dict[int, dict[str, set[str]]] = {}


def _normalise_links(taxonomy) -> dict[str, set[str]]:
    """Symmetric curated-link map restricted to ids the taxonomy knows."""
    key = id(taxonomy)
    cached = _LINK_CACHE.get(key)
    if cached is not None:
        return cached
    known = set(taxonomy.topics)
    sym: dict[str, set[str]] = {}
    for left, rights in CURATED_ANCHOR_LINKS.items():
        if left not in known:
            continue
        for right in rights:
            if right not in known or right == left:
                continue
            sym.setdefault(left, set()).add(right)
            sym.setdefault(right, set()).add(left)
    _LINK_CACHE[key] = sym
    return sym


def compatibility_closure(taxonomy, topic_id: str) -> set[str]:
    """Target + taxonomy neighbours + curated anchors (symmetric).

    Deterministic and side-effect free.  Unknown topic ids yield an empty
    set so callers fall back to their previous single-anchor behaviour.
    """
    start = taxonomy.resolve(topic_id)
    if not start:
        return set()
    out = {start}
    out |= taxonomy.related_closure(start, hops=1)
    out |= _normalise_links(taxonomy).get(start, set())
    return out


def family_sibling_ids(taxonomy, topic_id: str) -> set[str]:
    """Other topics inside the same family (weaker evidence than anchors)."""
    start = taxonomy.resolve(topic_id)
    if not start:
        return set()
    family = taxonomy.topics[start].family
    return {cid for cid, t in taxonomy.topics.items()
            if cid != start and t.family == family}


def anchor_reason(taxonomy, word_topic_id: str, target_id: str) -> str:
    """Human-readable explanation for why two topics are compatible."""
    links = _normalise_links(taxonomy)
    if word_topic_id in links.get(target_id, ()):
        return f"Curated anchor pair with '{taxonomy.display_name(word_topic_id)}'"
    return f"Related to '{taxonomy.display_name(target_id)}'"
