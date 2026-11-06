"""Small SQLite store that can grow to a large catalog without changing theme files."""
from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

MARKETPLACES = ("amazon", "etsy", "ingram", "website", "lulu", "bookvault", "barnes_noble", "payhip")
# Confirmed upload/live states. Automated flows (prepare, local scans, future
# API/browser adapters) must never move a marketplace backwards from these or
# overwrite the identifiers the user confirmed; only explicit manual saves may.
PROTECTED_STATUSES = ("Uploaded", "Published")


class _ClosingConnection(sqlite3.Connection):
    """Commit/rollback like sqlite3's context manager, then release the file."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class PublishingDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path; self.db_path.parent.mkdir(parents=True, exist_ok=True); self._setup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, factory=_ClosingConnection); connection.row_factory = sqlite3.Row; return connection

    def _setup(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS books (book_id TEXT PRIMARY KEY, source_key TEXT UNIQUE NOT NULL, metadata_json TEXT NOT NULL, metadata_locked INTEGER NOT NULL DEFAULT 0, package_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS marketplace_status (book_id TEXT NOT NULL, marketplace TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Not Prepared', external_id TEXT DEFAULT '', url TEXT DEFAULT '', updated_at TEXT NOT NULL, PRIMARY KEY (book_id, marketplace), FOREIGN KEY(book_id) REFERENCES books(book_id));
                CREATE TABLE IF NOT EXISTS isbns (isbn TEXT PRIMARY KEY, book_id TEXT, title TEXT, format TEXT, source TEXT, assigned_at TEXT);
                CREATE TABLE IF NOT EXISTS bundles (bundle_id TEXT PRIMARY KEY, title TEXT NOT NULL, book_ids_json TEXT NOT NULL, metadata_json TEXT NOT NULL, output_path TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS approved_production_queue (queue_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'Approved', added_at TEXT NOT NULL, updated_at TEXT NOT NULL, note TEXT DEFAULT '');
                CREATE TABLE IF NOT EXISTS book_package_revisions (revision_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, prior_package_path TEXT NOT NULL, package_path TEXT NOT NULL UNIQUE, evidence_json TEXT NOT NULL, adopted_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS release_locks (lock_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, revision INTEGER NOT NULL, package_path TEXT NOT NULL, snapshot_json TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL, locked_at TEXT NOT NULL, UNIQUE(book_id, revision));
                CREATE TABLE IF NOT EXISTS cover_concepts (concept_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, label TEXT NOT NULL, direction_json TEXT NOT NULL, selected INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, UNIQUE(book_id, label));
                CREATE TABLE IF NOT EXISTS final_local_reviews (review_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, proof_id TEXT NOT NULL DEFAULT '', package_path TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL, reviewer_source TEXT NOT NULL DEFAULT 'human', note TEXT NOT NULL DEFAULT '', UNIQUE(book_id, proof_id, package_path));
            """)
            # Additive migration for older catalogs: the persisted preparation
            # error message arrived after the first release of this table.
            columns = {row[1] for row in db.execute("PRAGMA table_info(marketplace_status)")}
            if "error_message" not in columns:
                db.execute("ALTER TABLE marketplace_status ADD COLUMN error_message TEXT NOT NULL DEFAULT ''")
            # Additive migration for online integration state (Etsy draft
            # automation).  These columns live NEXT TO the confirmed human
            # status on purpose: automated flows write here, while the
            # buyer-facing ``status`` column and its Uploaded/Published guard
            # keep their exact existing semantics.
            if "integration_state" not in columns:
                db.execute("ALTER TABLE marketplace_status ADD COLUMN integration_state TEXT NOT NULL DEFAULT ''")
            if "external_sku" not in columns:
                db.execute("ALTER TABLE marketplace_status ADD COLUMN external_sku TEXT NOT NULL DEFAULT ''")
            if "idempotency_key" not in columns:
                db.execute("ALTER TABLE marketplace_status ADD COLUMN idempotency_key TEXT NOT NULL DEFAULT ''")
            if "last_synced_at" not in columns:
                db.execute("ALTER TABLE marketplace_status ADD COLUMN last_synced_at TEXT NOT NULL DEFAULT ''")
            queue_columns = {row[1] for row in db.execute("PRAGMA table_info(approved_production_queue)")}
            for name, definition in (
                ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
                ("target_marketplaces_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("target_launch_date", "TEXT NOT NULL DEFAULT ''"),
                ("stop_reason", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in queue_columns:
                    db.execute(f"ALTER TABLE approved_production_queue ADD COLUMN {name} {definition}")
            # Append-only history of marketplace status changes. Rows are never
            # updated or deleted, so the publishing trail survives catalog prunes
            # and gives every screen one truthful answer to "what happened here?".
            db.executescript("""
                CREATE TABLE IF NOT EXISTS marketplace_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL,
                    marketplace TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT,
                    changed_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    external_id TEXT DEFAULT '',
                    listing_url TEXT DEFAULT '',
                    error_message TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_marketplace_audit_book ON marketplace_audit(book_id, changed_at);
                CREATE TABLE IF NOT EXISTS integration_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL,
                    marketplace TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_integration_log_book ON integration_log(book_id, marketplace, created_at);
            """)

    def upsert_book(self, book_id: str, source_key: str, metadata: dict, package_path: str = "") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            row = db.execute("SELECT metadata_locked, metadata_json FROM books WHERE book_id=?", (book_id,)).fetchone()
            stored = row["metadata_json"] if row and row["metadata_locked"] else json.dumps(metadata)
            db.execute("""INSERT INTO books(book_id,source_key,metadata_json,package_path,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(book_id) DO UPDATE SET source_key=excluded.source_key, metadata_json=?, package_path=excluded.package_path, updated_at=excluded.updated_at""", (book_id, source_key, stored, package_path, now, now, stored))
            for marketplace in MARKETPLACES: db.execute("INSERT OR IGNORE INTO marketplace_status(book_id,marketplace,status,updated_at) VALUES(?,?,?,?)", (book_id, marketplace, "Not Prepared", now))

    def list_books(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM books ORDER BY updated_at DESC").fetchall()
            statuses = {}
            for row in db.execute("SELECT book_id,marketplace,status FROM marketplace_status ORDER BY book_id,marketplace"):
                statuses.setdefault(row["book_id"], {})[row["marketplace"]] = row["status"]
            output = []
            for row in rows:
                item = dict(row)
                item["metadata"] = json.loads(item.pop("metadata_json"))
                item["statuses"] = statuses.get(item["book_id"], {})
                output.append(item)
            return output

    def get_book(self, book_id: str) -> dict | None:
        if not isinstance(book_id, str):
            return None
        with self._connect() as db:
            row = db.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            item["statuses"] = {
                status["marketplace"]: status["status"]
                for status in db.execute("SELECT marketplace,status FROM marketplace_status WHERE book_id=?", (book_id,))
            }
            return item

    def save_metadata(self, book_id: str, metadata: dict, locked: bool | None = None) -> None:
        with self._connect() as db:
            if locked is None: db.execute("UPDATE books SET metadata_json=?, updated_at=? WHERE book_id=?", (json.dumps(metadata), datetime.now().isoformat(timespec="seconds"), book_id))
            else: db.execute("UPDATE books SET metadata_json=?, metadata_locked=?, updated_at=? WHERE book_id=?", (json.dumps(metadata), int(locked), datetime.now().isoformat(timespec="seconds"), book_id))

    def statuses(self, book_id: str) -> dict[str, str]:
        with self._connect() as db: return {row["marketplace"]: row["status"] for row in db.execute("SELECT marketplace,status FROM marketplace_status WHERE book_id=?", (book_id,))}

    def marketplace_records(self, book_id: str) -> dict[str, dict]:
        """Return the full, buyer-facing publishing trail for one book."""
        with self._connect() as db:
            rows = db.execute("SELECT marketplace,status,external_id,url,updated_at,error_message,integration_state,last_synced_at FROM marketplace_status WHERE book_id=?", (book_id,)).fetchall()
        records = {row["marketplace"]: dict(row) for row in rows}
        for marketplace in MARKETPLACES:
            records.setdefault(marketplace, {"marketplace": marketplace, "status": "Not Prepared", "external_id": "", "url": "", "updated_at": "", "error_message": "", "integration_state": "", "last_synced_at": ""})
        return records

    def transition_status(self, book_id: str, marketplace: str, new_status: str, external_id: str | None = None,
                          url: str | None = None, source: str = "manual", error_message: str = "") -> dict:
        """The one guarded path for changing a marketplace status.

        - Confirmed ``Uploaded``/``Published`` records are protected: any
          non-manual source (prepare, local scans, future API/browser adapters)
          is refused without touching files or data.
        - Identifiers and links are preserved unless explicitly supplied.
        - Every actual change appends exactly one audit row; no-op calls write
          nothing at all.
        """
        if marketplace not in MARKETPLACES:
            raise ValueError("Unknown marketplace")
        prior = self.marketplace_records(book_id)[marketplace]
        if prior["status"] in PROTECTED_STATUSES and source != "manual":
            return {"changed": False, "protected": True,
                    "message": f"{marketplace} is already recorded as {prior['status']}; nothing was changed.",
                    "record": prior}
        final_external = prior["external_id"] if external_id is None else str(external_id).strip()
        final_url = prior["url"] if url is None else str(url).strip()
        final_error = "" if new_status != "Error" else str(error_message or "").strip()
        changed = (new_status != prior["status"] or final_external != prior["external_id"]
                   or final_url != prior["url"] or final_error != (prior.get("error_message") or ""))
        if not changed:
            return {"changed": False, "protected": False, "message": "", "record": prior}
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute("""INSERT INTO marketplace_status(book_id,marketplace,status,external_id,url,error_message,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(book_id,marketplace) DO UPDATE SET status=excluded.status, external_id=excluded.external_id, url=excluded.url, error_message=excluded.error_message, updated_at=excluded.updated_at""",
                       (book_id, marketplace, new_status, final_external, final_url, final_error, now))
            # Append-only trail: insert only, never update or delete.
            db.execute("""INSERT INTO marketplace_audit(book_id,marketplace,old_status,new_status,changed_at,source,external_id,listing_url,error_message) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (book_id, marketplace, prior["status"], new_status, now, source, final_external, final_url, final_error))
        return {"changed": True, "protected": False, "message": "", "record": self.marketplace_records(book_id)[marketplace]}

    def set_status(self, book_id: str, marketplace: str, status: str, external_id: str | None = None, url: str | None = None) -> None:
        """Backward-compatible wrapper; identifiers are preserved when omitted."""
        self.transition_status(book_id, marketplace, status, external_id=external_id, url=url)

    def update_marketplace_record(self, book_id: str, marketplace: str, status: str, external_id: str, url: str) -> None:
        """Save a confirmed marketplace identifier/link without guessing its live state."""
        self.transition_status(book_id, marketplace, status, external_id=external_id, url=url, source="manual")

    def audit_history(self, book_id: str | None = None, marketplace: str | None = None) -> list[dict]:
        """Read the append-only publishing trail, newest first."""
        query = "SELECT audit_id,book_id,marketplace,old_status,new_status,changed_at,source,external_id,listing_url,error_message FROM marketplace_audit"
        params: tuple = ()
        clauses = []
        if book_id is not None:
            clauses.append("book_id=?"); params += (book_id,)
        if marketplace is not None:
            clauses.append("marketplace=?"); params += (marketplace,)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY changed_at DESC, audit_id DESC"
        with self._connect() as db:
            return [dict(row) for row in db.execute(query, params)]

    # -- Online integration state (automated flows write here; ``status`` stays human-owned)

    def integration_record(self, book_id: str, marketplace: str) -> dict:
        """Automation-side record for one marketplace (never the buyer-facing status)."""
        with self._connect() as db:
            row = db.execute(
                "SELECT integration_state, external_sku, idempotency_key, last_synced_at FROM marketplace_status WHERE book_id=? AND marketplace=?",
                (book_id, marketplace),
            ).fetchone()
        if not row:
            return {"integration_state": "", "external_sku": "", "idempotency_key": "", "last_synced_at": ""}
        return {key: (row[key] or "") for key in ("integration_state", "external_sku", "idempotency_key", "last_synced_at")}

    def set_integration_state(self, book_id: str, marketplace: str, state: str,
                              external_sku: str | None = None, idempotency_key: str | None = None) -> dict:
        """Persist automated progress without touching the confirmed status column.

        Only the four integration columns are written; ``status``,
        ``external_id``, ``url`` and ``error_message`` keep their values, and
        no marketplace_audit row is produced (the integration log carries this
        stream instead).
        """
        if marketplace not in MARKETPLACES:
            raise ValueError("Unknown marketplace")
        prior = self.integration_record(book_id, marketplace)
        final_state = str(state).strip()
        final_sku = prior["external_sku"] if external_sku is None else str(external_sku).strip()
        final_key = prior["idempotency_key"] if idempotency_key is None else str(idempotency_key).strip()
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute("""INSERT INTO marketplace_status(book_id,marketplace,status,integration_state,external_sku,idempotency_key,last_synced_at,updated_at) VALUES(?,?,?,?,?,?,?,?)
                          ON CONFLICT(book_id,marketplace) DO UPDATE SET integration_state=excluded.integration_state, external_sku=excluded.external_sku, idempotency_key=excluded.idempotency_key, last_synced_at=excluded.last_synced_at""",
                       (book_id, marketplace, "Not Prepared", final_state, final_sku, final_key, now, now))
        return self.integration_record(book_id, marketplace)

    def clear_integration_state(self, book_id: str, marketplace: str) -> None:
        """Reset automation columns only (used when reconciliation proves a draft vanished)."""
        if marketplace not in MARKETPLACES:
            raise ValueError("Unknown marketplace")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute("""INSERT INTO marketplace_status(book_id,marketplace,status,integration_state,external_sku,idempotency_key,last_synced_at,updated_at) VALUES(?,?,?,?,?,?,?,?)
                          ON CONFLICT(book_id,marketplace) DO UPDATE SET integration_state='', external_sku='', idempotency_key='', last_synced_at=''""",
                       (book_id, marketplace, "Not Prepared", "", "", "", "", now))

    def record_integration_event(self, book_id: str, marketplace: str, event: str, detail: str = "") -> None:
        """Append one sanitized automation event to the integration log.

        The detail text passes through the shared secret redactor so token-like
        strings can never reach the log through an exception message.
        """
        from integrations.errors import redact_text

        clean_detail = redact_text(str(detail or "")).replace("\n", " ").strip()
        with self._connect() as db:
            db.execute("INSERT INTO integration_log(book_id,marketplace,event,detail,created_at) VALUES(?,?,?,?,?)",
                       (book_id, marketplace, str(event).strip(), clean_detail[:500], datetime.now().isoformat(timespec="seconds")))

    def integration_history(self, book_id: str, marketplace: str | None = None) -> list[dict]:
        """Read the append-only automation trail for one book, newest first."""
        query = "SELECT log_id,book_id,marketplace,event,detail,created_at FROM integration_log WHERE book_id=?"
        params: tuple = (book_id,)
        if marketplace is not None:
            query += " AND marketplace=?"
            params += (marketplace,)
        query += " ORDER BY created_at DESC, log_id DESC"
        with self._connect() as db:
            return [dict(row) for row in db.execute(query, params)]

    def assign_isbn(self, isbn: str, book_id: str, title: str, source: str) -> None:
        isbn = "".join(isbn.split()).replace("-", "")
        if not isbn: return
        with self._connect() as db:
            prior = db.execute("SELECT book_id FROM isbns WHERE isbn=?", (isbn,)).fetchone()
            if prior and prior["book_id"] not in (None, book_id): raise ValueError("That ISBN is already assigned to a different book.")
            db.execute("INSERT OR REPLACE INTO isbns(isbn,book_id,title,format,source,assigned_at) VALUES(?,?,?,?,?,?)", (isbn, book_id, title, "Paperback", source, datetime.now().isoformat(timespec="seconds")))

    def list_isbns(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM isbns ORDER BY assigned_at DESC")]

    def save_bundle(self, bundle_id: str, title: str, book_ids: list[str], metadata: dict, output_path: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO bundles(bundle_id,title,book_ids_json,metadata_json,output_path,created_at) VALUES(?,?,?,?,?,?)", (bundle_id, title, json.dumps(book_ids), json.dumps(metadata), output_path, datetime.now().isoformat(timespec="seconds")))

    def list_bundles(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM bundles ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row); item["book_ids"] = json.loads(item.pop("book_ids_json")); item["metadata"] = json.loads(item.pop("metadata_json")); result.append(item)
        return result

    # -- Approved production and immutable release records -----------------

    def approve_for_production(self, book_id: str, note: str = "", marketplaces: list[str] | None = None,
                               launch_date: str = "") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            order = db.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM approved_production_queue").fetchone()[0]
            targets = [item for item in (marketplaces or ["amazon", "etsy", "website"]) if item in MARKETPLACES]
            db.execute("""INSERT INTO approved_production_queue(book_id,status,added_at,updated_at,note,sort_order,target_marketplaces_json,target_launch_date,stop_reason) VALUES(?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(book_id) DO UPDATE SET status='Approved', updated_at=excluded.updated_at, note=excluded.note, target_marketplaces_json=excluded.target_marketplaces_json, target_launch_date=excluded.target_launch_date, stop_reason=''""",
                       (book_id, "Approved", now, now, str(note).strip(), order, json.dumps(targets), str(launch_date).strip(), ""))

    def approved_production_queue(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM approved_production_queue ORDER BY sort_order, queue_id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try: item["target_marketplaces"] = json.loads(item.pop("target_marketplaces_json") or "[]")
            except json.JSONDecodeError: item["target_marketplaces"] = []
            result.append(item)
        return result

    def set_approval_status(self, book_id: str, status: str, note: str = "") -> None:
        if status not in {"Approved", "In progress", "Completed", "Needs attention", "Abandoned"}:
            raise ValueError("Unknown approval status")
        with self._connect() as db:
            db.execute("UPDATE approved_production_queue SET status=?, note=?, stop_reason=?, updated_at=? WHERE book_id=?",
                       (status, str(note).strip(), str(note).strip() if status in {"Needs attention", "Abandoned"} else "", datetime.now().isoformat(timespec="seconds"), book_id))

    def update_approval_plan(self, book_id: str, marketplaces: list[str], launch_date: str = "") -> None:
        targets = [item for item in marketplaces if item in MARKETPLACES]
        with self._connect() as db:
            db.execute("UPDATE approved_production_queue SET target_marketplaces_json=?, target_launch_date=?, updated_at=? WHERE book_id=?",
                       (json.dumps(targets), str(launch_date).strip(), datetime.now().isoformat(timespec="seconds"), book_id))

    def move_approval_item(self, book_id: str, direction: int) -> bool:
        rows = self.approved_production_queue(); index = next((i for i, row in enumerate(rows) if row["book_id"] == book_id), None)
        if index is None or not 0 <= index + direction < len(rows): return False
        other = rows[index + direction]
        with self._connect() as db:
            db.execute("UPDATE approved_production_queue SET sort_order=? WHERE book_id=?", (other["sort_order"], book_id))
            db.execute("UPDATE approved_production_queue SET sort_order=? WHERE book_id=?", (rows[index]["sort_order"], other["book_id"]))
        return True

    def save_cover_concept(self, book_id: str, label: str, direction: dict, selected: bool = False) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            if selected: db.execute("UPDATE cover_concepts SET selected=0 WHERE book_id=?", (book_id,))
            db.execute("INSERT INTO cover_concepts(book_id,label,direction_json,selected,created_at) VALUES(?,?,?,?,?) ON CONFLICT(book_id,label) DO UPDATE SET direction_json=excluded.direction_json, selected=excluded.selected, created_at=excluded.created_at",
                       (book_id, str(label).strip() or "Concept", json.dumps(direction, ensure_ascii=False), int(selected), now))

    def cover_concepts(self, book_id: str) -> list[dict]:
        with self._connect() as db: rows = db.execute("SELECT * FROM cover_concepts WHERE book_id=? ORDER BY selected DESC, concept_id", (book_id,)).fetchall()
        result=[]
        for row in rows:
            item=dict(row); item["direction"] = json.loads(item.pop("direction_json")); result.append(item)
        return result

    def set_approval_status_for_source(self, source_key: str, status: str, note: str = "") -> bool:
        """Update a queued item from a creator outcome without guessing a book ID."""
        with self._connect() as db:
            row = db.execute("SELECT book_id FROM books WHERE source_key=?", (str(source_key),)).fetchone()
        if not row:
            return False
        self.set_approval_status(row["book_id"], status, note)
        return True

    def lock_release(self, book_id: str) -> dict:
        book = self.get_book(book_id)
        if not book or not str(book.get("package_path") or "").strip():
            raise ValueError("Create the complete package before locking this release.")
        package = Path(book["package_path"])
        from .package_layout import package_file
        from background_generation.index import verify_rendered_cover_approval
        cover_ok, cover_reason, _cover_proof = verify_rendered_cover_approval(package_file(package, "front_cover.png"))
        if not cover_ok:
            raise ValueError("Cover Art Required — release cannot be locked: " + cover_reason)
        files = {}
        for key, raw in (book["metadata"].get("files") or {}).items():
            path = Path(str(raw))
            if path.is_file(): files[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
        for path in package.glob("*.pdf") if package.is_dir() else ():
            files.setdefault(path.name, {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
        snapshot = {"book_id": book_id, "source_key": book["source_key"], "package_path": book["package_path"], "metadata": book["metadata"], "statuses": book["statuses"], "file_checksums": files}
        encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            row = db.execute("SELECT revision,snapshot_sha256,locked_at FROM release_locks WHERE book_id=? ORDER BY revision DESC LIMIT 1", (book_id,)).fetchone()
            if row and row["snapshot_sha256"] == digest:
                return {"revision": row["revision"], "sha256": digest, "locked_at": row["locked_at"], "unchanged": True}
            revision = int(row["revision"] if row else 0) + 1
            db.execute("INSERT INTO release_locks(book_id,revision,package_path,snapshot_json,snapshot_sha256,locked_at) VALUES(?,?,?,?,?,?)", (book_id, revision, book["package_path"], encoded, digest, now))
        return {"revision": revision, "sha256": digest, "locked_at": now, "unchanged": False}

    def release_locks(self, book_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT lock_id,book_id,revision,package_path,snapshot_sha256,locked_at FROM release_locks WHERE book_id=? ORDER BY revision DESC", (book_id,)).fetchall()
        return [dict(row) for row in rows]

    def latest_release_lock_snapshot(self, book_id: str) -> dict | None:
        """Return the newest immutable release snapshot for read-only checks.

        This does not create a lock or alter release state.  It lets the
        publishing screens prove that the cover being shown is the one that
        was included in the latest locked release, when a lock exists.
        """
        with self._connect() as db:
            row = db.execute(
                "SELECT revision,snapshot_json,snapshot_sha256,locked_at FROM release_locks "
                "WHERE book_id=? ORDER BY revision DESC LIMIT 1", (book_id,)
            ).fetchone()
        if not row:
            return None
        try:
            snapshot = json.loads(row["snapshot_json"])
        except (TypeError, json.JSONDecodeError):
            snapshot = {}
        return {
            "revision": row["revision"], "sha256": row["snapshot_sha256"],
            "locked_at": row["locked_at"], "snapshot": snapshot if isinstance(snapshot, dict) else {},
        }

    def lock_production_proof(self, book_id: str, proof: dict) -> dict:
        """Append a Phase 4 local-proof revision without touching marketplace state."""
        book = self.get_book(book_id)
        if not book:
            raise ValueError("Book was not found.")
        if str(proof.get("status") or "") not in {"ready_for_final_local_review", "ready_for_platform_preview"}:
            raise ValueError("A release lock requires a passing local production proof.")
        package = str(book.get("package_path") or "")
        if not package:
            raise ValueError("A package path is required for a release lock.")
        from .package_layout import package_file
        from background_generation.index import verify_rendered_cover_approval
        cover_ok, cover_reason, _cover_proof = verify_rendered_cover_approval(package_file(Path(package), "front_cover.png"))
        if not cover_ok:
            raise ValueError("Cover Art Required — production proof cannot be locked: " + cover_reason)
        snapshot = {"phase4_production_proof": proof, "book_id": book_id, "package_path": package,
                    "marketplace_statuses": book.get("statuses") or {}}
        encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest(); now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            prior = db.execute("SELECT revision,snapshot_sha256,locked_at FROM release_locks WHERE book_id=? ORDER BY revision DESC LIMIT 1", (book_id,)).fetchone()
            if prior and prior["snapshot_sha256"] == digest:
                return {"revision": prior["revision"], "sha256": digest, "locked_at": prior["locked_at"], "unchanged": True}
            revision = int(prior["revision"] if prior else 0) + 1
            db.execute("INSERT INTO release_locks(book_id,revision,package_path,snapshot_json,snapshot_sha256,locked_at) VALUES(?,?,?,?,?,?)", (book_id, revision, package, encoded, digest, now))
        return {"revision": revision, "sha256": digest, "locked_at": now, "unchanged": False}

    def record_final_local_review(self, book_id: str, proof_id: str = "", package_path: str = "", note: str = "") -> dict:
        """Persist an explicit human final-review decision.

        Opening a preview is deliberately not enough.  This lightweight record
        is the durable source for the Phase 5 "Final Local Review" step and
        never changes marketplace history or release artifacts.
        """
        if not self.get_book(book_id):
            raise ValueError("Book was not found.")
        now = datetime.now().isoformat(timespec="seconds")
        values = (book_id, str(proof_id or ""), str(package_path or ""), now, "human", str(note or "").strip())
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO final_local_reviews(book_id,proof_id,package_path,reviewed_at,reviewer_source,note) VALUES(?,?,?,?,?,?)", values)
        return {"book_id": book_id, "proof_id": values[1], "package_path": values[2], "reviewed_at": now, "reviewer_source": "human", "note": values[5]}

    def final_local_review(self, book_id: str, proof_id: str = "", package_path: str = "") -> dict | None:
        """Return the newest explicit review matching the current product truth."""
        query = "SELECT book_id,proof_id,package_path,reviewed_at,reviewer_source,note FROM final_local_reviews WHERE book_id=?"
        params: list[str] = [book_id]
        if proof_id:
            query += " AND proof_id=?"; params.append(proof_id)
        if package_path:
            query += " AND package_path=?"; params.append(package_path)
        query += " ORDER BY reviewed_at DESC, review_id DESC LIMIT 1"
        with self._connect() as db:
            row = db.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

    def prune_sources(self, active_source_keys: set[str]) -> int:
        """Prune only untracked, vanished or exact-alias theme ideas.

        The caller supplies theme paths, not every package identity. Absence
        from that list must never erase generated books or owner/workflow state.
        """
        def theme_hash(path):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(payload, dict) or not isinstance(payload.get("puzzles"), list):
                    return None
                raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
                return hashlib.sha256(raw.encode("utf-8")).hexdigest()
            except (OSError, UnicodeError, ValueError):
                return None

        active_paths = {Path(key).resolve() for key in active_source_keys if Path(key).is_absolute()}
        with self._connect() as db:
            # Keep reference/state checks and deletion in one write transaction.
            db.execute("BEGIN IMMEDIATE")
            linked = set()
            for table in ("isbns", "release_locks", "book_package_revisions", "final_local_reviews",
                          "marketplace_audit", "integration_log", "approved_production_queue", "cover_concepts"):
                linked.update(row[0] for row in db.execute(f"SELECT DISTINCT book_id FROM {table}") if row[0])
            for row in db.execute("SELECT book_ids_json FROM bundles"):
                try:
                    ids = json.loads(row[0])
                    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
                        return 0  # Unknown references: do not guess that a row is disposable.
                    linked.update(ids)
                except (ValueError, TypeError):
                    return 0
            # Unfinished/versioned chat forms may retain a source project too.
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "studio_draft_versions" in tables:
                for row in db.execute("SELECT payload FROM studio_draft_versions"):
                    try: pending = [json.loads(row[0])]
                    except (ValueError, TypeError): return 0
                    while pending:
                        item = pending.pop()
                        if isinstance(item, dict):
                            for name, value in item.items():
                                if name in ("book_id", "source_book_id") and isinstance(value, str): linked.add(value)
                                elif isinstance(value, (dict, list)): pending.append(value)
                        elif isinstance(item, list): pending.extend(item)
            active_hashes = None
            remove = []
            rows = db.execute("SELECT * FROM books").fetchall()
            artifact_keys = ("files", "isbn", "isbn13", "isbn_13", "asin", "external_id", "url",
                             "content_plan_approval", "final_review", "human_review", "quality_review",
                             "local_print_revision", "studio_chat_creation", "release_lock", "production_proof")
            for row in rows:
                identity, key = row["book_id"], row["source_key"]
                if key in active_source_keys or identity in linked or row["metadata_locked"] or row["package_path"]:
                    continue
                path = Path(key)
                if path.is_absolute() and path.resolve() in active_paths:
                    continue  # Equivalent native path spelling is still the active source.
                if not path.is_absolute() or path.suffix.casefold() != ".json" or "://" in key:
                    continue  # Includes package:, generated: and unknown identity schemes.
                try: metadata = json.loads(row["metadata_json"])
                except (ValueError, TypeError): continue
                if not isinstance(metadata, dict) or any(metadata.get(name) for name in artifact_keys):
                    continue
                statuses = db.execute("SELECT * FROM marketplace_status WHERE book_id=?", (identity,)).fetchall()
                if any(str(state["status"] or "").strip() not in ("", "Not Prepared") or
                       any(state[name] for name in ("external_id", "url", "error_message", "integration_state",
                                                   "external_sku", "idempotency_key", "last_synced_at")) for state in statuses):
                    continue
                if path.exists():
                    digest = theme_hash(path)
                    if not digest:
                        continue
                    if active_hashes is None:
                        active_hashes = {value for source in active_source_keys
                                         if (value := theme_hash(Path(source))) is not None}
                    if digest not in active_hashes:
                        continue  # Same title is not proof of duplicate content/edition.
                remove.append(identity)
            for book_id in remove:
                db.execute("DELETE FROM marketplace_status WHERE book_id=?", (book_id,))
                db.execute("DELETE FROM books WHERE book_id=?", (book_id,))
            return len(remove)

    def managed_print_revision_paths(self) -> set[Path]:
        """Paths already assigned to stable identities; scans must not reimport them."""
        with self._connect() as db:
            rows = db.execute("SELECT prior_package_path,package_path FROM book_package_revisions").fetchall()
        return {Path(value).resolve() for row in rows for value in row if value}

    def has_print_revision(self, book_id: str) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM book_package_revisions WHERE book_id=? LIMIT 1", (book_id,)).fetchone() is not None

    def _commit_print_revision(self, book_id, expected_package, expected_metadata, package, files, evidence, expected_source_key, expected_locked):
        """Atomic operational-path adoption, preserving owner fields and external state.

        Called only after service-level artifact validation. This records a
        local revision, never a release lock or human final-review decision.
        """
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT package_path,metadata_json,source_key,metadata_locked FROM books WHERE book_id=?", (book_id,)).fetchone()
            if row is None or row['package_path'] != expected_package or json.loads(row['metadata_json']) != expected_metadata or row['source_key'] != expected_source_key or row['metadata_locked'] != expected_locked:
                raise ValueError("The saved book changed during validation; reopen it and retry.")
            claimed = db.execute("SELECT book_id,package_path FROM books WHERE book_id!=?", (book_id,)).fetchall()
            if any(other['package_path'] and Path(other['package_path']).resolve()==Path(package).resolve() for other in claimed):
                raise ValueError("The revision was assigned to another catalog identity during validation.")
            metadata = json.loads(row['metadata_json'])
            metadata['files'] = files
            metadata['local_print_revision'] = {'previous_package': expected_package, 'package': package,
                'adopted_at': now, 'owner_review': 'pending', 'marketplace_submission': 'not_performed'}
            db.execute("INSERT INTO book_package_revisions(book_id,prior_package_path,package_path,evidence_json,adopted_at) VALUES(?,?,?,?,?)",
                (book_id,expected_package,package,json.dumps(evidence,ensure_ascii=False),now))
            db.execute("UPDATE books SET package_path=?,metadata_json=?,updated_at=? WHERE book_id=?",
                (package,json.dumps(metadata,ensure_ascii=False),now,book_id))
        return {'book_id':book_id,'package_path':package,'previous_package_path':expected_package,
                'owner_review':'pending','marketplace_state_changed':False}

    def prune_duplicate_unpublished_package_titles(self) -> int:
        """Keep the newest untracked package for a title without touching files.

        A package may be rebuilt after a cover or content correction.  Keep
        the newest local draft, while preserving actual uploads/publications,
        locked metadata, and ISBN assignments. A locally prepared ``Ready``
        handoff is not evidence that the old PDF was uploaded.
        """
        with self._connect() as db:
            rows = db.execute(
                "SELECT book_id, source_key, package_path, metadata_json, metadata_locked, updated_at FROM books "
                "WHERE source_key LIKE 'package:%'"
            ).fetchall()
            groups: dict[str, list[sqlite3.Row]] = {}
            for row in rows:
                try:
                    title = str(json.loads(row["metadata_json"]).get("title") or "").strip().casefold()
                except json.JSONDecodeError:
                    continue
                if title:
                    groups.setdefault(title, []).append(row)
            remove: list[str] = []
            for candidates in groups.values():
                if len(candidates) < 2:
                    continue
                protected = []
                for row in candidates:
                    statuses = db.execute(
                        "SELECT status FROM marketplace_status WHERE book_id=?", (row["book_id"],)
                    ).fetchall()
                    has_isbn = db.execute("SELECT 1 FROM isbns WHERE book_id=? LIMIT 1", (row["book_id"],)).fetchone() is not None
                    has_revision = db.execute("SELECT 1 FROM book_package_revisions WHERE book_id=? LIMIT 1", (row["book_id"],)).fetchone() is not None
                    if any(status["status"] in PROTECTED_STATUSES for status in statuses) or row["metadata_locked"] or has_isbn or has_revision:
                        protected.append(row)
                def package_time(row: sqlite3.Row) -> float:
                    path = Path(str(row["package_path"] or ""))
                    try:
                        return path.stat().st_mtime if path.is_dir() else 0.0
                    except OSError:
                        return 0.0
                keep = max(protected or candidates, key=lambda row: (package_time(row), str(row["updated_at"])))
                for row in candidates:
                    if row["book_id"] != keep["book_id"] and row not in protected:
                        remove.append(row["book_id"])
            for book_id in remove:
                db.execute("DELETE FROM marketplace_status WHERE book_id=?", (book_id,))
                db.execute("DELETE FROM books WHERE book_id=?", (book_id,))
            return len(remove)

    def prune_recovery_archive_packages(self) -> int:
        """Remove catalog-only rows that point into the recoverable archive.

        The Recovery Center intentionally keeps partial and superseded files on
        disk.  They must never appear as live books in Publishing Center.
        This touches database rows only; it never deletes or moves a package.
        """
        with self._connect() as db:
            rows = db.execute("SELECT book_id, source_key, package_path FROM books").fetchall()
            remove = [row["book_id"] for row in rows if "_recovery_archive" in str(row["source_key"] or "").casefold() or "_recovery_archive" in str(row["package_path"] or "").casefold()]
            for book_id in remove:
                db.execute("DELETE FROM marketplace_status WHERE book_id=?", (book_id,))
                db.execute("DELETE FROM books WHERE book_id=?", (book_id,))
            return len(remove)
