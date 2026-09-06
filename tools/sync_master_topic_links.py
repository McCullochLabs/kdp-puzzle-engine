"""Apply the Master Library's approved multi-topic links to its topic pools.

This is deliberately conservative: it uses only ``related_topic_links`` that
already exist in the saved Master Library, adds only to existing topic keys,
and never removes a word.  A timestamped backup is kept beside the library.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def sync(path: Path, apply: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    topics = data.get("topics") if isinstance(data.get("topics"), dict) else {}
    links = data.get("related_topic_links") if isinstance(data.get("related_topic_links"), dict) else {}
    profiles = data.get("word_profiles") if isinstance(data.get("word_profiles"), dict) else {}
    word_groups = data.get("word_groups") if isinstance(data.get("word_groups"), dict) else {}
    topic_packs = data.get("topic_packs") if isinstance(data.get("topic_packs"), dict) else {}
    original = {name: {str(word).strip().upper() for word in words if str(word).strip()}
                for name, words in topics.items() if isinstance(words, list)}
    updated = {name: set(words) for name, words in original.items()}
    additions: dict[str, int] = {name: 0 for name in updated}
    linked_words = 0
    for word, names in links.items():
        normalized = str(word).strip().upper()
        if not normalized or not isinstance(names, list):
            continue
        attached = False
        for name in names:
            if name in updated and normalized not in updated[name]:
                updated[name].add(normalized); additions[name] += 1; attached = True
        if attached: linked_words += 1
    profile_words = 0
    # ``word_profiles`` is the Master Library's other approved route for
    # cross-topic membership.  These are prior classifier/review outcomes,
    # not raw dictionary guesses, so copying them makes the generator see
    # links that already exist elsewhere in the same local library.
    for word, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        normalized = str(word).strip().upper()
        names = list(profile.get("topics") or []) + list(profile.get("related_topics") or [])
        attached = False
        for name in names:
            if name in updated and normalized not in updated[name]:
                updated[name].add(normalized); additions[name] += 1; attached = True
        if attached: profile_words += 1
    group_words = 0
    # Only focused, buyer-recognizable production packs may fan out into
    # their documented source topics.  Broad library/grade-ladder packs are
    # intentionally excluded: applying them would make every grade or niche
    # look larger by borrowing unrelated vocabulary.
    allowed_packs = {
        "Animals & Pets", "Pets, Backyard Animals & Care", "Cats, Dogs & Happy Pets",
        "Backyard Birds & Nature", "Coastal & Ocean Adventure",
        "Garden to Table", "Garden, Flowers & Growing Things", "Gardening, Herbs & Homestead Living",
        "Holidays & Seasonal Fun", "Christmas, Winter & Cozy Traditions", "Halloween, Autumn & Harvest",
        "Thanksgiving, Harvest & Family", "Easter, Spring & New Beginnings",
        "American Heritage", "Presidents, History & Americana",
        "National Parks & Outdoors", "National Parks, Trails & Wild Places", "Outdoor Adventure, Parks & Trails",
        "Travel & World Discovery", "Travel, Road Trips & Weekend Getaways", "Family Road Trips & Travel",
        "Food, Baking & Kitchen", "Home, Cozy Living & Self Care", "Farm, Country & Rural Life",
        "Vehicles, Cars & Trucks", "Car Care, Parts & Repair", "Classic Cars, Muscle Cars & Car Shows", "RV, Camping & Off-Road", "Automotive Audio & Upgrades",
        "Bible, Faith & Encouragement", "Bible, Faith & Encouragement — Complete", "Faith & Encouragement",
        "Science, Space & Discovery", "Space for Kids & Teens", "Planets & Solar System", "Stargazing, Telescopes & Night Sky", "Space Missions, Rockets & Astronauts",
        "Weather, Climate & Storms", "Forests, Wildlife & Outdoor Escape", "Coastal, Lake & River Life", "US Geography, Parks & Landmarks",
    }
    for word, group_names in word_groups.items():
        normalized = str(word).strip().upper()
        if not normalized or not isinstance(group_names, list):
            continue
        attached = False
        for group in group_names:
            if group not in allowed_packs or group not in topic_packs:
                continue
            for name in topic_packs[group]:
                if name in updated and normalized not in updated[name]:
                    updated[name].add(normalized); additions[name] += 1; attached = True
        if attached: group_words += 1
    changed = {name: count for name, count in additions.items() if count}
    report = {"topics_changed": len(changed), "words_with_new_cross_links": linked_words,
              "total_new_topic_memberships": sum(changed.values()),
              "words_linked_from_profiles": profile_words,
              "words_linked_from_curated_packs": group_words,
              "largest_additions": sorted(changed.items(), key=lambda item: (-item[1], item[0]))[:25]}
    if apply:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.stem}.before_related_link_sync_{stamp}{path.suffix}")
        shutil.copy2(path, backup)
        data["topics"] = {name: sorted(words) for name, words in updated.items()}
        capacities = data.get("topic_capacities") if isinstance(data.get("topic_capacities"), dict) else {}
        for name, words in updated.items():
            current = capacities.get(name) if isinstance(capacities.get(name), dict) else {}
            current["unique_words"] = len(words)
            current["linked_from_related_topics"] = additions.get(name, 0)
            capacities[name] = current
        data["topic_capacities"] = capacities
        data["last_related_link_sync"] = {"at": datetime.now().isoformat(timespec="seconds"), **report}
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(path)
        report["backup"] = str(backup)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--apply", action="store_true")
    parser.add_argument("--path", type=Path, default=Path(__file__).resolve().parents[1] / "word_banks" / "Guided_Builder_Master_Word_Bank.json")
    args = parser.parse_args(); print(json.dumps(sync(args.path, args.apply), indent=2))
