"""Catalog synchronization and marketplace preparation orchestration."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .database import MARKETPLACES, PROTECTED_STATUSES, PublishingDatabase
from .marketplaces import PUBLISHERS
from .metadata_service import build_metadata, refresh_marketplace_content
from .listing_copy import listing_copy_text, recommended_prices
from .etsy_bundles import build_etsy_bundle, eligible_book_error
from theme_health import read_theme_health
from .production_gate import book_gate
from .production_intelligence import finalize_package
from .package_layout import marketplace_handoff_folder, package_file
from .puzzle_types import REGISTRY


class PublishingService:
    def __init__(self, project: Path) -> None:
        self.project = project; self.output = project / "out"; self.db = PublishingDatabase(project / "data" / "books.db")

    @staticmethod
    def _id(source_key: str) -> str:
        return hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:12]

    def _record_history_marketplace(self, package: Path, marketplace: str, status: str) -> None:
        """Keep the local approval trail in step with real marketplace handoffs.

        This is deliberately best-effort: a completed handoff is never blocked
        merely because a history note from an older app version cannot be read.
        """
        history_path = self.project / "production_history.json"
        try:
            records = json.loads(history_path.read_text(encoding="utf-8-sig"))
            if not isinstance(records, list): return
            wanted = package.resolve()
            changed = False
            for record in records:
                if not isinstance(record, dict): continue
                try: matches = Path(str(record.get("package") or "")).resolve() == wanted
                except OSError: matches = False
                if not matches: continue
                markets = record.get("marketplaces") if isinstance(record.get("marketplaces"), dict) else {}
                markets[PUBLISHERS[marketplace].label] = status
                record["marketplaces"] = markets; changed = True; break
            if changed:
                history_path.write_text(json.dumps(records[:250], indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    def sync_theme(self, theme_path: Path, package_path: Path | None = None) -> str:
        source = json.loads(theme_path.read_text(encoding="utf-8-sig")); key = str(theme_path.resolve()); book_id = self._id(key)
        current = self.db.get_book(book_id)
        if package_path is None and current and self.db.has_print_revision(book_id):
            selected = Path(str(current.get('package_path') or ''))
            if selected.is_dir(): package_path = selected
        # A saved theme is a reusable source, while the package manifest is
        # the authoritative record for a particular custom-title build.  Read
        # it only as an overlay so source words and topic checks stay intact.
        if package_path and package_path.is_dir():
            try:
                manifest = json.loads(package_file(package_path, "PACKAGE_SOURCE_RECORD.json").read_text(encoding="utf-8"))
                source = {**source, **{field: manifest[field] for field in ("title", "subtitle", "author", "puzzle_count") if manifest.get(field) not in (None, "")}}
            except (OSError, json.JSONDecodeError):
                pass
        meta = build_metadata(source); pages = int(source.get("interior_pages") or 0)
        health = read_theme_health(self.project / "data" / "theme_readiness_cache.json", theme_path)
        if not package_path or not package_path.is_dir(): package_path = self._find_package_for_title(meta["title"])
        if package_path and package_path.exists():
            meta["page_count"] = pages or self._pages_from_manifest(package_path) or self._interior_pages(package_path)
            meta["files"] = self._package_files(package_path)
        else:
            meta["page_count"] = pages or self._estimate_wordsearch_pages(source); meta["files"] = {}
        meta.update({"book_id": book_id, "puzzle_count": len(source.get("puzzles") or []), "trim_size": "8.5x11", "language": "English", "publication_date": "", "isbn": str(source.get("isbn") or ""), "edition": "1", "categories": meta["ingram_subjects"], "production_status": str((health or {}).get("status") or "Needs content check"), "last_synced": datetime.now().isoformat(timespec="seconds")})
        meta["price"] = recommended_prices(meta)
        self.db.upsert_book(book_id, key, meta, str(package_path or "")); return book_id

    def adopt_print_revision(self, book_id: str, package: Path) -> dict:
        """Select a verified print-only revision without creating another product."""
        from .package_revisions import adopt_print_revision
        return adopt_print_revision(self, book_id, package)

    def production_gate(self, book_id: str) -> dict:
        """Compatibility view of the canonical read-only production truth."""
        from .truth_service import PublishingTruthService
        return PublishingTruthService(self).for_book(book_id)["content_and_source"]

    def production_truth(self, book_id: str) -> dict:
        """One read-only answer for catalog, package, cover, and handoff state."""
        from .truth_service import PublishingTruthService
        return PublishingTruthService(self).for_book(book_id)

    def autopilot_status(self, book_id: str) -> dict:
        """Return one local, explainable production status for a catalog book.

        This does not start generation or call a marketplace.  It connects the
        existing canonical record, gate, proof and checkpoint ledger so the UI
        can show only the next honest action.
        """
        from .production_autopilot import ProductionAutopilot, canonical_facts, quality_score
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Center.")
        source = {}
        try:
            source = json.loads(Path(str(book.get("source_key") or "")).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        score = quality_score(book, source)
        checkpoint = ProductionAutopilot(self.project, book_id).record()
        from .production_orchestrator import ProductionOrchestrator
        production_job = ProductionOrchestrator(self.project, book_id).state().to_dict()
        return {"facts": canonical_facts(book, source), "score": score, "checkpoint": checkpoint, "production_job": production_job}

    def catalog_intelligence(self, limit: int = 20, view: str = "fastest") -> list[dict]:
        """Return explainable local next-book guidance without changing data."""
        from .catalog_intelligence import CatalogIntelligence
        return [row.to_dict() for row in CatalogIntelligence(self).opportunities(limit, view)]

    def commercial_catalog_audit(self, limit: int = 20) -> dict:
        """Return the deeper read-only commercial view over this same catalog."""
        from .catalog_intelligence import CatalogIntelligence
        return CatalogIntelligence(self).commercial_catalog_audit(limit)

    def non_word_expansion_plan(self) -> dict:
        """Return the read-only plan for building depth in other puzzle types."""
        from .catalog_intelligence import CatalogIntelligence
        return CatalogIntelligence(self).non_word_expansion_plan()

    def product_qa(self, book_id: str, *, write_report: bool = True) -> dict:
        """Run the shared local prepress inspector for a completed package."""
        from .product_qa import inspect_product, write_product_qa_report
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in Publishing Center.")
        folder = Path(str(book.get("package_path") or ""))
        if not folder.is_dir():
            raise ValueError("Create the complete package before running Product QA.")
        report = inspect_product(self.project, folder, book.get("metadata") or {})
        if write_report:
            write_product_qa_report(package_file(folder, "PRODUCT_QA.txt", for_write=True), report)
        return report.to_dict()

    def final_inspection(self, book_id: str) -> dict:
        """Run the same local package intelligence used by new generators."""
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Center.")
        folder = Path(str(book.get("package_path") or ""))
        if not folder.is_dir():
            raise ValueError("Create the complete package before running its final inspection.")
        try:
            source = json.loads(Path(str(book.get("source_key") or "")).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            source = dict(book.get("metadata") or {})
        meta = book.get("metadata") or {}
        return finalize_package(self.project, folder, source, str(meta.get("title") or source.get("title") or "Untitled book"), str(meta.get("subtitle") or source.get("subtitle") or ""), int(meta.get("page_count") or 0) or None)

    def commercial_assessment(self, book_id: str, marketplace: str | None = None) -> dict:
        """Return the separate, factual marketplace-value review for one book.

        This intentionally leaves the production gate and saved marketplace
        states untouched.  It is a planning aid, not a sales prediction.
        """
        from .commercial_intelligence import commercial_assessment
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Center.")
        return commercial_assessment(book, marketplace)

    def write_commercial_assessment(self, book_id: str, target: Path | None = None) -> Path:
        """Write a human-readable commercial review beside a finished package.

        A report can also be created in reports/ for a saved theme that has
        not yet been generated, which keeps commercial planning independent of
        package creation.
        """
        from .commercial_intelligence import write_commercial_report
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Center.")
        package = Path(str(book.get("package_path") or ""))
        destination = target or (package / "04_REVIEW_AND_RECORDS" if package.is_dir() else self.project / "reports" / "commercial_reviews" / book_id)
        return write_commercial_report(book, destination)

    def write_kdp_a_plus_assets(self, book_id: str) -> Path:
        """Build local KDP A+ creative assets from a completed package."""
        from .commercial_intelligence import write_a_plus_asset_kit
        book = self.db.get_book(book_id)
        if not book:
            raise KeyError(f"Unknown book: {book_id}")
        package = Path(str(book.get("package_path") or ""))
        if not package.is_dir():
            raise ValueError("Create the complete package before creating its KDP A+ asset kit.")
        return write_a_plus_asset_kit(book, package)

    def write_etsy_merchandising_assets(self, book_id: str) -> Path:
        """Build real-product Etsy images after cover approval."""
        from .marketplace_merchandising import build_etsy_merchandising_kit
        book = self.db.get_book(book_id)
        if not book:
            raise KeyError(f"Unknown book: {book_id}")
        package = Path(str(book.get("package_path") or ""))
        if not package.is_dir():
            raise ValueError("Create the complete package before creating Etsy listing images.")
        return build_etsy_merchandising_kit(package, book.get("metadata") or {})

    def sync_catalog(self, themes: list[Path], release_catalog: dict) -> int:
        # Theme Builder keeps historical timestamped copies. They are useful
        # source backups but should not look like separate books for sale.
        grouped: dict[str, list[tuple[Path, Path | None]]] = {}
        unreadable: set[str] = set()
        for path in themes:
            try:
                source = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                # A theme file that still exists but cannot be read/parsed
                # (disk hiccup, partial write, encoding damage) must not
                # silently delete its catalog book — that would destroy
                # statuses, saved listing links and ISBN assignments during
                # a routine re-sync. Keep it active; fixing the file and
                # re-syncing refreshes it normally. Truly vanished files
                # (path gone) still prune as before.
                if path.is_file():
                    unreadable.add(str(path.resolve()))
                continue
            key = self._publication_key(source)
            record = release_catalog.get(path.name, {}); raw = str(record.get("package") or "")
            package = Path(raw) if raw else self._find_package_for_title(str(source.get("title") or ""))
            grouped.setdefault(key, []).append((path, package if package and package.is_dir() else None))
        active: set[str] = set()
        for candidates in grouped.values():
            path, package = max(candidates, key=self._canonical_score)
            self.sync_theme(path, package); active.add(str(path.resolve()))
        active |= unreadable
        self.db.prune_sources(active)
        return len(grouped)

    def sync_output_packages(self) -> int:
        """Register complete non-word-search books, which do not have theme JSON files."""
        imported = 0
        self.db.prune_recovery_archive_packages()
        seen: set[Path] = set()
        managed_revisions = self.db.managed_print_revision_paths()
        from .studio_revision_adoption import managed_chat_package_paths
        managed_revisions |= managed_chat_package_paths(self.project)
        for manifest_path in self.output.rglob("PACKAGE_SOURCE_RECORD.json"):
            if "_recovery_archive" in {part.casefold() for part in manifest_path.parts}:
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")); folder = manifest_path.parent.parent if manifest_path.parent.name == "04_REVIEW_AND_RECORDS" else manifest_path.parent
            except (OSError, json.JSONDecodeError):
                continue
            if folder.resolve() in managed_revisions:
                seen.add(folder.resolve()); continue
            seen.add(folder.resolve()); source_theme = str(manifest.get("source_theme") or "")
            if source_theme and Path(source_theme).is_file():
                self.sync_theme(Path(source_theme), folder); continue
            key = "package:" + str(folder.resolve()); book_id = self._id(key)
            source = {"title": manifest.get("title"), "subtitle": manifest.get("subtitle"), "author": manifest.get("author"), "series": manifest.get("series", ""), "puzzle_type": manifest.get("puzzle_type", ""), "detected_topic": manifest.get("theme") or manifest.get("puzzle_type") or "Puzzle Book", "puzzle_count": manifest.get("puzzle_count", 0), "difficulty_label": manifest.get("difficulty", "Standard")}
            # A format-specific package may carry reviewed copy. Preserve it
            # on every catalog refresh instead of regenerating a generic blurb.
            for field in ("description", "platform_descriptions", "amazon_keywords", "etsy_tags", "ingram_subjects", "audience"):
                if manifest.get(field):
                    source[field] = manifest[field]
            meta = build_metadata(source)
            # New manifests may deliberately represent a review-stage or
            # incomplete package. Preserve that state instead of implying a
            # complete release; older manifests retain their historical
            # default for backwards compatibility.
            production_status = str(manifest.get("production_status") or "Complete package")
            meta.update({"book_id": book_id, "trim_size": manifest.get("trim_size", "8.5x11"), "language": "English", "publication_date": "", "isbn": "", "edition": "1", "categories": meta["ingram_subjects"], "production_status": production_status, "page_count": int(manifest.get("pages") or manifest.get("interior_pages") or self._interior_pages(folder)), "files": self._package_files(folder), "last_synced": datetime.now().isoformat(timespec="seconds")})
            meta["price"] = recommended_prices(meta)
            self.db.upsert_book(book_id, key, meta, str(folder)); imported += 1
        # Version 3.28 and earlier already made high-quality non-word-search
        # packages. Import them from their listing kit instead of rebuilding.
        for interior in self.output.rglob("interior.pdf"):
            if "_recovery_archive" in {part.casefold() for part in interior.parts}:
                continue
            folder = interior.parent.parent if interior.parent.name == "01_PRINT_UPLOADS" else interior.parent
            if folder.resolve() in managed_revisions or folder.resolve() in seen or not package_file(folder, "AUTOMATIC_BOOK_PLAN.txt").is_file(): continue
            try:
                listing = package_file(folder, "KDP_LISTING_KIT.txt").read_text(encoding="utf-8-sig")
            except OSError:
                continue
            fields = {line.split(":", 1)[0].strip().casefold(): line.split(":", 1)[1].strip() for line in listing.splitlines() if ":" in line[:60]}
            kind = fields.get("book type", "")
            legacy_importable = {item.display_name for item in REGISTRY.all(include_nonproduction=False) if item.type_id != "word_search"}
            if kind not in legacy_importable: continue
            key = "package:" + str(folder.resolve()); book_id = self._id(key)
            source = {"title": fields.get("title", folder.name), "subtitle": fields.get("subtitle", ""), "author": fields.get("author", "Jordan M. Slade"), "puzzle_type": kind, "detected_topic": fields.get("content theme", kind), "puzzle_count": int(fields.get("puzzle count", "0") or 0), "difficulty_label": fields.get("difficulty", "Standard")}
            meta = build_metadata(source)
            meta.update({"book_id": book_id, "trim_size": "8.5x11", "language": "English", "publication_date": "", "isbn": "", "edition": "1", "categories": meta["ingram_subjects"], "production_status": "Complete package", "page_count": self._interior_pages(folder), "files": self._package_files(folder), "last_synced": datetime.now().isoformat(timespec="seconds")})
            meta["price"] = recommended_prices(meta)
            self.db.upsert_book(book_id, key, meta, str(folder)); imported += 1
        self.db.prune_duplicate_unpublished_package_titles()
        return imported

    def recommended_books(self, limit: int = 6) -> list[dict]:
        """Return practical next steps from the user's own verified catalog.

        This intentionally does not claim live sales data.  It favors broad,
        evergreen topics, adequate puzzle counts, and books that have not
        already been fully created.  A completed package appears only after
        those next-to-create ideas, so the list stays useful at production time.
        """
        priorities = {
            "national park": 32, "garden": 30, "homestead": 29, "christmas": 29,
            "holiday": 27, "bible": 27, "space": 26, "planet": 25, "pet": 25,
            "cat": 24, "dog": 24, "travel": 23, "bird": 23, "nature": 22,
            "car": 22, "vehicle": 22, "school": 21, "vocabulary": 21,
            "history": 20, "ocean": 20, "food": 19, "sport": 19,
        }
        from .catalog_view import collapse_catalog_books
        choices: list[dict] = []
        for book in collapse_catalog_books(self.db.list_books()):
            meta = book["metadata"]
            if meta.get("production_status") not in {"Passed", "Complete package"}:
                continue
            files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
            has_package = bool(files.get("print_interior") and files.get("print_cover") and Path(str(files["print_interior"])).is_file() and Path(str(files["print_cover"])).is_file())
            text = " ".join(str(meta.get(field) or "") for field in ("title", "subtitle", "theme", "series")).casefold()
            score = sum(weight for word, weight in priorities.items() if word in text)
            count = int(meta.get("puzzle_count") or 0)
            score += 12 if count >= 100 else 9 if count >= 48 else 0
            score += 4 if str(meta.get("difficulty") or "").casefold() in {"easy", "standard", "mixed"} else 0
            # Fresh ideas come first. A complete package is still useful as a
            # ready-to-prepare fallback after the new-book recommendations.
            score += 2 if not has_package else -10
            if score <= 0:
                continue
            topic = str(meta.get("theme") or "themed puzzles")
            reason_parts = ["broad evergreen topic"]
            if any(word in text for word in ("christmas", "holiday")):
                reason_parts = ["seasonal favorite with a clear gift angle"]
            elif any(word in text for word in ("national park", "travel", "garden", "space", "pet", "vocabulary")):
                reason_parts = ["strong series-friendly topic"]
            if count >= 100:
                reason_parts.append("100-puzzle edition")
            elif count >= 48:
                reason_parts.append(f"{count}-puzzle full book")
            choices.append({"book": book, "score": score, "action": "Prepare package" if has_package else "Create book", "reason": " • ".join(reason_parts), "topic": topic, "puzzles": count})
        return sorted(choices, key=lambda item: (-item["score"], item["book"]["metadata"].get("title", "")))[:limit]

    def ready_now_books(self, limit: int = 50) -> list[dict]:
        """Return only books that can honestly enter the production flow now.

        This is deliberately stricter than the catalog.  It joins the shared
        source/package gate with the latest saved health result, so an old
        theme remains visible for repair but never appears in Ready Now.
        """
        from .catalog_view import collapse_catalog_books
        rows: list[dict] = []
        for book in collapse_catalog_books(self.db.list_books()):
            meta = book.get("metadata") or {}
            gate = self.production_gate(book["book_id"])
            status = str(meta.get("production_status") or "")
            if not gate["ready"] or status not in {"Passed", "Passed with notes", "Complete package"}:
                continue
            files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
            has_package = bool(files.get("print_interior") and files.get("print_cover"))
            score = (20 if not has_package else 0) + min(int(meta.get("puzzle_count") or 0), 100)
            score += 10 if str(meta.get("difficulty") or "").casefold() in {"standard", "mixed", "relaxing"} else 0
            rows.append({"book": book, "gate": gate, "has_package": has_package, "score": score})
        return sorted(rows, key=lambda item: (-item["score"], str(item["book"].get("metadata", {}).get("title") or "")))[:limit]

    def best_version(self) -> dict | None:
        """The strongest ready source for the one-click package action."""
        rows = self.ready_now_books(limit=1)
        return rows[0] if rows else None

    def etsy_bundle_candidates(self) -> list[dict]:
        """Only offer completed books that Etsy can receive as buyer downloads."""
        return [book for book in self.db.list_books() if not eligible_book_error(book)]

    def create_etsy_bundle(self, title: str, book_ids: list[str], price: float) -> tuple[Path, dict]:
        books = [book for item in book_ids if (book := self.db.get_book(item))]
        if len(books) != len(book_ids):
            raise ValueError("One or more selected books are no longer in the catalog. Sync the catalog and try again.")
        folder, details = build_etsy_bundle(self.output, title, books, price)
        bundle_id = self._id("etsy-bundle:" + str(folder.resolve()))
        self.db.save_bundle(bundle_id, title, book_ids, details, str(folder))
        return folder, details

    @staticmethod
    def _publication_key(source: dict) -> str:
        """A buyer-facing identity, not a filename, is the manager's unique book key."""
        parts = (str(source.get("title") or ""), str(source.get("subtitle") or ""), str(source.get("author") or "Jordan M. Slade"))
        return "|".join("".join(char for char in part.casefold() if char.isalnum()) for part in parts)

    @staticmethod
    def _canonical_score(candidate: tuple[Path, Path | None]) -> tuple[int, int, float]:
        path, package = candidate
        # Prefer a valid completed package, then a clean non-timestamped source,
        # then the newest backup. All other copies stay safely on disk.
        stamped = bool(__import__("re").search(r"_20\d{6}_\d{6}$", path.stem))
        try: modified = path.stat().st_mtime
        except OSError: modified = 0.0
        return (1 if package else 0, 0 if stamped else 1, modified)

    def _find_package_for_title(self, title: str) -> Path | None:
        """Support older packages and moved folders without changing the original output."""
        wanted = "".join(char for char in title.casefold() if char.isalnum())
        matches: list[Path] = []
        managed_revisions = self.db.managed_print_revision_paths()
        from .studio_revision_adoption import managed_chat_package_paths
        managed_revisions |= managed_chat_package_paths(self.project)
        for interior in self.output.rglob("interior.pdf"):
            folder = interior.parent.parent if interior.parent.name == "01_PRINT_UPLOADS" else interior.parent
            if folder.resolve() in managed_revisions: continue
            try:
                listing = package_file(folder, "KDP_LISTING_KIT.txt").read_text(encoding="utf-8-sig")
            except OSError:
                listing = ""
            name = "".join(char for char in folder.name.casefold() if char.isalnum())
            if title.casefold() in listing.casefold() or wanted in name or name in wanted:
                if package_file(folder, "kdp_full_wrap.pdf").is_file(): matches.append(folder)
        return max(matches, key=lambda item: item.stat().st_mtime) if matches else None

    @staticmethod
    def _pages_from_manifest(folder: Path) -> int:
        try: return int(json.loads(package_file(folder, "PACKAGE_SOURCE_RECORD.json").read_text(encoding="utf-8")).get("interior_pages") or 0)
        except (OSError, ValueError, json.JSONDecodeError): return 0

    @staticmethod
    def _interior_pages(folder: Path) -> int:
        try:
            from pypdf import PdfReader
            return len(PdfReader(str(package_file(folder, "interior.pdf"))).pages)
        except Exception:
            return 0

    @staticmethod
    def _estimate_wordsearch_pages(source: dict) -> int:
        """Mirrors the current word-search interior layout without importing the GUI."""
        if source.get("interior_profile") == "memories_large_print_v1":
            return 160
        puzzles = source.get("puzzles") if isinstance(source.get("puzzles"), list) else []
        count = len(puzzles)
        signature = source.get("signature_edition") if isinstance(source.get("signature_edition"), dict) else {}
        signature_extra = (count + 59) // 60 + 1 if signature.get("enabled") else 0
        if signature.get("fact_cards"): signature_extra += 1
        detail_config = source.get("detail_pages") if isinstance(source.get("detail_pages"), dict) else {}
        details = 0 if detail_config.get("enabled") is False else 2
        # Keep pre-generation catalog estimates aligned with the real PDF
        # engine. Optional chapter dividers affect both page count and spine.
        try:
            from wordsearch import interior_divider_page_count
            dividers = interior_divider_page_count(source, puzzles)
        except Exception:
            dividers = 0
        raw = 4 + details + signature_extra + dividers + count + 1 + ((count + 1) // 2) + 2 + (1 if source.get("also_from") else 0)
        return raw if raw % 2 == 0 else raw + 1

    @staticmethod
    def _package_files(folder: Path) -> dict:
        return {"print_interior": str(package_file(folder, "interior.pdf")) if package_file(folder, "interior.pdf").exists() else "", "print_cover": str(package_file(folder, "kdp_full_wrap.pdf")) if package_file(folder, "kdp_full_wrap.pdf").exists() else "", "front_cover": str(package_file(folder, "front_cover.png")) if package_file(folder, "front_cover.png").exists() else "", "printable_pdf": ""}

    def prepare(self, book_id: str, marketplace: str) -> tuple[Path, list[str]]:
        book = self.db.get_book(book_id)
        if not book: raise ValueError("Book was not found in the Publishing Manager.")
        # Refresh automated intelligence before a handoff only when this
        # project explicitly enables the Gemini-first gateway. Test and
        # isolated projects remain deterministic/offline by default.
        try:
            settings = json.loads((self.project / "data" / "listing_intelligence_settings.json").read_text(encoding="utf-8"))
            if bool(settings.get("enabled")) and not isinstance(book.get("metadata", {}).get("listing_intelligence"), dict):
                self.refresh_listing_intelligence(book_id, "amazon")
                book = self.db.get_book(book_id) or book
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        # Price guidance is a calculated recommendation, not locked creative
        # metadata. Refresh it whenever a handoff is prepared so old catalog
        # records receive the current per-platform recommendations too.
        book["metadata"] = refresh_marketplace_content(book["metadata"])
        book["metadata"]["price"] = recommended_prices(book["metadata"])
        self.db.save_metadata(book_id, book["metadata"])
        publisher = PUBLISHERS[marketplace]; issues = publisher.validate(book)
        root = Path(book.get("package_path") or self.output / book["book_id"])
        prior = self.db.marketplace_records(book_id)[marketplace]
        if prior["status"] in PROTECTED_STATUSES:
            # The user already confirmed an upload/live listing. Re-preparing
            # must never downgrade that record or erase its ASIN/link.
            return root, [f"{publisher.label} is already recorded as {prior['status']}. Nothing was changed and your listing details are safe."]
        blockers = publisher.blocking_issues(issues)
        if blockers:
            self.db.transition_status(book_id, marketplace, "Needs Review", source="prepare")
            if root.is_dir(): self._record_history_marketplace(root, marketplace, "Needs review")
            return Path(book.get("package_path") or self.output), blockers
        try:
            folder_name = {"amazon": "kdp", "barnes_noble": "barnes_noble", "payhip": "payhip"}.get(marketplace, marketplace)
            target = marketplace_handoff_folder(root, folder_name, create=True)
            publisher.prepare(book, target)
        except Exception as exc:
            # Keep the human-readable reason with the record so errors survive
            # the restart; prepare_many's fallback write is deduplicated.
            self.db.transition_status(book_id, marketplace, "Error", source="prepare", error_message=str(exc))
            raise
        status = publisher.prepared_status(book)
        self.db.transition_status(book_id, marketplace, status, source="prepare")
        self._record_history_marketplace(root, marketplace, "Prepared" if status == "Ready" else "Prepared — final cover needed")
        return target, []

    def listing_copy(self, book_id: str, marketplace: str) -> str:
        """Return a validated listing sheet, preferring Gemini when configured.

        A Gemini draft is only used in memory for this copy action. It never
        changes saved metadata or overwrites a human-edited listing. If the
        optional provider is unavailable or rejected by the fact validator,
        this returns the deterministic local sheet instead.
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Manager.")
        record = self.ai_listing(book_id, marketplace)
        content = record.get("content") if isinstance(record.get("content"), dict) else {}
        if record.get("provider") == "Deterministic local listing" or not content.get("description"):
            return listing_copy_text(book, marketplace)
        draft = deepcopy(book)
        meta = draft.get("metadata") or {}
        meta["subtitle"] = str(content.get("subtitle") or meta.get("subtitle") or "")
        meta["description"] = str(content.get("description") or meta.get("description") or "")
        meta["platform_descriptions"] = {**(meta.get("platform_descriptions") or {}), marketplace: meta["description"]}
        if marketplace == "amazon" and content.get("keywords"):
            meta["amazon_keywords"] = list(content["keywords"])
        if marketplace == "etsy" and content.get("tags"):
            meta["etsy_tags"] = list(content["tags"])
        draft["metadata"] = meta
        return listing_copy_text(draft, marketplace)

    def ai_listing(self, book_id: str, marketplace: str) -> dict:
        """Create one AI-assisted draft, with deterministic local fallback."""
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Manager.")
        from .listing_intelligence import ListingIntelligence
        return ListingIntelligence(self.project).generate(book, marketplace, enabled=True)

    def refresh_listing_intelligence(self, book_id: str, marketplace: str = "amazon") -> dict:
        """Refresh automated listing fields through the one Gemini-first gateway.

        Titles and fields explicitly marked human/locked remain untouched.  The
        returned record documents whether Gemini succeeded or local fallback
        was necessary, which gives every marketplace handoff the same source.
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Manager.")
        from .listing_intelligence import ListingIntelligence, apply_listing_intelligence
        record = ListingIntelligence(self.project).generate(book, marketplace, enabled=True)
        metadata, _changed = apply_listing_intelligence(book["metadata"], record)
        metadata["price"] = recommended_prices(metadata)
        self.db.save_metadata(book_id, metadata)
        return record

    def prepare_many(self, book_ids: list[str], marketplaces: list[str]) -> list[tuple[str, str, str]]:
        report = []
        for book_id in book_ids:
            for marketplace in marketplaces:
                prior = self.db.marketplace_records(book_id)[marketplace]
                if prior["status"] in PROTECTED_STATUSES:
                    report.append((book_id, marketplace, f"Already {prior['status']}"))
                    continue
                try:
                    _folder, issues = self.prepare(book_id, marketplace)
                    status = self.db.marketplace_records(book_id)[marketplace]["status"]
                    report.append((book_id, marketplace, "Needs Review" if issues else status))
                except Exception as exc:
                    self.db.transition_status(book_id, marketplace, "Error", source="prepare", error_message=str(exc))
                    report.append((book_id, marketplace, f"Error: {exc}"))
        return report

    def launch_handoffs(self, book_id: str) -> dict:
        """Run the safe, local portion of a launch after a package is complete.

        This locks the exact release then creates KDP, Etsy, Payhip, and website
        handoffs. It never uploads or publishes on the user's behalf.
        """
        lock = self.db.lock_release(book_id)
        report = self.prepare_many([book_id], ["amazon", "etsy", "payhip", "website"])
        return {"lock": lock, "report": report}

    def detect_local_marketplace_status(self) -> int:
        """Record local handoffs with their real, platform-specific next step."""
        updated = 0
        folder_names = {"amazon": "kdp", "barnes_noble": "barnes_noble", "payhip": "payhip"}
        for book in self.db.list_books():
            package = Path(str(book.get("package_path") or ""))
            if not package.is_dir():
                continue
            for marketplace in MARKETPLACES:
                target = marketplace_handoff_folder(package, folder_names.get(marketplace, marketplace))
                record = self.db.marketplace_records(book["book_id"])[marketplace]
                if target.is_dir() and record["status"] in ("Not Prepared", "Ready"):
                    status = PUBLISHERS[marketplace].prepared_status(book)
                    if record["status"] != status:
                        self.db.transition_status(book["book_id"], marketplace, status, source="local_scan")
                        updated += 1
        return updated
