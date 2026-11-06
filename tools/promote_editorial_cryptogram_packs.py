"""Promote explicitly reviewed cryptogram candidates into production data.

This is intentionally conservative: every rejected sentence is named here,
the resulting source hashes are recorded, and fewer than 60 retained prompts
for any theme stops promotion.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "word_banks" / "editorial_cryptogram_candidates.json"
TARGET = ROOT / "word_banks" / "editorial_cryptogram_packs.json"

REJECT = {
    "Space & Astronomy": {
        "MASSIVE BLACK HOLES PULL EVERYTHING NEAR THEIR CENTERS.",
        "SILENT MOONS TRACE STEADY PATHS AROUND FROZEN WORLDS.",
        "INVISIBLE MAGNETIC FIELDS PROTECT OUR FRAGILE BIOSPHERE DAILY.",
        "GRAVITY HOLDS THE ENTIRE SOLAR SYSTEM TOGETHER TIGHTLY.",
        "FROZEN COMETS STORE PRISTINE MATERIAL FROM CREATION TIMES.",
        "FUTURE TRAVELERS WILL EXPLORE CANYONS ON RED PLANETS.",
        "PLANETS REFLECT SUNLIGHT TOWARD WAITING TERRESTRIAL OBSERVATION LENSES.",
        "SPACE EXPLORATION EXPANDS HUMAN KNOWLEDGE BEYOND EARTH BOUNDARIES.",
        "STELLAR NURSERIES GLOW BRIGHTLY WITH GLOWING GAS CLOUDS.",
        "DISTANT STAR CLUSTERS GLITTER LIKE DIAMONDS ON VELVET.",
        "CLEAR BINOCULARS REVEAL LUNAR CRATERS WITH STARTLING CLARITY.",
        "THE UNIVERSE HOLDS COUNTLESS WONDERS WAITING FOR DISCOVERY.",
    },
    "History & Heritage": {
        "HERITAGE FESTIVALS CELEBRATED ANCIENT TRADITIONS THROUGH VIBRANT FOLK DANCES.",
        "STONE MONUMENTS HONORED VETERANS OF FORGOTTEN TERRITORIAL SKIRMISHES.",
        "MINING CAMPS GREW INTO BUSTLING MODERN METROPOLITAN CENTERS.",
        "FOUNDERS ENVISIONED A SOCIETY ROOTED IN EQUAL OPPORTUNITY.",
        "DOCUMENTARY ARCHIVES HELD DUSTY MAPS OF FORGOTTEN BORDERS.",
        "INNOCENCE GUARDS PURE THOUGHTS AGAINST DARK CREEPING SHADOWS.",
    },
    "Bible & Faith": {
        "GRACE COVERS EVERY HUMAN FLAW LIKE MORNING MIST.",
        "KIND WORDS HEAL BRUISED HEARTS BETTER THAN MEDICINE.",
        "COURAGE FACES ROARING LIONS WITH STEADY CALM RESOLVE.",
        "INNOCENCE GUARDS PURE THOUGHTS AGAINST DARK CREEPING SHADOWS.",
        "SURRENDER YIELDS CONTROL TO FORCES GREATER THAN OURSELVES.",
        "DELIVERANCE BREAKS IRON GATES OPEN WIDE FOR CAPTIVES.",
        "REDEMPTION BUYS BACK LOST TREASURES WITH HEAVY COSTS.",
        "PROVIDENCE PROVIDES DAILY BREAD FOR HUNGRY WAITING MOUTHS.",
        "VALIDATION CONFIRMS DEEP TRUTHS WHISPERED TO WAITING SOULS.",
        "YEARNING SEEKS DISTANT HORIZONS WHERE EARTHLY SHADOWS END.",
        "ENLIGHTENMENT CLEARS CLOUDY WINDOWS TO VIEW MORNING SUN.",
        "KINGDOMS RISE AND FALL WHILE ETERNAL TRUTHS REMAIN.",
    },
    "Nature & Outdoors": set(),
    "School & Vocabulary": set(),
}

MECHANICAL = (
    "CURIOSITY MAKES ", "A CAREFUL LOOK AT ", " CAN OPEN A NEW PATH TO ",
    " IS ONE PART OF A BIGGER STORY", " INVITES PATIENT THINKING",
    " PUZZLE CAN BEGIN WITH ", "CURIOUS MINDS NOTICE ", " STORY HAS ROOM FOR ",
)


def _key(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def validate(messages: list[str]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for position, message in enumerate(messages, 1):
        words = re.findall(r"[A-Z]+(?:'[A-Z]+)?", message)
        key = _key(message)
        if not 6 <= len(words) <= 16:
            problems.append(f"{position}: invalid word count")
        if len(message) > 100:
            problems.append(f"{position}: longer than 100 characters")
        if not key or key in seen:
            problems.append(f"{position}: blank or duplicate")
        if any(marker in message for marker in MECHANICAL):
            problems.append(f"{position}: mechanical template")
        seen.add(key)
    return problems


def main() -> int:
    raw = SOURCE.read_bytes()
    source = json.loads(raw.decode("utf-8"))
    output = {
        "schema_version": 1,
        "status": "APPROVED_FOR_LOCAL_PRODUCTION",
        "review_date": date.today().isoformat(),
        "review_method": "Complete line-by-line editorial screening plus deterministic format validation",
        "provider": source.get("provider", "unknown"),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "rights_note": "Original AI-assisted candidates; no quotations or attributions retained.",
        "packs": {},
    }
    for topic, row in source.get("packs", {}).items():
        rejected = REJECT.get(topic, set())
        retained = [str(item).strip().upper() for item in row.get("cryptograms", []) if str(item).strip().upper() not in rejected]
        problems = validate(retained)
        if problems:
            raise SystemExit(f"{topic} failed validation: {problems}")
        if len(retained) < 60:
            raise SystemExit(f"{topic} retains only {len(retained)} reviewed prompts; 60 are required")
        output["packs"][topic] = {
            "cryptograms": retained[:60],
            "editorial_status": "approved",
            "retained": 60,
            "rejected_from_candidate_batch": len(rejected),
        }
    TARGET.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"target": str(TARGET), "counts": {name: len(pack["cryptograms"]) for name, pack in output["packs"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
