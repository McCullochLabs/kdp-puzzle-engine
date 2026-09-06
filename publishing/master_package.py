"""Create a clear, platform-aware master handoff beside every finished book."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .package_layout import package_file


PLATFORM_GUIDES = {
    "KDP": "https://kdp.amazon.com/en_US/help/topic/G201857950",
    "Etsy": "https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings",
    "IngramSpark": "https://www.ingramspark.com/blog/file-requirements-for-print-books",
    "Lulu": "https://help.lulu.com/en/support/solutions/articles/64000255462",
    "Bookvault": "https://help.bookvault.app/hubfs/Guide%20To%20PDFs%20-%20Digital%20Version%20.pdf",
    "Barnes & Noble": "https://help.barnesandnoble.com/hc/en-us/articles/5353991979163-How-to-Submit-Content",
    "Shopify": "https://shopify.dev/docs/api/admin-graphql",
    "WooCommerce": "https://developer.woocommerce.com/docs/apis/rest-api/v3/products",
    "Wix": "https://dev.wix.com/docs/rest/business-solutions/stores",
}


def _copy(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size == source.stat().st_size:
        return True
    if target.exists():
        target.unlink()
    # A hard link saves disk space when the package lives on the same drive.
    # Copy only when Windows/filesystem rules do not allow a link.
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
    return True


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_master_package(folder: Path, metadata: dict) -> Path | None:
    """Make a safe upload map without ever modifying the original package files."""
    # New packages use the organized layout; package_file also preserves
    # compatibility with earlier flat packages.
    interior = package_file(folder, "interior.pdf")
    cover = package_file(folder, "kdp_full_wrap.pdf")
    front = package_file(folder, "front_cover.png")
    if not interior.is_file() or not cover.is_file():
        return None

    root = folder / "MASTER_RELEASE_PACKAGE"
    root.mkdir(exist_ok=True)
    title = str(metadata.get("title") or folder.name)
    author = str(metadata.get("author") or "Jordan M. Slade")
    trim = str(metadata.get("trim_size") or "8.5x11")
    pages = str(metadata.get("page_count") or "")
    metadata_copy = dict(metadata)
    metadata_copy["master_package_note"] = "This folder is a platform-aware handoff. Reuse the interior only when the platform's trim, paper, bleed, and margin requirements match. Never assume a KDP full cover wrap fits another printer."
    _write(root / "MASTER_METADATA.json", json.dumps(metadata_copy, indent=2, ensure_ascii=False) + "\n")
    _write(root / "00_READ_ME_FIRST.txt", f"""MASTER RELEASE PACKAGE
{'=' * 52}
Book: {title}
Contributor: {author}
Trim size: {trim}
Interior pages: {pages or 'see interior PDF'}

WHAT CAN BE REUSED
• The interior PDF is the source print file. It can be reused only when a platform's trim size, bleed, margins, and paper choice match this book.
• The KDP full cover wrap is ready for Amazon KDP only. Do not upload it to another printer without rebuilding it on that printer's template; spine width and cover dimensions can differ.
• The front-cover PNG is for listing images and previews, not a print wrap.

START HERE
1. Use 01_KDP_UPLOAD for Amazon KDP.
2. Use 02_ETSY_DIGITAL or 03_DIRECT_WEBSITE for the buyer-download PDF.
3. Use the printer-specific folders for IngramSpark, Lulu, and Bookvault. Each contains the reusable interior plus clear instructions for the required platform cover template.
4. Before every upload, review the platform's current official guide linked in that folder and run its upload preview/proof.
""")

    # KDP accepts this project’s paired interior and full-wrap PDF.
    kdp = root / "01_KDP_UPLOAD"
    _copy(interior, kdp / "interior.pdf"); _copy(cover, kdp / "cover.pdf")
    _write(kdp / "UPLOAD_NOTES.txt", f"""KDP UPLOAD
