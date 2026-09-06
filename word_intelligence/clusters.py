"""Subtopic / concept-cluster engine for coherent puzzle building.

A broad topic (``national_parks``) is not one flat bucket: it contains
natural mini-themes (geology, wildlife, rangers, trails).  A puzzle drawn
from a single cluster feels intentional; twelve random words from the whole
topic feel like noise.

Clusters come from two sources, merged deterministically:

1.  SEED_CLUSTERS - curated word seeds per canonical topic.  Small on
    purpose: they anchor meaning without pretending to be complete.
2.  Lexicon/token overlap - trusted words of the topic are attached to the
    cluster whose seed tokens they share; everything else lands in
    ``general``.

Nothing here writes to project data.
"""

from __future__ import annotations

from .normalization import clean_surface, split_tokens

# Curated mini-theme seeds: canonical topic id -> {cluster -> seed words}.
# Keep seeds tight and unambiguous; the token-overlap pass does the rest.
SEED_CLUSTERS: dict[str, dict[str, list[str]]] = {
    "gardening": {
        "soil_compost": ["COMPOST", "MULCH", "SOIL", "FERTILIZER", "PEAT",
                         "MANURE", "TOPSOIL"],
        "planting": ["SEED", "SEEDLING", "SPROUT", "TRANSPLANT", "SOW",
                     "GERMINATE"],
        "tools": ["TROWEL", "PRUNER", "SHOVEL", "RAKE", "HOSE", "WATERINGCAN"],
        "flowers": ["ROSE", "TULIP", "DAISY", "PEONY", "LILAC"],
        "vegetables": ["TOMATO", "ZUCCHINI", "CARROT", "LETTUCE", "BEANS"],
        "garden_care": ["WEED", "PRUNE", "WATER", "HARVEST", "BLOOM"],
    },
    "christmas": {
        "decorations": ["ORNAMENT", "TINSEL", "LIGHTS", "WREATH", "GARLAND",
                        "BAUBLE"],
        "santa": ["SANTA", "ELF", "SLEIGH", "REINDEER", "CHIMNEY", "STOCKING"],
        "food": ["GINGERBREAD", "EGGNOG", "CANDYCANE", "COOKIES", "HAM"],
        "carols": ["CAROL", "CHOIR", "JINGLE", "HYMN"],
        "winter": ["SNOW", "SNOWFLAKE", "ICICLE", "FROST", "BLIZZARD"],
    },
    "ocean_life": {
        "mammals": ["WHALE", "DOLPHIN", "SEAL", "MANATEE", "OTTER"],
        "fish": ["TUNA", "SALMON", "ANGLERFISH", "SARDINE", "GROUPER"],
        "invertebrates": ["OCTOPUS", "JELLYFISH", "CRAB", "LOBSTER", "CLAM"],
        "reef": ["CORAL", "ANEMONE", "REEF", "SEAURCHIN"],
        "plants_habitat": ["KELP", "ALGAE", "SEAGRASS", "TIDEPOOL"],
    },
    "national_parks": {
        "trails": ["TRAIL", "HIKE", "HIKER", "BACKPACK", "MAP", "RANGER"],
        "geology": ["CANYON", "ARCH", "CLIFF", "MESA", "GEOLOGY", "SANDSTONE"],
        "wildlife": ["ELK", "BISON", "EAGLE", "BEAR", "WILDLIFE", "HABITAT"],
        "water": ["RIVER", "WATERFALL", "LAKE", "SPRING", "GLACIER", "CREEK"],
        "camping": ["CAMPGROUND", "TENT", "CABIN", "PICNIC", "FIRE", "TRAILHEAD"],
    },
    "space_astronomy": {
        "planets": ["PLANET", "MARS", "VENUS", "JUPITER", "SATURN", "NEPTUNE"],
        "stars_galaxies": ["STAR", "GALAXY", "NEBULA", "SUPERNOVA", "CONSTELLATION", "QUASAR"],
        "exploration": ["ROCKET", "ASTRONAUT", "ROVER", "MISSION", "LAUNCH", "SATELLITE"],
        "sky_tools": ["TELESCOPE", "OBSERVATORY", "LENS", "ORBIT", "ECLIPSE", "COMET"],
        "space_science": ["GRAVITY", "LIGHTYEAR", "VACUUM", "ASTEROID", "METEOR", "COSMIC"],
    },
    "vehicles_automotive": {
        "road_trip": ["HIGHWAY", "ROAD", "MAP", "TRIP", "MILE", "DESTINATION"],
        "vehicle_types": ["CAR", "TRUCK", "SUV", "VAN", "CAMPER", "MOTORHOME"],
        "parts": ["ENGINE", "WHEEL", "TIRE", "BRAKE", "STEERING", "MIRROR"],
        "care": ["WASH", "WAX", "SERVICE", "GARAGE", "REPAIR", "FUEL"],
        "outdoors": ["TRAILER", "TOWING", "OFFROAD", "CAMPING", "HITCH", "RACK"],
    },
    "nostalgia_through_decades": {
        "music": ["MUSIC", "RADIO", "RECORD", "CASSETTE", "CONCERT", "DANCE"],
        "fashion": ["FASHION", "JEANS", "JACKET", "SNEAKERS", "STYLE", "COLOR"],
        "home_life": ["KITCHEN", "TELEVISION", "PHONE", "CAMERA", "MAGAZINE", "TOY"],
        "school_fun": ["SCHOOL", "ARCADE", "GAME", "SUMMER", "FRIEND", "WEEKEND"],
    },
    "grade_school_vocabulary": {
        "language": ["WORD", "MEANING", "SENTENCE", "READ", "WRITE", "SPELL"],
        "science": ["SCIENCE", "ANIMAL", "PLANT", "WEATHER", "EARTH", "ENERGY"],
        "math": ["NUMBER", "FRACTION", "MEASURE", "PATTERN", "GRAPH", "SHAPE"],
    },
    "middle_school_vocabulary": {
        "language": ["CONTEXT", "SYNONYM", "ANTONYM", "INFERENCE", "PARAGRAPH", "ESSAY"],
        "science": ["ECOSYSTEM", "MATTER", "CLIMATE", "CELL", "FORCE", "CHEMICAL"],
        "social_studies": ["HISTORY", "CULTURE", "CITIZEN", "GOVERNMENT", "MAP", "TRADE"],
    },
    "high_school_vocabulary": {
        "language": ["ANALYZE", "ARGUMENT", "RHETORIC", "NUANCE", "THESIS", "EVIDENCE"],
        "science": ["BIOLOGY", "CHEMISTRY", "PHYSICS", "GENETICS", "VARIABLE", "THEORY"],
        "academic": ["RESEARCH", "DEBATE", "HYPOTHESIS", "ETHICS", "ECONOMY", "GEOMETRY"],
    },
}

