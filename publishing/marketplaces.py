"""Marketplace preparation adapters. They only make files; official API clients can replace them later."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .publisher_base import PublisherBase
from .listing_copy import listing_copy_text, upload_notes_text
from .metadata_service import marketplace_content
from .manual_sheets import write_manual_sheet


def _copy(source: Path | None, target: Path) -> Path | None:
    if not source or not source.is_file(): return None
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); return target


def _text(target: Path, value: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value, encoding="utf-8"); return target


def _handoff_documents(book: dict, platform: str, target: Path) -> list[Path]:
    """One clean copy sheet and one platform-specific upload note per handoff."""
    return [
        _text(target / "READY_TO_COPY_LISTING.txt", listing_copy_text(book, platform)),
        _text(target / "UPLOAD_NOTES.txt", upload_notes_text(book, platform)),
        write_manual_sheet(book, platform, target),
    ]


class PreparedPublisher(PublisherBase):
    key = ""
    label = ""
    # Official seller-portal home page. The UI may open it in the user's
    # browser; automation is intentionally out of scope for these adapters.
    portal_url = ""

    def validate(self, book: dict) -> list[str]:
        meta, files = book["metadata"], book["metadata"].get("files", {})
        missing = [label for label, value in (("title", meta.get("title")), ("author", meta.get("author"))) if not value]
        for label, value in (("interior PDF", files.get("print_interior")), ("cover PDF", files.get("print_cover"))):
            if not value or not Path(str(value)).is_file():
                missing.append(label)
        return [f"Add {item} before preparing {self.label}." for item in missing]

    def common_metadata(self, book: dict) -> str:
        meta = book["metadata"]
        return json.dumps(meta, indent=2, ensure_ascii=False) + "\n"


class KdpPublisher(PreparedPublisher):
    key, label = "amazon", "Amazon KDP"
    portal_url = "https://kdp.amazon.com/en_US/bookshelf"
    def prepare(self, book: dict, target: Path) -> list[Path]:
        meta, files = book["metadata"], book["metadata"].get("files", {}); created = []
        for source, name in ((files.get("print_interior"), "interior.pdf"), (files.get("print_cover"), "cover.pdf")):
            copied = _copy(Path(source) if source else None, target / name)
            if copied: created.append(copied)
        content = marketplace_content(meta)
        created += [_text(target / "metadata.txt", self.common_metadata(book)), _text(target / "description.txt", content["platform_descriptions"]["amazon"] + "\n"), _text(target / "keywords.txt", "\n".join(content["amazon_keywords"]) + "\n"), _text(target / "categories.txt", "\n".join(content["ingram_subjects"]) + "\n"), _text(target / "pricing.txt", f"Suggested Amazon paperback price: ${meta['price']['amazon']:.2f}\n"), _text(target / "publishing_checklist.txt", "Upload interior.pdf and cover.pdf. Copy the reviewed metadata. Run KDP Print Previewer before publishing. Do not use Slade Puzzles as the contributor name.\n")]
        return created + _handoff_documents(book, self.key, target)


class EtsyPublisher(PreparedPublisher):
    key, label = "etsy", "Etsy"
    portal_url = "https://www.etsy.com/shop-manager"
    def validate(self, book: dict) -> list[str]:
        meta, files = book["metadata"], book["metadata"].get("files", {})
        download = Path(str(files.get("printable_pdf") or files.get("print_interior") or ""))
        issues = [f"Add {item} before preparing Etsy." for item, value in (("title", meta.get("title")), ("author", meta.get("author"))) if not value]
        if not download.is_file():
            issues.append("Create the complete package first so Etsy has a customer digital-download PDF.")
        elif download.stat().st_size > 20 * 1024 * 1024:
            issues.append("Split or ZIP the customer download because Etsy instant-download files are limited to 20 MB each.")
        return issues
    def prepare(self, book: dict, target: Path) -> list[Path]:
        meta, files = book["metadata"], book["metadata"].get("files", {}); created = []
        printable = files.get("printable_pdf") or files.get("print_interior")
        copied = _copy(Path(printable) if printable else None, target / "printable.pdf")
        if copied: created.append(copied)
        cover = Path(files["front_cover"]) if files.get("front_cover") else None
        if cover and cover.exists():
            with Image.open(cover).convert("RGB") as image:
                image.thumbnail((2000, 2000), Image.LANCZOS)
                for index, label in enumerate(("Puzzle Book Cover", "Instant Digital Download", f"Includes {meta['puzzle_count']} Puzzles", "Solutions Included"), 1):
                    card = image.copy(); draw = ImageDraw.Draw(card); draw.rectangle((0, max(0, card.height-150), card.width, card.height), fill=(20, 25, 34))
                    draw.text((35, max(25, card.height-115)), label, fill="white", font=ImageFont.load_default())
                    output = target / f"preview-{index:02d}.jpg"; card.save(output, quality=92); created.append(output)
                thumb = target / "thumbnail.jpg"; image.thumbnail((600, 600), Image.LANCZOS); image.save(thumb, quality=90); created.append(thumb)
        content = marketplace_content(meta)
        created += [_text(target / "title.txt", meta["title"] + "\n"), _text(target / "description.txt", content["platform_descriptions"]["etsy"] + "\n"), _text(target / "tags.txt", "\n".join(content["etsy_tags"]) + "\n"), _text(target / "price.txt", f"Suggested digital price: ${meta['price']['etsy']:.2f}\n"), _text(target / "listing_checklist.txt", "Review Etsy's current digital-product rules, product type, tax settings, and delivery file before publishing. API publishing is intentionally disabled until official Etsy credentials are connected.\n")]
        return created + _handoff_documents(book, self.key, target)


class IngramPublisher(PreparedPublisher):
    key, label = "ingram", "IngramSpark"
    portal_url = "https://www.ingramspark.com"
    def validate(self, book: dict) -> list[str]:
        issues = super().validate(book)
        meta = book["metadata"]
        if not meta.get("isbn"):
            issues.append("Assign your own ISBN before preparing IngramSpark distribution.")
        issues.append("Build the final cover on the current IngramSpark template; a KDP wrap is reference-only because spine dimensions can differ.")
        return issues

    def prepared_status(self, book: dict) -> str:
        return "Prepared — Final Cover Needed"

    def prepare(self, book: dict, target: Path) -> list[Path]:
        meta, files = book["metadata"], book["metadata"].get("files", {}); created = []
        for source, name in (
            (files.get("print_interior"), "interior_starting_file.pdf"),
            (files.get("print_cover"), "kdp_cover_REFERENCE_ONLY.pdf"),
            (files.get("front_cover"), "front_cover_reference.png"),
        ):
            copied = _copy(Path(source) if source else None, target / name)
            if copied: created.append(copied)
        created += [_text(target / "START_HERE.txt", "STATUS: PREPARED — FINAL INGRAMSPARK COVER NEEDED\n\nThis folder has the interior starting file and visual references. Before uploading, create a final cover with the current IngramSpark template for this book's exact trim, paper, binding, and final page count.\n\nDo not upload kdp_cover_REFERENCE_ONLY.pdf to IngramSpark.\n"), _text(target / "metadata.txt", self.common_metadata(book)), _text(target / "isbn.txt", (meta.get("isbn") or "No ISBN assigned\n")), _text(target / "pricing.txt", f"Suggested list price: ${meta['price']['ingram']:.2f}\n"), _text(target / "subjects.txt", "\n".join(meta["ingram_subjects"]) + "\n"), _text(target / "distribution_checklist.txt", "Create the final cover on the current IngramSpark template first. Then confirm your ISBN, trim, paper, discount, return policy, and territory choices. If distributing this ISBN through IngramSpark, do not automatically enable KDP Expanded Distribution for the same ISBN.\n")]
        return created + _handoff_documents(book, self.key, target)


class WebsitePublisher(PreparedPublisher):
    key, label = "website", "Direct Website"
    def validate(self, book: dict) -> list[str]:
        meta, files = book["metadata"], book["metadata"].get("files", {})
        download = Path(str(files.get("printable_pdf") or files.get("print_interior") or ""))
        issues = [f"Add {item} before preparing Direct Website." for item, value in (("title", meta.get("title")), ("author", meta.get("author"))) if not value]
        if not download.is_file():
            issues.append("Create the complete package first so the website has a customer download PDF.")
        return issues
    def prepare(self, book: dict, target: Path) -> list[Path]:
        meta, files = book["metadata"], book["metadata"].get("files", {}); created = []
        export = {"book_id": book["book_id"], "title": meta["title"], "subtitle": meta["subtitle"], "description": meta["description"], "tags": meta["website_tags"], "products": [{"name": "Printable PDF", "price": meta["price"]["direct_digital"], "file": files.get("printable_pdf") or files.get("print_interior")}, {"name": "Paperback", "price": meta["price"]["direct_print"], "file": None}]}
        created += [_text(target / "product.json", json.dumps(export, indent=2, ensure_ascii=False) + "\n"), _text(target / "product.csv", "title,product,price\n" + f'"{meta["title"]}","Printable PDF",{meta["price"]["direct_digital"]:.2f}\n' + f'"{meta["title"]}","Paperback",{meta["price"]["direct_print"]:.2f}\n')]
        if files.get("front_cover"):
            copied = _copy(Path(files["front_cover"]), target / "product-cover.png")
            if copied: created.append(copied)
        return created + _handoff_documents(book, self.key, target)


class PlaceholderPublisher(PreparedPublisher):
    def prepare(self, book: dict, target: Path) -> list[Path]:
        meta = book["metadata"]
        created = [_text(target / "metadata.txt", self.common_metadata(book)), _text(target / "README.txt", f"{self.label} is prepared as a modular future connection. No credentials are stored in this package. Use the official {self.label} portal until its official API is configured.\nSuggested price: ${meta['price'].get(self.key, meta['price']['direct_print']):.2f}\n")]
        return created + _handoff_documents(book, self.key, target)


class TemplateCoverPublisher(PlaceholderPublisher):
    """Never label a KDP-sized wrap as ready for a different printer."""
    def validate(self, book: dict) -> list[str]:
        issues = super().validate(book)
        issues.append(f"Build the final cover on the current {self.label} template; the KDP wrap is reference-only because spine dimensions can differ.")
        return issues

    def prepared_status(self, book: dict) -> str:
        return "Prepared — Final Cover Needed"

    def prepare(self, book: dict, target: Path) -> list[Path]:
        """Supply reusable source files but never mislabel a KDP wrap as final."""
        files = book["metadata"].get("files", {})
        created: list[Path] = []
        for source, name in (
            (files.get("print_interior"), "interior_starting_file.pdf"),
            (files.get("print_cover"), "kdp_cover_REFERENCE_ONLY.pdf"),
            (files.get("front_cover"), "front_cover_reference.png"),
        ):
            copied = _copy(Path(source) if source else None, target / name)
            if copied:
                created.append(copied)
        created.append(_text(target / "START_HERE.txt", f"STATUS: PREPARED — FINAL {self.label.upper()} COVER NEEDED\n\nThis folder has the interior starting file and visual references. Before uploading, create a final cover with the current {self.label} template for this book's exact trim, paper, binding, and final page count.\n\nDo not upload kdp_cover_REFERENCE_ONLY.pdf as the final {self.label} cover.\n"))
        return created + super().prepare(book, target)


class LuluPublisher(TemplateCoverPublisher): key, label = "lulu", "Lulu Direct"; portal_url = "https://www.lulu.com"
class BookVaultPublisher(TemplateCoverPublisher): key, label = "bookvault", "BookVault"; portal_url = "https://www.bookvault.app"


class BarnesNoblePublisher(PlaceholderPublisher):
    key, label = "barnes_noble", "Barnes & Noble"
    portal_url = "https://www.barnesandnoblepress.com"
    def validate(self, book: dict) -> list[str]:
        issues = super().validate(book)
        issues.append("Build the final cover on the current Barnes & Noble Press template; the KDP wrap is reference-only because spine dimensions can differ.")
        return issues

    def prepared_status(self, book: dict) -> str:
        return "Prepared — Final Cover Needed"

    def prepare(self, book: dict, target: Path) -> list[Path]:
        files = book["metadata"].get("files", {})
        created: list[Path] = []
        for source, name in (
            (files.get("print_interior"), "interior_starting_file.pdf"),
            (files.get("print_cover"), "kdp_cover_REFERENCE_ONLY.pdf"),
            (files.get("front_cover"), "front_cover_reference.png"),
        ):
            copied = _copy(Path(source) if source else None, target / name)
            if copied:
                created.append(copied)
        created.append(_text(target / "START_HERE.txt", "STATUS: PREPARED — FINAL BARNES & NOBLE PRESS COVER NEEDED\n\nThis folder has the interior starting file and visual references. Before uploading, create a final cover with the current B&N Press template for this book's exact trim and final page count.\n\nDo not upload kdp_cover_REFERENCE_ONLY.pdf as the final B&N Press cover.\n"))
        created += [_text(target / "BN_PRESS_PREFLIGHT.txt", "B&N PRESS PREFLIGHT\n\n"
                           "Use the current B&N Press Cover Template Tool after the final interior page count and trim size are fixed. "
                           "It precisely measures front, spine, and back; do not move its template elements.\n\n"
                           "Interior and cover PDFs must pass B&N Press pre-press review. B&N documents an 18–800 page range for white/cream interiors and a 650 MB print-project maximum; verify current rules before upload.\n")]
        return created + super().prepare(book, target)


class PayhipPublisher(PreparedPublisher):
    key, label = "payhip", "Payhip"
    portal_url = "https://payhip.com/"
    def validate(self, book: dict) -> list[str]:
        meta, files = book["metadata"], book["metadata"].get("files", {})
        download = Path(str(files.get("printable_pdf") or files.get("print_interior") or ""))
        issues = [f"Add {item} before preparing Payhip." for item, value in (("title", meta.get("title")), ("author", meta.get("author"))) if not value]
        if not download.is_file():
            issues.append("Create the complete package first so Payhip has a customer digital-download PDF.")
        elif download.stat().st_size > 5 * 1024 * 1024 * 1024:
            issues.append("Split the customer download because Payhip currently limits each uploaded file to 5 GB.")
        return issues
    def prepare(self, book: dict, target: Path) -> list[Path]:
        from integrations.payhip.digital_factory import build_payhip_digital_handoff
        return build_payhip_digital_handoff(book, target)


PUBLISHERS = {publisher.key: publisher for publisher in (KdpPublisher(), EtsyPublisher(), IngramPublisher(), WebsitePublisher(), LuluPublisher(), BookVaultPublisher(), BarnesNoblePublisher(), PayhipPublisher())}