• Upload interior.pdf as the paperback manuscript and cover.pdf as the full paperback wrap.
• This cover contains back, spine, and front in one PDF.
• Use the KDP Print Previewer before publishing.
Official guidance: {PLATFORM_GUIDES['KDP']}
""")

    # Digital customers need the playable interior, not a print wrap.
    etsy = root / "02_ETSY_DIGITAL"
    _copy(interior, etsy / "digital_download.pdf"); _copy(front, etsy / "listing_cover.png")
    _write(etsy / "LISTING_UPLOAD_PLAN.txt", f"""ETSY DIGITAL DOWNLOAD
Upload digital_download.pdf as the customer’s puzzle-book file. Do not upload the KDP print cover as the purchased download.
The included listing_cover.png is for your listing imagery. Etsy currently allows up to five digital files, up to 20 MB each; use a ZIP only if your buyer download needs multiple files.
Before listing, confirm the file size and use a clear buyer-facing filename.
Official guidance: {PLATFORM_GUIDES['Etsy']}
""")

    website = root / "03_DIRECT_WEBSITE"
    _copy(interior, website / "digital_download.pdf"); _copy(front, website / "product_cover.png")
    _write(website / "PRODUCT_SETUP.txt", "DIRECT WEBSITE PRODUCT\n\nUse digital_download.pdf for a downloadable puzzle-book product. Use product_cover.png as the product image. The print wrap is not a customer download. Set the product description, price, tax, delivery, and refund terms in your own store platform.\n")

    for number, platform, slug in (("03A", "Shopify", "shopify"), ("03B", "WooCommerce", "woocommerce"), ("03C", "Wix", "wix")):
        target = root / f"{number}_{slug.upper()}"
        _copy(interior, target / "digital_download.pdf"); _copy(front, target / "product_cover.png")
        _write(target / "PRODUCT_HANDOFF.txt", f"""{platform.upper()} PRODUCT HANDOFF
This folder is a safe local handoff, not a live listing. Use digital_download.pdf only for a deliberately configured digital product. Use product_cover.png as the primary product image.

For a physical product, create the storefront listing separately and connect its fulfillment route (for example, Lulu) before accepting orders. Do not give customers a printer production wrap as a digital download.
Official developer guidance: {PLATFORM_GUIDES[platform]}
""")

    for number, platform, slug in (("04", "IngramSpark", "ingramspark"), ("05", "Lulu", "lulu"), ("06", "Bookvault", "bookvault")):
        target = root / f"{number}_{slug.upper()}"
        _copy(interior, target / "interior_reusable_if_spec_matches.pdf")
        _copy(front, target / "front_cover_reference.png")
        _write(target / "BUILD_PLATFORM_COVER_FIRST.txt", f"""{platform.upper()} PRINT HANDOFF
The interior file is supplied as a possible starting point. Reuse it only after confirming its trim size, bleed, margins, paper selection, and page count match your {platform} title setup.

The Amazon KDP wrap is intentionally not copied here. Build a new full cover spread using {platform}'s current template/calculator; printer templates use their own spine width and cover dimensions.

Then upload the platform-specific interior and newly built cover as separate PDFs. Confirm embedded fonts, flattened transparency, no crop/trim marks, and 300-DPI images where applicable. Order or review a proof before release.
Official guidance: {PLATFORM_GUIDES[platform]}
""")

    bn = root / "07_BARNES_NOBLE"
    _copy(interior, bn / "interior_reusable_if_spec_matches.pdf")
    _copy(front, bn / "front_cover_listing_image.png")
    _write(bn / "CATALOG_HANDOFF.txt", f"""BARNES & NOBLE HANDOFF
The interior file is supplied as a possible starting point. Reuse it only after confirming its trim size, bleed, margins, paper selection, and page count match your B&N Press setup. The Amazon KDP wrap is intentionally not copied here; build the final cover on B&N Press's current template.
For catalog merchandising, use a single front-cover image—not the full KDP wrap. Keep title, contributor, ISBN, price, description, and categories consistent with your selected distribution route.
Official content guidance: {PLATFORM_GUIDES['Barnes & Noble']}
""")
    return root
