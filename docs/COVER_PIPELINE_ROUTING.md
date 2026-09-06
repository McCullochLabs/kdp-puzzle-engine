# Cover Pipeline Routing

## Purpose

Every active creation workflow uses a small shared request adapter before the existing approval-enforced registry, `cover.py`, and `wrap_cover.py`. The adapter does not render covers, own metadata, or call an online provider.

```text
Creation route
  -> CoverRequest adapter
  -> shared preference and niche-direction reader
  -> BackgroundAssetIndex production ranking
  -> approved existing asset
  -> cover.py approval boundary
  -> wrap_cover.py approval-proof boundary
```

If no relevant approved asset exists, production stops with **Cover Art Required**. The operator may separately request generation, review the result, and approve it. Generation is never silently triggered.

## Routing matrix

| Creation route | Cover entry | Asset discovery | Generated reuse | Generator access | Preferences | Niche memory | Shared pipeline | Approval gate | Status |
|---|---|---|---|---|---|---|---|---|---|
| Book Assistant | Word Search Studio or Puzzle Studio | Shared registry ranking | Yes | Explicit UI only | Yes | Yes | Yes | Renderer + wrap + package | Known Good — preserved |
| Guided Builder | Word Search Studio | Shared registry ranking | Yes | Explicit UI only | Yes | Yes | Yes | Renderer + wrap + package | Repaired consistency |
| Word Search workspace | `_studio_cover_settings` | Shared registry ranking | Yes | Explicit UI only | Yes | Yes | Yes | Renderer + wrap + package | Known Good — preserved |
| Signature Word Search | Word Search package route | Shared registry ranking | Yes | Explicit UI only | Yes | Style/palette only | Yes | Renderer + wrap + package | Known Good — edition retained |
| Sudoku | `cover_spec` | Shared registry ranking | Yes | No silent access | Shared adapter | Shared adapter | Yes | Renderer + wrap + package | Repaired consistency |
| Cryptogram | `cover_spec` | Shared registry ranking | Yes | No silent access | Shared adapter | Shared adapter | Yes | Renderer + wrap + package | Repaired consistency |
| Scramble + Trivia | `cover_spec` | Shared registry ranking | Yes | No silent access | Shared adapter | Shared adapter | Yes | Renderer + wrap + package | Repaired consistency |
| Mixed Brain Games | `cover_spec` with mixed-format context | Shared registry ranking | Yes | No silent access | Shared adapter | Shared adapter | Yes | Renderer + wrap + package | Known Good — format exception retained |
| Series Builder | Word Search Studio | Shared registry ranking | Yes | Explicit UI only | Yes | Style/palette family | Yes | Renderer + wrap + package | Known Good — series identity retained |
| Production Queue / batch UI | Word Search queue | Shared registry ranking | Yes | No silent access | Yes | Yes | Yes | Renderer + wrap + package | Known Good after fallback removal |
| Publishing Center | Continue/Create routes | Delegates to applicable studio | Yes | Explicit UI only | Yes | Yes | Yes | Release contract + proof lock | Known Good — preserved |
| Cover repair/rebuild UI | Applicable studio route | Shared registry ranking | Yes | Explicit UI only | Yes | Yes | Yes | Renderer + wrap + stale-proof handling | Known Good — preserved |
| Cover preview galleries | `cover.py --preview` | Shared selection | Yes | Explicit UI only | Yes | Yes | Yes | Intentional preview exception | Intentional Exception |
| Discussed-book builder | Word Search adapter | Shared registry ranking | Yes | None | Shared route | Shared route | Yes | Renderer + wrap | Repaired; fail-closed |
| Active audit/sample scripts using `recommend_background_photo` | Word Search adapter | Shared registry ranking | Yes | None | Direction when supplied | Direction when supplied | Yes | Renderer + wrap | Consistent |
| Older one-off Signature/launch/rebuild scripts | Direct approved path into `cover.py` | Fixed historical input | Explicit path only | None | No | No | Renderer only | Renderer + wrap | Legacy; fail-closed, not primary workflow |
| Theme-only source builders | None | None | N/A | None | N/A | N/A | N/A | N/A | Intentional Exception — no cover created |

## Shared request contract

`background_generation.routing.CoverRequest` communicates only the cover facts needed for selection: route, book ID, title, subtitle, author, puzzle type, topic, audience, edition, series, requested style/palette, theme path, optional preferred asset, and whether the surrounding UI may offer generation.

`CoverDecision` returns the selected registry record, candidates, style/palette direction, fallback reason, and lightweight diagnostics. It does not duplicate book metadata or weaken the registry.

## Selection policy

1. Read saved theme preferences and niche/series style direction.
2. Ask `BackgroundAssetIndex.production_choices()` for current approved, relevant candidates.
3. Honor a saved asset only if it remains approved, checksum-current, and relevant.
4. Rank by topic evidence and usage; generated imagery receives no artificial priority.
5. Use an approved photo when it is the stronger match.
6. Return no asset when no strong approved match exists. Never call a provider automatically.

Approved photos are first-class only when their registry record includes explicit production approval, an accepted photo classification/source type, verified rights, a written rights basis, and a current checksum. Folder location alone grants nothing.

## Puzzle-format behavior

- Word Search retains its word-grid hero and existing typography/layout choices.
- Sudoku retains number/letter/shape and geometric directions.
- Cryptogram retains cipher/code visual language.
- Scramble + Trivia retains word/quiz visual language.
- Mixed Brain Games supplies mixed-format context and retains its mixed-specific layouts.
- Signature and series books may share typography, borders, palette family, and composition; they do not permanently force one old image file.

## Persistence and provenance

The registry remains the sole asset authority. Approved assets survive restart and can be reused by any relevant workflow without file duplication. Packages write `COVER_ROUTING.json` plus asset ID, checksum, approval revision/state, and provenance into `PACKAGE_SOURCE_RECORD.json`. Existing rights ledgers remain in place.

## Developer diagnostics

`COVER_ROUTING.json` records the creation route, shared pipeline name, candidate count/source mix, selected asset/path/provider, approval state, fallback reason, and whether generation was requested. This is intentionally kept out of the normal user interface.

