"""Read-only migration preview for legacy content sources.

The preview intentionally reports conversion workload without changing master
content, themes, caches, or production packages.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .content_registry import load_master_bank_legacy, load_puzzle_content_library_legacy
from .pipeline import load_taxonomy


MECHANICAL_MARKERS = (
    "CURIOSITY MAKES ", " IS ONE PART OF A BIGGER STORY", "A CAREFUL LOOK AT ",
    " INVITES PATIENT THINKING", " CAN OPEN A NEW PATH TO ",
)


def _duplicates(records):
    values = Counter((record.type, record.normalized) for record in records)
    return sum(count - 1 for count in values.values() if count > 1)


def preview_legacy_migration(project_root: Path | str = ".") -> dict[str, object]:
    root = Path(project_root)
    taxonomy = load_taxonomy(root)
    master = load_master_bank_legacy(root / "word_banks" / "Guided_Builder_Master_Word_Bank.json", taxonomy)
    library = load_puzzle_content_library_legacy(root / "word_banks" / "puzzle_content_library.json", taxonomy)
    all_records = [*master.records.values(), *library.records.values()]
    unresolved_links = sum(1 for record in all_records for link in record.topics if link.confidence == 0)
    no_provenance = sum(1 for record in all_records if record.provenance is None)
    mechanical = [record for record in library.records.values()
                  if record.type == "cryptogram_prompt" and any(marker in record.display.upper() for marker in MECHANICAL_MARKERS)]
    by_type = Counter(record.type for record in all_records)
    needs_review = sum(1 for record in all_records if record.quality.editorial_status != "approved")
    return {
        "schema_version": 1,
        "sources": {"master_bank": str(root / "word_banks" / "Guided_Builder_Master_Word_Bank.json"),
                    "puzzle_content_library": str(root / "word_banks" / "puzzle_content_library.json")},
        "legacy_word_records_inspected": len(master.records),
        "content_library_records_inspected": len(library.records),
        "records_successfully_mapped": len(all_records),
        "records_by_type": dict(sorted(by_type.items())),
        "records_missing_stable_ids": sum(1 for record in all_records if not record.id),
        "records_without_canonical_topics": unresolved_links,
        "records_without_provenance": no_provenance,
        "duplicate_normalized_content": _duplicates(all_records),
        "generated_or_mechanical_records": len(mechanical),
        "records_requiring_editorial_review": needs_review,
        "notes": [
            "Legacy source records are mapped in memory only and remain legacy_unreviewed.",
            "Dictionary and generated sources are not promoted to approved content by this preview.",
            "Mechanical prompt count is a review signal, not an automatic deletion or rejection.",
        ],
    }
