"""Safe diagnostic: verifies Gemini listing access without revealing credentials."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main() -> None:
    from publishing import PublishingService
    from publishing.listing_intelligence import GeminiCredentials, GeminiListingProvider, verified_facts
    creds = GeminiCredentials.load()
    print("configured=" + str(bool(creds)), flush=True)
    if not creds:
        return
    manifest = json.loads((PROJECT / "reports" / "COMMERCIAL_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    wanted = {Path(str(item["package"])).resolve() for item in manifest["packages"]}
    service = PublishingService(PROJECT)
    book = next(item for item in service.db.list_books() if Path(str(item["package_path"])).resolve() in wanted)
    try:
        output = GeminiListingProvider(creds, timeout=12).generate_listing(verified_facts(book, "amazon"))
        print("result=success", flush=True)
        print("fields=" + ",".join(sorted(output)), flush=True)
    except Exception as exc:
        print("result=fallback_required", flush=True)
        print("reason=" + type(exc).__name__ + ": " + str(exc), flush=True)


if __name__ == "__main__":
    main()
