"""Plain-English Payhip customer communication templates.

The returned text is for manual Payhip configuration.  It intentionally does
not send mail, create campaigns, or claim a store integration.
"""
from __future__ import annotations


def store_receipt(brand: str = "SladePuzzleCo") -> dict[str, str]:
    brand = str(brand or "SladePuzzleCo").strip()
    return {
        "subject": "Thank you for your puzzle purchase!",
        "message": (
            "Thank you for your purchase! I hope you enjoy your new puzzle collection.\n\n"
            "Your digital download is available through the link included with this receipt. "
            "If you have trouble accessing your files, please use the store contact information and we will be glad to help.\n\n"
            f"Check back with {brand} for new puzzle books, printable packs, themed collections, and bundles.\n\n"
            "Thanks again for supporting independent puzzle publishing!"
        ),
    }


def product_receipt(metadata: dict) -> dict[str, str]:
    """Optional product-specific language, using a custom value when supplied."""
    custom = metadata.get("payhip_receipt") if isinstance(metadata.get("payhip_receipt"), dict) else {}
    title = str(metadata.get("title") or "your puzzle collection").strip()
    subject = str(custom.get("subject") or f"Your {title} download is ready").strip()
    message = str(custom.get("message") or (
        f"Thank you for choosing {title}. Your download is ready through the link in this receipt.\n\n"
        "For the best experience, open the PDF in a current PDF reader and print at actual size when you want a paper copy. "
        "If you need help with access, please use the store contact information."
    )).strip()
    return {"subject": subject, "message": message}


def store_setup_sheet(brand: str = "SladePuzzleCo") -> str:
    receipt = store_receipt(brand)
    return "\n".join((
        "PAYHIP — STORE SETUP SHEET", "=" * 56,
        "Enter these store-wide settings once in Payhip. This document does not change your online store.", "",
        "STORE NAME / BRAND", brand, "",
        "CUSTOMER EMAIL RECEIPT — STORE SETUP (ENTER ONCE)", "-" * 56,
        "SUBJECT — COPY:", receipt["subject"], "", "MESSAGE — COPY:", receipt["message"], "",
        "STORE-WIDE REVIEW", "-" * 56,
        "• Add your real support/contact wording in Payhip before going live.",
        "• Review customer-account, store-policy, checkout, tax, and visibility settings available in your current Payhip dashboard.",
        "• Optional future fields: related-product suggestion, bundle mention, coupon code, and mailing-list invitation. Add only when you have the matching Payhip setting and a truthful offer.",
        "• Recheck Payhip's current help articles before final store setup.", "",
    ))
