"""Create a local U.S.-history vocabulary cache from public-domain sources.

Only normalized words and source provenance are stored.  The generated cache
is consumed only by the American History library, never as generic filler for
another niche.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "word_banks" / "source_data" / "public_domain_us_history_terms.json"
SOURCE_IDS = (20925, 22567, 23748, 22676, 22777, 24023)
EXCLUDED = {
    "about", "above", "after", "again", "against", "also", "among", "another",
    "before", "being", "below", "between", "could", "every", "first", "found",
    "great", "have", "here", "into", "itself", "just", "know", "like", "made",
    "many", "might", "more", "most", "much", "must", "neither", "never", "only",
    "other", "ourselves", "over", "shall", "should", "some", "such", "than", "that",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they", "thing",
    "this", "those", "through", "thus", "very", "were", "what", "when", "where",
    "which", "while", "whom", "whose", "will", "with", "without", "would", "your",
    "yours", "yourself", "yourselves", "project", "gutenberg", "ebook", "foundation",
}


def _content(text: str) -> str:
    start_marker = "*** START OF"
    end_marker = "*** END OF"
    start = text.find(start_marker)
    if start >= 0:
        newline = text.find("\n", start)
        text = text[newline + 1:] if newline >= 0 else text[start:]
    end = text.find(end_marker)
    return text[:end] if end >= 0 else text


def main() -> None:
    corpus: list[str] = []
    source_urls: list[str] = []
    for identifier in SOURCE_IDS:
        url = f"https://www.gutenberg.org/files/{identifier}/{identifier}-0.txt"
        try:
            with urlopen(url, timeout=60) as response:
                text = response.read().decode("utf-8", "replace")
        except HTTPError as exc:
            if exc.code != 404:
                raise
            url = f"https://www.gutenberg.org/files/{identifier}/{identifier}.txt"
            with urlopen(url, timeout=60) as response:
                text = response.read().decode("utf-8", "replace")
        corpus.append(_content(text))
        source_urls.append(url)
    counts = Counter(word.casefold() for word in re.findall(r"[A-Za-z]+", "\n".join(corpus)))
    terms = sorted({
        word.upper() for word, count in counts.items()
        if count >= 3 and 4 <= len(word) <= 18 and word not in EXCLUDED
    })
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps({
        "schema_version": 1,
        "source_name": "Project Gutenberg — History of the United States, six-volume set",
        "source_urls": source_urls,
        "license_note": "The listed Project Gutenberg U.S. history texts are public domain in the USA; vocabulary-only extraction, no passages stored.",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entry_policy": "Words occur at least three times in the public-domain U.S. history corpus; connector and source-boilerplate words are excluded.",
        "terms": terms,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(terms)} public-domain U.S.-history vocabulary entries to {TARGET}")


if __name__ == "__main__":
    main()
