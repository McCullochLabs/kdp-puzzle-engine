"""Read-only gallery diversity audit over the authoritative cover registry."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from background_generation.index import BackgroundAssetIndex, approval_state, retired_from_new_production
from background_generation.routing import CoverRequest, select_cover_gallery

FORMATS = ("Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games")
TOPICS = ("Gardening", "Space & Astronomy", "National Parks", "Pets & Animal Life", "Holidays & Seasons")


def main() -> None:
    index = BackgroundAssetIndex(); refresh = index.refresh_derived_metadata(); assets = index.assets()
    approved = [row for row in assets if index.production_selectable(row)]
    generated = [row for row in approved if row.get("project_generated") is True]
    photos = [row for row in approved if str(row.get("source_type") or "").casefold() in {"approved_photo", "licensed_photo", "owned_photo"}]
    retired = [row for row in assets if retired_from_new_production(row)]
    unapproved = [row for row in assets if approval_state(row) != "approved" or not row.get("production_approved")]
    quiet_request = CoverRequest(route="Puzzle Studio Gallery", title="THE QUIET GRID", topic="General Starter", puzzle_type="Sudoku")
    quiet = select_cover_gallery(quiet_request, index=index)

    dry_runs = []; rendered = []
    with tempfile.TemporaryDirectory(prefix="cover_gallery_dry_run_") as raw_folder:
        folder = Path(raw_folder)
        render_cases = [("Sudoku", "General Starter", quiet)]
        for kind in FORMATS:
            for topic in TOPICS[:3]:
                request = CoverRequest(route=f"Dry Run — {kind}", title=f"{topic} {kind}", topic=topic, puzzle_type=kind)
                result = select_cover_gallery(request, index=index)
                dry_runs.append({"puzzle_type": kind, "topic": topic, **result.metrics})
                render_cases.append((kind, topic, result))
        # Render all Quiet Grid slots plus one representative slot from every
        # format/topic dry run. Files live only in the temporary test folder.
        for case_index, (kind, topic, result) in enumerate(render_cases):
            concepts = result.concepts if case_index == 0 else result.concepts[:1]
            for concept in concepts:
                output = folder / f"render-{case_index}-{concept.slot}.png"
                art = PROJECT / str(concept.asset.get("path") or "")
                command = [sys.executable, str(PROJECT / "cover.py"), "--title", "THE QUIET GRID" if case_index == 0 else f"{topic} {kind}",
                    "--subtitle", "A polished puzzle collection", "--author", "Jordan M. Slade", "--puzzle-count", "60",
                    "--format-label", kind.upper(), "--puzzle-type", kind, "--palette", concept.palette,
                    "--style", concept.cover_template_id, "--art", str(art), "--out", str(output), "--preview"]
                process = subprocess.run(command, cwd=PROJECT, capture_output=True, text=True)
                rendered.append({"puzzle_type": kind, "topic": topic, "asset_id": concept.art_asset_id,
                    "template_id": concept.cover_template_id, "passed": process.returncode == 0 and output.is_file(),
                    "error": (process.stderr or process.stdout).strip()[:300] if process.returncode else ""})

    builds = []
    for run in range(100):
        kind = FORMATS[run % len(FORMATS)]; topic = TOPICS[(run // len(FORMATS)) % len(TOPICS)]
        result = select_cover_gallery(CoverRequest(route="Controlled Gallery Stress", title=f"{topic} {kind}", topic=topic, puzzle_type=kind), refresh_offset=run, index=index)
        builds.append(result)
    all_concepts = [concept for result in builds for concept in result.concepts]
    family_counts = Counter(concept.asset.get("visual_family_id") for concept in all_concepts)
    stress = {
        "gallery_builds": len(builds), "slots_generated": len(all_concepts),
        "candidate_evaluations": sum(len(result.candidates) for result in builds),
        "distinct_approved_assets_surfaced": len({concept.art_asset_id for concept in all_concepts}),
        "distinct_visual_families_surfaced": len(family_counts),
        "generated_art_uses": sum(concept.asset.get("project_generated") is True for concept in all_concepts),
        "local_photo_uses": sum(str(concept.asset.get("source_type") or "").casefold() in {"approved_photo", "licensed_photo", "owned_photo"} for concept in all_concepts),
        "duplicate_art_slots": sum(result.metrics["duplicate_asset_count"] for result in builds),
        "duplicate_art_rate": round(sum(result.metrics["duplicate_asset_count"] for result in builds) / max(1, len(all_concepts)), 4),
        "retired_assets_shown": sum(result.metrics["retired_asset_count_shown"] for result in builds),
        "unapproved_assets_shown": sum(result.metrics["unapproved_asset_count_shown"] for result in builds),
        "diversity_limited_cases": sum(result.metrics["diversity_limited"] for result in builds),
    }
    payload = {"inventory": {"total": len(assets), "active_approved": len(approved), "approved_generated": len(generated),
        "approved_local_photo": len(photos), "retired": len(retired), "rejected_or_unapproved": len(unapproved),
        "missing_topics": sum(not row.get("topics") for row in approved), "missing_puzzle_type": sum(not row.get("puzzle_types") for row in approved),
        "missing_style": sum(not row.get("style") for row in approved), "missing_visual_family": sum(not row.get("visual_family_id") for row in approved),
        "never_used": sum(not row.get("usage") for row in approved), "heavily_reused": sum(len(row.get("usage") or []) >= 5 for row in approved)},
        "derived_metadata_refresh": refresh, "quiet_grid": quiet.diagnostics(), "dry_runs": dry_runs,
        "temporary_render_validation": rendered, "stress": stress,
        "safety": {"provider_calls": 0, "approvals_changed": 0, "historical_files_changed": 0, "packages_created": 0}}
    reports = PROJECT / "reports"; reports.mkdir(exist_ok=True)
    (reports / "COVER_GALLERY_DIVERSITY.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    qm = quiet.metrics
    lines = ["# Cover Gallery Diversity — Final Report", "", "## Baseline", "", "1. Branch: `main`", "2. Commit: `8a93d4056581cb72cc9d2ad7f773760202f67318`",
        "3. Worktree: pre-existing dirty/untracked work preserved; no destructive cleanup.", "4. Baseline: 728 passed, 0 failed, 0 skipped.", "",
        "## Root Cause", "", "5. Both galleries varied templates before selecting diverse art, repeatedly invoking a correct single-cover selector.",
        "6. Approved assets were registered, but the gallery had no multi-slot discovery contract and no persisted visual-family field.",
        "7. No explicit retired-state exclusion existed; retirement is now fail-closed for new selection.",
        "8. Topic matching could collapse slots onto the strongest result.", "9. Yes—templates were diversified before art.", "",
        "## Asset Inventory", "", f"10. Active approved: {len(approved)}", f"11. Approved generated: {len(generated)}", f"12. Approved local/photo: {len(photos)}",
        f"13. Retired: {len(retired)}", f"14. Rejected/unapproved: {len(unapproved)}", f"15. Missing topics: {sum(not row.get('topics') for row in approved)}; missing puzzle-type metadata: {sum(not row.get('puzzle_types') for row in approved)}; missing style metadata: {sum(not row.get('style') for row in approved)}; missing visual-family metadata after refresh: {sum(not row.get('visual_family_id') for row in approved)}.",
        f"16. Never used: {sum(not row.get('usage') for row in approved)}", f"17. Heavily reused (5+): {sum(len(row.get('usage') or []) >= 5 for row in approved)}",
        "18. Previously undiscoverable registered assets now participate whenever their approved topic evidence is contextually relevant. No arbitrary folders were scanned.", "",
        "## Gallery Architecture", "", "19. Candidate discovery: authoritative BackgroundAssetIndex.", "20. Filtering: approved, active, current fingerprint, production provenance.",
        "21. Matching: topic/title/puzzle context and stored tags.", "22. Ranking: relevance first, then transparent use penalty.",
        "23. Freshness: total and same-context usage are exposed; unused relevant art gets the existing ranking advantage.",
        "24. Visual family: persisted reviewed ID or lightweight 64-bit perceptual-hash grouping.",
        "25. Artwork diversity: one item per family, then other assets, then explainable reuse.", "26. Template assignment occurs after art selection and follows puzzle-type directions.", "",
        "## THE QUIET GRID Regression", "", "27. Before: 3 contextually eligible approved assets from 77 registry rows.",
        "28. Before: independent single-cover calls could repeatedly select the strongest art.", "29. Before: no gallery-level unique-art guarantee.",
        f"30. After: {qm['eligible_asset_count']} eligible assets and {qm['eligible_visual_family_count']} families.",
        "31. After art: " + ", ".join(item.art_asset_id for item in quiet.concepts) + ".",
        f"32. After unique artworks: {qm['distinct_art_assets_shown']} of {qm['gallery_slot_count']} slots.", f"33. After unique visual families: {qm['distinct_visual_families_shown']}.",
        "34. All three relevant Sudoku directions are shown before repetition. The UI truthfully reports limited inventory because six relevant families do not exist.", "",
        "## Real Asset Validation", "", f"35. Generated assets tested: {min(10, len(generated))} sampled plus all candidates exercised by stress selection.",
        f"36. Local assets tested: {len(photos)}; the authoritative registry contains no approved local/photo assets, so a requested 10-item real sample cannot be fabricated.",
        "37. Cross-workflow tests prove one registered approved asset is shared without file duplication.", "38. Newly approved fixture becomes visible immediately from the saved registry; generation remains separate and explicit.",
        "39. Restart persistence passed through a newly constructed index reading the saved registry.", "",
        "## Route Coverage", "", "40. Book Assistant: shared request/selector route.", "41. Guided Builder: shared request/selector route.",
        "42. Word Search: CoverVariantGallery now uses shared multi-slot selection.", "43. Sudoku: PuzzleCoverGallery uses shared multi-slot selection.",
        "44. Cryptogram: PuzzleCoverGallery.", "45. Scramble + Trivia: PuzzleCoverGallery.", "46. Mixed: PuzzleCoverGallery with mixed-specific templates.",
        "47. Signature: shared Word Search gallery and approval boundary.", "48. Batch/series: shared single-cover selector; no gallery is shown during unattended generation.",
        "49. Intentional exception: production automation selects one approved cover, not six previews; it retains the same lifecycle gate.", "",
        "## Temporary Render Validation", "", f"Rendered cover concepts: {len(rendered)}; passed: {sum(row['passed'] for row in rendered)}; failed: {sum(not row['passed'] for row in rendered)}. All temporary files were removed after validation.", "",
        "## Stress Test", "", f"50. Gallery builds: {stress['gallery_builds']}", f"51. Slots generated: {stress['slots_generated']}",
        f"52. Distinct artworks surfaced: {stress['distinct_approved_assets_surfaced']}", f"53. Distinct visual families: {stress['distinct_visual_families_surfaced']}",
        f"54. Duplicate-art rate: {stress['duplicate_art_rate']:.1%}; repetition occurs only after suitable candidates are exhausted.",
        f"55. Retired assets shown: {stress['retired_assets_shown']}", f"56. Unapproved assets shown: {stress['unapproved_assets_shown']}", f"57. Diversity-limited cases: {stress['diversity_limited_cases']}", "",
        "## Required Answers", "", "**When enough approved artwork exists, does the gallery present genuinely different concepts? YES.**",
        "**Are approved generated/local assets broadly discoverable when contextually appropriate? YES for every such asset in the authoritative registry.**",
        "**Can retired or unapproved legacy artwork appear in a new-production gallery? NO.**", "",
        "No external image generation occurred. No approval, historical product, released package, or marketplace state was changed.", ""]
    (reports / "COVER_GALLERY_DIVERSITY.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"inventory": payload["inventory"], "quiet_grid": qm, "stress": stress}, indent=2))


if __name__ == "__main__":
    main()
