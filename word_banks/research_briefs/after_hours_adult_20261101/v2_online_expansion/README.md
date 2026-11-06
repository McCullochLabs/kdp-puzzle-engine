# After Hours adults-only word-search research — v2

This is a pending editorial candidate, not an approved production bank or a generated book. The original v1 evidence remains intact in the parent directory.

The expanded pool has 722 distinct normalized targets: 59 profanity/minced oaths, 91 cheeky/flirtation terms, 96 lingerie/adult-accessory/material names, 66 bar-service terms, 165 alcoholic drinks, 75 named cocktails, 90 beer styles, and 80 wine-grape varieties. This adds 304 independently sourced terms over the 418-term initial lexical pool. Nineteen original holds now have primary references; 29 original lexical holds remain unresolved.

## Reviewable Standard candidate

`standard_48_group_candidates.json` selects exactly 576 globally unique targets across 48 groups of 12. Allocation: four profanity/minced-oath groups, seven cheeky-flirtation groups, six lingerie/accessory groups, five bar-service groups, twelve alcoholic-drink groups, six named-cocktail groups, four beer-style groups, four wine-grape groups. Displays preserve readable spaces; grid targets contain only A–Z. Maximum selected target length is 18 letters against the 21-letter limit.

All 48 groups passed the existing `wordsearch.validate_word_set` contract at their calculated `grid_size_for` sizes. A separate JSON read-back repeated the checks and confirmed source evidence for every selected target. Embedded-host conflicts were handled by distributing words across groups and checking the existing contract; no validator was relaxed. Familiar profanity and requested adult object names were prioritized. These are broad but consistent research niche groups; titles/ordering and fine-grained editorial balance can still be improved during review.

No grid placement, ambiguity scan on generated grids, PDF, cover, catalog, publishing package, or marketplace acceptance check has been performed. Those remain production work for the owning agent. No approval, production source bank, gate, UI, or generator was changed.

## Sources and exclusions

Per-target exact WordNet lemma evidence is retained where available. Online additions use primary dictionary, official IBA cocktail-directory/per-cocktail links, BJCP style names, Australian Wine Research Institute grape references, and manufacturer/retailer category names for generic adult objects and materials. Only names/facts were collected; no recipes, usage instructions, graphic act descriptions, or marketing prose were imported. Source links and reviewed exclusions are recorded in the JSON files. Normalized transliteration removes diacritics for grids; it does not invent concatenated display phrases. Plural object names such as handcuffs are established object names, not singular/plural inflation.

Protected product/liqueur names, celebrity/eponym associations needing review, numeric cocktail identities that lose meaning under A–Z normalization, source encoding problems, and potentially unsuitable listing wording were held in `source_exclusions.json`. Some broad adjectives and clothing/bar terms are still pending editorial topic-fit review. Material names are grouped with adult accessories only where the primary adult-product reference explicitly names the material.

The local Qwen suggestion batch failed quality checks and contributed zero terms; its raw evidence/rejection record remains in the parent directory. No further models were run, and Ollama was verified unloaded.

## Signature hold

The entire 722-term pool remains 478 below Signature's 1,200-target requirement, before additional quality trimming. Do not label this a complete Signature candidate or relax any gate. The 48-group Standard candidate is concrete and reviewable but remains unapproved.

Reproduce from repository root with `.venv\Scripts\python.exe word_banks/research_briefs/after_hours_adult_20261101/build_online_expansion_v2.py`.