# Fallback cluster when nothing matches (still better than dropping words).
GENERAL_CLUSTER = "general"

# Token cache for seed words, built lazily per topic id.
_seed_token_cache: dict[str, dict[str, set[str]]] = {}


def _seed_tokens(topic_id: str) -> dict[str, set[str]]:
    """Lowercased meaningful tokens per cluster for a topic."""
    cached = _seed_token_cache.get(topic_id)
    if cached is not None:
        return cached
    mapping: dict[str, set[str]] = {}
    for cluster, words in SEED_CLUSTERS.get(topic_id, {}).items():
        toks: set[str] = set()
        for word in words:
            norm = clean_surface(word)
            if len(norm) >= 4:
                toks |= set(split_tokens(norm))
        mapping[cluster] = toks - {"THE", "AND"}
    _seed_token_cache[topic_id] = mapping
    return mapping


def assign_clusters(store, taxonomy, topic_id: str,
                    words: list[str]) -> dict[str, str]:
    """Deterministic word -> cluster map for one topic's pool.

    Order of evidence:
      1. exact curated seed membership,
      2. shared-token overlap with a cluster's seeds (largest overlap wins,
         ties break alphabetically),
      3. ``general``.
    """
    cid = (taxonomy.resolve(topic_id) if taxonomy is not None else None) \
        or topic_id
    seeds = _seed_tokens(cid)
    out: dict[str, str] = {}
    for word in words:
        norm = clean_surface(word)
        if not norm:
            continue
        direct = next((c for c, ws in SEED_CLUSTERS.get(cid, {}).items()
                       if norm in {clean_surface(w) for w in ws}), None)
        if direct:
            out[norm] = direct
            continue
        toks = set(split_tokens(norm))
        best_cluster, best_hits = GENERAL_CLUSTER, 0
        for cluster in sorted(seeds):
            hits = len(toks & seeds[cluster])
            if hits > best_hits:
                best_cluster, best_hits = cluster, hits
        out[norm] = best_cluster if best_hits else GENERAL_CLUSTER
    return out


def clusters_overview(topic_id: str) -> list[dict]:
    """Static view of curated clusters for GUI/reporting."""
    cid_rows = []
    for cluster, words in SEED_CLUSTERS.get(topic_id, {}).items():
        cid_rows.append({"cluster": cluster, "seed_words": len(words)})
    return cid_rows
