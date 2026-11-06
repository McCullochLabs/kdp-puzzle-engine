"""Shared, conservative education signals and buyer-facing copy."""
from __future__ import annotations


EDUCATIONAL_MARKERS = (
    "vocabulary", "grade school", "grade 1", "grade 2", "grade 3", "grade 4",
    "grade 5", "grade 6", "grade 7", "grade 8", "middle school", "high school",
    "classroom", "homeschool", "student", "word skills",
)


def is_educational_context(*values: object) -> bool:
    text = " ".join(str(value or "") for value in values).casefold()
    return any(marker in text for marker in EDUCATIONAL_MARKERS)


def educator_back_cover_section(*values: object) -> str:
    if not is_educational_context(*values):
        return ""
    return (
        "FOR FAMILIES AND EDUCATORS\n\n"
        "A screen-free way to reinforce spelling, word recognition, and confident "
        "independent practice at home, in classrooms, tutoring, or homeschool settings."
    )
