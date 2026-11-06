"""Generate review candidates for missing themed cryptogram packs.

This utility never changes the production content library. It writes a
separate candidate file that must pass local validation and editorial review
before a maintainer deliberately promotes it.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publishing.listing_intelligence import GeminiCredentials, _interaction_output_text

TOPICS = {
    "Space & Astronomy": "planets, moons, stars, galaxies, telescopes, observatories, astronauts, spaceflight, gravity, orbits, and careful sky observation. Keep every statement scientifically accurate and accessible to general readers.",
    "History & Heritage": "United States civic history, everyday heritage, public institutions, landmarks, documents, inventions, migration, and community life. Keep every statement accurate and nonpartisan.",
    "Bible & Faith": "broad Christian faith, prayer, worship, fellowship, service, hope, gratitude, wisdom, and biblical-era settings. Write original reflections, not Bible quotations or paraphrases of identifiable verses.",
    "Nature & Outdoors": "forests, wildlife, trails, rivers, mountains, weather, conservation, camping, observation, and responsible outdoor enjoyment.",
    "School & Vocabulary": "reading, vocabulary, writing, libraries, study habits, classroom curiosity, word roots, parts of speech, research, and learning confidence.",
}

MECHANICAL = (
    "CURIOSITY MAKES ", "A CAREFUL LOOK AT ", " CAN OPEN A NEW PATH TO ",
    " IS ONE PART OF A BIGGER STORY", " INVITES PATIENT THINKING",
    " PUZZLE CAN BEGIN WITH ", "CURIOUS MINDS NOTICE ", " STORY HAS ROOM FOR ",
    "THE STORY OF ", "CURIOUS MINDS KEEP LOOKING TOWARD ",
)


def request_pack(credentials: GeminiCredentials, topic: str, direction: str) -> list[str]:
    schema = {
        "type": "object",
        "properties": {"messages": {"type": "array", "items": {"type": "string"}}},
        "required": ["messages"], "additionalProperties": False,
    }
    prompt = (
        "Write 72 original, publication-safe cryptogram messages for one commercial puzzle book. "
        "Each must be a complete natural sentence of 6 to 16 words and no more than 100 characters. "
        "Vary sentence structure and openings; do not use fill-in templates, quotations, attributions, "
        "brands, people, political persuasion, statistics, disputed claims, or copyrighted wording. "
        "Every sentence must clearly fit the topic. Return JSON only.\n\n"
        f"TOPIC: {topic}\nEDITORIAL DIRECTION: {direction}"
    )
    body = {"model": credentials.model, "input": prompt, "store": False,
            "generation_config": {"max_output_tokens": 5000, "thinking_level": "minimal"},
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema}}
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": credentials.api_key, "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode())
    result = json.loads(_interaction_output_text(payload))
    return list(result.get("messages") or [])


def clean(messages: list[str]) -> tuple[list[str], list[str]]:
    accepted, rejected, seen = [], [], set()
    for raw in messages:
        message = " ".join(str(raw).strip().upper().split())
        normal = re.sub(r"[^A-Z]", "", message)
        words = re.findall(r"[A-Z]+(?:'[A-Z]+)?", message)
        reason = ""
        if not 6 <= len(words) <= 16: reason = "word_count"
        elif len(message) > 100: reason = "too_long"
        elif not normal or normal in seen: reason = "blank_or_duplicate"
        elif any(marker in message for marker in MECHANICAL): reason = "mechanical_template"
        elif re.search(r"[^A-Z0-9 ,.'!?-]", message): reason = "unsupported_character"
        if reason:
            rejected.append(f"{reason}: {message[:120]}")
        else:
            accepted.append(message); seen.add(normal)
    return accepted, rejected


def main() -> int:
    credentials = GeminiCredentials.load()
    if not credentials:
        raise SystemExit("Gemini credentials are not configured.")
    try:
        existing = json.loads((ROOT / "word_banks" / "editorial_cryptogram_candidates.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    result = {"schema_version": 1, "status": "REVIEW_REQUIRED", "provider": "Gemini",
              "note": "Candidates only. Do not use in production until editorial review is recorded.",
              "packs": dict(existing.get("packs", {}))}
    for topic, direction in TOPICS.items():
        saved = result["packs"].get(topic, {})
        if len(saved.get("cryptograms", [])) >= 60:
            continue
        collected, rejected = [], []
        for _attempt in range(2):
            batch, rejected_batch = clean(request_pack(credentials, topic, direction))
            rejected.extend(rejected_batch)
            known = {re.sub(r"[^A-Z]", "", item) for item in collected}
            collected.extend(item for item in batch if re.sub(r"[^A-Z]", "", item) not in known)
            if len(collected) >= 60:
                break
        result["packs"][topic] = {"cryptograms": collected[:72], "accepted": len(collected[:72]),
                                  "rejected": rejected, "required": 60}
    target = ROOT / "word_banks" / "editorial_cryptogram_candidates.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shortages = {topic: row["accepted"] for topic, row in result["packs"].items() if row["accepted"] < row["required"]}
    print(json.dumps({"target": str(target), "counts": {k: v["accepted"] for k, v in result["packs"].items()}, "shortages": shortages}, indent=2))
    return 1 if shortages else 0


if __name__ == "__main__":
    raise SystemExit(main())
