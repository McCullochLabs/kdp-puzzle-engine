"""Print the read-only Phase 1 legacy-content migration preview as JSON."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from word_intelligence.migration_preview import preview_legacy_migration


if __name__ == "__main__":
    print(json.dumps(preview_legacy_migration(ROOT), indent=2, sort_keys=True))
