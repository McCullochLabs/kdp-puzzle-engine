"""Read-only conversational checks over the canonical catalog and existing QA."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading

from .studio_codex import RequestCancelled

_CHECK_LOCK = threading.Lock()


def check_saved_book(project, book_id, cancel=None):
    """Inspect a selected catalog identity; never accept a model-supplied path."""
    def cancelled():
        if cancel is not None and cancel.is_set():
            raise RequestCancelled("Book check cancelled.")
    cancelled()
    if not isinstance(book_id, str) or not book_id.strip() or len(book_id) > 200 or any(ord(c) < 32 for c in book_id):
        raise ValueError("Choose a saved book before checking its actual files.")
    project = Path(project).resolve()
    catalog = project / "data" / "books.db"
    if not catalog.is_file():
        raise ValueError("The saved catalog is unavailable. Open My books and choose an existing book.")
    if not _CHECK_LOCK.acquire(blocking=False):
        raise ValueError("The previous local book check is still finishing. Wait a moment and try again.")
    try:
        # Do not initialize/migrate the catalog for a read-only conversational action.
        with closing(sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT book_id, metadata_json, package_path FROM books WHERE book_id=?", (book_id,)).fetchone()
        if row is None:
            raise ValueError("The selected book is no longer in the catalog. Choose it again in My books.")
        metadata = json.loads(row["metadata_json"])
        if not isinstance(metadata, dict):
            raise ValueError("The saved book metadata needs review before its files can be checked.")
        raw_folder = str(row["package_path"] or "").strip()
        if not raw_folder or not Path(raw_folder).is_dir():
            raise ValueError("Create or recover this book's complete package before running local checks.")
        folder = Path(raw_folder)
        cancelled()
        from .product_qa import inspect_product
        from preflight import preflight
        qa = inspect_product(project, folder, metadata).to_dict()
        cancelled()
        passed, findings = preflight(folder)
        cancelled()
        return {"book_id": book_id, "title": str(metadata.get("title") or "Untitled book"),
                "qa": qa, "preflight": {"passed": passed, "findings": findings}}
    finally:
        _CHECK_LOCK.release()


def book_check_text(result):
    """Describe local evidence without granting owner or marketplace approval."""
    qa = result["qa"]
    summary = qa["summary"]
    print_checks = result["preflight"]
    lines = ["Local book check: " + result["title"],
             "PDF preflight: " + ("passed" if print_checks["passed"] else "need attention"),
             f"Product QA: {qa['status']} ({summary['blockers']} blocker(s), {summary['warnings']} review note(s))."]
    problems = [line for line in print_checks["findings"] if line.startswith(("FAIL", "WARN"))]
    problems.extend(row["message"] for row in qa["findings"] if not row["passed"] and row["severity"] in ("BLOCKER", "WARNING"))
    if problems:
        lines.extend("- " + text for text in dict.fromkeys(problems) if text)
    lines.append("These are local checks. Owner review and KDP Print Previewer remain separate steps; no approval or marketplace status was changed.")
    return "\n".join(lines)


_EXPORT_LOCK = threading.Lock()


def export_saved_book(project, book_id, cancel=None):
    """Prepare a versioned local KDP handoff from the selected canonical identity.

    No remote calls, catalog writes, release locks or approval changes occur.
    """
    from uuid import uuid4
    from integrations.factory import MasterProductFactory
    from integrations.registry import get_export_integration
    def cancelled():
        if cancel is not None and cancel.is_set():
            raise RequestCancelled("Export cancelled. Any completed local files remain for recovery.")
    cancelled()
    if not _EXPORT_LOCK.acquire(blocking=False):
        raise ValueError("A local export is already finishing. Wait and try again.")
    try:
        project = Path(project).resolve()
        if not isinstance(book_id, str) or not book_id.strip() or len(book_id)>200:
            raise ValueError("Choose a saved book before exporting.")
        catalog = project / 'data' / 'books.db'
        def saved():
            with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)) as db:
                db.row_factory=sqlite3.Row
                row=db.execute('SELECT * FROM books WHERE book_id=?',(book_id,)).fetchone()
            if row is None: raise ValueError("The selected book is no longer saved.")
            return dict(row)
        snapshot=saved()
        folder=Path(str(snapshot.get('package_path') or '')).resolve()
        if not folder.is_relative_to(project/'out') or not folder.is_dir():
            raise ValueError("Export requires a complete saved package inside this project's out folder.")
        metadata=json.loads(snapshot['metadata_json'])
        book=dict(snapshot,metadata=metadata)
        product=MasterProductFactory.from_book_record(book,price_channel='amazon')
        from hashlib import sha256
        paths=[Path(a.path).resolve() for a in product.artifacts]
        if any(not path.is_relative_to(folder) for path in paths):
            raise ValueError("Export artifacts must belong to the selected book's package.")
        from .package_layout import package_file
        canonical_print={'print_interior':'interior.pdf','print_cover':'kdp_full_wrap.pdf'}
        for artifact in product.artifacts:
            purpose=getattr(artifact.purpose,'value',str(artifact.purpose))
            if purpose in canonical_print and Path(artifact.path).resolve()!=package_file(folder,canonical_print[purpose]).resolve():
                raise ValueError("Export print assets must match the selected book files checked by QA.")
        paths.extend(folder.glob('*.puzzles.json'))
        paths.extend(folder.glob('PACKAGE_SOURCE_RECORD.json'))
        interior=package_file(folder,'interior.pdf').resolve()
        source=package_file(folder,'PACKAGE_SOURCE_RECORD.json').resolve()
        if not interior.is_relative_to(folder) or not source.is_relative_to(folder):
            raise ValueError('Export source evidence must belong to the selected package.')
        evidence_files=[('PACKAGE_SOURCE_RECORD.json',source),('interior.puzzles.json',interior.with_suffix('.puzzles.json')),('interior.typography.json',interior.with_suffix('.typography.json'))]
        evidence_files=[(name,path) for name,path in evidence_files if path.is_file()]
        if any(not path.resolve().is_relative_to(folder) for _,path in evidence_files):
            raise ValueError('Export source evidence must belong to the selected package.')
        from .sudoku_typography import configured_package_typography
        configured_package_typography(folder)
        paths.extend(path for _,path in evidence_files)
        paths=list(dict.fromkeys(paths))
        def file_hashes():
            return {str(path):sha256(path.read_bytes()).hexdigest() for path in paths}
        validated_hashes=file_hashes()
        from collections import Counter
        expected_artifacts=Counter(sha256(Path(a.path).read_bytes()).hexdigest() for a in product.artifacts)
        evidence=check_saved_book(project,book_id,cancel)
        if not evidence['preflight']['passed'] or evidence['qa']['summary']['blockers']:
            raise ValueError("Export blocked by local QA or preflight findings. Ask to check this book for details.")
        if saved()!=snapshot:
            raise ValueError("The selected book changed during validation. Submit the export again.")
        if file_hashes()!=validated_hashes:
            raise ValueError("Book files changed during validation. Submit the export again.")
        adapter=get_export_integration('amazon_kdp')
        if adapter is None: raise ValueError("The local KDP export adapter is unavailable.")
        cancelled()
        destination=project/'out'/'conversational_exports'/uuid4().hex
        result=adapter.export_package(product,destination)
        if not result.success: raise ValueError(result.message)
        exported=Path(result.recovery['export_path']).resolve()
        if not exported.is_relative_to(destination.resolve()):
            raise ValueError("The export adapter returned an unexpected destination.")
        copied=Counter(sha256(path.read_bytes()).hexdigest() for path in (exported/'files').rglob('*') if path.is_file())
        if copied!=expected_artifacts or file_hashes()!=validated_hashes or saved()!=snapshot:
            raise ValueError("Export integrity changed during copying. The local draft is retained for recovery; do not upload it.")
        copied_evidence={}
        if evidence_files:
            import shutil
            evidence_root=exported/'LOCAL_SOURCE_EVIDENCE'
            evidence_root.mkdir(exist_ok=False)
            for name,path in evidence_files:
                cancelled()
                target=evidence_root/name
                shutil.copy2(path,target)
                if sha256(target.read_bytes()).hexdigest()!=validated_hashes[str(path)]:
                    raise ValueError('Export source evidence integrity changed during copying; local files retained.')
                copied_evidence[name]=validated_hashes[str(path)]
        if file_hashes()!=validated_hashes or saved()!=snapshot:
            raise ValueError('Export source evidence integrity changed during copying; local files retained.')
        validation=dict(book_id=book_id,source_sha256=validated_hashes,copied_artifact_count=sum(copied.values()),status='LOCAL_COPY_VERIFIED_OWNER_REVIEW_PENDING')
        if copied_evidence:validation['local_source_evidence_sha256']=copied_evidence
        (exported/'LOCAL_VALIDATION.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
        cancelled()
        return dict(book_id=book_id,title=evidence['title'],export_path=str(result.recovery['export_path']),local_checks=evidence)
    finally:
        _EXPORT_LOCK.release()


def book_export_text(result):
    return ("Local KDP export prepared: "+result['title']+"\nFiles: "+result['export_path']+
            "\nNothing was uploaded. No owner approvals, release locks, or marketplace statuses changed. "
            "Human review, Print Previewer and physical proof remain separate gates.")
