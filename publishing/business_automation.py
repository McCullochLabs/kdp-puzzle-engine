"""Connected local business guidance for the Publishing Center.

This module deliberately produces recommendations, local files, and safe next
actions only. It never claims sales data, contacts a marketplace, or changes a
human-confirmed publishing status.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from .listing_copy import recommended_bundle_prices, recommended_prices
from .package_layout import marketplace_handoff_folder
from .production_gate import book_gate
from .puzzle_types import resolve_puzzle_type

STATE_NAME = "business_automation_state.json"
MARKETING_DIR = "MARKETING"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _words(value: str) -> set[str]:
    import re
    return {item for item in re.findall(r"[a-z0-9]+", str(value).casefold()) if len(item) > 2}


def _similarity(left: str, right: str) -> float:
    a, b = _words(left), _words(right)
    return len(a & b) / max(1, len(a | b))


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class BusinessAutomation:
    """One stateful service for opportunities, next actions, digital products and marketing."""

    def __init__(self, service) -> None:
        self.service = service
        self.project = Path(service.project)
        self.path = self.project / "data" / STATE_NAME

    def state(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"version": 1, "tasks": {}, "artifacts": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "tasks": {}, "artifacts": {}}

    def save(self, state: dict) -> None:
        state["updated_at"] = _now(); self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp"); temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"); temporary.replace(self.path)

    @staticmethod
    def source_revision(book: dict) -> str:
        meta = dict(book.get("metadata") or {})
        files = meta.pop("files", {}) if isinstance(meta.get("files"), dict) else {}
        fingerprints = {}
        for key in ("print_interior", "print_cover", "front_cover"):
            path = Path(str(files.get(key) or ""))
            if path.is_file():
                fingerprints[key] = {"bytes": path.stat().st_size, "modified": round(path.stat().st_mtime, 3)}
        return _sha({"metadata": meta, "files": fingerprints})

    # -- Opportunities -----------------------------------------------------

    def _background_score(self, meta: dict) -> int:
        try:
            from background_generation.index import BackgroundAssetIndex
            text = " ".join(str(meta.get(key) or "") for key in ("title", "subtitle", "theme", "detected_topic", "series"))
            return min(100, len(BackgroundAssetIndex().approved_choices(text)) * 34)
        except Exception:
            return 0

    @staticmethod
    def _season_score(text: str) -> int:
        month = date.today().month; text = text.casefold()
        targets = {"christmas": (10, 12), "holiday": (10, 12), "halloween": (8, 10), "valentine": (12, 2), "summer": (4, 8), "travel": (4, 8), "camp": (4, 8), "school": (7, 9), "vocabulary": (7, 9), "garden": (2, 6)}
        for term, months in targets.items():
            if term in text:
                return 90 if month in months else 35
        return 65  # evergreen remains valuable.

    def opportunities(self, limit: int = 12) -> list[dict]:
        books = self.service.db.list_books(); rows: list[dict] = []
        topic_counts: dict[str, int] = {}
        for book in books:
            meta = book.get("metadata") or {}; topic = str(meta.get("theme") or meta.get("detected_topic") or "General").casefold()
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        for book in books:
            meta = book.get("metadata") or {}; gate = book_gate(book); title = str(meta.get("title") or "Untitled")
            text = " ".join(str(meta.get(key) or "") for key in ("title", "subtitle", "theme", "detected_topic", "series"))
            topic = str(meta.get("theme") or meta.get("detected_topic") or "General"); puzzle_type = str(meta.get("puzzle_type") or "Word Search")
            source_ready = 100 if gate.get("ready") else 25
            puzzles = int(meta.get("puzzle_count") or 0)
            word_strength = 100 if puzzles >= 100 else 82 if puzzles >= 60 else 70 if puzzles >= 48 else 25
            gap = max(5, 100 - min(90, (topic_counts.get(topic.casefold(), 1) - 1) * 22))
            close = max((_similarity(title, str((other.get("metadata") or {}).get("title") or "")) for other in books if other.get("book_id") != book.get("book_id")), default=0.0)
            duplicate_risk = round(close * 100)
            packages = bool(str(book.get("package_path") or ""))
            marketplace_fit = 90 if packages else 64
            capability = resolve_puzzle_type(meta.get("puzzle_type_id") or puzzle_type)
            digital_fit = 92 if packages and capability and capability.production_available and capability.digital_compatible else 55
            bundle_fit = 80 if topic_counts.get(topic.casefold(), 0) >= 2 else 52
            dimensions = {"topic_quality": source_ready, "word_bank_strength": word_strength, "catalog_gap": gap, "content_uniqueness": 100 - duplicate_risk, "background_readiness": self._background_score(meta), "cover_potential": self._background_score(meta) or 55, "puzzle_type_fit": 90, "digital_product_fit": digital_fit, "bundle_potential": bundle_fit, "seasonal_relevance": self._season_score(text), "marketplace_fit": marketplace_fit, "duplication_risk": duplicate_risk, "cannibalization_risk": duplicate_risk}
            score = round(0.18 * dimensions["topic_quality"] + 0.15 * dimensions["word_bank_strength"] + 0.13 * dimensions["catalog_gap"] + 0.14 * dimensions["content_uniqueness"] + 0.08 * dimensions["background_readiness"] + 0.08 * dimensions["digital_product_fit"] + 0.08 * dimensions["bundle_potential"] + 0.08 * dimensions["seasonal_relevance"] + 0.08 * dimensions["marketplace_fit"])
            risk = "No blocking risk found." if gate.get("ready") and duplicate_risk < 45 else ("Needs content/production review." if not gate.get("ready") else "Similar title/topic already exists in the catalog.")
            reason = ["passes the production gate" if gate.get("ready") else "has a clear repair path", f"{puzzles} puzzles", f"{dimensions['background_readiness']}% approved-background readiness"]
            rows.append({"book": book, "book_id": book.get("book_id"), "title": title, "topic": topic, "puzzle_type": puzzle_type, "score": score, "readiness": source_ready, "dimensions": dimensions, "reason": " • ".join(reason), "main_risk": risk, "next_action": "Prepare publishing package" if packages else "Create book", "requires_background": dimensions["background_readiness"] == 0})
        return sorted(rows, key=lambda row: (-row["score"], row["title"].casefold()))[:limit]

    # -- Persistent next-action queue -------------------------------------

    def _task(self, *, book: dict, kind: str, priority: int, reason: str, action: str, marketplace: str = "", dependencies: list[str] | None = None) -> dict:
        identifier = hashlib.sha1(f"{book['book_id']}|{kind}|{marketplace}".encode()).hexdigest()[:16]
        return {"task_id": identifier, "product_id": book["book_id"], "task_type": kind, "marketplace": marketplace, "priority": priority, "status": "OPEN", "reason": reason, "recommended_action": action, "blocking_issue": "" if priority < 90 else reason, "source": "business_automation", "dependencies": dependencies or []}

    def rebuild_queue(self) -> list[dict]:
        state = self.state(); prior = state.setdefault("tasks", {}); tasks: dict[str, dict] = {}
        for book in self.service.db.list_books():
            meta = book.get("metadata") or {}; package = Path(str(book.get("package_path") or "")); gate = book_gate(book)
            if not gate.get("ready"):
                task = self._task(book=book, kind="FIX_CONTENT", priority=100, reason="Production Gate has blocking content or package issues.", action="Open production check")
                tasks[task["task_id"]] = task; continue
            if not package.is_dir():
                task = self._task(book=book, kind="CREATE_BOOK", priority=82, reason="This checked source has no completed package yet.", action="Create complete package")
                tasks[task["task_id"]] = task; continue
            if self._background_score(meta) == 0:
                task = self._task(book=book, kind="GENERATE_BACKGROUND", priority=64, reason="No topic-matched approved project background is available yet.", action="Open approved background generator")
                tasks[task["task_id"]] = task
            records = self.service.db.marketplace_records(book["book_id"])
            for marketplace in ("amazon", "payhip", "barnes_noble"):
                if records.get(marketplace, {}).get("status") not in {"Ready", "Uploaded", "Published"}:
                    task = self._task(book=book, kind=f"PREPARE_{marketplace.upper()}", priority=72 if marketplace == "amazon" else 58, reason=f"{marketplace.replace('_', ' ').title()} files have not been prepared.", action="Prepare marketplace files", marketplace=marketplace)
                    tasks[task["task_id"]] = task
            payhip = marketplace_handoff_folder(package, "payhip")
            if not (payhip / "customer_product.pdf").is_file():
                task = self._task(book=book, kind="CREATE_DIGITAL_EDITION", priority=68, reason="A customer-safe digital edition has not been prepared.", action="Prepare Payhip digital product", marketplace="payhip")
                tasks[task["task_id"]] = task
            marketing = package / "05_MARKETPLACE_HANDOFFS" / MARKETING_DIR
            artifact = state.get("artifacts", {}).get(f"marketing:{book['book_id']}", {})
            stale = artifact.get("revision") != self.source_revision(book)
            if not marketing.is_dir() or stale:
                task = self._task(book=book, kind="GENERATE_MARKETING_KIT", priority=45, reason="Marketing kit is missing or stale after a source change.", action="Generate marketing kit")
                tasks[task["task_id"]] = task
        # Preserve manual completion only while its prerequisite is unchanged.
        for task_id, task in tasks.items():
            saved = prior.get(task_id, {})
            if saved.get("status") == "COMPLETED": task["status"] = "COMPLETED"
            task["created_at"] = saved.get("created_at") or _now(); task["updated_at"] = _now()
        state["tasks"] = tasks; self.save(state)
        return sorted(tasks.values(), key=lambda row: (row["status"] == "COMPLETED", -row["priority"], row["task_id"]))

    def next_action(self) -> dict | None:
        return next((task for task in self.rebuild_queue() if task["status"] == "OPEN"), None)

    def complete_task(self, task_id: str) -> None:
        state = self.state(); task = state.get("tasks", {}).get(task_id)
        if task: task["status"] = "COMPLETED"; task["updated_at"] = _now(); self.save(state)

    # -- Digital editions and bundles -------------------------------------

    def create_digital_edition(self, book_id: str) -> Path:
        """Reuse the checked Payhip factory; it only creates local buyer files."""
        folder, issues = self.service.prepare(book_id, "payhip")
        if issues: raise ValueError("Payhip preparation needs attention: " + " | ".join(issues))
        return folder

    def create_mini_pack(self, book_id: str, puzzle_pages: int = 12) -> Path:
        """Build a small customer-safe sampler with playable pages and answers.

        It is purposefully conservative: if the source does not contain
        identifiable puzzle and solution pages, it stops instead of creating a
        misleading miniature product.
        """
        from pypdf import PdfReader, PdfWriter
        book = self.service.db.get_book(book_id)
        if not book: raise ValueError("Book was not found in Publishing Center.")
        meta, files = book.get("metadata") or {}, (book.get("metadata") or {}).get("files") or {}
        source = Path(str(files.get("printable_pdf") or files.get("print_interior") or ""))
        if not source.is_file(): raise ValueError("Create the complete package first so a mini pack has a checked customer source.")
        reader = PdfReader(str(source)); playable = []; answers = []
        for index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").upper()
            if "SOLUTION" in text or "ANSWER KEY" in text: answers.append(index)
            elif "PUZZLE" in text or "CRYPTOGRAM" in text or "UNSCRAMBLE" in text or "SUDOKU" in text: playable.append(index)
        selected = playable[:max(1, min(int(puzzle_pages), 25))]
        if not selected or not answers: raise ValueError("This source does not expose enough identifiable playable pages and solution pages for a safe mini pack.")
        package = Path(str(book.get("package_path") or "")); target = package / "05_MARKETPLACE_HANDOFFS" / "digital_mini_pack"; target.mkdir(parents=True, exist_ok=True)
        output = target / "mini_puzzle_pack.pdf"; writer = PdfWriter()
        for page_index in selected + answers: writer.add_page(reader.pages[page_index])
        with output.open("wb") as stream: writer.write(stream)
        title = str(meta.get("title") or "Puzzle Book") + " — Mini Puzzle Pack"
        price = max(2.99, round(float(recommended_prices(meta).get("payhip", 5.99)) * 0.58, 2))
        sheet = target / "MINI_PACK_PUBLISHING_SHEET.txt"; sheet.write_text(
            f"MINI PUZZLE PACK — PUBLISHING SHEET\n{'='*52}\nTitle: {title}\nSuggested price: ${price:.2f}\n"
            f"Customer file: {output.name}\n\nDescription:\nA compact printable sampler from {meta.get('title', 'this puzzle collection')}. "
            f"It includes {len(selected)} playable sample pages plus the source book's answer pages. Digital PDF only; no physical product will be shipped.\n\n"
            "Review the PDF before sale to confirm the selected puzzle pages and answer section are appropriate for this smaller product.\n", encoding="utf-8")
        manifest = {"product_type": "mini_pack", "source_book_id": book_id, "source_revision": self.source_revision(book), "playable_source_pages": [item + 1 for item in selected], "answer_source_pages": [item + 1 for item in answers], "price": price, "created_at": _now()}
        (target / "mini_pack_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return target

    def bundle_candidates(self) -> list[dict]:
        groups: dict[tuple[str, str], list[dict]] = {}
        for book in self.service.db.list_books():
            package = Path(str(book.get("package_path") or "")); meta = book.get("metadata") or {}
            if not package.is_dir() or not Path(str((meta.get("files") or {}).get("print_interior") or "")).is_file(): continue
            key = (str(meta.get("theme") or meta.get("detected_topic") or "General"), str(meta.get("puzzle_type") or "Word Search")); groups.setdefault(key, []).append(book)
        output=[]
        for (topic, kind), books in groups.items():
            if len(books) < 2: continue
            titles = [str(item.get("metadata", {}).get("title") or "") for item in books]
            overlap = max((_similarity(a, b) for i, a in enumerate(titles) for b in titles[i + 1:]), default=0.0)
            if overlap >= .75: continue
            price = recommended_bundle_prices(books)
            output.append({"topic": topic, "puzzle_type": kind, "books": books, "overlap": round(overlap * 100), "price": price, "title": f"{topic} {kind} Collection"})
        return sorted(output, key=lambda item: (-len(item["books"]), item["title"].casefold()))

    def create_bundle(self, candidate: dict) -> Path:
        """Use the existing Etsy bundle builder, including its file-limit guard."""
        books = list(candidate.get("books") or [])
        if len(books) < 2: raise ValueError("A bundle needs at least two compatible completed products.")
        book_ids = [book["book_id"] for book in books]
        folder, _details = self.service.create_etsy_bundle(str(candidate.get("title") or "Puzzle Collection"), book_ids, float(candidate.get("price", {}).get("etsy") or 0))
        return folder

    # -- Marketing ----------------------------------------------------------

    def generate_marketing_kit(self, book_id: str) -> Path:
        book = self.service.db.get_book(book_id)
        if not book: raise ValueError("Book was not found in Publishing Center.")
        package = Path(str(book.get("package_path") or "")); meta = book.get("metadata") or {}; files = meta.get("files") or {}
        cover = Path(str(files.get("front_cover") or ""))
        if not package.is_dir() or not cover.is_file(): raise ValueError("Create the complete package with a front cover before generating marketing assets.")
        target = package / "05_MARKETPLACE_HANDOFFS" / MARKETING_DIR; target.mkdir(parents=True, exist_ok=True)
        title = str(meta.get("title") or "Puzzle Book"); puzzle_count = int(meta.get("puzzle_count") or 0); kind = str(meta.get("puzzle_type") or "Puzzle Book")
        assets = {"social_square.png": (1080, 1080), "social_portrait.png": (1080, 1350), "story_reel.png": (1080, 1920), "pinterest_pin.png": (1000, 1500), "product_hero.png": (1600, 1600)}
        for name, size in assets.items(): self._marketing_image(cover, target / name, size, title, f"{puzzle_count} {kind} challenges" if puzzle_count else kind)
        price = recommended_prices(meta).get("payhip", 0.0)
        copy = self._marketing_copy(meta, price)
        (target / "captions.txt").write_text(copy["captions"], encoding="utf-8")
        (target / "ad_copy.txt").write_text(copy["ad_copy"], encoding="utf-8")
        (target / "hashtags.txt").write_text(copy["hashtags"], encoding="utf-8")
        (target / "video_ad_prompt.txt").write_text(copy["video"], encoding="utf-8")
        revision = self.source_revision(book)
        manifest = {"generated_at": _now(), "source_book_id": book_id, "source_revision": revision, "uses_real_cover": str(cover), "price_reference": {"payhip": price}, "assets": assets, "status": "READY"}
        (target / "marketing_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        state = self.state(); state.setdefault("artifacts", {})[f"marketing:{book_id}"] = {"revision": revision, "path": str(target), "status": "READY", "updated_at": _now()}; self.save(state)
        return target

    @staticmethod
    def _marketing_image(cover: Path, target: Path, size: tuple[int, int], title: str, benefit: str) -> None:
        width, height = size; canvas = Image.new("RGB", size, "#10252a"); draw = ImageDraw.Draw(canvas)
        with Image.open(cover).convert("RGB") as image:
            image.thumbnail((int(width * .68), int(height * .68)), Image.Resampling.LANCZOS)
            x, y = (width - image.width) // 2, int(height * .13); canvas.paste(image, (x, y))
        from font_utils import image_font_candidates, load_image_font
        title_font = load_image_font(image_font_candidates("sans-bold"), max(32, width // 22)); body_font = load_image_font(image_font_candidates("sans"), max(24, width // 34))
        draw.text((width // 2, int(height * .83)), title[:60], anchor="ma", fill="#ffffff", font=title_font, align="center")
        draw.text((width // 2, int(height * .90)), benefit[:70], anchor="ma", fill="#a9ead7", font=body_font, align="center")
        canvas.save(target)

    @staticmethod
    def _marketing_copy(meta: dict, price: float) -> dict[str, str]:
        title = str(meta.get("title") or "This puzzle collection"); count = int(meta.get("puzzle_count") or 0); kind = str(meta.get("puzzle_type") or "puzzle"); topic = str(meta.get("theme") or meta.get("detected_topic") or "themed")
        digital = f"Printable digital PDF • ${price:.2f} • no physical item ships." if price else "Printable digital PDF • no physical item ships."
        return {"captions": f"{title}\n\nTake a screen-free break with {count} {topic.lower()} {kind.lower()} challenges and complete solutions. {digital}\n\nSave it for a quiet evening, travel day, or thoughtful gift.\n", "ad_copy": f"HEADLINE\n{title}\n\nSHORT COPY\n{count} {topic.lower()} {kind.lower()} challenges in one clean, printable collection.\n\nCTA\nExplore the collection\n\nLONG COPY\n{title} gives puzzle fans a focused, easy-to-use collection with clear pages and complete solutions. {digital}\n", "hashtags": "#SladePuzzleCo #PrintablePuzzles #PuzzleBook #ScreenFreeFun #PuzzleTime #AdultPuzzles\n", "video": f"STANDARD (15 sec)\nVertical 9:16 video. Use the real cover for {title}; do not redraw it. Show three text beats: ‘{count} {kind} challenges’ / ‘{topic} theme’ / ‘Print, solve, unwind.’ End: ‘Printable PDF — explore SladePuzzleCo.’\n\nSHORT\nReal cover, {count} {kind} challenges, printable PDF, clear CTA.\n\nULTRA-SHORT\nReal cover + printable puzzle break + CTA.\n"}
