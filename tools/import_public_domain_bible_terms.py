"""Build a local, auditable Bible vocabulary source from Project Gutenberg.

The source text is public domain in the United States.  This tool stores only
normalized vocabulary and provenance, never quotations or verses.  It is a
one-time library maintenance tool; the book generator itself stays offline.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "word_banks" / "source_data" / "public_domain_kjv_terms.json"
SOURCE_URL = "https://www.gutenberg.org/files/30/30-0.txt"

# Ordinary connector words are not useful word-search entries, even when they
# occur in a Scripture text.  The retained words are still traceable directly
# to the public-domain KJV source and are used only in Bible/Faith books.
EXCLUDED = {
    "about", "above", "after", "again", "against", "also", "among", "another",
    "before", "being", "below", "between", "could", "every", "first", "found",
    "great", "hath", "have", "here", "into", "itself", "just", "know", "like",
    "made", "many", "might", "more", "most", "much", "must", "neither", "never",
    "only", "other", "ourselves", "over", "shall", "should", "some", "such",
    "than", "that", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "thing", "this", "those", "through", "thus", "unto", "upon",
    "very", "were", "what", "when", "where", "which", "while", "whom", "whose",
    "will", "with", "without", "would", "your", "yours", "yourself", "yourselves",
}


def _terms(text: str) -> list[str]:
    # Ignore Project Gutenberg's header/footer.  Those are useful licensing
    # records, but are never Bible vocabulary.
    start = text.find("Book 01 Genesis")
    end = text.find("*** END OF THE PROJECT GUTENBERG EBOOK")
    if start >= 0:
        text = text[start:end if end >= 0 else None]
    counts = Counter(word.casefold() for word in re.findall(r"[A-Za-z]+", text))
    selected = [
        word.upper() for word, count in counts.items()
        if count >= 2 and 4 <= len(word) <= 18 and word not in EXCLUDED
    ]
    return sorted(set(selected))


def main() -> None:
    with urlopen(SOURCE_URL, timeout=60) as response:
        text = response.read().decode("utf-8", "replace")
    terms = _terms(text)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "source_name": "Project Gutenberg — The King James Bible, Complete",
        "source_url": SOURCE_URL,
        "license_note": "Public domain in the USA; vocabulary-only extraction, no verses stored.",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entry_policy": "Words appear at least twice in the public-domain source; common connector words are excluded.",
        "terms": terms,
    }
    TARGET.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(terms)} public-domain Bible vocabulary entries to {TARGET}")


if __name__ == "__main__":
    main()
