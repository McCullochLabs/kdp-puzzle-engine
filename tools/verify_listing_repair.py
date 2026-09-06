"""Verify a listing-only repair did not alter protected book artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""): h.update(block)
    return h.hexdigest()


def main() -> None:
    baseline=json.loads((PROJECT/"reports"/"PUBLISHING_INTELLIGENCE_REPAIR_BASELINE.json").read_text(encoding="utf-8"))
    rows=[]
    for item in baseline["packages"]:
        package=Path(item["package"]); checks={}
        for relative, expected in item["protected_hashes"].items():
            target=package/relative; actual=digest(target) if target.is_file() else "MISSING"; checks[relative]={"unchanged":actual==expected,"expected":expected,"actual":actual}
        rows.append({"title":item["title"],"package":str(package),"files":checks,"passed":all(value["unchanged"] for value in checks.values())})
    report={"books":rows,"all_protected_files_unchanged":all(row["passed"] for row in rows)}
    (PROJECT/"reports"/"PUBLISHING_INTELLIGENCE_REPAIR_VERIFICATION.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (PROJECT/"reports"/"PUBLISHING_INTELLIGENCE_REPAIR_VERIFICATION.txt").write_text("LISTING REPAIR PRESERVATION VERIFICATION\n\n"+"\n".join(f"{'PASS' if row['passed'] else 'FAIL'} — {row['title']}" for row in rows)+f"\n\nAll protected interior/cover/wrap files unchanged: {report['all_protected_files_unchanged']}\n",encoding="utf-8")
    print(json.dumps({"books":len(rows),"all_protected_files_unchanged":report["all_protected_files_unchanged"]},indent=2))


if __name__=="__main__": main()
