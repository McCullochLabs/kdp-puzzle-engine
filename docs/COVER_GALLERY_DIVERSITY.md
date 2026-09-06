# Cover Gallery Diversity

The Cover Gallery uses the same authoritative `BackgroundAssetIndex` and approval boundary as production. It never scans arbitrary folders and never generates artwork while refreshing ideas.

## Selection order

1. Discover registered assets.
2. Exclude missing, changed, unapproved, rejected, pending, and retired assets.
3. Rank by topic, audience, puzzle-type context, and prior use.
4. Group exact/near-identical images into visual families using reviewed `visual_family_id` or the existing local perceptual hash.
5. Select one artwork from each suitable family before reusing a family or file.
6. Assign a puzzle-type-compatible cover template after artwork selection.
7. Render the gallery previews.

An artwork ID and a template ID are separate facts. A different layout around the same image is not counted as new artwork diversity.

## Lifecycle

- Approved + active: eligible for new cover selection.
- Approved + retired: retained for historical provenance, excluded from new selection.
- Awaiting review, rejected, or unknown: excluded.

The safe discovery refresh derives only perceptual family, orientation, generated/local source type, and lifecycle fields from existing evidence. It never changes approval, provenance, files, or usage history.

## Refresh Cover Ideas

Refresh rotates and reranks approved existing visual families. It makes no provider call. New artwork remains a separate explicitly confirmed generation-and-review workflow.

When fewer than four relevant approved families exist, the gallery says diversity is limited and reuses only after showing all available families.

## Puzzle-type directions

- Sudoku: clean, geometric, calm, logic-led.
- Cryptograms: mystery, editorial, vintage, cipher-led.
- Scramble + Trivia: energetic, playful, nostalgic, event-led.
- Mixed Brain Games: organized variety and premium collection direction.
- Word Search: topic-led imagery.

