"""Tkinter Publishing Manager UI kept out of the puzzle creator module."""
from __future__ import annotations

import os
import queue
import re
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from .database import MARKETPLACES
from .catalog_view import (
    CATALOG_VIEWS, catalog_counts, catalog_state, collapse_catalog_books,
    in_catalog_view, record_kind_label,
)
from .marketplaces import PUBLISHERS
from .etsy_bundles import ETSY_STORE_NAME
from .production_gate import book_gate, gate_text, topic_gate
from .readiness import PREPARED_FOLDER_NAMES, format_history, marketplace_rows, next_actions, online_state_text, whats_left
from .package_layout import marketplace_handoff_folder, missing_core_package_files, release_contract
from .production_orchestrator import ProductionJobIndex
from integrations.publication import PublicationRecord

DISPLAY = {"amazon": "Amazon", "etsy": "Etsy", "ingram": "Ingram", "website": "Website", "lulu": "Lulu", "bookvault": "BookVault", "barnes_noble": "B&N", "payhip": "Payhip"}
STATUS_VALUES = ("Not Prepared", "Ready", "Prepared — Final Cover Needed", "Uploaded", "Published", "Error", "Needs Review")
# Buyer-facing platform names for the Hub readiness grid; keys follow the
# canonical database.MARKETPLACES order so all seven rows always render.
DISPLAY_GRID = {
    "amazon": "Amazon KDP",
    "etsy": "Etsy",
    "ingram": "IngramSpark",
    "website": "Website / Direct",
    "lulu": "Lulu",
    "bookvault": "BookVault",
    "barnes_noble": "Barnes & Noble Press",
    "payhip": "Payhip digital downloads",
}
# Validator phrases that are advice about other printers' cover templates,
# never blockers; keeping them separate stops advisories masquerading as failures.
ADVISORY_ISSUE_HINTS = ("reference-only", "template")


def fit_dialog_to_screen(window: tk.Toplevel, width: int, height: int, min_width: int, min_height: int) -> None:
    """Keep a secondary window inside the usable laptop work area."""
    screen_width = max(800, window.winfo_screenwidth())
    screen_height = max(600, window.winfo_screenheight())
    usable_width = max(760, screen_width - 70)
    usable_height = max(500, screen_height - 110)
    actual_width = min(width, usable_width)
    actual_height = min(height, usable_height)
    window.geometry(f"{actual_width}x{actual_height}")
    window.minsize(min(min_width, actual_width), min(min_height, actual_height))


def split_issues(issues: list[str]) -> tuple[list[str], list[str]]:
    """Split validator output into hard blockers and advisory template notes."""
    blockers: list[str] = []
    advisories: list[str] = []
    for issue in issues:
        low = issue.casefold()
        (advisories if any(hint in low for hint in ADVISORY_ISSUE_HINTS) else blockers).append(issue)
    return blockers, advisories


def draft_action_enabled(row: dict | None) -> bool:
    """True only when the selected readiness row may offer the Etsy draft action.

    Gating is deliberately strict: Etsy row only, a prepared folder on disk,
    and never when a human already confirmed Uploaded/Published.
    """
    if not row:
        return False
    info = integration_info_for("etsy")
    return (
        row.get("key") == "etsy"
        and bool((info or {}).get("capabilities", {}).get("can_create_draft"))
        and bool(row.get("has_local_folder"))
        and row.get("status") not in ("Uploaded", "Published")
    )


def integration_info_for(key: str) -> dict | None:
    """Discovery metadata for one marketplace key (None when unknown).

    Backed by the integration registry so the UI never hardcodes per-platform
    branching: mode (api/export_only/manual), status (active/planned) and
    truthful capabilities all come from one source.
    """
    from integrations.registry import get_integration_info

    return get_integration_info(key)


def export_action_enabled(row: dict | None, info: dict | None) -> bool:
    """Capability-driven gate for 'Generate Export Package'.

    Enabled only for a channel whose registered integration is an ACTIVE
    export-only adapter advertising can_export_package, with a prepared
    folder to export from.  Human-confirmed records stay untouchable.
    """
    if not row or not info:
        return False
    return (
        info.get("mode") == "export_only"
        and info.get("status") == "active"
        and bool(info.get("capabilities", {}).get("can_export_package"))
        and bool(row.get("has_local_folder"))
        and row.get("status") not in ("Uploaded", "Published")
    )


def selected_book_overview(product, book: dict) -> str:
    """The one-line overview from the canonical MasterProduct read model.

    Raw catalog fields are still available to callers; this helper simply
    proves the Hub's displayed identity flows through the universal model.
    """
    meta = book.get("metadata") or {}
    details: list[str] = []
    if product.subtitle:
        details.append(str(product.subtitle))
    if product.series:
        details.append(f"Series: {product.series}")
    theme = str(meta.get("theme") or "").strip()
    if theme:
        details.append(f"Theme: {theme}")
    pages = int(product.page_count or 0)
    details.append(f"{pages} page{'s' if pages != 1 else ''}")
    details.append(f"ISBN: {product.isbn or 'not assigned'}")
    return "  |  ".join(details)


def _format_bytes(size) -> str:
    try:
        size = int(size)
    except (TypeError, ValueError):
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def artifact_summary_lines(product) -> list[str]:
    """Read-only artifact manifest lines; never computes hashes here."""
    lines: list[str] = []
    for artifact in product.artifacts:
        position = f"#{artifact.position} " if artifact.position else ""
        size = _format_bytes(artifact.file_size) or "size unknown"
        checksum = artifact.checksum or "Not calculated"
        label = f" — {artifact.label}" if artifact.label else ""
        lines.append(
            f"{position}{artifact.purpose.value}: {os.path.basename(artifact.path)}"
            f" [{artifact.media_type or 'unknown type'}, {size}, checksum: {checksum}]{label}"
        )
        lines.append(f"    {artifact.path}")
    return lines


def render_master_product_text(product) -> str:
    """Full read-only inspector text for the canonical product.

    Sections: Identity / Metadata / Commercial / Print / Artifacts /
    Source.  Contains no credentials by construction - MasterProduct cannot
    carry them.
    """
    def line(label: str, value) -> str:
        text = str(value).strip() if value is not None else ""
        return f"{label}: {text if text else '—'}"

    sections = [
        "IDENTITY",
        line("  Internal product ID", product.internal_product_id),
        line("  SKU", product.sku),
        line("  Revision", product.revision),
        "",
        "METADATA",
        line("  Title", product.title),
        line("  Subtitle", product.subtitle),
        line("  Series", product.series),
        line("  Author/Creator", product.author),
        line("  Brand/Imprint", product.brand),
        line("  Language", product.language),
        line("  Product type", product.product_type),
        line("  Target audience", product.target_audience),
        line("  Categories", "; ".join(product.categories)),
        line("  Keywords", "; ".join(product.keywords)),
        line("  Tags", ", ".join(product.tags)),
        "",
        "COMMERCIAL",
        line("  Price", f"{product.price:.2f} {product.currency}" if product.price is not None else ""),
        line("  Publication date", product.publication_date),
        line("  Copyright", product.copyright_notice),
        "",
        "PRINT",
        line("  ISBN", product.isbn),
        line("  Page count", product.page_count or ""),
        line("  Trim size", product.trim_size),
        line("  Bleed", f'{product.bleed_inches}"' if product.bleed_inches is not None else ""),
        "",
        "ARTIFACTS" + ("" if product.artifacts else "  (none found)"),
        *artifact_summary_lines(product),
        "",
        "SOURCE / REVISION",
        line("  Source reference", product.source_reference),
        line("  Generated at", product.generated_at),
        line("  AI disclosure", product.ai_disclosure or "Not set"),
    ]
    return "\n".join(sections)


def marketplace_row_values(record, row_label: str, readiness_label: str) -> tuple:
    """Treeview values derived from the PublicationRecord view.

    Output is byte-identical to the previous raw-row rendering, so adopting
    the domain model changes nothing the user can see.
    """
    return (
        row_label,
        record.listing_status or "Not Prepared",
        readiness_label,
        record.remote_id or "—",
        "Saved link" if record.remote_url else "—",
        record.updated_at[:16].replace("T", " ") or "—",
    )


def apply_export_outcome(db, book_id: str, marketplace: str, result) -> None:
    """Persist ONLY automation-owned state after an export attempt.

    The human-owned status/external_id/url columns and their audit trail are
    never touched: an export package is preparation, not publication.
    """
    if result.success:
        db.set_integration_state(book_id, marketplace, "exported")
    else:
        db.record_integration_event(book_id, marketplace, "export_failed", result.message)


class MasterProductDialog(tk.Toplevel):
    """Read-only canonical product inspector ("View Master Product")."""

    def __init__(self, parent, service, book: dict) -> None:
        super().__init__(parent)
        from integrations.factory import MasterProductFactory

        self.title("Master Product")
        self.geometry("760x620"); self.minsize(600, 420)
        self.configure(background="#1f1f1f"); self.transient(parent)
        root = ttk.Frame(self, padding=18, style="Publish.TFrame"); root.pack(fill="both", expand=True)
        root.rowconfigure(1, weight=1); root.columnconfigure(0, weight=1)
        title = (book.get("metadata") or {}).get("title") or "book"
        ttk.Label(root, text=f'Master Product — {title}', style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        box = tk.Text(root, wrap="word", state="disabled", background="#292929",
                      foreground="#d9f5ee", relief="flat", padx=12, pady=10)
        box.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(root, orient="vertical", command=box.yview)
        scroll.grid(row=1, column=1, sticky="ns"); box.configure(yscrollcommand=scroll.set)
        ttk.Button(root, text="Close", command=self.destroy, style="Publish.Action.TButton").grid(row=2, column=0, sticky="e", pady=(10, 0))
        try:
            product = MasterProductFactory.from_book_record(book)
            text = render_master_product_text(product)
        except Exception as exc:
            text = (f"The master product could not be built from this catalog record.\n\n"
                    f"Details: {exc}")
        box.configure(state="normal"); box.delete("1.0", "end"); box.insert("end", text); box.configure(state="disabled")


def publishing_counts_line(rows: list[dict]) -> str:
    """One truthful status line, e.g. '2 of 7 published · 1 uploaded'."""
    counts = whats_left(rows)
    parts = [f"{counts['published']} of {counts['total']} published"]
    if counts["uploaded"]:
        parts.append(f"{counts['uploaded']} uploaded")
    if counts["ready_to_upload"]:
        parts.append(f"{counts['ready_to_upload']} ready to upload")
    if counts["final_cover_needed"]:
        parts.append(f"{counts['final_cover_needed']} need final covers")
    if counts["needs_items"]:
        parts.append(f"{counts['needs_items']} need items")
    if counts["needs_attention"]:
        parts.append(f"{counts['needs_attention']} need attention")
    return " · ".join(parts)


def whats_left_text(rows: list[dict]) -> str:
    """Headline counts plus capped plain-English next steps for one book."""
    counts = whats_left(rows)
    lines = [f"{counts['published']} of {counts['total']} marketplaces published."]
    if counts["uploaded"]:
        lines.append(f"{counts['uploaded']} uploaded — confirm each live listing, then mark it Published.")
    if counts["ready_to_upload"]:
        lines.append(f"{counts['ready_to_upload']} prepared package(s) waiting to be uploaded.")
    if counts["final_cover_needed"]:
        lines.append(f"{counts['final_cover_needed']} printer package(s) need a final platform cover before upload.")
    if counts["needs_items"]:
        lines.append(f"{counts['needs_items']} marketplace(s) still need required items.")
    if counts["needs_attention"]:
        lines.append(f"{counts['needs_attention']} marketplace(s) recorded an error.")
    actions = next_actions(rows)
    if actions:
        lines.append("")
        lines.append("Next steps:")
        lines.extend(f"• {action}" for action in actions)
    return "\n".join(lines)


class PublishingManagerDialog(tk.Toplevel):
    def __init__(self, parent, service, sync_catalog, open_recommendation=None, create_package=None, new_book=None, open_dashboard: bool = False) -> None:
        super().__init__(parent); self.parent, self.service, self.sync_catalog = parent, service, sync_catalog
        self.open_recommendation = open_recommendation
        self.create_package = create_package
        self.new_book = new_book
        self._open_dashboard_on_start = open_dashboard
        self.title("Publishing Center"); fit_dialog_to_screen(self, 1320, 820, 920, 560)
        self.configure(background="#1f1f1f")
        self.filter_text = tk.StringVar(); self.market_filter = tk.StringVar(value="All marketplaces")
        self.catalog_view = tk.StringVar(value="Completed books")
        self.ready_only = tk.BooleanVar(value=False)  # Backward-compatible; replaced by the clearer Show filter.
        self.status = tk.StringVar(value="Sync your existing books to start the publishing catalog.")
        self.job_status_filter = tk.StringVar(value="All statuses"); self.job_type_filter = tk.StringVar(value="All puzzle types"); self.job_priority_filter = tk.StringVar(value="All priorities"); self.job_attention_filter = tk.StringVar(value="")
        self.rows: dict[str, dict] = {}; self.recommendations: dict[str, dict] = {}; self._prepare_in_progress = False
        self._catalog_refresh_generation = 0
        self._catalog_search_timer: str | None = None
        self._idea_gate_cache: dict[tuple, dict] = {}
        self._setup_styles(); self._build()
        # Put the saved catalog on screen first.  A large theme library can
        # take time to rescan, but that should never make an existing catalog
        # look empty or leave the operator wondering whether the app froze.
        self.after(25, self._show_cached_catalog_preview)
        self.after(150, self._background_initial_sync)
        self.after_idle(self._maximize_window)
        self.after_idle(self._open_initial_dashboard)

    def _show_cached_catalog_preview(self) -> None:
        """Show known books immediately while full production checks run."""
        if not self.winfo_exists() or self.tree.get_children():
            return
        try:
            books = self.service.db.list_books()
        except Exception as exc:
            self.status.set(f"The saved catalog could not be read: {exc}. The full background check is still running.")
            return
        collapsed = collapse_catalog_books(books)
        counts = catalog_counts(collapsed)
        visible = [book for book in collapsed if in_catalog_view(book, self.catalog_view.get())]
        self.rows.clear(); self.tree.delete(*self.tree.get_children())
        for book in visible:
            meta, statuses = book["metadata"], book["statuses"]
            iid = book["book_id"]; self.rows[iid] = book
            state = catalog_state(book)
            self.tree.insert(
                "", "end", iid=iid,
                values=(meta.get("title", ""), meta.get("series", ""), meta.get("puzzle_type", "Word Search"),
                        meta.get("page_count", 0), record_kind_label(book["catalog_kind"]), "Checking…", state["next_action"]),
                tags=("alternate",) if len(self.rows) % 2 == 0 else (),
            )
        self.refresh_selected_view()
        self.status.set(
            f"Showing {len(visible)} distinct {self.catalog_view.get().casefold()} while readiness is checked… "
            f"{counts['packages']} complete package(s), {counts['in_progress']} incomplete, "
            f"{counts['ideas']} idea(s), {counts['missing']} missing source/package(s), "
            f"and {counts['aliases_hidden']} alias record(s) hidden."
        )

    def _background_initial_sync(self) -> None:
        """Sync the large catalog without freezing navigation or first paint."""
        self.status.set(f"Showing {len(self.rows)} saved book record(s); checking themes and current readiness in the background…")
        def work() -> None:
            try:
                count = self.sync_catalog()
                self.after(0, lambda: self._initial_sync_finished(count))
            except Exception as exc:
                self.after(0, lambda: self._catalog_refresh_failed(str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _initial_sync_finished(self, count: int) -> None:
        if not self.winfo_exists():
            return
        self.status.set(f"Catalog sources checked ({count} record(s)). Loading readiness in the background…")
        self._refresh_catalog_async()

    def _initial_sync_failed(self, detail: str) -> None:
        if self.winfo_exists():
            self.status.set(f"Catalog opened, but the background sync needs attention: {detail}")
            self._refresh_catalog_async()

    def _refresh_catalog_async(self) -> None:
        """Calculate slow production gates away from Tk's event loop."""
        selected_market = next((key for key, label in DISPLAY.items() if label == self.market_filter.get()), "")
        query = self.filter_text.get().casefold().strip()
        chosen_view = self.catalog_view.get()
        self._catalog_refresh_generation += 1
        generation = self._catalog_refresh_generation
        def work() -> None:
            try:
                books = collapse_catalog_books(self.service.db.list_books())
                counts = catalog_counts(books)
                rows = []
                for book in books:
                    meta, statuses = book["metadata"], book["statuses"]
                    if generation != self._catalog_refresh_generation:
                        return
                    haystack = " ".join(str(meta.get(key) or "") for key in ("title", "series", "theme")).casefold()
                    if query and query not in haystack:
                        continue
                    if selected_market and statuses.get(selected_market) == "Not Prepared":
                        continue
                    gate = None
                    if book["catalog_kind"] == "book_package":
                        # Same shared gate, using the already-loaded record.
                        # Avoid reloading all 200 SQLite rows for every book.
                        gate = book_gate(book)
                    elif book["catalog_kind"] in {"ready_book_idea", "blocked_book_idea", "theme_idea"}:
                        gate = self._cached_idea_gate(book)
                    final_review = False
                    contract_ready = None
                    if book["catalog_kind"] == "book_package":
                        package = str(book.get("package_path") or "")
                        contract_ready = bool(release_contract(package)["ready"])
                        lock = self.service.db.latest_release_lock_snapshot(book["book_id"])
                        proof = ((lock or {}).get("snapshot") or {}).get("phase4_production_proof") or {}
                        proof_id = str(proof.get("proof_id") or "")
                        final_review = bool(proof_id and self.service.db.final_local_review(
                            book["book_id"], proof_id=proof_id, package_path=package))
                    state = catalog_state(book, gate=gate, final_review=final_review,
                                          contract_ready=contract_ready)
                    if not in_catalog_view(book, chosen_view, state):
                        continue
                    book["catalog_state"] = state
                    rows.append((book, state))
                recommendations = self.service.recommended_books()
                self.after(0, lambda: self._show_catalog_snapshot(rows, recommendations, counts)
                           if generation == self._catalog_refresh_generation else None)
            except Exception as exc:
                detail = str(exc)
                self.after(0, lambda: self._catalog_refresh_failed(detail)
                           if generation == self._catalog_refresh_generation else None)
        threading.Thread(target=work, daemon=True).start()

    def _catalog_refresh_failed(self, detail: str) -> None:
        if self.winfo_exists():
            self.status.set(f"Catalog refresh needs attention: {detail}. Saved rows remain available; use Sync catalog to retry.")

    def _cached_idea_gate(self, book: dict) -> dict:
        """Reuse an unchanged theme check without caching completed-PDF proof."""
        source = Path(str(book.get("source_key") or ""))
        try:
            source_stamp = source.stat().st_mtime_ns
        except OSError:
            source_stamp = -1
        meta = book.get("metadata") or {}
        key = (
            str(book.get("book_id") or ""), source_stamp,
            str(meta.get("title") or ""), str(meta.get("author") or ""),
            str(meta.get("production_status") or ""),
        )
        if key not in self._idea_gate_cache:
            self._idea_gate_cache[key] = book_gate(book)
        return self._idea_gate_cache[key]

    def _schedule_catalog_search(self) -> None:
        """Wait for typing to pause before recalculating the filtered view."""
        if self._catalog_search_timer:
            self.after_cancel(self._catalog_search_timer)
        self._catalog_search_timer = self.after(250, self.refresh)

    def _show_catalog_snapshot(self, rows: list[tuple[dict, dict]], recommendations: list[dict], counts: dict[str, int]) -> None:
        if not self.winfo_exists():
            return
        selected = tuple(self.tree.selection())
        self.rows.clear(); self.tree.delete(*self.tree.get_children())
        for book, state in rows:
            meta = book["metadata"]
            iid = book["book_id"]; self.rows[iid] = book
            self.tree.insert("", "end", iid=iid, values=(
                meta.get("title", ""), meta.get("series", ""), meta.get("puzzle_type", "Word Search"),
                meta.get("page_count", 0), record_kind_label(book["catalog_kind"]),
                state["status"], state["next_action"]),
                tags=("alternate",) if len(self.rows) % 2 == 0 else ())
        keep_selection = tuple(book_id for book_id in selected if book_id in self.rows)
        if keep_selection:
            self.tree.selection_set(keep_selection)
        self.recommendations.clear(); self.recommendation_tree.delete(*self.recommendation_tree.get_children())
        for item in recommendations:
            book = item["book"]; iid = book["book_id"]; self.recommendations[iid] = item
            self.recommendation_tree.insert("", "end", iid=iid, values=(book["metadata"].get("title", ""), item["topic"], item["puzzles"] or "—", item["action"], item["reason"]), tags=("alternate",) if len(self.recommendations) % 2 == 0 else ())
        self.refresh_selected_view()
        self.status.set(
            f"Showing {len(self.rows)} distinct {self.catalog_view.get().casefold()}. "
            f"Catalog truth: {counts['packages']} complete package(s), {counts['in_progress']} incomplete, "
            f"{counts['ideas']} idea(s), {counts['missing']} missing source/package(s), "
            f"{counts['aliases_hidden']} alias record(s) hidden."
        )

    def _open_initial_dashboard(self) -> None:
        """Let the main studio open the useful publishing view in one click."""
        if self._open_dashboard_on_start and self.winfo_exists():
            self.open_production_center()

    def _maximize_window(self) -> None:
        """Use the available workspace without forcing a separate fullscreen mode."""
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    def _setup_styles(self) -> None:
        """Give this separate window the same calm, modern dark look as Book Studio."""
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        bg, panel, raised, text, muted, border, primary = "#101418", "#171d23", "#222a31", "#f4f7f8", "#aab7bd", "#34424a", "#10a37f"
        style.configure("Publish.TFrame", background=bg)
        style.configure("Publish.Card.TFrame", background=panel)
        style.configure("Publish.TLabel", background=bg, foreground=text, font=("Segoe UI", 9))
        style.configure("Publish.Title.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 22))
        style.configure("Publish.Subtitle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 10))
        style.configure("Publish.BookTitle.TLabel", background=bg, foreground=text, font=("Segoe UI", 14, "bold"))
        style.configure("Publish.Status.TLabel", background=raised, foreground="#d9f5ee", padding=(12, 9), font=("Segoe UI", 9))
        style.configure("Publish.Card.TLabelframe", background=panel, borderwidth=1, relief="solid", bordercolor=border)
        style.configure("Publish.Card.TLabelframe.Label", background=panel, foreground=text, font=("Segoe UI", 10, "bold"))
        style.configure("Publish.TEntry", fieldbackground="#303030", foreground=text, insertcolor=text, bordercolor=border)
        style.configure("Publish.TCombobox", fieldbackground="#303030", background=panel, foreground=text, arrowcolor=text)
        style.map("Publish.TCombobox", fieldbackground=[("readonly", "#303030")], foreground=[("readonly", text)])
        style.configure("Publish.Treeview", background="#171d23", fieldbackground="#171d23", foreground=text, rowheight=32, bordercolor=border)
        style.map("Publish.Treeview", background=[("selected", "#0c755c")], foreground=[("selected", "#ffffff")])
        style.configure("Publish.Treeview.Heading", background="#222a31", foreground=text, font=("Segoe UI Semibold", 9), relief="flat")
        style.map("Publish.Treeview.Heading", background=[("active", "#2c3941")])
        style.configure("Publish.Primary.TButton", background=primary, foreground="#ffffff", padding=(12, 8), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Publish.Primary.TButton", background=[("active", "#0b896a")])
        style.configure("Publish.Action.TButton", background="#343434", foreground=text, padding=(10, 7), font=("Segoe UI", 9), borderwidth=0)
        style.map("Publish.Action.TButton", background=[("active", "#414141")])
        style.configure("Publish.Action.TMenubutton", background="#343434", foreground=text, padding=(10, 7), font=("Segoe UI", 9), borderwidth=0)
        style.map("Publish.Action.TMenubutton", background=[("active", "#414141")])
        style.configure("Publish.Primary.TMenubutton", background=primary, foreground="#ffffff", padding=(12, 8), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Publish.Primary.TMenubutton", background=[("active", "#0b896a")])
        style.configure("Publish.TNotebook", background=bg, borderwidth=0, tabmargins=(0, 6, 0, 0))
        style.configure("Publish.TNotebook.Tab", background="#303030", foreground=muted, padding=(16, 8), font=("Segoe UI", 9, "bold"))
        style.map("Publish.TNotebook.Tab", background=[("selected", panel)], foreground=[("selected", text)])

    def _build(self) -> None:
        root = ttk.Frame(self, padding=(30, 24), style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(3, weight=1)
        heading = ttk.Frame(root, style="Publish.TFrame"); heading.grid(row=0, column=0, sticky="ew"); heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Publishing Center", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(heading, text="What needs attention?", command=self.open_book_readiness, style="Publish.Primary.TButton").grid(row=0, column=1, sticky="e", padx=(0, 8))
        ttk.Button(heading, text="Production dashboard", command=self.open_production_center, style="Publish.Action.TButton").grid(row=0, column=2, sticky="e", padx=(0, 8))
        more = ttk.Menubutton(heading, text="More tools", style="Publish.Action.TMenubutton")
        more.grid(row=0, column=3, sticky="e", padx=(0, 8))
        more_menu = tk.Menu(more, tearoff=False)
        more_menu.add_command(label="What should I do next?", command=self.open_business_guidance)
        more_menu.add_command(label="Review selected books", command=self.open_batch_review)
        more_menu.add_command(label="Approved production queue", command=self.open_approved_queue)
        more_menu.add_separator()
        more_menu.add_command(label="Upload status", command=self.open_upload_status)
        more_menu.add_command(label="Create Etsy bundle", command=self.open_etsy_bundle_builder)
        more_menu.add_command(label="Business guidance", command=self.open_business_guidance)
        more_menu.add_command(label="Marketplace connections", command=self.open_marketplace_connections)
        more_menu.add_command(label="ISBN manager", command=lambda: ISBNManagerDialog(self, self.service))
        more_menu.add_command(label="Launch dashboard", command=self.open_launch_dashboard)
        more_menu.add_command(label="Visual series map", command=self.open_series_map)
        more_menu.add_command(label="Legacy recovery tools", command=self.open_recovery_center)
        more.configure(menu=more_menu)
        ttk.Button(heading, text="New book", command=self.start_new_book, style="Publish.Primary.TButton").grid(row=0, column=4, sticky="e")
        ttk.Button(heading, text="Create best version", command=self.create_best_version, style="Publish.Primary.TButton").grid(row=0, column=5, sticky="e", padx=(8, 0))
        ttk.Label(root, text="Choose a book, review its production readiness, then prepare the marketplace files you need. A Master Release is your approved source package; marketplace packages are safe copies made from it.", style="Publish.Subtitle.TLabel", wraplength=1150).grid(row=1, column=0, sticky="w", pady=(3, 16))
        recommended = ttk.Labelframe(root, text="Recommended next books", padding=12, style="Publish.Card.TLabelframe")
        recommended.grid(row=2, column=0, sticky="ew", pady=(0, 10)); recommended.columnconfigure(0, weight=1)
        ttk.Label(recommended, text="These are the strongest places to start from your own checked library. New books appear before completed packages that are ready to prepare.", style="Publish.TLabel", wraplength=1080).grid(row=0, column=0, sticky="w", pady=(0, 8))
        rec_columns = ("book", "topic", "puzzles", "next", "why")
        self.recommendation_tree = ttk.Treeview(recommended, columns=rec_columns, show="headings", height=4, selectmode="browse", style="Publish.Treeview")
        self.recommendation_tree.tag_configure("alternate", background="#1d262d")
        rec_labels = {"book": "Recommended book", "topic": "Topic", "puzzles": "Puzzles", "next": "Next step", "why": "Why we recommend it"}
        rec_widths = {"book": 290, "topic": 190, "puzzles": 70, "next": 120, "why": 430}
        for key in rec_columns:
            self.recommendation_tree.heading(key, text=rec_labels[key]); self.recommendation_tree.column(key, width=rec_widths[key], anchor="w" if key not in ("puzzles",) else "center")
        self.recommendation_tree.grid(row=1, column=0, sticky="ew")
        self.recommendation_tree.bind("<Double-1>", lambda _event: self.open_recommended_book())
        rec_actions = ttk.Frame(recommended); rec_actions.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(rec_actions, text="Open selected book", command=self.open_recommended_book, style="Publish.Action.TButton").pack(side="left")
        ttk.Button(rec_actions, text="Create Master Release", command=self.create_recommended_package, style="Publish.Primary.TButton").pack(side="left", padx=6)
        ttk.Button(rec_actions, text="Refresh recommendations", command=self.refresh_recommendations, style="Publish.Action.TButton").pack(side="left", padx=6)
        # Structural Hub foundation: existing widgets keep their logic and
        # simply live inside the Catalog tab; the Selected Book tab stays a
        # placeholder until later steps add readiness content.
        self.notebook = ttk.Notebook(root, style="Publish.TNotebook"); self.notebook.grid(row=3, column=0, sticky="nsew")
        catalog_tab = ttk.Frame(self.notebook, style="Publish.TFrame")
        selected_tab = ttk.Frame(self.notebook, style="Publish.TFrame")
        content_tab = ttk.Frame(self.notebook, style="Publish.TFrame")
        queue_tab = ttk.Frame(self.notebook, style="Publish.TFrame")
        self.notebook.add(catalog_tab, text="Catalog")
        self.notebook.add(selected_tab, text="Selected Book")
        self.notebook.add(content_tab, text="Content capacity")
        self.notebook.add(queue_tab, text="Production queue")
        catalog_tab.columnconfigure(0, weight=1); catalog_tab.rowconfigure(1, weight=1)
        selected_tab.columnconfigure(0, weight=1); selected_tab.rowconfigure(0, weight=1)
        self.selected_empty_text = tk.StringVar(value="Select a book from the Catalog tab to view publishing readiness and marketplace actions.")
        self.selected_empty = ttk.Label(selected_tab, textvariable=self.selected_empty_text, style="Publish.Subtitle.TLabel", wraplength=760, justify="center", anchor="center")
        self.selected_empty.grid(row=0, column=0, sticky="nsew")
        self.selected_content = ttk.Frame(selected_tab, style="Publish.TFrame")
        self._build_selected_content()
        self._build_content_capacity(content_tab)
        self._build_production_queue(queue_tab)
        filters = ttk.Frame(catalog_tab, style="Publish.TFrame"); filters.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(filters, text="Find", style="Publish.TLabel").pack(side="left"); search = ttk.Entry(filters, textvariable=self.filter_text, width=28, style="Publish.TEntry"); search.pack(side="left", padx=(7, 14)); search.bind("<KeyRelease>", lambda _event: self._schedule_catalog_search())
        ttk.Label(filters, text="Show", style="Publish.TLabel").pack(side="left")
        view_combo = ttk.Combobox(filters, textvariable=self.catalog_view, values=CATALOG_VIEWS, state="readonly", width=18, style="Publish.TCombobox")
        view_combo.pack(side="left", padx=7); view_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(filters, text="Marketplace", style="Publish.TLabel").pack(side="left", padx=(8, 0)); combo = ttk.Combobox(filters, textvariable=self.market_filter, values=("All marketplaces", *[DISPLAY[key] for key in MARKETPLACES]), state="readonly", width=14, style="Publish.TCombobox"); combo.pack(side="left", padx=7); combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(filters, text="Scan prepared folders", command=self.scan_local_status, style="Publish.Action.TButton").pack(side="right")
        ttk.Button(filters, text="Sync catalog", command=lambda: self.refresh(sync=True), style="Publish.Action.TButton").pack(side="right", padx=(0, 6))
        columns = ("book", "series", "type", "pages", "record", "status", "next")
        self.tree = ttk.Treeview(catalog_tab, columns=columns, show="headings", selectmode="extended", style="Publish.Treeview")
        self.tree.tag_configure("alternate", background="#1d262d")
        labels = {"book": "Book", "series": "Series", "type": "Puzzle type", "pages": "Pages", "record": "Record", "status": "Status", "next": "One next action"}
        widths = {"book": 270, "series": 145, "type": 125, "pages": 55, "record": 125, "status": 140, "next": 260}
        for key in columns: self.tree.heading(key, text=labels[key]); self.tree.column(key, width=widths[key], anchor="w" if key in ("book", "series", "type", "next") else "center")
        self.tree.grid(row=1, column=0, sticky="nsew"); scroll = ttk.Scrollbar(catalog_tab, orient="vertical", command=self.tree.yview); scroll.grid(row=1, column=1, sticky="ns"); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self.open_book())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.refresh_selected_view())
        actions = ttk.Frame(catalog_tab, style="Publish.TFrame"); actions.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(actions, text="Book details", command=self.open_book, style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions, text="Review & proof", command=self.open_listing_review, style="Publish.Action.TButton").pack(side="left", padx=6)
        ttk.Button(actions, text="Approve for production", command=self.approve_selected, style="Publish.Action.TButton").pack(side="left", padx=6)
        ttk.Button(actions, text="Create Master Release", command=self.create_selected_package, style="Publish.Primary.TButton").pack(side="left", padx=6)
        prepare = ttk.Menubutton(actions, text="Prepare selected", style="Publish.Primary.TMenubutton")
        prepare.pack(side="left", padx=6)
        prepare_menu = tk.Menu(prepare, tearoff=False)
        prepare_menu.add_command(label="Amazon KDP", command=lambda: self.prepare(["amazon"]))
        prepare_menu.add_command(label="Etsy", command=lambda: self.prepare(["etsy"]))
        prepare_menu.add_command(label="IngramSpark", command=lambda: self.prepare(["ingram"]))
        prepare_menu.add_command(label="Direct Website", command=lambda: self.prepare(["website"]))
        prepare_menu.add_separator()
        prepare_menu.add_command(label="All marketplaces", command=lambda: self.prepare(list(MARKETPLACES)))
        prepare.configure(menu=prepare_menu)
        details = ttk.Menubutton(actions, text="More", style="Publish.Action.TMenubutton")
        details.pack(side="left")
        details_menu = tk.Menu(details, tearoff=False)
        details_menu.add_command(label="Open Master Release Folder", command=self.open_selected_master)
        details_menu.add_command(label="Lock approved release", command=self.lock_selected_release)
        details_menu.add_command(label="Check selected series", command=self.check_selected_series)
        details_menu.add_command(label="Why not KDP ready?", command=self.show_kdp_readiness)
        details_menu.add_command(label="Release checklist", command=self.show_release_checklist)
        details_menu.add_command(label="Compare with saved books", command=self.compare_selected_book)
        details.configure(menu=details_menu)
        ttk.Label(root, textvariable=self.status, wraplength=1150, style="Publish.Status.TLabel").grid(row=4, column=0, sticky="ew", pady=(10, 0))

    def _build_production_queue(self, tab) -> None:
        """Show the persisted production truth inside Publishing Center."""
        tab.columnconfigure(0, weight=1); tab.rowconfigure(2, weight=1)
        ttk.Label(tab, text="Production queue", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w", pady=(12, 3))
        filters = ttk.Frame(tab, style="Publish.TFrame"); filters.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        choices = (
            ("Status", self.job_status_filter, ("All statuses", "ready", "waiting_for_review", "needs_review", "blocked", "stale", "stopped", "complete"), 19),
            ("Puzzle type", self.job_type_filter, ("All puzzle types", "word_search", "sudoku", "cryptogram", "scramble_trivia", "mixed"), 18),
            ("Priority", self.job_priority_filter, ("All priorities", "urgent", "high", "normal", "low"), 15),
        )
        for label, variable, values, width in choices:
            ttk.Label(filters, text=label, style="Publish.TLabel").pack(side="left", padx=(0, 5))
            combo = ttk.Combobox(filters, textvariable=variable, values=values, state="readonly", width=width, style="Publish.TCombobox"); combo.pack(side="left", padx=(0, 12)); combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_production_queue())
        ttk.Label(filters, text="Find issue", style="Publish.TLabel").pack(side="left", padx=(0, 5))
        search = ttk.Entry(filters, textvariable=self.job_attention_filter, width=22, style="Publish.TEntry"); search.pack(side="left"); search.bind("<KeyRelease>", lambda _event: self.refresh_production_queue())
        ttk.Button(filters, text="Refresh", command=self.refresh_production_queue, style="Publish.Action.TButton").pack(side="right")
        columns = ("title", "type", "status", "stage", "next", "priority")
        self.job_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse", style="Publish.Treeview")
        labels = {"title":"Book", "type":"Puzzle type", "status":"Status", "stage":"Waiting at", "next":"What to do", "priority":"Priority"}
        widths = {"title":300, "type":120, "status":135, "stage":145, "next":280, "priority":85}
        for key in columns: self.job_tree.heading(key, text=labels[key]); self.job_tree.column(key, width=widths[key], anchor="w")
        self.job_tree.grid(row=2, column=0, sticky="nsew"); scroll = ttk.Scrollbar(tab, orient="vertical", command=self.job_tree.yview); scroll.grid(row=2, column=1, sticky="ns"); self.job_tree.configure(yscrollcommand=scroll.set)
        self.job_note = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.job_note, style="Publish.Status.TLabel", wraplength=1100).grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.refresh_production_queue()

    def refresh_production_queue(self) -> None:
        status = "" if self.job_status_filter.get() == "All statuses" else self.job_status_filter.get()
        puzzle_type = "" if self.job_type_filter.get() == "All puzzle types" else self.job_type_filter.get()
        priority = "" if self.job_priority_filter.get() == "All priorities" else self.job_priority_filter.get()
        rows = ProductionJobIndex(self.service.project).rows(status=status, puzzle_type=puzzle_type, priority=priority, blocker=self.job_attention_filter.get().strip())
        self.job_tree.delete(*self.job_tree.get_children())
        for index, row in enumerate(rows):
            iid = f"job_{index}"
            self.job_tree.insert("", "end", iid=iid, values=(row["title"], row["puzzle_type"].replace("_", " ").title(), row["status"].replace("_", " ").title(), row["current_stage"].replace("_", " ").title(), row["next_action"], row["priority"].title()))
        attention = sum(1 for row in rows if row["status"] in {"blocked", "needs_review", "stale", "stopped"})
        waiting = sum(1 for row in rows if row["status"] == "waiting_for_review")
        ready = sum(1 for row in rows if row["status"] in {"ready", "complete"})
        self.job_note.set(f"Showing {len(rows)} production job(s): {attention} need attention, {waiting} are waiting for your review, and {ready} are ready or complete. This screen reads saved job records; it never publishes automatically.")

    def _build_content_capacity(self, tab) -> None:
        """A full scrollable page, not only a table with a scrollbar."""
        tab.columnconfigure(0, weight=1); tab.rowconfigure(0, weight=1)
        canvas = tk.Canvas(tab, background="#101418", highlightthickness=0, borderwidth=0)
        page_scroll = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=page_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew"); page_scroll.grid(row=0, column=1, sticky="ns")
        page = ttk.Frame(canvas, style="Publish.TFrame")
        page_window = canvas.create_window((0, 0), window=page, anchor="nw")
        def fit_page(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def fit_width(event):
            canvas.itemconfigure(page_window, width=event.width)
        page.bind("<Configure>", fit_page); canvas.bind("<Configure>", fit_width)
        def wheel(event):
            # Child widgets do not inherit a parent frame's <MouseWheel>
            # binding in Tk.  The earlier enter/leave approach therefore
            # stopped scrolling whenever the pointer crossed a label or
            # button.  Route wheel events from the full window only while
            # this notebook tab is active; the table keeps its own scroll.
            if str(self.notebook.select()) != str(tab) or event.widget is self.capacity_tree:
                return None
            steps = int(event.delta / 120) if event.delta else 0
            if steps:
                canvas.yview_scroll(-steps, "units")
                return "break"
            return None
        self.bind_all("<MouseWheel>", wheel, add="+")
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text="Content capacity", style="Publish.Title.TLabel").grid(row=0,column=0,sticky="w",padx=18,pady=(18,2))
        ttk.Label(page, text="A practical answer to “what can I make next?” Word Search and other puzzle types are counted separately, so no topic is presented as ready until its actual content supports it.", style="Publish.Subtitle.TLabel", wraplength=1050).grid(row=1,column=0,sticky="w",padx=18,pady=(0,12))
        columns=("topic","words","wordbooks","cryptos","cryptobooks","trivia","triviabooks","next")
        self.capacity_tree=ttk.Treeview(page,columns=columns,show="headings",style="Publish.Treeview",selectmode="browse",height=12)
        headings={"topic":"Topic family","words":"Topic words","wordbooks":"Word Search books","cryptos":"Cryptogram entries","cryptobooks":"Cryptogram books","trivia":"Trivia entries","triviabooks":"Trivia books","next":"What to build next"}
        widths={"topic":185,"words":95,"wordbooks":115,"cryptos":130,"cryptobooks":120,"trivia":105,"triviabooks":105,"next":245}
        for key in columns: self.capacity_tree.heading(key,text=headings[key]); self.capacity_tree.column(key,width=widths[key],anchor="w" if key in {"topic","next"} else "center")
        self.capacity_tree.grid(row=2,column=0,sticky="ew",padx=(18,0))
        capacity_scroll=ttk.Scrollbar(page,orient="vertical",command=self.capacity_tree.yview); capacity_scroll.grid(row=2,column=1,sticky="ns",padx=(0,18)); self.capacity_tree.configure(yscrollcommand=capacity_scroll.set)
        self.capacity_tree.bind("<MouseWheel>", lambda event: (self.capacity_tree.yview_scroll(-1 * int(event.delta / 120), "units"), "break")[1])
        actions=ttk.Frame(page,style="Publish.TFrame"); actions.grid(row=3,column=0,sticky="ew",padx=18,pady=12)
        ttk.Button(actions,text="Refresh capacity",command=self.refresh_content_capacity,style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions,text="Create only if ready",command=self.use_content_blueprint,style="Publish.Primary.TButton").pack(side="left",padx=7)
        ttk.Button(actions,text="Plan safe expansion",command=self.open_content_expansion,style="Publish.Action.TButton").pack(side="left",padx=7)
        self.capacity_note=tk.StringVar(value=""); ttk.Label(page,textvariable=self.capacity_note,style="Publish.Status.TLabel",wraplength=1050).grid(row=4,column=0,sticky="ew",padx=18,pady=(0,18))
        self.capacity_rows={}; self.refresh_content_capacity()

    def refresh_content_capacity(self) -> None:
        from .content_capacity import topic_capacity
        self.capacity_rows={}; self.capacity_tree.delete(*self.capacity_tree.get_children())
        rows=topic_capacity(self.service.project)
        for index,row in enumerate(rows):
            iid=f"capacity_{index}"; self.capacity_rows[iid]=row
            self.capacity_tree.insert("","end",iid=iid,values=(row["topic"],row["words"],row["word_search_books"],row["cryptograms"],row["cryptogram_books"],row["trivia"],row["trivia_books"],row["next_step"]))
        ready=sum(1 for row in rows if row["word_search_books"] >= 2)
        cross=sum(1 for row in rows if row["cryptogram_books"] >= 2 and row["trivia_books"] >= 2)
        self.capacity_note.set(f"{ready} topic families can support at least two full Word Search books. {cross} currently support two curated Cryptogram and Trivia books too. The remaining gaps are clearly labeled instead of being treated as ready.")

    def use_content_blueprint(self) -> None:
        selected=self.capacity_tree.selection()
        if not selected: messagebox.showwarning("Choose a topic", "Choose a topic family from Content capacity first.", parent=self); return
        topic=self.capacity_rows[selected[0]]["topic"]
        gate=topic_gate(self.service.project, topic)
        if not gate["ready"]:
            messagebox.showwarning("Topic needs more words", f"{topic}\n\n{gate['message']}\n\nIt stays visible for planning, but automatic creation is locked until the topic can honestly support the full no-repeat book.", parent=self)
            return
        if not self.new_book:
            messagebox.showinfo("Ready blueprint", f"{topic}\n\n{gate['message']}", parent=self)
            return
        self.destroy()
        self.new_book({"topic": topic, "plan": gate["plan"], "words": gate["words"], "two_book_ready": gate["two_book_ready"]})

    def open_content_expansion(self) -> None:
        selected = self.capacity_tree.selection()
        if not selected:
            messagebox.showinfo("Choose a topic", "Choose a topic family first. The planner will show its real word gap and linked sources.", parent=self)
            return
        ContentExpansionDialog(self, self.service.project, self.capacity_rows[selected[0]]["topic"])

    def _build_selected_content(self) -> None:
        """Real Selected Book pane: overview, What's left, readiness grid, actions."""
        self.selected_book = None; self.selected_market_key = ""; self.marketplace_row_map: dict[str, dict] = {}
        # Set while the readiness grid rebuilds: ttk delivers <<TreeviewSelect>>
        # asynchronously for programmatic delete/clear, and those echoes must
        # not be mistaken for the user clicking an empty area.
        self._market_rebuilding = False
        root = self.selected_content
        root.columnconfigure(0, weight=1); root.rowconfigure(3, weight=1)
        overview = ttk.Labelframe(root, text="Book overview", padding=12, style="Publish.Card.TLabelframe"); overview.grid(row=0, column=0, sticky="ew"); overview.columnconfigure(0, weight=1)
        self.sel_title = tk.StringVar(value=""); self.sel_detail = tk.StringVar(value=""); self.sel_path = tk.StringVar(value=""); self.sel_counts = tk.StringVar(value="")
        self.selected_catalog_state = {"status": "Needs review", "next_action": "Review the book"}
        ttk.Label(overview, textvariable=self.sel_title, style="Publish.BookTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(overview, text="Commercial plan", command=self._show_commercial_plan, style="Publish.Action.TButton").grid(row=0, column=1, sticky="e", padx=(0, 6))
        # Read-only canonical product inspector (Universal Publishing adoption).
        ttk.Button(overview, text="View Master Product", command=self._open_master_product, style="Publish.Action.TButton").grid(row=0, column=2, sticky="e")
        ttk.Label(overview, textvariable=self.sel_detail, style="Publish.TLabel", wraplength=1080).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Label(overview, textvariable=self.sel_path, style="Publish.Subtitle.TLabel", wraplength=1080, justify="left").grid(row=2, column=0, sticky="w", pady=(3, 0))
        ttk.Label(overview, textvariable=self.sel_counts, style="Publish.Status.TLabel", wraplength=850).grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.primary_next_button = ttk.Button(overview, text="Open next step", command=self._run_primary_catalog_action, style="Publish.Primary.TButton")
        self.primary_next_button.grid(row=3, column=1, columnspan=2, sticky="e", padx=(10, 0), pady=(8, 0))
        left = ttk.Labelframe(root, text="What's left?", padding=12, style="Publish.Card.TLabelframe"); left.grid(row=1, column=0, sticky="ew", pady=(10, 0)); left.columnconfigure(0, weight=1)
        self.whats_left_box = tk.Text(left, height=8, wrap="word", state="disabled", background="#292929", foreground="#d9f5ee", relief="flat", padx=10, pady=8)
        self.whats_left_box.grid(row=0, column=0, sticky="ew")
        cards = ttk.Labelframe(root, text="Choose a marketplace", padding=10, style="Publish.Card.TLabelframe"); cards.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.market_cards = ttk.Frame(cards, style="Publish.Card.TFrame")
        self.market_cards.pack(fill="x", expand=True)
        grid_frame = ttk.Labelframe(root, text="Detailed marketplace status", padding=12, style="Publish.Card.TLabelframe"); grid_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        grid_frame.columnconfigure(0, weight=1); grid_frame.rowconfigure(0, weight=1)
        columns = ("platform", "status", "readiness", "listing", "link", "updated")
        self.market_tree = ttk.Treeview(grid_frame, columns=columns, show="headings", height=7, selectmode="browse", style="Publish.Treeview")
        heads = {"platform": "Platform", "status": "Status", "readiness": "Readiness", "listing": "Listing ID", "link": "Live link", "updated": "Updated"}
        widths = {"platform": 190, "status": 110, "readiness": 300, "listing": 130, "link": 100, "updated": 140}
        for key in columns:
            anchor = "w" if key in ("platform", "readiness") else "center"
            self.market_tree.heading(key, text=heads[key]); self.market_tree.column(key, width=widths[key], anchor=anchor)
        self.market_tree.tag_configure("attention", foreground="#ffb46b")
        self.market_tree.tag_configure("ok", foreground="#9fe8c6")
        self.market_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(grid_frame, orient="vertical", command=self.market_tree.yview); scroll.grid(row=0, column=1, sticky="ns"); self.market_tree.configure(yscrollcommand=scroll.set)
        self.market_tree.bind("<<TreeviewSelect>>", lambda _event: self._on_marketplace_row_selected())
        self.sel_error_detail = tk.StringVar(value="")
        ttk.Label(grid_frame, textvariable=self.sel_error_detail, style="Publish.Subtitle.TLabel", wraplength=1080, justify="left").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        # Truthful online-integration line (e.g. "a draft listing was created on
        # Etsy — it is NOT published").  Empty until an automated flow runs.
        self.sel_online_detail = tk.StringVar(value="")
        ttk.Label(grid_frame, textvariable=self.sel_online_detail, style="Publish.Subtitle.TLabel", wraplength=1080, justify="left").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        bar = ttk.Frame(root, style="Publish.TFrame"); bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        specs = (
            ("prepare", "Prepare selected marketplace", self._prepare_selected_marketplace, "Publish.Primary.TButton"),
            ("validate", "Validate", self._validate_selected_marketplace, "Publish.Action.TButton"),
            ("copy", "Copy listing", self._copy_selected_listing_information, "Publish.Action.TButton"),
            ("sheet", "Open publishing sheet", self._open_publishing_sheet, "Publish.Action.TButton"),
            ("payhip_preview", "Open Payhip preview", self._open_payhip_preview, "Publish.Action.TButton"),
            ("payhip_customer", "Open customer PDF", self._open_payhip_customer_pdf, "Publish.Action.TButton"),
            ("folder", "Open prepared folder", self._open_prepared_folder, "Publish.Action.TButton"),
            ("site", "Open publisher site", self._open_publisher_site, "Publish.Action.TButton"),
            ("listing", "Open saved live listing", self._open_saved_listing, "Publish.Action.TButton"),
            ("record", "Record listing / update status", self._open_record_listing, "Publish.Primary.TButton"),
            ("draft", "Create Etsy draft", self._create_etsy_draft, "Publish.Action.TButton"),
            ("export", "Generate Export Package", self._generate_export_package, "Publish.Action.TButton"),
            ("history", "View history", self._open_marketplace_history, "Publish.Action.TButton"),
        )
        self.market_buttons: dict[str, ttk.Button] = {}
        for name, label, command, style_name in specs:
            button = ttk.Button(bar, text=label, command=command, style=style_name, state="disabled")
            self.market_buttons[name] = button
        # Keep the four normal next actions visible.  Less common file,
        # preview, online and history actions remain available in two short
        # menus instead of overflowing a laptop-width row.
        for name in ("prepare", "validate", "copy", "record"):
            self.market_buttons[name].pack(side="left", padx=(0, 6))
        files = ttk.Menubutton(bar, text="Files & previews ▾", style="Publish.Action.TMenubutton")
        files.pack(side="left", padx=(0, 6))
        files_menu = tk.Menu(files, tearoff=False)
        for name in ("sheet", "payhip_preview", "payhip_customer", "folder"):
            files_menu.add_command(label=self.market_buttons[name].cget("text"), command=self.market_buttons[name].invoke)
        files.configure(menu=files_menu)
        more_actions = ttk.Menubutton(bar, text="More actions ▾", style="Publish.Action.TMenubutton")
        more_actions.pack(side="left")
        more_actions_menu = tk.Menu(more_actions, tearoff=False)
        for name in ("site", "listing", "draft", "export", "history"):
            more_actions_menu.add_command(label=self.market_buttons[name].cget("text"), command=self.market_buttons[name].invoke)
        more_actions.configure(menu=more_actions_menu)
        self.market_action_menus = {
            "sheet": (files_menu, 0), "payhip_preview": (files_menu, 1),
            "payhip_customer": (files_menu, 2), "folder": (files_menu, 3),
            "site": (more_actions_menu, 0), "listing": (more_actions_menu, 1),
            "draft": (more_actions_menu, 2), "export": (more_actions_menu, 3),
            "history": (more_actions_menu, 4),
        }
        ttk.Label(bar, text="Creates files only; nothing is published automatically.", style="Publish.Subtitle.TLabel").pack(side="right")

    def refresh_selected_view(self) -> None:
        """Mirror the catalog selection into the Selected Book tab (no tab switching)."""
        books = self._selected()
        if len(books) != 1:
            self.selected_content.grid_remove(); self.selected_empty.grid()
            if len(books) > 1:
                self.selected_empty_text.set("Multiple books are selected. Catalog batch actions still apply; select exactly one book to see its detailed publishing readiness and marketplace actions.")
            else:
                self.selected_empty_text.set("Select a book from the Catalog tab to view publishing readiness and marketplace actions.")
            self.selected_book, self.selected_market_key, self.marketplace_row_map = None, "", {}
            self.master_product = None
            self.publication_records = {}
            if hasattr(self, "primary_next_button"):
                self.primary_next_button.configure(state="disabled", text="Open next step")
            return
        book = books[0]; self.selected_book = book
        self.selected_content.grid(); self.selected_empty.grid_remove()
        meta = book["metadata"]
        # Canonical read model for this selection (Universal Publishing adoption):
        # display identity flows through MasterProduct; raw records stay available
        # to the service calls below.
        from integrations.factory import MasterProductFactory

        try:
            product = MasterProductFactory.from_book_record(book)
            self.master_product = product
        except Exception:
            self.master_product = None
        self.sel_title.set(meta.get("title") or "Untitled book")
        self.sel_detail.set(selected_book_overview(self.master_product, book) if self.master_product else "")
        package = str(book.get("package_path") or "")
        self.sel_path.set(f"Master package: {package}" if package else "Source theme only — create the complete package to unlock marketplace preparation.")
        truth = self.service.production_truth(book["book_id"])
        records = self.service.db.marketplace_records(book["book_id"])
        rows = truth["marketplaces"]
        self.marketplace_row_map = {row["key"]: row for row in rows}
        # Domain views over the authoritative rows (no second persistence layer):
        self.publication_records = {
            key: PublicationRecord.from_marketplace_record(
                book["book_id"], key, {**record, "marketplace": key, "book_id": book["book_id"]},
                {"integration_state": record.get("integration_state", ""),
                 "idempotency_key": record.get("idempotency_key", ""),
                 "external_sku": record.get("external_sku", ""),
                 "last_synced_at": record.get("last_synced_at", "")})
            for key, record in records.items()
        }
        self.selected_catalog_state = catalog_state(
            book,
            gate=truth["content_and_source"],
            final_review=bool((truth.get("cover") or {}).get("final_local_review")),
            contract_ready=bool((truth.get("package_contract") or {}).get("ready")),
        )
        self.sel_counts.set(
            f"{self.selected_catalog_state['status']}  •  Next: {self.selected_catalog_state['next_action']}\n"
            f"{publishing_counts_line(rows)}"
        )
        self.primary_next_button.configure(
            state="normal", text=self.selected_catalog_state["next_action"]
        )
        self.whats_left_box.configure(state="normal"); self.whats_left_box.delete("1.0", "end"); self.whats_left_box.insert("end", whats_left_text(rows)); self.whats_left_box.configure(state="disabled")
        self.market_tree.selection_remove(*self.market_tree.selection())
        self.market_tree.delete(*self.market_tree.get_children())
        self._market_rebuilding = True
        try:
            for row in rows:
                attention = row["status"] in ("Error", "Needs Review") or bool(row["error_message"])
                tag = "attention" if attention else ("ok" if row["indicator"] == "ok" else "")
                values = marketplace_row_values(
                    self.publication_records.get(row["key"]),
                    DISPLAY_GRID.get(row["key"], row["label"]), row["readiness_label"])
                self.market_tree.insert("", "end", iid=row["key"], tags=(tag,) if tag else (), values=values)
            # Keep the user's marketplace row across refreshes (after Prepare,
            # saving a listing, etc.) so async selection echoes land somewhere
            # stable instead of wiping the action bar state.
            previous_key = self.selected_market_key
            if previous_key in self.marketplace_row_map:
                self.market_tree.selection_set(previous_key)
            else:
                previous_key = ""
            self.selected_market_key = previous_key
        finally:
            self._market_rebuilding = False
        self._render_marketplace_cards(rows)
        self._set_market_error_detail(); self._update_market_actions()

    def _run_primary_catalog_action(self) -> None:
        """Run the one plain-English next action shown for the selected book."""
        if not self.selected_book:
            return
        status = str(self.selected_catalog_state.get("status") or "")
        statuses = self.selected_book.get("statuses") or {}

        def choose_marketplace(wanted: str) -> bool:
            key = next((name for name, value in statuses.items() if value == wanted), "")
            if not key and wanted == "Ready":
                key = "amazon"
            if key not in self.marketplace_row_map:
                return False
            self.selected_market_key = key
            self.market_tree.selection_set(key); self.market_tree.focus(key)
            self._set_market_error_detail(); self._update_market_actions()
            return True

        if status == "Published":
            if choose_marketplace("Published"):
                row = self._current_market_row()
                (self._open_saved_listing if row and row.get("url") else self._open_record_listing)()
            return
        if status == "Uploaded — verify live":
            if choose_marketplace("Uploaded"):
                self._open_record_listing()
            return
        if status == "Ready to publish":
            if choose_marketplace("Ready"):
                row = self._current_market_row()
                (self._open_publishing_sheet if row and row.get("has_local_folder") else self._prepare_selected_marketplace)()
            return
        if status == "Approved":
            if choose_marketplace("Ready"):
                self._prepare_selected_marketplace()
            return
        if status == "Ready to create":
            self.create_selected_package()
            return
        if status in {"Missing package", "Incomplete package"}:
            self.open_listing_review()
            return
        self.open_listing_review()

    def _render_marketplace_cards(self, rows: list[dict]) -> None:
        """Show the normal publish path as compact cards; retain the table for details."""
        for child in self.market_cards.winfo_children():
            child.destroy()
        for column in range(4):
            self.market_cards.columnconfigure(column, weight=1)
        for index, row in enumerate(rows):
            column, line = index % 4, index // 4
            card = ttk.Frame(self.market_cards, padding=9, style="Publish.Card.TFrame")
            card.grid(row=line, column=column, sticky="nsew", padx=4, pady=4)
            ttk.Label(card, text=row["label"], style="Publish.TLabel").pack(anchor="w")
            status = row["readiness_label"].upper()
            color = "#9fe8c6" if row["status"] in {"Ready", "Uploaded", "Published"} else "#ffbf69" if row["status"] in {"Needs Review", "Error"} else "#aab7bd"
            label = ttk.Label(card, text=status, style="Publish.Subtitle.TLabel")
            label.configure(foreground=color)
            label.pack(anchor="w", pady=(2, 5))
            if row["key"] == "payhip" and row["has_local_folder"]:
                detail = "Customer PDF, preview, images, and sheet ready"
            elif row["has_local_folder"]:
                detail = "Package and publishing sheet ready"
            elif row["issues"]:
                detail = "Needs attention before preparation"
            else:
                detail = "Ready to prepare"
            ttk.Label(card, text=detail, style="Publish.Subtitle.TLabel", wraplength=205).pack(anchor="w")
            action = "Open publishing sheet" if row["has_local_folder"] else "Prepare"
            ttk.Button(card, text=action, command=lambda key=row["key"]: self._market_card_action(key), style="Publish.Action.TButton").pack(anchor="w", pady=(8, 0))

    def _market_card_action(self, key: str) -> None:
        if key not in self.marketplace_row_map:
            return
        self.selected_market_key = key
        self.market_tree.selection_set(key); self.market_tree.focus(key)
        self._set_market_error_detail(); self._update_market_actions()
        if self.marketplace_row_map[key]["has_local_folder"]:
            self._open_publishing_sheet()
        else:
            self._prepare_selected_marketplace()

    def _on_marketplace_row_selected(self) -> None:
        if self._market_rebuilding:
            return
        selection = self.market_tree.selection()
        self.selected_market_key = selection[0] if selection else ""
        self._set_market_error_detail()
        self._update_market_actions()

    def _show_commercial_plan(self) -> None:
        """Show the separate marketplace-value review for the current book.

        It remains a review only: no status, listing, or price is modified
        until the owner deliberately prepares or publishes a marketplace.
        """
        if not self.selected_book:
            messagebox.showinfo("Choose a book", "Select one book first to see its marketplace commercial plan.", parent=self)
            return
        try:
            from .commercial_intelligence import render_commercial_report
            assessment = self.service.commercial_assessment(self.selected_book["book_id"])
            self._show_report("Marketplace commercial plan", render_commercial_report(assessment))
        except Exception as exc:
            self.status.set("Commercial plan could not be created. Your saved book was not changed.")
            messagebox.showerror("Commercial plan", str(exc), parent=self)

    def _set_market_error_detail(self) -> None:
        """One shared truth for the attention and online lines under the grid."""
        row = self.marketplace_row_map.get(self.selected_market_key)
        if not row:
            self.sel_error_detail.set("")
        elif row["key"] == "payhip" and self._payhip_folder() and (self._payhip_folder() / "payhip_manifest.json").is_file():
            # Keep the compact marketplace view useful without showing every
            # tag or raw manifest field.  The publishing sheet remains the
            # detailed, one-document source of truth for manual entry.
            try:
                import json
                manifest = json.loads((self._payhip_folder() / "payhip_manifest.json").read_text(encoding="utf-8"))
                checks = [
                    ("Customer PDF", self._payhip_folder() / "customer_product.pdf"),
                    ("Preview PDF", self._payhip_folder() / "preview.pdf"),
                    ("Product images", self._payhip_folder() / "product_cover.png"),
                    ("Publishing sheet", self._payhip_folder() / "PAYHIP_PUBLISHING_SHEET.txt"),
                ]
                ready = ", ".join(f"{label}: {'Ready' if path.is_file() else 'Missing'}" for label, path in checks)
                self.sel_error_detail.set(f"Payhip — {ready}. Collection: {manifest.get('collection', '—')}; Category: {manifest.get('marketplace_category', '—')}; Tags: {'Ready' if manifest.get('tags') else 'Missing'}; Price: ${float(manifest.get('price') or 0):.2f}.")
            except (OSError, ValueError, TypeError):
                self.sel_error_detail.set("Payhip package is present. Open its publishing sheet for the customer PDF, preview, images, category, tags, and price.")
        elif row["error_message"]:
            self.sel_error_detail.set(f"Attention — {row['label']}: {row['error_message']}")
        else:
            blockers, _advisories = split_issues(row["issues"])
            self.sel_error_detail.set(f"Needs items — {blockers[0]}" if blockers else "")
        self.sel_online_detail.set(online_state_text(row.get("integration_state", "")) if row else "")

    def _update_market_actions(self) -> None:
        """Enable each action only when the selected record actually supports it."""
        row = self.marketplace_row_map.get(self.selected_market_key)
        payhip_folder = self._payhip_folder() if row and row["key"] == "payhip" else None
        enabled = {
            "prepare": bool(row),
            "validate": bool(row),
            "copy": bool(row and self.selected_book),
            "sheet": bool(row and row["has_local_folder"]),
            "payhip_preview": bool(payhip_folder and (payhip_folder / "preview.pdf").is_file()),
            "payhip_customer": bool(payhip_folder and (payhip_folder / "customer_product.pdf").is_file()),
            "folder": bool(row and row["has_local_folder"]),
            "site": bool(row and row["portal_url"]),
            "listing": bool(row and row["url"]),
            "record": bool(row),
            "draft": draft_action_enabled(row) and not getattr(self, "_draft_in_progress", False),
            "export": export_action_enabled(row, integration_info_for(row["key"] if row else "")) and not getattr(self, "_export_in_progress", False),
            "history": bool(row),
        }
        for name, button in self.market_buttons.items():
            button.configure(state="normal" if enabled[name] else "disabled")
        for name, (menu, index) in self.market_action_menus.items():
            menu.entryconfigure(index, state="normal" if enabled[name] else "disabled")

    def _current_market_row(self) -> dict | None:
        return self.marketplace_row_map.get(self.selected_market_key)

    def _payhip_folder(self) -> Path | None:
        if not self.selected_book:
            return None
        package = Path(str(self.selected_book.get("package_path") or ""))
        return marketplace_handoff_folder(package, "payhip") if package else None

    def _open_payhip_file(self, filename: str, friendly_name: str) -> None:
        folder = self._payhip_folder()
        target = folder / filename if folder else None
        if target and target.is_file():
            os.startfile(str(target))
            self.status.set(f"Opened the Payhip {friendly_name}.")
        else:
            messagebox.showinfo("Payhip file not ready", "Choose Prepare for Payhip first. It creates the local download, preview, images, and publishing sheet; it never uploads anything.", parent=self)

    def _open_payhip_preview(self) -> None:
        self._open_payhip_file("preview.pdf", "customer preview")

    def _open_payhip_customer_pdf(self) -> None:
        self._open_payhip_file("customer_product.pdf", "customer download PDF")

    def _prepare_selected_marketplace(self) -> None:
        if self._current_market_row():
            self.prepare([self.selected_market_key])

    def _validate_selected_marketplace(self) -> None:
        """Re-run the platform validator read-only; advisories stay advisory."""
        row = self._current_market_row()
        if not row:
            return
        sections: list[str] = []
        if row["status"] in ("Uploaded", "Published"):
            sections.append(f"This marketplace is already recorded as {row['status']}; this check looks at local files and saved details only.")
        blockers, advisories = split_issues(row["issues"])
        sections.append("Required before preparing:\n• " + "\n• ".join(blockers) if blockers else "All required items are present for preparation.")
        if advisories:
            sections.append("Advisory notes (these do not block preparation):\n• " + "\n• ".join(advisories))
        messagebox.showinfo(f"Validation — {row['label']}", "\n\n".join(sections), parent=self)

    def _copy_selected_listing_information(self) -> None:
        """Put the full platform listing sheet on the Windows clipboard."""
        row = self._current_market_row()
        book = self.selected_book
        if not row or not book:
            return
        try:
            text = self.service.listing_copy(book["book_id"], row["key"])
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception as exc:
            messagebox.showerror("Could not copy listing information", str(exc), parent=self)
            return
        self.status.set(f"Copied {row['label']} listing information. Paste it into the seller portal or a note when you are ready.")

    def _open_prepared_folder(self) -> None:
        row = self._current_market_row(); book = self.selected_book
        if not row or not book:
            return
        package = str(book.get("package_path") or "")
        folder = os.path.join(package, PREPARED_FOLDER_NAMES.get(row["key"], row["key"])) if package else ""
        if folder and os.path.isdir(folder):
            os.startfile(folder); self.status.set(f"Opened the prepared {row['label']} folder. Nothing was uploaded or changed.")
        else:
            messagebox.showinfo("No prepared folder yet", f"The prepared {row['label']} folder does not exist yet. Click Prepare first — this creates files only, it never uploads.", parent=self)

    def _open_publishing_sheet(self) -> None:
        """Open the platform's human publishing sheet after local preparation."""
        from .manual_sheets import sheet_filename
        row = self._current_market_row(); book = self.selected_book
        if not row or not book:
            return
        package = Path(str(book.get("package_path") or ""))
        folder_name = "kdp" if row["key"] == "amazon" else row["key"]
        sheet = marketplace_handoff_folder(package, folder_name) / sheet_filename(row["key"])
        if sheet.is_file():
            os.startfile(str(sheet)); self.status.set(f"Opened the {row['label']} publishing sheet.")
        else:
            messagebox.showinfo("Publishing sheet not ready", "Choose Prepare first. It creates the handoff folder and its copy-ready publishing sheet locally.", parent=self)

    def _open_publisher_site(self) -> None:
        row = self._current_market_row()
        if not row:
            return
        if row["portal_url"]:
            webbrowser.open(row["portal_url"])
            self.status.set(f"Opened the official {row['label']} portal in your browser. Signing in and uploading stay entirely in your hands.")
        else:
            messagebox.showinfo("No seller portal", "This channel has no seller portal. Sell it directly from your own website store.", parent=self)

    def _open_saved_listing(self) -> None:
        row = self._current_market_row()
        if not row:
            return
        if row["url"]:
            webbrowser.open(row["url"])
        else:
            messagebox.showinfo("No saved link yet", "Paste and save the public listing link first — use “Record listing / update status” once the listing is live.", parent=self)

    def _open_record_listing(self) -> None:
        if self.selected_book and self._current_market_row():
            UploadStatusDialog(self, self.service, self.selected_book, self.refresh, initial_marketplace=self.selected_market_key)

    def _open_marketplace_history(self) -> None:
        if self.selected_book and self._current_market_row():
            MarketplaceHistoryDialog(self, self.service, self.selected_book, initial_marketplace=self.selected_market_key)

    def open_marketplace_connections(self) -> None:
        MarketplaceConnectionsDialog(self)

    def _create_etsy_draft(self) -> None:
        """Run the draft-only Etsy automation in a background thread.

        The remote work itself lives in integrations.etsy.draft_service (fully
        tested offline); this handler only guards double-clicks, keeps the UI
        responsive, and reports the truthful result.
        """
        row = self._current_market_row()
        book = self.selected_book
        if not row or not book:
            return
        if getattr(self, "_draft_in_progress", False):
            return
        if not book.get("package_path"):
            messagebox.showinfo("Prepare first", "Create the complete package and choose Prepare Etsy before creating an online draft.", parent=self)
            return
        self._draft_in_progress = True
        button = self.market_buttons.get("draft")
        if button is not None:
            button.configure(state="disabled")
        self.status.set("Connecting to Etsy to create the DRAFT listing… Nothing will be published.")

        service = self.service

        def work():
            from integrations.etsy.draft_service import EtsyDraftService

            try:
                return EtsyDraftService().create_or_resume(service, book)
            except Exception as exc:  # last-resort net so the UI never dies silently
                from integrations.etsy.draft_service import DraftResult

                return DraftResult(ok=False, message=f"Unexpected problem: {exc}")

        def done(result):
            self._draft_in_progress = False
            self.refresh()
            title = "Etsy draft" if result.ok else "Etsy draft needs attention"
            if result.ok:
                messagebox.showinfo(title, result.message + ("\n\nEvents:\n• " + "\n• ".join(result.events) if result.events else ""), parent=self)
            else:
                messagebox.showwarning(title, result.message, parent=self)

        def runner():
            result = work()
            self.after(0, lambda: done(result))

        threading.Thread(target=runner, daemon=True).start()

    def _open_master_product(self) -> None:
        book = self.selected_book
        if not book:
            return
        MasterProductDialog(self, self.service, book)

    def _generate_export_package(self) -> None:
        """Run the registered export-only adapter in a background thread.

        Writes a local handoff folder only. On success the automation-owned
        integration_state becomes "exported"; human-owned statuses are never
        touched (an export package is preparation, not publication).
        """
        row = self._current_market_row()
        book = self.selected_book
        if not row or not book or getattr(self, "_export_in_progress", False):
            return
        info = integration_info_for(row["key"])
        if not export_action_enabled(row, info):
            messagebox.showinfo(
                "Export not available yet",
                f"{row['label']} does not offer an automated export package yet.",
                parent=self)
            return

        self._export_in_progress = True
        button = self.market_buttons.get("export")
        if button is not None:
            button.configure(state="disabled")
        self.status.set(f"Building the {row['label']} export package… Files are written locally only.")

        service = self.service

        def work():
            from integrations.factory import MasterProductFactory
            from integrations.registry import get_export_integration

            try:
                export_key = info.get("export_key") or row["key"]
                adapter = get_export_integration(export_key)
                if adapter is None:
                    from integrations.results import PublishResult

                    return PublishResult.failure("No export adapter is registered for this marketplace.")
                product = MasterProductFactory.from_book_record(book)
                destination = Path(service.output) / "exports" / export_key
                return adapter.export_package(product, destination)
            except Exception as exc:  # last-resort net so the UI never dies silently
                from integrations.results import PublishResult

                return PublishResult.failure(f"Unexpected problem while building the export package: {exc}")

        def done(result):
            self._export_in_progress = False
            apply_export_outcome(self.service.db, book["book_id"], row["key"], result)
            self.refresh()
            folder = str(getattr(result, "recovery", {}).get("folder", "")) if isinstance(getattr(result, "recovery", None), dict) else ""
            if result.success:
                self.status.set(f"{row['label']} export package ready at {result.artifact_path}. Nothing was uploaded.")
                open_now = messagebox.askyesno(
                    "Export package ready",
                    f"{result.message}\n\nOpen the folder now?", parent=self)
                if open_now:
                    target = folder or str(result.artifact_path)
                    if os.path.isdir(target):
                        os.startfile(target)
                    else:
                        messagebox.showinfo("Folder moved", f"The folder is no longer here:\n{target}", parent=self)
            else:
                self.status.set(f"The {row['label']} export could not be built: {result.message}")
                messagebox.showwarning("Export needs attention", result.message, parent=self)

        def runner():
            result = work()
            self.after(0, lambda: done(result))

        threading.Thread(target=runner, daemon=True).start()

    def refresh(self, sync: bool = False) -> None:
        self._catalog_search_timer = None
        if sync:
            self._background_initial_sync()
            return
        self.status.set(f"Refreshing {self.catalog_view.get().casefold()} and its current next actions…")
        self._refresh_catalog_async()

    def create_best_version(self) -> None:
        candidate = self.service.best_version()
        if not candidate:
            messagebox.showinfo("Nothing ready yet", "No saved book currently passes every Ready Now check. Use Content Capacity or Production center to see the exact next step.", parent=self)
            return
        book = candidate["book"]
        if candidate["has_package"]:
            self.tree.selection_set(book["book_id"]); self.tree.focus(book["book_id"])
            self.status.set("The strongest ready book already has a complete package. It is selected below for marketplace preparation.")
            return
        self._request_complete_package(book)

    def show_release_checklist(self) -> None:
        books = self._selected()
        if len(books) != 1:
            messagebox.showinfo("Choose one book", "Choose one catalog book first to see its final release checklist.", parent=self); return
        book = books[0]; gate = self.service.production_gate(book["book_id"]); meta = book.get("metadata") or {}
        files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
        lines = ["FINAL RELEASE CHECKLIST", "=" * 42, f"Book: {meta.get('title') or 'Untitled'}", "",
                 "[✓]" if gate["ready"] else "[ ]", "Source and package gate",]
        if gate["blockers"]: lines.extend(f"    • {item}" for item in gate["blockers"])
        lines += [f"[{'✓' if files.get('print_interior') else ' '}] Interior PDF", f"[{'✓' if files.get('print_cover') else ' '}] Print cover / full wrap", f"[{'✓' if meta.get('description') else ' '}] Buyer description", f"[{'✓' if meta.get('keywords') else ' '}] Search keywords", f"[{'✓' if (meta.get('price') or {}).get('amazon') else ' '}] Amazon price guidance", "", "Always run KDP Print Previewer before publishing."]
        self._show_report("Release checklist", "\n".join(lines))

    def compare_selected_book(self) -> None:
        books = self._selected()
        if len(books) != 1:
            messagebox.showinfo("Choose one book", "Choose one catalog book first to compare its title and topic with saved books.", parent=self); return
        book = books[0]; meta = book.get("metadata") or {}; title = str(meta.get("title") or "")
        words = {token for token in re.findall(r"[a-z0-9]+", title.casefold()) if len(token) > 2}
        matches: list[tuple[float, str]] = []
        for other in self.service.db.list_books():
            if other["book_id"] == book["book_id"]: continue
            other_title = str((other.get("metadata") or {}).get("title") or "")
            other_words = {token for token in re.findall(r"[a-z0-9]+", other_title.casefold()) if len(token) > 2}
            score = len(words & other_words) / max(len(words | other_words), 1)
            if score >= .35: matches.append((score, other_title))
        lines = ["SAVED-BOOK COMPARISON", "=" * 42, f"Current title: {title}", ""]
        if matches:
            lines += ["Potentially similar titles:"] + [f"• {name} — {score:.0%} meaningful-word overlap" for score, name in sorted(matches, reverse=True)[:8]]
        else:
            lines.append("No materially similar saved titles were found.")
        lines += ["", "This is a local originality signal, not a trademark or copyright clearance."]
        self._show_report("Saved-book comparison", "\n".join(lines))

    def refresh_recommendations(self) -> None:
        """Re-scan and visibly rebuild both live panels.

        Database work is deliberately returned to the Tk event loop.  The old
        worker-thread version occasionally handed results back while widgets
        were rebuilding, which made the button look like it had done nothing.
        """
        if getattr(self, "_recommendations_refreshing", False):
            return
        self._recommendations_refreshing = True
        self.status.set("Refreshing recommendations and checking current topic capacity…")
        def work() -> None:
            try:
                count = self.sync_catalog()
                self.after(0, lambda: self._recommendations_refreshed(count))
            except Exception as exc:
                self.after(0, lambda: self._recommendations_refresh_failed(str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _recommendations_refreshed(self, synced: int) -> None:
        self._recommendations_refreshing = False
        self.refresh(sync=False); self.refresh_content_capacity()
        count = len(self.recommendations)
        self.status.set(f"Refreshed {count} recommendation{'s' if count != 1 else ''} and checked content capacity after syncing {synced} catalog record{'s' if synced != 1 else ''}.")

    def _recommendations_refresh_failed(self, detail: str) -> None:
        self._recommendations_refreshing = False
        self.status.set("Recommendations could not refresh. Your saved books were not changed.")
        messagebox.showerror("Could not refresh recommendations", detail, parent=self)

    def open_recommended_book(self) -> None:
        selected = self.recommendation_tree.selection()
        if not selected:
            messagebox.showwarning("Choose a recommendation", "Choose a recommended book first.", parent=self); return
        item = self.recommendations.get(selected[0])
        if not item:
            return
        book = item["book"]
        if item["action"] == "Prepare package":
            self.tree.selection_set(book["book_id"]); self.tree.focus(book["book_id"])
            self.status.set("This package is already created. It is selected below; choose Prepare KDP when you are ready.")
            return
        if self.open_recommendation:
            self.destroy()
            self.open_recommendation(book)
            return
        self.status.set("Open this title from Word Search tools to create its full package.")

    def start_new_book(self) -> None:
        if not self.new_book:
            messagebox.showinfo("New book", "Open Book Studio and choose New Book to start a guided project.", parent=self)
            return
        self.destroy()
        self.new_book()

    def open_book_readiness(self) -> None:
        """One shared content/attention view; it never changes a package by opening."""
        from .operator_ui import OperatorWorkflowDialog
        OperatorWorkflowDialog(self, self.service.project, self.service.db)

    def open_etsy_bundle_builder(self) -> None:
        EtsyBundleDialog(self, self.service, self.refresh)

    def open_business_guidance(self) -> None:
        BusinessGuidanceDialog(self, self.service, self.refresh)

    def open_production_center(self) -> None:
        ProductionReadinessDialog(self, self.service, self.refresh)

    def scan_local_status(self) -> None:
        found = self.service.detect_local_marketplace_status(); self.refresh()
        self.status.set(f"Checked local production folders. Marked {found} newly prepared marketplace handoff(s) as ready; uploaded and published records were left untouched.")

    def open_upload_status(self) -> None:
        books = self._selected()
        if len(books) != 1:
            messagebox.showinfo("Choose one book", "Choose one book in the catalog first, then open Upload status to record its exact marketplace link or ID.", parent=self); return
        UploadStatusDialog(self, self.service, books[0], self.refresh)

    def _request_complete_package(self, book: dict) -> None:
        gate = self.service.production_gate(book["book_id"])
        if not gate["ready"]:
            self._show_report("Production gate", gate_text(gate))
            self.status.set("Package creation is paused until the Production Gate passes. Nothing was changed.")
            return
        if not self.create_package:
            messagebox.showinfo("Create package", "Open this saved theme in Word Search tools, then select Review & Create Package.", parent=self)
            return
        self.destroy()
        self.create_package(book)

    def create_recommended_package(self) -> None:
        selected = self.recommendation_tree.selection()
        if not selected:
            messagebox.showwarning("Choose a recommendation", "Choose a recommended book first.", parent=self); return
        item = self.recommendations.get(selected[0])
        if item:
            self._request_complete_package(item["book"])

    def create_selected_package(self) -> None:
        books = self._selected()
        if not books:
            messagebox.showwarning("Choose a book", "Choose one saved book first.", parent=self); return
        if len(books) > 1:
            messagebox.showwarning("Choose one book", "Create one complete package at a time so the final proof and package folder stay clear.", parent=self); return
        self._request_complete_package(books[0])

    def _selected(self) -> list[dict]: return [self.rows[item] for item in self.tree.selection() if item in self.rows]

    def open_listing_review(self) -> None:
        books = self._selected()
        if len(books) != 1:
            messagebox.showwarning("Choose one book", "Select one book to see its cover, listing copy, and proof checks.", parent=self); return
        ListingReviewDialog(self, self.service, books[0], self.refresh)

    def open_batch_review(self) -> None:
        books = self._selected()
        if not books:
            messagebox.showwarning("Choose books", "Select one or more books in the Catalog first.", parent=self); return
        BatchReviewDialog(self, self.service, books, self.refresh)

    def approve_selected(self) -> None:
        books = self._selected()
        if not books:
            messagebox.showwarning("Choose a book", "Choose one or more books to add to the approved production queue.", parent=self); return
        blocked = [book for book in books if not self.service.production_gate(book["book_id"])["ready"]]
        if blocked:
            titles = "\n• ".join(str(book["metadata"].get("title") or "Untitled") for book in blocked)
            messagebox.showwarning("Approval paused", "These books need attention before they can enter the production queue:\n\n• " + titles + "\n\nUse Preview & proof for the exact fixes.", parent=self)
            return
        for book in books:
            self.service.db.approve_for_production(book["book_id"])
        self.status.set(f"Added {len(books)} book{'s' if len(books) != 1 else ''} to the approved production queue.")

    def lock_selected_release(self) -> None:
        books = self._selected()
        if len(books) != 1:
            messagebox.showwarning("Choose one book", "Choose one completed book to lock its approved release record.", parent=self); return
        try:
            result = self.service.db.lock_release(books[0]["book_id"])
        except ValueError as exc:
            messagebox.showwarning("Release cannot be locked yet", str(exc), parent=self); return
        wording = "already matches the saved lock" if result["unchanged"] else "was saved as a new immutable record"
        self.status.set(f"Release revision {result['revision']} {wording}.")

    def open_approved_queue(self) -> None:
        ApprovedProductionQueueDialog(self, self.service, self.refresh)

    def check_selected_series(self) -> None:
        books = self._selected()
        from .review import series_consistency_report
        self._show_report("Series consistency check", "\n".join(series_consistency_report(books)))

    def open_series_map(self) -> None:
        SeriesMapDialog(self, self.service)

    def open_launch_dashboard(self) -> None:
        books = self.service.db.list_books()[:20]
        lines = ["LAUNCH DASHBOARD", "", "Approved → Package ready → Uploaded → Live", ""]
        for book in books:
            statuses = book.get("statuses") or {}
            state = "Live" if "Published" in statuses.values() else "Uploaded" if "Uploaded" in statuses.values() else "Package ready" if str(book.get("package_path") or "") else "Approved" if any(row["book_id"] == book["book_id"] for row in self.service.db.approved_production_queue()) else "Draft"
            lines.append(f"• {state}: {book['metadata'].get('title', 'Untitled')}")
        self._show_report("Launch dashboard", "\n".join(lines))

    def open_recovery_center(self) -> None:
        RecoveryCenterDialog(self, self.service, self.refresh)

    def _show_report(self, title: str, text: str) -> None:
        dialog = tk.Toplevel(self); dialog.title(title); dialog.geometry("820x560"); dialog.configure(background="#101418"); dialog.transient(self)
        box = tk.Text(dialog, wrap="word", background="#171d23", foreground="#f4f7f8", relief="flat", padx=16, pady=14); box.pack(fill="both", expand=True, padx=18, pady=18); box.insert("1.0", text); box.configure(state="disabled")

    def open_selected_master(self) -> None:
        books = self._selected()
        if not books:
            messagebox.showwarning("Choose a book", "Choose one completed book first.", parent=self); return
        if len(books) > 1:
            messagebox.showwarning("Choose one book", "Open one marketplace handoff folder at a time.", parent=self); return
        package = str(books[0].get("package_path") or "")
        master = os.path.join(package, "05_MARKETPLACE_HANDOFFS") if package else ""
        if master and os.path.isdir(master):
            os.startfile(master)
            self.status.set("Opened the marketplace handoffs folder. It contains only marketplaces you chose to prepare.")
        elif package and os.path.isdir(package):
            self.status.set("No marketplace handoffs have been prepared for this book yet. Choose Prepare selected first.")
        else:
            self.status.set("This is a saved theme, not a completed package yet. Choose Create complete package first.")

    def prepare(self, marketplaces: list[str]) -> None:
        books = self._selected()
        if not books: messagebox.showwarning("Choose a book", "Select one or more books first.", parent=self); return
        if self._prepare_in_progress:
            messagebox.showinfo("Preparation running", "The current marketplace preparation is still working. It will update the catalog when it finishes.", parent=self); return
        book_ids = [book["book_id"] for book in books]
        self._prepare_in_progress = True
        self.status.set(f"Preparing {len(book_ids)} book(s) for {len(marketplaces)} marketplace(s) in the background…")

        def work() -> None:
            try:
                report = self.service.prepare_many(book_ids, marketplaces)
                self.after(0, lambda: self._finish_prepare(report))
            except Exception as exc:  # Defensive: individual failures are normally captured by prepare_many.
                self.after(0, lambda: self._finish_prepare([], str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _finish_prepare(self, report: list[tuple[str, str, str]], unexpected_error: str = "") -> None:
        """Refresh the UI after a background marketplace handoff run."""
        self._prepare_in_progress = False
        self.refresh()
        if unexpected_error:
            self.status.set(f"Marketplace preparation stopped: {unexpected_error}. Existing files were left untouched.")
            return
        # Imported here so this truthful-reporting change stays confined to
        # this method; readiness.py holds the shared classification logic.
        from .readiness import classify_prepare_report
        buckets = classify_prepare_report(report)
        parts: list[str] = []
        made = buckets["prepared"]
        if made:
            parts.append(f"Prepared {len(made)} marketplace package(s) ready to review and upload.")
        if buckets["final_cover_needed"]:
            parts.append(f"Prepared {len(buckets['final_cover_needed'])} printer package(s); each still needs its final platform cover before upload.")
        confirmed: dict[tuple[str, str], None] = {}
        for _book_id, marketplace, prior in buckets["already_confirmed"]:
            confirmed.setdefault((marketplace, prior))
        for marketplace, prior in confirmed:
            parts.append(f"{PUBLISHERS[marketplace].label} is already recorded as {prior}. Nothing was changed and your saved listing details remain intact.")
        if buckets["needs_review"]:
            parts.append(f"{len(buckets['needs_review'])} marketplace package(s) still need required items. Select the book and choose “Why not KDP ready?” for the exact fix. Your files were not changed.")
        if buckets["errors"]:
            first_book, first_market, message = buckets["errors"][0]
            parts.append(f"Preparation failed for {PUBLISHERS[first_market].label}: {message} Nothing was deleted.")
        if buckets["other"]:
            parts.append(f"{len(buckets['other'])} result(s) need a closer look. Open Upload status for the exact confirmed records.")
        self.status.set(" ".join(parts) if parts else "Nothing needed preparing.")

    def show_kdp_readiness(self) -> None:
        books = self._selected()
        if not books:
            messagebox.showwarning("Choose a book", "Select one book first, then I will explain its KDP readiness.", parent=self); return
        book = books[0]
        issues = PUBLISHERS["amazon"].validate(book)
        title = book["metadata"].get("title", "This book")
        if not issues:
            messagebox.showinfo("Ready to prepare for KDP", f"{title} has both required print files and its basic contributor details. Click Prepare KDP to make an upload folder, then run KDP Print Previewer before publishing.", parent=self)
            return
        friendly = []
        for issue in issues:
            if "interior PDF" in issue or "cover PDF" in issue:
                friendly.append("Create the complete package from Word Search tools. This makes both the interior PDF and the full KDP cover wrap.")
            elif "author" in issue:
                friendly.append("Open Book Details and enter your contributor name (Jordan M. Slade), not the Slade Puzzles brand.")
            else:
                friendly.append(issue)
        unique = list(dict.fromkeys(friendly))
        messagebox.showinfo("What this book needs", f"{title} is not ready for KDP yet.\n\nWhat to do next:\n• " + "\n• ".join(unique) + "\n\nYour saved theme and current files are safe—do not delete them.", parent=self)

    def open_book(self) -> None:
        selected = self._selected()
        if not selected: messagebox.showwarning("Choose a book", "Select a book first.", parent=self); return
        BookPublishingDialog(self, self.service, selected[0], self.refresh)


class UploadStatusDialog(tk.Toplevel):
    """One truthful record per marketplace: local prep, upload, then live link."""
    def __init__(self, parent, service, book: dict, on_saved, initial_marketplace: str = "") -> None:
        super().__init__(parent); self.service, self.book, self.on_saved = service, book, on_saved
        self.initial_marketplace = initial_marketplace
        self.title("Upload status"); fit_dialog_to_screen(self, 850, 590, 700, 500); self.configure(background="#1f1f1f"); self.transient(parent)
        self.marketplace = tk.StringVar(value="amazon"); self.status_value = tk.StringVar(); self.external_id = tk.StringVar(); self.url = tk.StringVar(); self.updated = tk.StringVar()
        self._build(); self._apply_initial_marketplace(); self._load_record()

    def _apply_initial_marketplace(self) -> None:
        """Pre-select one marketplace when opened from a Hub readiness row."""
        if self.initial_marketplace in MARKETPLACES:
            self.market_combo.set(f"{DISPLAY[self.initial_marketplace]}|{self.initial_marketplace}")

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1)
        title = self.book["metadata"].get("title", "Book")
        ttk.Label(root, text="Upload status", style="Publish.Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(root, text=title, style="Publish.Subtitle.TLabel", wraplength=760).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 12))
        note = ("This screen records only what you confirm. “Ready” means the local upload folder exists. "
                "After you upload, paste the ASIN, listing ID, or live link here. The app will never guess that a book is live.")
        ttk.Label(root, text=note, style="Publish.Status.TLabel", wraplength=760).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 16))
        ttk.Label(root, text="Marketplace", style="Publish.TLabel").grid(row=3, column=0, sticky="w", pady=7)
        choices = [f"{DISPLAY[key]}|{key}" for key in MARKETPLACES]
        self.market_combo = ttk.Combobox(root, values=choices, state="readonly", style="Publish.TCombobox", width=28)
        self.market_combo.grid(row=3, column=1, sticky="w", pady=7); self.market_combo.set(f"{DISPLAY['amazon']}|amazon")
        self.market_combo.bind("<<ComboboxSelected>>", lambda _event: self._load_record())
        ttk.Label(root, text="Progress", style="Publish.TLabel").grid(row=4, column=0, sticky="w", pady=7)
        ttk.Combobox(root, textvariable=self.status_value, values=STATUS_VALUES, state="readonly", style="Publish.TCombobox", width=28).grid(row=4, column=1, sticky="w", pady=7)
        ttk.Label(root, text="ASIN, listing ID, or product ID", style="Publish.TLabel").grid(row=5, column=0, sticky="w", pady=7)
        ttk.Entry(root, textvariable=self.external_id, style="Publish.TEntry").grid(row=5, column=1, columnspan=2, sticky="ew", pady=7)
        ttk.Label(root, text="Live listing link", style="Publish.TLabel").grid(row=6, column=0, sticky="w", pady=7)
        ttk.Entry(root, textvariable=self.url, style="Publish.TEntry").grid(row=6, column=1, columnspan=2, sticky="ew", pady=7)
        ttk.Label(root, textvariable=self.updated, style="Publish.Subtitle.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 14))
        self.summary = tk.Text(root, height=8, wrap="word", state="disabled", background="#292929", foreground="#d9f5ee", relief="flat", padx=10, pady=10)
        self.summary.grid(row=8, column=0, columnspan=3, sticky="nsew"); root.rowconfigure(8, weight=1)
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(actions, text="Save confirmed status", command=self.save, style="Publish.Primary.TButton").pack(side="right")
        ttk.Button(actions, text="Open saved link", command=self.open_link, style="Publish.Action.TButton").pack(side="right", padx=6)

    def _marketplace_key(self) -> str:
        return self.market_combo.get().rsplit("|", 1)[-1]

    def _load_record(self) -> None:
        key = self._marketplace_key(); record = self.service.db.marketplace_records(self.book["book_id"])[key]
        self.status_value.set(record["status"]); self.external_id.set(record["external_id"]); self.url.set(record["url"])
        stamp = record["updated_at"].replace("T", " ") if record["updated_at"] else "No confirmed record saved yet."
        self.updated.set(f"Last saved: {stamp}")
        package = str(self.book.get("package_path") or "")
        folder = {"amazon": "kdp", "barnes_noble": "barnes_noble"}.get(key, key)
        local = os.path.join(package, folder) if package else ""
        local_text = "Local upload folder found." if local and os.path.isdir(local) else "No local upload folder found yet."
        self.summary.configure(state="normal"); self.summary.delete("1.0", "end")
        self.summary.insert("end", f"{DISPLAY[key]}: {record['status']}\n\n{local_text}\n\nUse “Uploaded” only after the files are accepted by the marketplace. Use “Published” after the public listing is visible. Paste the exact listing link so it can be opened later from here.")
        self.summary.configure(state="disabled")

    def save(self) -> None:
        key, status = self._marketplace_key(), self.status_value.get()
        if not status:
            messagebox.showwarning("Choose progress", "Choose the current marketplace progress before saving.", parent=self); return
        link = self.url.get().strip()
        if link and not link.startswith(("https://", "http://")):
            messagebox.showwarning("Check link", "Paste a full link beginning with https:// or http://.", parent=self); return
        self.service.db.update_marketplace_record(self.book["book_id"], key, status, self.external_id.get(), link)
        self.book = self.service.db.get_book(self.book["book_id"]); self._load_record(); self.on_saved()
        messagebox.showinfo("Status saved", f"Saved the confirmed {DISPLAY[key]} status for this book.", parent=self)

    def open_link(self) -> None:
        link = self.url.get().strip()
        if not link:
            messagebox.showinfo("No link yet", "Paste and save the public listing link first.", parent=self); return
        webbrowser.open(link)


class EtsyBundleDialog(tk.Toplevel):
    """Build a compliant Etsy digital bundle from finished customer PDFs."""
    def __init__(self, parent, service, on_created) -> None:
        super().__init__(parent); self.service, self.on_created = service, on_created
        self.title("Create Etsy Bundle"); fit_dialog_to_screen(self, 920, 650, 760, 500); self.configure(background="#1f1f1f"); self.transient(parent)
        self.title_value = tk.StringVar(value=f"{ETSY_STORE_NAME} Printable Puzzle Book Bundle")
        self.price = tk.StringVar(value="12.99"); self.price_note = tk.StringVar(value="Choose two or more books to calculate a bundle recommendation."); self.status = tk.StringVar(value="Choose two or more completed books. Only buyer-ready digital PDFs are shown.")
        self.books = {book["book_id"]: book for book in service.etsy_bundle_candidates()}; self._build()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1); root.rowconfigure(3, weight=1)
        ttk.Label(root, text="Create Etsy bundle", style="Publish.Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(root, text="This creates buyer-ready ZIP download file(s), a bundle cover, and an Etsy listing kit. It does not touch your original book packages.", style="Publish.Subtitle.TLabel", wraplength=820).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 14))
        ttk.Label(root, text="Bundle title", style="Publish.TLabel").grid(row=2, column=0, sticky="w", pady=5); ttk.Entry(root, textvariable=self.title_value, style="Publish.TEntry").grid(row=2, column=1, sticky="ew", pady=5)
        columns = ("book", "puzzles", "theme", "pages")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", selectmode="extended", height=12, style="Publish.Treeview")
        for key, label, width in (("book", "Completed book", 390), ("puzzles", "Puzzles", 75), ("theme", "Theme", 200), ("pages", "Pages", 75)):
            self.tree.heading(key, text=label); self.tree.column(key, width=width, anchor="w" if key in ("book", "theme") else "center")
        self.tree.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(10, 12))
        for book_id, book in self.books.items():
            meta = book["metadata"]; self.tree.insert("", "end", iid=book_id, values=(meta.get("title", ""), meta.get("puzzle_count", ""), meta.get("theme", ""), meta.get("page_count", "")))
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.refresh_price())
        ttk.Label(root, text="Suggested Etsy price", style="Publish.TLabel").grid(row=4, column=0, sticky="w", pady=5); ttk.Entry(root, textvariable=self.price, width=12, style="Publish.TEntry").grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(root, textvariable=self.price_note, style="Publish.Subtitle.TLabel", wraplength=600).grid(row=5, column=0, columnspan=2, sticky="w")
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Create buyer-ready Etsy bundle", command=self.create, style="Publish.Primary.TButton").pack(side="right")
        ttk.Label(root, textvariable=self.status, style="Publish.Status.TLabel", wraplength=820).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def refresh_price(self) -> None:
        selected = [self.books[item] for item in self.tree.selection() if item in self.books]
        if len(selected) < 2:
            self.price_note.set("Choose two or more books to calculate a bundle recommendation.")
            return
        from .listing_copy import recommended_bundle_prices
        plan = recommended_bundle_prices(selected)
        self.price.set(f"{plan['etsy']:.2f}")
        self.price_note.set(f"Automatic recommendation: ${plan['etsy']:.2f} digital bundle price ({plan['savings_percent']}% savings versus buying the included digital books separately).")

    def create(self) -> None:
        selected = list(self.tree.selection())
        if len(selected) < 2:
            messagebox.showwarning("Choose books", "Choose at least two completed books for this Etsy bundle.", parent=self); return
        title = self.title_value.get().strip()
        if not title:
            messagebox.showwarning("Add a title", "Give the Etsy bundle a buyer-facing title.", parent=self); return
        try:
            price = float(self.price.get())
            if price <= 0: raise ValueError
        except ValueError:
            messagebox.showwarning("Check price", "Enter a positive price, for example 12.99.", parent=self); return
        try:
            folder, details = self.service.create_etsy_bundle(title, selected, price)
        except Exception as exc:
            messagebox.showerror("Bundle needs attention", str(exc), parent=self); return
        self.on_created()
        self.status.set(f"Bundle created with {len(details['books'])} books. Open the folder and upload the ZIP file(s) listed in ETSY_LISTING_KIT.txt.")
        os.startfile(folder)


class BookPublishingDialog(tk.Toplevel):
    def __init__(self, parent, service, book: dict, on_saved) -> None:
        super().__init__(parent); self.service, self.book, self.on_saved = service, book, on_saved
        self.title(f"Book Control Center: {book['metadata'].get('title', 'Book')}"); fit_dialog_to_screen(self, 980, 710, 780, 520); self.configure(background="#1f1f1f")
        self.vars = {key: tk.StringVar(value=str(book["metadata"].get(key) or "")) for key in ("title", "subtitle", "author", "series", "isbn")}; self.locked = tk.BooleanVar(value=bool(book.get("metadata_locked"))); self._build()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1); root.rowconfigure(7, weight=1)
        ttk.Label(root, text="Book Control Center", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="One place for this book’s details, quality review, marketplace files, and marketing materials. Nothing here publishes a book automatically.", style="Publish.Subtitle.TLabel", wraplength=900).grid(row=0, column=1, columnspan=2, sticky="e", pady=(3, 0))
        for row, key in enumerate(("title", "subtitle", "author", "series", "isbn"), 1):
            ttk.Label(root, text=key.replace("_", " ").title(), style="Publish.TLabel").grid(row=row, column=0, sticky="w", pady=4); ttk.Entry(root, textvariable=self.vars[key], style="Publish.TEntry").grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Label(root, text="Description", style="Publish.TLabel").grid(row=6, column=0, sticky="nw", pady=4); self.description = tk.Text(root, height=8, wrap="word", background="#303030", foreground="#f2f2f2", insertbackground="#f2f2f2", relief="flat", padx=8, pady=8); self.description.grid(row=6, column=1, columnspan=2, sticky="nsew", pady=4); self.description.insert("1.0", self.book["metadata"].get("description", ""))
        self.status_box = tk.Text(root, height=10, wrap="word", state="disabled", background="#292929", foreground="#d9f5ee", relief="flat", padx=10, pady=10); self.status_box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(12, 0)); self._show_statuses()
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Checkbutton(actions, text="Lock saved book details", variable=self.locked).pack(side="left")
        ttk.Button(actions, text="Save changes", command=self.save, style="Publish.Primary.TButton").pack(side="right")
        ttk.Button(actions, text="Upload status…", command=self.open_upload_status, style="Publish.Action.TButton").pack(side="right", padx=6)
        ttk.Button(actions, text="Open marketplace files", command=self.open_master_package, style="Publish.Action.TButton").pack(side="right", padx=6)
        ttk.Button(actions, text="Marketing materials", command=self.open_marketing, style="Publish.Action.TButton").pack(side="right", padx=6)
        ttk.Button(actions, text="Preview & listing review", command=self.open_review, style="Publish.Action.TButton").pack(side="right", padx=6)
        ttk.Button(actions, text="Open book folder", command=self.open_package, style="Publish.Action.TButton").pack(side="right")

    def _show_statuses(self) -> None:
        self.status_box.configure(state="normal"); self.status_box.delete("1.0", "end")
        meta = self.book["metadata"]; self.status_box.insert("end", f"Pages: {meta.get('page_count', 0)} | Trim: {meta.get('trim_size', '8.5x11')} | Theme: {meta.get('theme', '')}\nContent check: {meta.get('production_status', 'Needs content check')}\n\n")
        try:
            autopilot = self.service.autopilot_status(self.book["book_id"])
            quality = autopilot["score"]
            checkpoint = autopilot["checkpoint"]
            current = next((name for name, item in (checkpoint.get("stages") or {}).items() if item.get("status") in {"failed", "needs_human_review"}), "")
            self.status_box.insert("end", f"Local quality score: {quality['score']}/100 — {quality['label']}\n")
            if current:
                self.status_box.insert("end", f"Needs attention: {current.replace('_', ' ').title()} — {(checkpoint.get('stages') or {}).get(current, {}).get('detail', '')}\n")
            elif quality["costs"]:
                self.status_box.insert("end", f"Next local review: {quality['costs'][0]}\n")
            else:
                self.status_box.insert("end", "Autopilot checkpoints: no active local issue recorded.\n")
            self.status_box.insert("end", "\n")
        except Exception:
            # A Book Control Center must still open for older catalog records.
            pass
        for key in MARKETPLACES: self.status_box.insert("end", f"{DISPLAY[key]}: {self.book['statuses'].get(key, 'Not Prepared')}\n")
        self.status_box.configure(state="disabled")

    def save(self) -> None:
        meta = dict(self.book["metadata"])
        for key, var in self.vars.items(): meta[key] = var.get().strip()
        meta["description"] = self.description.get("1.0", "end-1c").strip(); self.service.db.save_metadata(self.book["book_id"], meta, self.locked.get())
        if meta["isbn"]: self.service.db.assign_isbn(meta["isbn"], self.book["book_id"], meta["title"], "User-owned ISBN")
        self.book = self.service.db.get_book(self.book["book_id"]); self._show_statuses(); self.on_saved(); messagebox.showinfo("Saved", "Your master metadata record is saved.", parent=self)

    def open_upload_status(self) -> None:
        UploadStatusDialog(self, self.service, self.book, self._after_upload_status)

    def _after_upload_status(self) -> None:
        self.book = self.service.db.get_book(self.book["book_id"]); self._show_statuses(); self.on_saved()

    def open_package(self) -> None:
        path = self.book.get("package_path")
        if path and os.path.isdir(path): os.startfile(path)
        else: messagebox.showinfo("No package", "Create a complete book package first, then sync this catalog.", parent=self)

    def open_master_package(self) -> None:
        path = self.book.get("package_path")
        master = os.path.join(path, "05_MARKETPLACE_HANDOFFS") if path else ""
        if master and os.path.isdir(master):
            os.startfile(master)
        elif path and os.path.isdir(path):
            messagebox.showinfo("No handoffs yet", "Choose Prepare in Publishing Center to create only the marketplace folders you need.", parent=self)
        else:
            messagebox.showinfo("No package", "Create a complete book package first, then prepare the marketplace you want to use.", parent=self)

    def open_review(self) -> None:
        """Use the existing visual review screen as this book hub’s preview tab."""
        ListingReviewDialog(self, self.service, self.book, self._after_review)

    def _after_review(self) -> None:
        self.book = self.service.db.get_book(self.book["book_id"]) or self.book
        self._show_statuses(); self.on_saved()

    def open_marketing(self) -> None:
        package = Path(str(self.book.get("package_path") or ""))
        candidates = (package / "06_MARKETING", package / "MARKETING", package)
        target = next((folder for folder in candidates if folder.is_dir()), None)
        if target:
            os.startfile(target)
        else:
            messagebox.showinfo("No marketing materials yet", "Create the complete package first. Its marketing materials will appear in the book folder.", parent=self)


class ListingReviewDialog(tk.Toplevel):
    """One visual, copy-ready approval stop before marketplace preparation."""
    def __init__(self, parent, service, book: dict, on_changed) -> None:
        super().__init__(parent); self.service, self.book, self.on_changed = service, book, on_changed
        self.title("Publish Pack & Proof"); fit_dialog_to_screen(self, 1080, 760, 820, 520); self.configure(background="#1f1f1f"); self.transient(parent)
        self.market = tk.StringVar(value="amazon"); self.cover_image = self.wrap_image = None
        root = ttk.Frame(self, padding=20, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1); root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Publish Pack & Proof", style="Publish.Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(root, text="One place to review the cover, files, listing copy, price direction, and marketplace readiness. This screen never publishes a book.", style="Publish.Subtitle.TLabel", wraplength=980).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        left = ttk.Frame(root, style="Publish.TFrame"); left.grid(row=2, column=0, sticky="nsw", padx=(0, 18))
        self.cover_label = ttk.Label(left, text="No cover image", style="Publish.Subtitle.TLabel"); self.cover_label.pack(anchor="n")
        self.wrap_label = ttk.Label(left, text="Full-wrap preview unavailable", style="Publish.Subtitle.TLabel", wraplength=280, justify="center"); self.wrap_label.pack(anchor="n", pady=(10, 0))
        meta = self.book.get("metadata") or {}
        ttk.Label(left, text=f"{meta.get('puzzle_count') or '—'} puzzles • {meta.get('difficulty_label') or 'Standard'}\n{meta.get('trim_size') or '8.5x11'} • ${((meta.get('price') or {}).get('amazon') or 0):.2f} suggested Amazon price", style="Publish.Subtitle.TLabel", justify="center", wraplength=280).pack(anchor="n", pady=(8, 0))
        ttk.Label(left, text="Marketplace", style="Publish.TLabel").pack(anchor="w", pady=(14, 3))
        chooser = ttk.Combobox(left, textvariable=self.market, values=tuple(f"{DISPLAY[key]}|{key}" for key in MARKETPLACES), state="readonly", width=24, style="Publish.TCombobox"); chooser.pack(anchor="w"); chooser.set(f"{DISPLAY['amazon']}|amazon"); chooser.bind("<<ComboboxSelected>>", lambda _event: self.refresh_review())
        right = ttk.Frame(root, style="Publish.TFrame"); right.grid(row=2, column=1, sticky="nsew"); right.rowconfigure(0, weight=1); right.columnconfigure(0, weight=1)
        self.text = tk.Text(right, wrap="word", background="#292929", foreground="#d9f5ee", insertbackground="#f2f2f2", relief="flat", padx=14, pady=12); self.text.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(actions, text="Copy listing", command=self.copy_listing, style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions, text="Copy title", command=lambda: self.copy_field("title"), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Copy description", command=lambda: self.copy_field("description"), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Copy keywords", command=lambda: self.copy_field("keywords"), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Copy price", command=lambda: self.copy_field("price"), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Run final inspection", command=self.run_final_inspection, style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Cover concepts", command=lambda: CoverConceptBoard(self, self.service, self.book), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Run launch handoffs", command=self.launch_handoffs, style="Publish.Primary.TButton").pack(side="left", padx=7)
        ttk.Button(actions, text="Lock approved release", command=self.lock_release, style="Publish.Action.TButton").pack(side="left", padx=7)
        self.prepare_button = ttk.Button(actions, text="Prepare this marketplace", command=self.prepare, style="Publish.Primary.TButton")
        self.prepare_button.pack(side="left", padx=7)
        ttk.Button(actions, text="Open book folder", command=self.open_folder, style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy, style="Publish.Action.TButton").pack(side="right")
        self._load_cover(); self._load_wrap(); self.refresh_review()

    def key(self) -> str: return self.market.get().rsplit("|", 1)[-1]

    def _load_cover(self) -> None:
        path = str((self.book.get("metadata") or {}).get("files", {}).get("front_cover") or "")
        if not path or not os.path.isfile(path): return
        try:
            image = Image.open(path).convert("RGB"); image.thumbnail((280, 365), Image.Resampling.LANCZOS)
            self.cover_image = ImageTk.PhotoImage(image); self.cover_label.configure(image=self.cover_image, text="")
        except Exception:
            self.cover_label.configure(text="Cover preview unavailable")

    def _load_wrap(self) -> None:
        package = Path(str(self.book.get("package_path") or ""))
        path = package / "kdp_full_wrap_preview.png"
        if not path.is_file():
            return
        try:
            image = Image.open(path).convert("RGB"); image.thumbnail((280, 130), Image.Resampling.LANCZOS)
            self.wrap_image = ImageTk.PhotoImage(image); self.wrap_label.configure(image=self.wrap_image, text="Full KDP wrap preview")
        except Exception:
            self.wrap_label.configure(text="Full-wrap preview unavailable")

    def refresh_review(self) -> None:
        from .review import review_text
        from .metadata_service import marketplace_copy_quality
        audit = marketplace_copy_quality(self.book.get("metadata") or {}, self.key())
        quality = ["BUYER COPY QUALITY", "-" * 24, f"{audit['score']}/100 — {audit['label']}"]
        quality.extend(f"• {note}" for note in audit["notes"])
        self.text.configure(state="normal"); self.text.delete("1.0", "end"); self.text.insert("1.0", review_text(self.book, self.key()) + "\n\n" + "\n".join(quality)); self.text.configure(state="disabled")

    def copy_listing(self) -> None:
        try:
            self.clipboard_clear(); self.clipboard_append(self.service.listing_copy(self.book["book_id"], self.key())); self.update()
            messagebox.showinfo("Copied", "The complete platform listing information is ready to paste.", parent=self)
        except Exception as exc: messagebox.showerror("Could not copy", str(exc), parent=self)

    def copy_field(self, field: str) -> None:
        """Copy a focused marketplace field without making the user hunt in a long kit."""
        meta = self.book.get("metadata") or {}
        if field == "title": value = str(meta.get("title") or "")
        elif field == "price":
            from .listing_copy import recommended_prices
            value = f"${float(recommended_prices(meta).get(self.key(), 0) or 0):.2f}"
        else:
            text = self.service.listing_copy(self.book["book_id"], self.key())
            if field == "description":
                match = re.search(r"DESCRIPTION[^\n]*\n(.*?)(?:\n\s*KEYWORD|\n\s*CATEGOR|\Z)", text, re.S | re.I); value = match.group(1).strip() if match else text
            else:
                match = re.search(r"KEYWORD[^\n]*\n(.*?)(?:\n\s*CATEGOR|\Z)", text, re.S | re.I); value = match.group(1).strip() if match else ""
        if not value:
            messagebox.showinfo("Nothing to copy", "This package does not yet contain that listing field.", parent=self); return
        self.clipboard_clear(); self.clipboard_append(value); self.update(); messagebox.showinfo("Copied", f"{field.title()} is ready to paste.", parent=self)

    def lock_release(self) -> None:
        try:
            result = self.service.db.lock_release(self.book["book_id"])
        except ValueError as exc:
            messagebox.showwarning("Release cannot be locked yet", str(exc), parent=self); return
        messagebox.showinfo("Release locked", f"Revision {result['revision']} {'already matched this release' if result['unchanged'] else 'was saved as an immutable release record'}.", parent=self)

    def run_final_inspection(self) -> None:
        try:
            report = self.service.final_inspection(self.book["book_id"])
        except ValueError as exc:
            messagebox.showwarning("Final inspection", str(exc), parent=self)
            return
        lines = ["FINAL PRODUCTION INTELLIGENCE", "", f"Result: {'READY' if report['ready'] else 'NEEDS ATTENTION'}"]
        lines += [f"• {item}" for item in report.get("blockers", [])] or ["• Local package, cover, PDF, and word-reservation checks passed."]
        lines += ["", f"Title score: {report['title_assessment']['score']}/100 — {report['title_assessment']['label']}"]
        lines += [f"• {item}" for item in report['title_assessment']['notes']]
        lines += ["", report['remaining_capacity']['message'], report['series_direction']['message'], f"Marketplace images refreshed: {len(report['marketplace_assets'])}"]
        self.text.configure(state="normal"); self.text.insert("end", "\n\n" + "\n".join(lines)); self.text.configure(state="disabled")

    def launch_handoffs(self) -> None:
        try:
            result = self.service.launch_handoffs(self.book["book_id"])
        except ValueError as exc:
            messagebox.showwarning("Launch cannot start yet", str(exc), parent=self); return
        ready = sum(1 for _book, _market, state in result["report"] if state == "Ready")
        self.book = self.service.db.get_book(self.book["book_id"]) or self.book
        self.on_changed(); self.refresh_review()
        messagebox.showinfo("Launch handoffs ready", f"Release revision {result['lock']['revision']} is locked. Prepared {ready} local KDP, Etsy, and website handoff folder(s). Uploading remains your decision.", parent=self)

    def prepare(self) -> None:
        self.prepare_button.configure(state="disabled")
        self.text.configure(state="normal"); self.text.insert("end", "\n\nPreparing this marketplace handoff in the background…"); self.text.configure(state="disabled")
        key, book_id = self.key(), self.book["book_id"]
        def work() -> None:
            try:
                target, issues = self.service.prepare(book_id, key)
                self.after(0, lambda: self._prepared(target, issues))
            except Exception as exc:
                self.after(0, lambda: self._prepare_failed(str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _prepared(self, target, issues: list[str]) -> None:
        self.prepare_button.configure(state="normal")
        self.book = self.service.db.get_book(self.book["book_id"]); self.on_changed(); self.refresh_review()
        if issues: messagebox.showwarning("Needs attention", "\n".join(issues), parent=self)
        else: messagebox.showinfo("Prepared", f"Prepared files are ready in:\n{target}", parent=self)

    def _prepare_failed(self, detail: str) -> None:
        self.prepare_button.configure(state="normal")
        messagebox.showerror("Preparation problem", f"The marketplace handoff could not be prepared. Existing files were left untouched.\n\n{detail}", parent=self)

    def open_folder(self) -> None:
        path = str(self.book.get("package_path") or "")
        if path and os.path.isdir(path): os.startfile(path)
        else: messagebox.showinfo("No package folder", "Create the complete package first.", parent=self)


class RecoveryCenterDialog(tk.Toplevel):
    """Detect partial packages and expose only deliberate, reversible actions."""
    def __init__(self, parent, service, on_changed) -> None:
        super().__init__(parent); self.service,self.on_changed=service,on_changed; self.title("Recovery center"); fit_dialog_to_screen(self, 980, 600, 700, 440); self.configure(background="#101418"); self.transient(parent)
        root=ttk.Frame(self,padding=20,style="Publish.TFrame"); root.pack(fill="both",expand=True); root.columnconfigure(0,weight=1); root.rowconfigure(2,weight=1)
        ttk.Label(root,text="Recovery center",style="Publish.Title.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(root,text="Incomplete attempts are detected automatically. Opening, retrying, and marking a catalog record are safe; archiving moves only the selected partial folder into an on-disk recovery archive after confirmation.",style="Publish.Subtitle.TLabel",wraplength=900).grid(row=1,column=0,sticky="w",pady=(4,12))
        self.tree=ttk.Treeview(root,columns=("folder","missing","suggested"),show="headings",style="Publish.Treeview")
        for key,label,width in (("folder","Partial folder",360),("missing","Missing pieces",300),("suggested","Safe next step",260)): self.tree.heading(key,text=label); self.tree.column(key,width=width,anchor="w")
        self.tree.grid(row=2,column=0,sticky="nsew"); actions=ttk.Frame(root,style="Publish.TFrame"); actions.grid(row=3,column=0,sticky="ew",pady=(12,0))
        ttk.Button(actions,text="Open selected folder",command=self.open_selected,style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions,text="Retry from source",command=self.retry_selected,style="Publish.Primary.TButton").pack(side="left",padx=7)
        ttk.Button(actions,text="Mark abandoned",command=self.abandon_selected,style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions,text="Archive selected partial",command=self.archive_selected,style="Publish.Action.TButton").pack(side="left",padx=7)
        ttk.Button(actions,text="Refresh",command=self.refresh,style="Publish.Action.TButton").pack(side="right",padx=7); ttk.Button(actions,text="Close",command=self.destroy,style="Publish.Action.TButton").pack(side="right")
        self.rows={}; self.refresh()
    def refresh(self):
        self.rows.clear(); self.tree.delete(*self.tree.get_children()); output=Path(self.service.output)
        for folder in sorted(output.iterdir()) if output.is_dir() else []:
            if not folder.is_dir() or folder.name == "_recovery_archive": continue
            missing=missing_core_package_files(folder)
            if missing:
                iid=str(folder); self.rows[iid]=folder; self.tree.insert("","end",iid=iid,values=(folder.name,", ".join(missing),"Open and retry from its source, or archive it"))
    def selected_folder(self):
        selected=self.tree.selection()
        if not selected: messagebox.showwarning("Choose a partial package", "Choose one detected incomplete folder first.", parent=self); return None
        return self.rows.get(selected[0])
    def open_selected(self):
        folder=self.selected_folder()
        if folder: os.startfile(folder)
    def _matched_book(self, folder):
        return next((book for book in self.service.db.list_books() if str(book.get("package_path") or "") == str(folder)),None)
    def retry_selected(self):
        folder=self.selected_folder()
        if not folder: return
        book=self._matched_book(folder)
        if book and str(book.get("source_key") or "").startswith("theme:"):
            messagebox.showinfo("Retry from source", "The source theme is selected in Publishing Center. Use Create complete package to retry through the normal proof checks.", parent=self)
        else: messagebox.showinfo("Retry from source", "This partial package has no linked saved theme. Open the folder to inspect it, then recreate it from its original creator screen.", parent=self)
    def abandon_selected(self):
        folder=self.selected_folder()
        if not folder: return
        book=self._matched_book(folder)
        if book: self.service.db.set_approval_status(book["book_id"],"Abandoned","Partial package marked abandoned; files left untouched."); self.on_changed()
        self.refresh()
    def archive_selected(self):
        folder=self.selected_folder()
        if not folder: return
        if not messagebox.askyesno("Archive partial package", f"Move only this incomplete folder into out\\_recovery_archive?\n\n{folder.name}\n\nNo files will be deleted.", parent=self): return
        archive=Path(self.service.output)/"_recovery_archive"; archive.mkdir(exist_ok=True); target=archive/folder.name
        if target.exists(): target=archive/f"{folder.name}_{datetime.now():%Y%m%d_%H%M%S}"
        import shutil; shutil.move(str(folder),str(target)); self.refresh()


class SeriesMapDialog(tk.Toplevel):
    """A visual planning map built from the same saved catalog used by production."""
    def __init__(self, parent, service) -> None:
        super().__init__(parent); self.service=service; self.title("Visual series map"); fit_dialog_to_screen(self, 1080, 650, 760, 460); self.configure(background="#101418"); self.transient(parent)
        root=ttk.Frame(self,padding=20,style="Publish.TFrame"); root.pack(fill="both",expand=True); root.columnconfigure(0,weight=1); root.rowconfigure(2,weight=1)
        ttk.Label(root,text="Visual series map",style="Publish.Title.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(root,text="Every planned and completed book is grouped by series. Readiness comes from the same package and queue records that the Publishing Center uses.",style="Publish.Subtitle.TLabel",wraplength=1000).grid(row=1,column=0,sticky="w",pady=(4,12))
        cols=("book","subtopic","puzzles","price","cover","freshness","ready")
        tree=ttk.Treeview(root,columns=cols,show="tree headings",style="Publish.Treeview")
        tree.heading("#0",text="Series"); tree.column("#0",width=190,anchor="w")
        for key,label,width in (("book","Planned book",250),("subtopic","Subtopic / theme",160),("puzzles","Puzzles",65),("price","Start price",82),("cover","Cover direction",145),("freshness","Word-bank signal",120),("ready","Queue / package",135)):
            tree.heading(key,text=label); tree.column(key,width=width,anchor="w")
        tree.grid(row=2,column=0,sticky="nsew")
        groups={}
        queued={row["book_id"]:row for row in service.db.approved_production_queue()}
        for book in service.db.list_books():
            meta=book.get("metadata") or {}; series=str(meta.get("series") or meta.get("theme_group") or "Standalone books")
            parent_id=groups.get(series)
            if parent_id is None: parent_id=tree.insert("","end",text=series,open=True,values=("","","","","","")); groups[series]=parent_id
            queue=queued.get(book["book_id"],{}); state=queue.get("status") or ("Package ready" if book.get("package_path") else "Planned")
            price=float((meta.get("price") or {}).get("amazon") or 0)
            tree.insert(parent_id,"end",text="",values=(meta.get("title","Untitled"),meta.get("topic") or meta.get("theme") or "—",meta.get("puzzle_count") or "—",f"${price:.2f}" if price else "—",meta.get("cover_style") or meta.get("palette") or "Automatic",meta.get("freshness") or "Checked",state))
        ttk.Button(root,text="Close",command=self.destroy,style="Publish.Action.TButton").grid(row=3,column=0,sticky="e",pady=(12,0))


class CoverConceptBoard(tk.Toplevel):
    """Retains up to three clear directions without replacing the active cover."""
    def __init__(self, parent, service, book: dict) -> None:
        super().__init__(parent); self.service, self.book = service, book
        self.title("Cover A/B concept board"); self.geometry("760x500"); self.minsize(600, 410); self.configure(background="#101418"); self.transient(parent)
        self.label = tk.StringVar(value="Concept A"); self.palette = tk.StringVar(value=str((book.get("metadata") or {}).get("palette") or "Automatic")); self.layout = tk.StringVar(value=str((book.get("metadata") or {}).get("cover_style") or "Automatic")); self.note = tk.StringVar()
        root=ttk.Frame(self,padding=20,style="Publish.TFrame"); root.pack(fill="both",expand=True); root.columnconfigure(1,weight=1); root.rowconfigure(4,weight=1)
        ttk.Label(root,text="Cover A/B concept board",style="Publish.Title.TLabel").grid(row=0,column=0,columnspan=2,sticky="w")
        ttk.Label(root,text="Save up to three reusable cover directions. Selecting one records your winner; it never overwrites an already-created cover.",style="Publish.Subtitle.TLabel",wraplength=690).grid(row=1,column=0,columnspan=2,sticky="w",pady=(4,14))
        for row,label,var in ((2,"Concept name",self.label),(3,"Palette / layout note",self.palette)):
            ttk.Label(root,text=label,style="Publish.TLabel").grid(row=row,column=0,sticky="w",pady=5); ttk.Entry(root,textvariable=var).grid(row=row,column=1,sticky="ew",pady=5)
        self.tree=ttk.Treeview(root,columns=("name","direction","score","winner"),show="headings",style="Publish.Treeview");
        for key,head,width in (("name","Concept",150),("direction","Direction",320),("score","Score",70),("winner","Winner",70)): self.tree.heading(key,text=head); self.tree.column(key,width=width,anchor="w")
        self.tree.grid(row=4,column=0,columnspan=2,sticky="nsew",pady=(12,0))
        ttk.Label(root, textvariable=self.note, style="Publish.Status.TLabel", wraplength=690).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions=ttk.Frame(root,style="Publish.TFrame"); actions.grid(row=6,column=0,columnspan=2,sticky="ew",pady=(12,0))
        ttk.Button(actions,text="Save concept",command=self.save,style="Publish.Primary.TButton").pack(side="left"); ttk.Button(actions,text="Choose selected winner",command=self.choose,style="Publish.Action.TButton").pack(side="left",padx=7); ttk.Button(actions,text="Close",command=self.destroy,style="Publish.Action.TButton").pack(side="right")
        self.refresh()
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.service.db.cover_concepts(self.book["book_id"]):
            from .production_intelligence import cover_concept_score
            direction=item.get("direction") or {}; score=cover_concept_score(str((self.book.get("metadata") or {}).get("title") or ""), str(direction.get("palette") or ""), str(direction.get("layout") or ""))
            self.tree.insert("","end",iid=str(item["concept_id"]),values=(item["label"], f"{direction.get('palette','')} • {direction.get('layout','')}", f"{score['score']}/100", "✓" if item.get("selected") else ""))
        from .truth_service import PublishingTruthService
        cover = PublishingTruthService(self.service).for_book(self.book["book_id"])["cover"]
        if cover.get("release_lock", {}).get("matches_final_render"):
            self.note.set(f"Recorded cover: matches release lock #{cover['release_lock']['revision']}. {cover['render_sha256'][:12]}…")
        elif cover.get("front_cover"):
            self.note.set("Recorded cover: final file found, but it is not bound to a release lock yet.")
        else:
            self.note.set("Recorded cover: no final cover file is available yet.")
    def save(self):
        if len(self.service.db.cover_concepts(self.book["book_id"])) >= 3 and not any(item["label"] == self.label.get().strip() for item in self.service.db.cover_concepts(self.book["book_id"])):
            messagebox.showinfo("Three concepts saved", "Keep the board focused: edit one of the three directions or choose a winner.", parent=self); return
        self.service.db.save_cover_concept(self.book["book_id"],self.label.get(),{"palette":self.palette.get(),"layout":self.layout.get()},False); self.refresh()
    def choose(self):
        selected=self.tree.selection()
        if not selected: messagebox.showwarning("Choose a concept", "Choose a saved direction first.", parent=self); return
        item=next((x for x in self.service.db.cover_concepts(self.book["book_id"]) if str(x["concept_id"]) == selected[0]),None)
        if item: self.service.db.save_cover_concept(self.book["book_id"],item["label"],item["direction"],True); self.refresh()


class ContentExpansionDialog(tk.Toplevel):
    """Explain a topic gap without ever auto-inserting unreviewed vocabulary."""

    def __init__(self, parent, project: Path, topic: str) -> None:
        super().__init__(parent); self.project, self.topic = Path(project), topic
        self.title("Content expansion plan"); self.geometry("820x610"); self.minsize(660, 480); self.configure(background="#101418"); self.transient(parent)
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(4, weight=1)
        ttk.Label(root, text="Content expansion plan", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="This planner shows the real gap before a topic is treated as ready. It never adds loose dictionary words or changes your Master Library by itself.", style="Publish.Subtitle.TLabel", wraplength=760).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self.report = tk.Text(root, wrap="word", state="disabled", background="#171d23", foreground="#d9f5ee", relief="flat", padx=14, pady=12)
        self.report.grid(row=2, column=0, sticky="nsew")
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(actions, text="Save research brief", command=self.save_brief, style="Publish.Primary.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy, style="Publish.Action.TButton").pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        from .content_expansion import expansion_plan
        plan = expansion_plan(self.project, self.topic)
        lines = [plan["topic"].upper(), "=" * 54, "", plan["state"], f"Current verified topic words: {plan['current_words']:,}", f"Two-book target: {plan['target_words']:,}", "", "CURRENTLY LINKED SOURCES"]
        lines.extend(f"• {value}" for value in plan["source_topics"])
        lines += ["", "SAFE RESEARCH STARTERS", "Use these only to locate source vocabulary. Review every term for relevance and duplicates before importing it."]
        lines.extend(f"• {value}" for value in plan["research_queries"])
        lines += ["", "NEXT STEP", plan["next_step"], "", "When new words are ready, use Word Search Library → More Book & Library Tools → Import Word Bank. The existing quality checks will keep unrelated words out of production."]
        self.report.configure(state="normal"); self.report.delete("1.0", "end"); self.report.insert("1.0", "\n".join(lines)); self.report.configure(state="disabled")

    def save_brief(self) -> None:
        from .content_expansion import save_research_brief
        target = save_research_brief(self.project, self.topic)
        messagebox.showinfo("Research brief saved", f"Saved a review-only expansion brief here:\n{target}\n\nYour Master Library was not changed.", parent=self)


class ProductionReadinessDialog(tk.Toplevel):
    """Rank the strongest next production moves using only local verified data."""
    def __init__(self, parent, service, on_changed) -> None:
        super().__init__(parent); self.parent_manager, self.service, self.on_changed = parent, service, on_changed
        self.title("Production dashboard"); fit_dialog_to_screen(self, 1120, 720, 820, 500); self.configure(background="#1f1f1f"); self.transient(parent)
        self.status = tk.StringVar(value="Checking the catalog…"); self.rows = {}
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(4, weight=1)
        ttk.Label(root, text="Production dashboard", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Your best next books, ranked from real local readiness: production gate, completed files, specific marketplace copy, cover availability, and series connection. This is a production score—not a sales prediction.", style="Publish.Subtitle.TLabel", wraplength=1040).grid(row=1, column=0, sticky="w", pady=(3, 12))
        ttk.Label(root, text="Needs your attention first", style="Publish.Section.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.attention = ttk.Treeview(root, columns=("book", "issues", "next"), show="headings", style="Publish.Treeview", height=4)
        for key, label, width in (("book", "Book", 320), ("issues", "What needs attention", 480), ("next", "Next step", 350)):
            self.attention.heading(key, text=label); self.attention.column(key, width=width, anchor="w")
        self.attention.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.tree = ttk.Treeview(root, columns=("book", "score", "package", "copy", "next"), show="headings", style="Publish.Treeview")
        for key, label, width in (("book", "Book", 280), ("score", "Production score", 110), ("package", "Package", 115), ("copy", "Copy quality", 105), ("next", "Why it is ready", 490)):
            self.tree.heading(key, text=label); self.tree.column(key, width=width, anchor="w")
        ranked = ttk.Frame(root, style="Publish.TFrame"); ranked.grid(row=4, column=0, sticky="nsew")
        ranked.columnconfigure(0, weight=1); ranked.rowconfigure(0, weight=1)
        self.tree.grid(in_=ranked, row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(ranked, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns"); self.tree.configure(yscrollcommand=tree_scroll.set)
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        for column in range(5): actions.columnconfigure(column, weight=1)
        self.refresh_button = ttk.Button(actions, text="Refresh", command=self.refresh, style="Publish.Action.TButton"); self.refresh_button.grid(row=0, column=0, sticky="ew", padx=(0,4))
        ttk.Button(actions, text="Review selected", command=self.review_selected, style="Publish.Action.TButton").grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(actions, text="Build best next book", command=self.build_best, style="Publish.Primary.TButton").grid(row=0, column=2, sticky="ew", padx=4)
        self.repair_button = ttk.Button(actions, text="Recheck local files", command=self.fix_local_status, style="Publish.Action.TButton"); self.repair_button.grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(actions, text="Close", command=self.destroy, style="Publish.Action.TButton").grid(row=0, column=4, sticky="ew", padx=(4,0))
        ttk.Label(root, textvariable=self.status, style="Publish.Status.TLabel", wraplength=940).grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.refresh()

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled"); self.status.set("Checking local files and marketplace handoff readiness in the background…")
        def work() -> None:
            try:
                from .production_dashboard import production_attention, production_candidates
                self.after(0, lambda: self._show(production_candidates(self.service), production_attention(self.service)))
            except Exception as exc:
                self.after(0, lambda: self._refresh_failed(str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, rows: list[dict], attention: list[dict]) -> None:
        self.attention.delete(*self.attention.get_children())
        for index, row in enumerate(attention):
            title = row["book"].get("metadata", {}).get("title", "Untitled")
            suffix = f" (+{row['count'] - 1} more)" if row["count"] > 1 else ""
            self.attention.insert("", "end", iid=f"attention_{index}", values=(title, row["issue"] + suffix, row["next"]))
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for index, row in enumerate(rows):
            iid = f"candidate_{index}"; self.rows[iid] = row
            self.tree.insert("", "end", iid=iid, values=(row["book"]["metadata"].get("title", "Untitled"), f"{row['score']}/100", "Complete" if row["has_package"] else "Ready to build", f"{row['copy_score']}/100", row["reason"]))
        self.status.set(f"{len(attention)} book{'s' if len(attention) != 1 else ''} need attention; {len(rows)} locally ready book{'s' if len(rows) != 1 else ''} found. Review one, build the top choice, or refresh after you add content."); self.refresh_button.configure(state="normal")

    def review_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Choose a book", "Choose a ranked book first.", parent=self); return
        ListingReviewDialog(self, self.service, self.rows[selected[0]]["book"], self.refresh)

    def build_best(self) -> None:
        if not self.rows:
            messagebox.showinfo("Nothing ready yet", "There is no locally ready book to create yet. Use Content Capacity to plan the next safe expansion.", parent=self); return
        self.destroy()
        self.parent_manager.create_best_version()

    def _refresh_failed(self, detail: str) -> None:
        self.refresh_button.configure(state="normal")
        self.status.set(f"Could not refresh readiness: {detail}. Nothing was changed.")

    def fix_local_status(self) -> None:
        self.repair_button.configure(state="disabled"); self.status.set("Scanning local marketplace folders in the background…")
        def work() -> None:
            try:
                found = self.service.detect_local_marketplace_status()
                self.after(0, lambda: self._fixed(found))
            except Exception as exc:
                self.after(0, lambda: self._fix_failed(str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _fixed(self, found: int) -> None:
        self.repair_button.configure(state="normal"); self.on_changed(); self.status.set(f"Updated {found} local handoff status record(s). Uploaded and published records were left untouched."); self.refresh()

    def _fix_failed(self, detail: str) -> None:
        self.repair_button.configure(state="normal"); self.status.set(f"Could not scan local handoffs: {detail}. Nothing was changed.")


class ApprovedProductionQueueDialog(tk.Toplevel):
    """One intentional, one-at-a-time route from approval to package creation."""
    def __init__(self, parent: PublishingManagerDialog, service, on_changed) -> None:
        super().__init__(parent); self.parent_manager, self.service, self.on_changed = parent, service, on_changed
        self.title("Approved production queue"); fit_dialog_to_screen(self, 900, 590, 680, 440); self.configure(background="#101418"); self.transient(parent)
        root = ttk.Frame(self, padding=20, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Approved production queue", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="These are the books you deliberately approved. Start one at a time; the normal complete-package flow and all proof checks still run before anything is ready for upload.", style="Publish.Subtitle.TLabel", wraplength=820).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self.tree = ttk.Treeview(root, columns=("book", "status", "targets", "launch", "stopped", "note"), show="headings", style="Publish.Treeview", selectmode="browse")
        for key, label, width in (("book", "Book", 235), ("status", "Status", 105), ("targets", "Target places", 145), ("launch", "Launch date", 95), ("stopped", "Why it stopped", 170), ("note", "Note", 180)):
            self.tree.heading(key, text=label); self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(actions, text="Start selected book", command=self.start_selected, style="Publish.Primary.TButton").pack(side="left")
        ttk.Button(actions, text="Move up", command=lambda: self._move(-1), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Move down", command=lambda: self._move(1), style="Publish.Action.TButton").pack(side="left", padx=(7,0))
        ttk.Button(actions, text="Set launch plan", command=self.set_launch_plan, style="Publish.Action.TButton").pack(side="left", padx=7)
        ttk.Button(actions, text="Mark completed", command=lambda: self._set_selected("Completed"), style="Publish.Action.TButton").pack(side="left", padx=7)
        ttk.Button(actions, text="Needs attention", command=lambda: self._set_selected("Needs attention"), style="Publish.Action.TButton").pack(side="left")
        ttk.Button(actions, text="Refresh", command=self.refresh, style="Publish.Action.TButton").pack(side="right", padx=7)
        ttk.Button(actions, text="Close", command=self.destroy, style="Publish.Action.TButton").pack(side="right")
        self.rows: dict[str, dict] = {}; self.refresh()

    def refresh(self) -> None:
        self.rows.clear(); self.tree.delete(*self.tree.get_children())
        for row in self.service.db.approved_production_queue():
            book = self.service.db.get_book(row["book_id"])
            if not book:
                continue
            self.rows[row["book_id"]] = book
            targets = ", ".join(DISPLAY.get(key, key) for key in row.get("target_marketplaces", [])) or "Not set"
            self.tree.insert("", "end", iid=row["book_id"], values=(book["metadata"].get("title", "Untitled"), row["status"], targets, row.get("target_launch_date", "") or "—", row.get("stop_reason", "") or "—", row.get("note", "")))

    def _move(self, direction: int) -> None:
        selected=self.tree.selection()
        if not selected: messagebox.showwarning("Choose a book", "Choose a queued book first.", parent=self); return
        if self.service.db.move_approval_item(selected[0], direction): self.refresh(); self.tree.selection_set(selected[0])

    def set_launch_plan(self) -> None:
        selected=self.tree.selection()
        if not selected: messagebox.showwarning("Choose a book", "Choose a queued book first.", parent=self); return
        row=next((item for item in self.service.db.approved_production_queue() if item["book_id"] == selected[0]), {})
        dialog=tk.Toplevel(self); dialog.title("Launch plan"); dialog.configure(background="#101418"); dialog.transient(self); dialog.grab_set()
        ttk.Label(dialog,text="Launch date (YYYY-MM-DD, optional)",style="Publish.TLabel").pack(anchor="w",padx=18,pady=(16,3)); date=tk.StringVar(value=row.get("target_launch_date", "")); ttk.Entry(dialog,textvariable=date,width=28).pack(fill="x",padx=18)
        choices={key:tk.BooleanVar(value=key in row.get("target_marketplaces", [])) for key in ("amazon","etsy","website","ingram")}
        ttk.Label(dialog,text="Target marketplaces",style="Publish.TLabel").pack(anchor="w",padx=18,pady=(12,3))
        for key,var in choices.items(): ttk.Checkbutton(dialog,text=DISPLAY[key],variable=var).pack(anchor="w",padx=18)
        def save():
            self.service.db.update_approval_plan(selected[0],[key for key,var in choices.items() if var.get()],date.get()); dialog.destroy(); self.refresh(); self.tree.selection_set(selected[0])
        ttk.Button(dialog,text="Save launch plan",command=save,style="Publish.Primary.TButton").pack(fill="x",padx=18,pady=16)

    def _set_selected(self, status: str) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Choose a book", "Choose a queued book first.", parent=self); return
        self.service.db.set_approval_status(selected[0], status)
        self.on_changed(); self.refresh()

    def start_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Choose a book", "Choose an approved book first.", parent=self); return
        book = self.rows.get(selected[0])
        if not book:
            return
        gate = self.service.production_gate(book["book_id"])
        if not gate["ready"]:
            self.service.db.set_approval_status(book["book_id"], "Needs attention", "; ".join(gate["blockers"])[:500])
            self.on_changed(); self.refresh()
            messagebox.showwarning("Production gate stopped this book", gate_text(gate), parent=self)
            return
        self.service.db.set_approval_status(book["book_id"], "In progress")
        self.on_changed()
        self.destroy()
        self.parent_manager._request_complete_package(book)


class BatchReviewDialog(tk.Toplevel):
    """A compact approval queue for selected completed books."""
    def __init__(self, parent, service, books: list[dict], on_changed) -> None:
        super().__init__(parent); self.service, self.books, self.on_changed = service, books, on_changed
        self.title("Batch review queue"); fit_dialog_to_screen(self, 900, 620, 700, 460); self.configure(background="#1f1f1f"); self.transient(parent)
        root = ttk.Frame(self, padding=20, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Batch review queue", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Only books that pass their marketplace checks are prepared. This creates local handoff folders; it never uploads or publishes.", style="Publish.Subtitle.TLabel", wraplength=820).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self.text = tk.Text(root, wrap="word", background="#292929", foreground="#d9f5ee", relief="flat", padx=14, pady=12); self.text.grid(row=2, column=0, sticky="nsew")
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.status = tk.StringVar(value="Review the results, then prepare only the books that pass their checks.")
        self.prepare_button = ttk.Button(actions, text="Prepare KDP + Etsy + Website", command=self.prepare_core, style="Publish.Primary.TButton")
        self.prepare_button.pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy, style="Publish.Action.TButton").pack(side="right")
        ttk.Label(root, textvariable=self.status, style="Publish.Subtitle.TLabel", wraplength=820).grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.refresh_queue()

    def refresh_queue(self) -> None:
        from .review import review_result
        lines = []
        for book in self.books:
            result = review_result(book, "amazon")
            state = "READY" if result["ready"] else "NEEDS ATTENTION"
            lines.append(f"{state} — {book['metadata'].get('title', 'Untitled book')}")
            lines.extend(f"  • {item}" for item in (result["blockers"] or result["checks"][:2]))
        self.text.delete("1.0", "end"); self.text.insert("1.0", "\n".join(lines) or "No books selected.")

    def prepare_core(self) -> None:
        ready_books = [book for book in self.books if self.service.production_gate(book["book_id"])["ready"]]
        stopped = [book for book in self.books if book not in ready_books]
        if stopped:
            self.status.set(f"{len(stopped)} book(s) were held by the Production Gate. Only the {len(ready_books)} ready book(s) can be prepared.")
        if not ready_books:
            messagebox.showwarning("Nothing ready to prepare", "Every selected book has a production gate issue. Review the proof summary and fix those first.", parent=self)
            return
        self.prepare_button.configure(state="disabled")
        self.status.set("Preparing marketplace handoff folders in the background…")
        book_ids = [book["book_id"] for book in ready_books]

        def work() -> None:
            try:
                report = self.service.prepare_many(book_ids, ["amazon", "etsy", "website"])
                self.after(0, lambda: self._prepared(report))
            except Exception as exc:
                self.after(0, lambda: self._prepare_failed(str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _prepared(self, report: list[tuple[str, str, str]]) -> None:
        self.prepare_button.configure(state="normal")
        self.books = [self.service.db.get_book(book["book_id"]) or book for book in self.books]
        self.on_changed(); self.refresh_queue()
        ready = sum(1 for _book, _market, state in report if state == "Ready")
        self.status.set(f"Prepared {ready} marketplace handoff folder(s). Review any needs-attention item before uploading.")
        messagebox.showinfo("Batch preparation complete", self.status.get(), parent=self)

    def _prepare_failed(self, detail: str) -> None:
        self.prepare_button.configure(state="normal")
        self.status.set(f"Preparation stopped: {detail}. Existing files were left untouched.")
        messagebox.showerror("Batch preparation problem", self.status.get(), parent=self)


class ISBNManagerDialog(tk.Toplevel):
    """Read-only safety view: ISBN assignment happens on each Book Details screen."""
    def __init__(self, parent, service) -> None:
        super().__init__(parent); self.service = service; self.title("ISBN Manager"); self.geometry("760x440"); self.minsize(620, 350); self.configure(background="#1f1f1f")
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(2, weight=1)
        ttk.Label(root, text="ISBN manager", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Assign an ISBN in Book Details. This list prevents one ISBN from being assigned to two different books. A KDP-provided ISBN should remain KDP-specific.", style="Publish.Subtitle.TLabel", wraplength=700).grid(row=1, column=0, sticky="w", pady=(3, 12))
        tree = ttk.Treeview(root, columns=("isbn", "title", "format", "source", "date"), show="headings", style="Publish.Treeview")
        for key, label, width in (("isbn", "ISBN", 150), ("title", "Title", 280), ("format", "Format", 100), ("source", "Source", 140), ("date", "Assigned", 130)):
            tree.heading(key, text=label); tree.column(key, width=width, anchor="w")
        tree.grid(row=2, column=0, sticky="nsew")
        for item in service.db.list_isbns(): tree.insert("", "end", values=(item.get("isbn", ""), item.get("title", ""), item.get("format", ""), item.get("source", ""), str(item.get("assigned_at", ""))[:16].replace("T", " ")))


class MarketplaceHistoryDialog(tk.Toplevel):
    """Human-readable, newest-first audit trail for one book's marketplaces."""

    def __init__(self, parent, service, book: dict, initial_marketplace: str = "") -> None:
        super().__init__(parent); self.service, self.book = service, book
        self.title(f"Publishing history — {book['metadata'].get('title', 'Book')}"); self.geometry("800x560"); self.minsize(640, 420)
        self.configure(background="#1f1f1f"); self.transient(parent)
        choices = ["All marketplaces"] + [f"{DISPLAY_GRID[key]}|{key}" for key in MARKETPLACES]
        default = f"{DISPLAY_GRID[initial_marketplace]}|{initial_marketplace}" if initial_marketplace in MARKETPLACES else "All marketplaces"
        self.market_choice = tk.StringVar(value=default)
        root = ttk.Frame(self, padding=20, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(3, weight=1)
        ttk.Label(root, text="Publishing history", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text=book["metadata"].get("title", ""), style="Publish.Subtitle.TLabel", wraplength=740).grid(row=1, column=0, sticky="w", pady=(3, 10))
        picker = ttk.Frame(root, style="Publish.TFrame"); picker.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(picker, text="Marketplace", style="Publish.TLabel").pack(side="left")
        combo = ttk.Combobox(picker, textvariable=self.market_choice, values=choices, state="readonly", width=26, style="Publish.TCombobox")
        combo.pack(side="left", padx=7); combo.bind("<<ComboboxSelected>>", lambda _event: self.reload())
        ttk.Button(picker, text="Refresh", command=self.reload, style="Publish.Action.TButton").pack(side="left")
        self.count_var = tk.StringVar(value=""); ttk.Label(picker, textvariable=self.count_var, style="Publish.Subtitle.TLabel").pack(side="right")
        self.history_box = tk.Text(root, wrap="word", state="disabled", background="#292929", foreground="#d9f5ee", relief="flat", padx=12, pady=10)
        self.history_box.grid(row=3, column=0, sticky="nsew")
        ttk.Button(root, text="Close", command=self.destroy, style="Publish.Action.TButton").grid(row=4, column=0, sticky="e", pady=(10, 0))
        self.reload()

    def _marketplace_key(self) -> str:
        value = self.market_choice.get()
        return value.rsplit("|", 1)[-1] if "|" in value else ""

    def reload(self) -> None:
        key = self._marketplace_key()
        entries = self.service.db.audit_history(book_id=self.book["book_id"], marketplace=key or None)
        label = DISPLAY_GRID.get(key, key) if key else ""
        self.count_var.set(f"{len(entries)} recorded change(s)" + (f" — {label}" if label else ""))
        self.history_box.configure(state="normal"); self.history_box.delete("1.0", "end")
        self.history_box.insert("end", format_history(entries))
        self.history_box.configure(state="disabled")


class _StoredEtsyCredentialProvider:
    """Credential provider reading env vars first, then Windows Credential Manager."""

    def load(self):
        from integrations.etsy.session import load_credentials

        return load_credentials()


class BusinessGuidanceDialog(tk.Toplevel):
    """One small, connected view for what to make, do, sell, and promote."""

    def __init__(self, parent, service, on_changed=None) -> None:
        super().__init__(parent); self.parent_manager, self.service, self.on_changed = parent, service, on_changed
        self.title("Business guidance"); fit_dialog_to_screen(self, 1120, 720, 840, 500); self.configure(background="#101418"); self.transient(parent)
        self.engine = None; self.tasks = {}; self.opportunities = {}; self.opportunity_records = {}; self.bundles = {}
        self.opportunity_view = tk.StringVar(value="Fastest to Production")
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(3, weight=1)
        ttk.Label(root, text="Business guidance", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        self.next_text = tk.StringVar(value="Checking your local catalog…")
        ttk.Label(root, textvariable=self.next_text, style="Publish.Status.TLabel", wraplength=1020).grid(row=1, column=0, sticky="ew", pady=(6, 12))
        buttons = ttk.Frame(root, style="Publish.TFrame"); buttons.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(buttons, text="Continue Production", command=self.continue_production, style="Publish.Primary.TButton").pack(side="left")
        ttk.Button(buttons, text="Run Product QA", command=self.run_product_qa, style="Publish.Action.TButton").pack(side="left", padx=7)
        more = ttk.Menubutton(buttons, text="More actions", style="Publish.Action.TButton")
        menu = tk.Menu(more, tearoff=False)
        menu.add_command(label="Create digital edition", command=self.create_digital)
        menu.add_command(label="Create mini pack", command=self.create_mini_pack)
        menu.add_command(label="Improve listing with AI", command=self.improve_listing)
        menu.add_command(label="Generate marketing kit", command=self.create_marketing)
        menu.add_command(label="Create Etsy listing images", command=self.create_etsy_merchandising)
        menu.add_command(label="Create recommended bundle", command=self.create_bundle)
        menu.add_separator()
        menu.add_command(label="Approve recommendation", command=lambda: self.review_opportunity("approved"))
        menu.add_command(label="Reject recommendation", command=lambda: self.review_opportunity("rejected"))
        more.configure(menu=menu); more.pack(side="left")
        ttk.Button(buttons, text="Refresh", command=self.refresh, style="Publish.Action.TButton").pack(side="right")
        view = ttk.Combobox(buttons, textvariable=self.opportunity_view, values=("Fastest to Production", "Catalog Gaps", "Series Ideas"), state="readonly", width=21)
        view.pack(side="right", padx=7); view.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        tabs = ttk.Notebook(root, style="Publish.TNotebook"); tabs.grid(row=3, column=0, sticky="nsew")
        queue_tab, opportunity_tab, bundle_tab, non_word_tab = (ttk.Frame(tabs, style="Publish.TFrame") for _ in range(4))
        tabs.add(queue_tab, text="What should I do?"); tabs.add(opportunity_tab, text="What should I make?"); tabs.add(bundle_tab, text="What else can I sell?")
        tabs.add(non_word_tab, text="Build Out Other Puzzle Types")
        for tab in (queue_tab, opportunity_tab, bundle_tab, non_word_tab): tab.columnconfigure(0, weight=1); tab.rowconfigure(0, weight=1)
        self.queue_tree = ttk.Treeview(queue_tab, columns=("priority", "book", "task", "reason", "status"), show="headings", style="Publish.Treeview")
        self.opportunity_tree = ttk.Treeview(opportunity_tab, columns=("rank", "book", "topic", "type", "score", "evidence", "risk", "next"), show="headings", style="Publish.Treeview")
        self.bundle_tree = ttk.Treeview(bundle_tab, columns=("bundle", "topic", "books", "overlap", "price"), show="headings", style="Publish.Treeview")
        self.non_word_tree = ttk.Treeview(non_word_tab, columns=("format", "count", "target", "ready", "content", "development", "opportunity", "next"), show="headings", style="Publish.Treeview")
        for tree, cols, labels in ((self.queue_tree, ("priority", "book", "task", "reason", "status"), ("Priority", "Book", "Task", "Why now", "Status")), (self.opportunity_tree, ("rank", "book", "topic", "type", "score", "evidence", "risk", "next"), ("Rank", "Proposed title", "Topic", "Puzzle type", "Score", "Evidence", "Main risk", "Next action")), (self.bundle_tree, ("bundle", "topic", "books", "overlap", "price"), ("Recommended bundle", "Topic", "Books", "Overlap", "Suggested digital price"))):
            for key, label in zip(cols, labels): tree.heading(key, text=label); tree.column(key, width=150, anchor="w")
            tree.column(cols[0], width=85); tree.grid(row=0, column=0, sticky="nsew")
        for key, label, width in (("format", "Puzzle type", 150), ("count", "Catalog", 70), ("target", "Planning range", 95), ("ready", "Ready", 65), ("content", "Needs content/review", 130), ("development", "Needs development", 130), ("opportunity", "Strong opportunity", 250), ("next", "Next safe action", 220)):
            self.non_word_tree.heading(key, text=label); self.non_word_tree.column(key, width=width, anchor="w")
        self.non_word_tree.grid(row=0, column=0, sticky="nsew")
        self.refresh()

    def refresh(self) -> None:
        from .business_automation import BusinessAutomation
        from .market_opportunity import MarketOpportunityService
        self.engine = BusinessAutomation(self.service); queue = self.engine.rebuild_queue(); bundles = self.engine.bundle_candidates()
        view_key = {"Catalog Gaps": "gaps", "Series Ideas": "series"}.get(self.opportunity_view.get(), "fastest")
        ranked = self.service.catalog_intelligence(20, view_key)
        records = MarketOpportunityService(self.service).refresh()
        opportunities = {item["book_id"]: item for item in ranked}
        self.tasks = {item["task_id"]: item for item in queue}; self.opportunities = opportunities; self.opportunity_records = {item.book_id: item for item in records}; self.bundles = {f"bundle-{index}": item for index, item in enumerate(bundles)}
        for tree in (self.queue_tree, self.opportunity_tree, self.bundle_tree, self.non_word_tree): tree.delete(*tree.get_children())
        for item in queue:
            book = self.service.db.get_book(item["product_id"]); title = str((book or {}).get("metadata", {}).get("title") or "Unknown book")
            self.queue_tree.insert("", "end", iid=item["task_id"], values=(item["priority"], title, item["task_type"].replace("_", " ").title(), item["reason"], item["status"]))
        for index, item in enumerate(ranked, 1):
            evidence = (item.get("reasons") or ["Local catalog evidence"])[0]
            risk = (item.get("warnings") or item.get("missing_work") or ["No blocking risk found"])[0]
            action = (item.get("missing_work") or ["Review and start this book"])[0]
            self.opportunity_tree.insert("", "end", iid=item["book_id"], values=(f"#{index}", item["title"], item["topic_id"], item["recommended_format"].replace("_", " ").title(), item["score"], evidence, risk, action))
        for index, item in enumerate(bundles):
            self.bundle_tree.insert("", "end", iid=f"bundle-{index}", values=(item["title"], item["topic"], len(item["books"]), f"{item['overlap']}%", f"${item['price']['etsy']:.2f}"))
        non_word = self.service.non_word_expansion_plan()
        for key, section in non_word["formats"].items():
            states = section["status_counts"]; top = section["top_20"][0] if section["top_20"] else {}
            needs_content = states.get("Needs Minor Content Expansion", 0) + states.get("Needs Editorial Review", 0)
            self.non_word_tree.insert("", "end", iid="non-word-" + key, values=(section["label"], section["catalog_count"], f"{section['target_range'][0]}–{section['target_range'][1]}", states.get("Ready Now", 0), needs_content, states.get("Needs Format Development", 0), top.get("title", "No safe opportunity yet"), top.get("next_safe_action", "Inspect evidence")))
        next_task = next((item for item in queue if item["status"] == "OPEN"), None)
        self.next_text.set((f"NEXT BEST ACTION — {next_task['recommended_action']}: {next_task['reason']}" if next_task else "Everything currently tracked is complete. See What should I make? for the strongest local opportunities."))
        if self.on_changed: self.on_changed()

    def _selected_task(self):
        selected = self.queue_tree.selection(); return self.tasks.get(selected[0]) if selected else self.engine.next_action()

    def do_next(self) -> None:
        task = self._selected_task()
        if not task: messagebox.showinfo("No action waiting", "There is no open business action right now.", parent=self); return
        book = self.service.db.get_book(task["product_id"])
        if not book: messagebox.showwarning("Book missing", "The source book is no longer in the catalog.", parent=self); return
        try:
            if task["task_type"] == "CREATE_BOOK":
                self.parent_manager._request_complete_package(book); return
            if task["task_type"].startswith("PREPARE_"):
                self.service.prepare(book["book_id"], task["marketplace"])
            elif task["task_type"] == "CREATE_DIGITAL_EDITION":
                self.engine.create_digital_edition(book["book_id"])
            elif task["task_type"] == "GENERATE_MARKETING_KIT":
                self.engine.generate_marketing_kit(book["book_id"])
            else:
                self.parent_manager.tree.selection_set(book["book_id"]); self.parent_manager.tree.focus(book["book_id"]); self.parent_manager.notebook.select(1)
                messagebox.showinfo("Review needed", "The selected book is open in Publishing Center. Review the production gate details before continuing.", parent=self); return
            self.engine.complete_task(task["task_id"]); self.refresh()
        except Exception as exc:
            messagebox.showwarning("Action needs attention", str(exc), parent=self)

    def _selected_book(self):
        selected = self.opportunity_tree.selection()
        if selected:
            return self.service.db.get_book(selected[0])
        task = self._selected_task()
        return self.service.db.get_book(task["product_id"]) if task else None

    def continue_production(self) -> None:
        """Use the canonical job state when available, otherwise existing queue routing."""
        book = self._selected_book()
        if not book:
            self.do_next(); return
        state = self.service.autopilot_status(book["book_id"]).get("production_job") or {}
        stage = state.get("current_stage")
        if stage == "product_qa" and book.get("package_path"):
            self.run_product_qa(); return
        if stage == "final_review":
            self.complete_final_local_review(book, state); return
        if stage == "content_plan":
            self.approve_content_plan(book, state); return
        if stage == "marketplace_handoff":
            messagebox.showinfo("Your review is needed", f"NEXT: {state.get('next_action')}\n\nThis is a human checkpoint, so the app will not pass it automatically.", parent=self); return
        self.do_next()

    def approve_content_plan(self, book: dict, state: dict) -> None:
        """Show the exact plan facts and persist only an explicit decision."""
        from .production_orchestrator import ProductionOrchestrator, plan_review_summary
        job = ProductionOrchestrator(self.service.project, book["book_id"])
        record = job.load()
        context = dict(record.get("context") or {})
        summary = plan_review_summary(context)
        confirmed = messagebox.askyesno(
            "Review and approve the book plan",
            "Review the exact plan below. Approval allows production to continue, but does not create, upload, or publish anything.\n\n"
            + summary
            + "\n\nDoes this plan match the book you intend to create?",
            parent=self,
        )
        if not confirmed:
            self.next_text.set("Book Plan approval remains open. No approval was recorded.")
            return
        approved_at = datetime.now().isoformat(timespec="seconds")
        job.approve_human_stage(
            "content_plan", source="publishing_center.operator_confirmation",
            evidence_id=f"{book['book_id']}:{approved_at}",
            detail="Operator reviewed and approved the displayed book-plan facts.",
        )
        self.next_text.set("Book Plan approved. Continue Production will now begin with the interior; nothing has been published.")
        self.refresh()

    def complete_final_local_review(self, book: dict, state: dict) -> None:
        """Open the current package and persist only an explicit human decision."""
        package = Path(str(book.get("package_path") or ""))
        if not package.is_dir():
            messagebox.showwarning("Final review needs the package", "Create the complete package before Final Local Review.", parent=self)
            return
        lock = self.service.db.latest_release_lock_snapshot(book["book_id"])
        proof = ((lock or {}).get("snapshot") or {}).get("phase4_production_proof") or {}
        proof_id = str(proof.get("proof_id") or "")
        if not proof_id:
            messagebox.showwarning("Run the Production Check first", "Final Local Review requires a current locked Production Proof. Run Product QA / Production Check, then continue again.", parent=self)
            return
        try:
            os.startfile(package)
        except OSError:
            pass
        confirmed = messagebox.askyesno(
            "Complete Final Local Review",
            "The current package folder is open. Before confirming, inspect the interior, solutions, front cover, full wrap, listing information, and every reported warning.\n\nHave you personally completed that review and approved this exact proof revision?",
            parent=self,
        )
        if not confirmed:
            self.next_text.set("Final Local Review remains open. No approval was recorded.")
            return
        review = self.service.db.record_final_local_review(book["book_id"], proof_id, str(package), "Approved through Continue Production after manual inspection.")
        from .production_orchestrator import ProductionOrchestrator
        ProductionOrchestrator(self.service.project, book["book_id"]).approve_human_stage(
            "final_review", source="publishing_database.final_local_reviews",
            evidence_id=f"{proof_id}:{review['reviewed_at']}", detail="Operator approved the exact locked local proof revision.",
        )
        icon_warning = ""
        try:
            from .folder_icons import mark_sale_ready_folder, refresh_explorer_icons
            mark_sale_ready_folder(self.service.project, package)
            refresh_explorer_icons()
        except OSError as exc:
            icon_warning = f" Windows could not refresh the red folder icon ({exc}); reopen the out folder or run the ready-folder icon refresh tool."
        self.next_text.set("Final Local Review recorded. The package may now move to Platform Preview; it has not been published." + icon_warning)
        self.refresh()

    def run_product_qa(self) -> None:
        book = self._selected_book()
        if not book:
            messagebox.showinfo("Choose a book", "Choose a tracked or recommended book first.", parent=self); return
        results: queue.Queue = queue.Queue(maxsize=1)
        self.next_text.set("Product QA is checking the interior, cover, solutions, and package files…")

        def inspect() -> None:
            try:
                results.put((True, self.service.product_qa(book["book_id"])))
            except Exception as exc:
                results.put((False, exc))

        def finish() -> None:
            try:
                ok, value = results.get_nowait()
            except queue.Empty:
                self.after(100, finish)
                return
            if not ok:
                self.next_text.set("Product QA stopped. Open the message for the exact recovery step.")
                messagebox.showwarning("Product QA needs attention", str(value), parent=self)
                return
            report = value
            summary = report.get("summary") or {}
            lines = ["PRODUCT QA", "=" * 44, "", report.get("status", ""),
                     f"Blockers: {summary.get('blockers', 0)}", f"Warnings: {summary.get('warnings', 0)}", ""]
            lines += [f"• {item['severity']} — {item['message']}" for item in report.get("findings", []) if not item.get("passed")]
            self.parent_manager._show_report("Product QA", "\n".join(lines))
            self.next_text.set(f"Product QA finished: {report.get('status', 'review the report')}.")
            self.refresh()

        threading.Thread(target=inspect, name="product-qa", daemon=True).start()
        self.after(100, finish)

    def _book_for_selected_opportunity(self):
        selected = self.opportunity_tree.selection(); return self.service.db.get_book(selected[0]) if selected else None

    def review_opportunity(self, decision: str) -> None:
        selected = self.opportunity_tree.selection()
        record = self.opportunity_records.get(selected[0]) if selected else None
        if not record:
            messagebox.showinfo("Choose a recommendation", "Choose a recommendation in What should I make? first.", parent=self)
            return
        from .market_opportunity import MarketOpportunityService
        if MarketOpportunityService(self.service).review(record.opportunity_id, decision):
            self.refresh()
            self.next_text.set(f"Recommendation marked {decision}. This only records your local planning decision; it does not create or publish anything.")

    def create_digital(self) -> None:
        book = self._book_for_selected_opportunity()
        if not book: messagebox.showinfo("Choose a recommended book", "Choose a book in What should I make? first.", parent=self); return
        try: self.engine.create_digital_edition(book["book_id"]); self.refresh()
        except Exception as exc: messagebox.showwarning("Digital edition needs attention", str(exc), parent=self)

    def create_mini_pack(self) -> None:
        book = self._book_for_selected_opportunity()
        if not book: messagebox.showinfo("Choose a recommended book", "Choose a book in What should I make? first.", parent=self); return
        try: target = self.engine.create_mini_pack(book["book_id"]); self.refresh(); messagebox.showinfo("Mini pack ready", f"Created a review-ready mini pack in:\n{target}", parent=self)
        except Exception as exc: messagebox.showwarning("Mini pack needs attention", str(exc), parent=self)

    def create_marketing(self) -> None:
        book = self._book_for_selected_opportunity()
        if not book: messagebox.showinfo("Choose a recommended book", "Choose a book in What should I make? first.", parent=self); return
        try: target = self.engine.generate_marketing_kit(book["book_id"]); self.refresh(); messagebox.showinfo("Marketing kit ready", f"Created local marketing assets in:\n{target}", parent=self)
        except Exception as exc: messagebox.showwarning("Marketing kit needs attention", str(exc), parent=self)

    def create_etsy_merchandising(self) -> None:
        book = self._book_for_selected_opportunity()
        if not book: messagebox.showinfo("Choose a recommended book", "Choose a completed book in What should I make? first.", parent=self); return
        self.next_text.set("Creating Etsy listing images from the real approved cover and completed puzzle pages…")
        def work():
            try:
                target = self.service.write_etsy_merchandising_assets(book["book_id"])
                self.after(0, lambda: messagebox.showinfo("Etsy images ready", f"Created ten real-product listing images in:\n{target}", parent=self))
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda value=message: messagebox.showwarning("Etsy images need attention", value, parent=self))
            finally:
                self.after(0, self.refresh)
        __import__('threading').Thread(target=work, daemon=True).start()

    def improve_listing(self) -> None:
        book = self._book_for_selected_opportunity()
        if not book: messagebox.showinfo("Choose a recommended book", "Choose a book in What should I make? first.", parent=self); return
        self.next_text.set("Generating optional AI-assisted Payhip listing copy…")
        def work():
            record=self.service.ai_listing(book["book_id"],"payhip")
            content=record.get("content",{}); lines=["AI-ASSISTED LISTING REVIEW", "="*42, f"Provider: {record.get('provider')}", f"Validation: {record.get('validation')}", "", "SUBTITLE", str(content.get('subtitle') or ''), "", "DESCRIPTION", str(content.get('description') or ''), "", "TAGS — ENTER ONE AT A TIME", *[f"• {item}" for item in content.get('tags',[])], "", "This is a review draft. It does not overwrite your saved listing or user-edited copy."]
            self.after(0,lambda:self.parent_manager._show_report("AI listing review","\n".join(lines)))
            self.after(0,self.refresh)
        __import__('threading').Thread(target=work,daemon=True).start()

    def create_bundle(self) -> None:
        selected = self.bundle_tree.selection(); candidate = self.bundles.get(selected[0]) if selected else None
        if not candidate: messagebox.showinfo("Choose a bundle", "Choose a compatible bundle in What else can I sell? first.", parent=self); return
        try: target = self.engine.create_bundle(candidate); self.refresh(); messagebox.showinfo("Bundle ready", f"Created a local, customer-download bundle in:\n{target}", parent=self)
        except Exception as exc: messagebox.showwarning("Bundle needs attention", str(exc), parent=self)


class MarketplaceConnectionsDialog(tk.Toplevel):
    """One calm place to connect, test, or forget marketplace credentials.

    Secrets are stored ONLY in the Windows Credential Manager (never in files,
    never in this catalog database).  The dialog reports what it knows without
    ever displaying a secret value.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Marketplace connections"); fit_dialog_to_screen(self, 820, 650, 680, 500)
        self.configure(background="#1f1f1f"); self.transient(parent)
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1); root.rowconfigure(3, weight=1)
        ttk.Label(root, text="Marketplace connections", style="Publish.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            root,
            text=("Connect your Etsy shop so the app can create DRAFT listings for you — it never publishes, "
                  "prices, or deletes anything. Credentials are kept in Windows Credential Manager on this "
                  "computer. Etsy can create drafts. Lulu credentials are saved here for a future official API connection; "
                  "other channels keep using their own seller portals and your manual uploads."),
            style="Publish.Subtitle.TLabel", wraplength=760).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self.status_box = tk.Text(root, height=15, wrap="word", state="disabled", background="#292929",
                                  foreground="#d9f5ee", relief="flat", padx=10, pady=10)
        self.status_box.grid(row=2, column=0, sticky="ew")
        self.detail_box = tk.Text(root, height=8, wrap="word", state="disabled", background="#292929",
                                  foreground="#b7b7b7", relief="flat", padx=10, pady=10)
        self.detail_box.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        actions = ttk.Frame(root, style="Publish.TFrame"); actions.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        actions.columnconfigure(0, weight=1); actions.columnconfigure(1, weight=1); actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="Test Etsy connection", command=self.test_etsy, style="Publish.Action.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(actions, text="Connect / reconnect Etsy…", command=self.connect_etsy, style="Publish.Primary.TButton").grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Forget Etsy", command=self.forget_etsy, style="Publish.Action.TButton").grid(row=0, column=2, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(actions, text="Check Lulu setup", command=self.test_lulu, style="Publish.Action.TButton").grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(actions, text="Configure Lulu…", command=self.connect_lulu, style="Publish.Primary.TButton").grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Forget Lulu", command=self.forget_lulu, style="Publish.Action.TButton").grid(row=1, column=2, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(actions, text="Configure cover generator…", command=self.connect_cloudflare, style="Publish.Primary.TButton").grid(row=2, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Forget cover generator", command=self.forget_cloudflare, style="Publish.Action.TButton").grid(row=2, column=2, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(actions, text="Configure Gemini copy…", command=self.connect_gemini, style="Publish.Primary.TButton").grid(row=3, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Forget Gemini copy", command=self.forget_gemini, style="Publish.Action.TButton").grid(row=3, column=2, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(actions, text="Close", command=self.destroy, style="Publish.Action.TButton").grid(row=4, column=2, sticky="e", pady=(8, 0))
        self.refresh_status()

    # -- status rendering -------------------------------------------------------

    def refresh_status(self) -> None:
        try:
            from integrations.etsy.session import load_credentials

            creds = load_credentials()
            lines = [
                "Etsy",
                f"  App keystring : {'stored' if creds.api_keystring else 'missing'}",
                f"  Shared secret : {'stored' if creds.shared_secret else 'not stored (optional)'}",
                f"  Access token  : {'stored' if creds.access_token else 'missing'}",
                f"  Refresh token : {'stored' if creds.refresh_token else 'missing'}",
                "",
            ]
        except Exception as exc:  # storage problems must never crash the Hub
            lines = [f"Etsy — could not read stored credentials safely ({exc}).", ""]
        try:
            from integrations.lulu.session import load_credentials

            lulu = load_credentials()
            lines.extend([
                "Lulu",
                f"  Client key    : {'stored' if lulu.client_key else 'missing'}",
                f"  Client secret : {'stored' if lulu.client_secret else 'missing'}",
                f"  Environment   : {lulu.environment}",
                "  This screen only saves your credentials securely; it does not contact Lulu or place orders.",
                "",
            ])
        except Exception as exc:
            lines.extend([f"Lulu — could not read stored credentials safely ({exc}).", ""])
        try:
            from background_generation.providers import CloudflareCredentials
            cloudflare = CloudflareCredentials.load()
            lines.extend([
                "Cover background generator (Cloudflare Workers AI)",
                f"  Account ID    : {'stored' if cloudflare else 'missing'}",
                f"  API token     : {'stored' if cloudflare else 'missing'}",
                f"  Model         : {cloudflare.model if cloudflare else 'default will be used when connected'}",
                "  This only creates queued original cover-background candidates; it never contacts Cloudflare until you request generation.",
                "",
            ])
        except Exception as exc:
            lines.extend([f"Cover background generator — could not read setup safely ({exc}).", ""])
        try:
            from .listing_intelligence import GeminiCredentials
            gemini = GeminiCredentials.load()
            lines.extend(["Gemini listing assistance", f"  API key       : {'stored' if gemini else 'missing'}", f"  Model         : {gemini.model if gemini else 'local copy remains active'}", "  Gemini is tried first for AI listing drafts when configured; verified facts stay in control and local copy takes over safely if needed.", ""])
        except Exception as exc:
            lines.extend([f"Gemini listing assistance — could not read setup safely ({exc}).", ""])
        lines.append("Amazon KDP / IngramSpark / BookVault / Barnes & Noble")
        lines.append("  No API connections yet — upload through each official seller portal as usual.")
        self.status_box.configure(state="normal"); self.status_box.delete("1.0", "end")
        self.status_box.insert("end", "\n".join(lines))
        self.status_box.configure(state="disabled")

    def _set_detail(self, text: str) -> None:
        self.detail_box.configure(state="normal"); self.detail_box.delete("1.0", "end")
        self.detail_box.insert("end", text); self.detail_box.configure(state="disabled")

    # -- actions -----------------------------------------------------------------

    def test_etsy(self) -> None:
        from integrations.etsy.connection import EtsyIntegration

        integration = EtsyIntegration(credential_provider=_StoredEtsyCredentialProvider())
        self._set_detail("Testing the Etsy connection…")
        def runner():
            report = integration.test_connection()
            self.after(0, lambda: self._set_detail(report.message))
        threading.Thread(target=runner, daemon=True).start()

    def connect_etsy(self) -> None:
        EtsyConnectDialog(self, on_done=self.refresh_status)

    def forget_etsy(self) -> None:
        from integrations.etsy.session import forget_credentials

        if not messagebox.askyesno(
                "Forget Etsy connection",
                "Remove the stored Etsy credentials from Windows Credential Manager on this computer?\n\n"
                "Prepared files and catalog records stay exactly as they are.",
                parent=self):
            return
        forgotten = forget_credentials()
        self.refresh_status()
        self._set_detail("Stored Etsy credentials removed." if forgotten
                         else "There were no stored Etsy credentials to remove.")

    def test_lulu(self) -> None:
        from integrations.lulu.session import setup_report

        self._set_detail(setup_report())

    def connect_lulu(self) -> None:
        LuluConnectDialog(self, on_done=self.refresh_status)

    def forget_lulu(self) -> None:
        from integrations.lulu.session import forget_credentials

        if not messagebox.askyesno(
                "Forget Lulu connection",
                "Remove the stored Lulu client key and client secret from Windows Credential Manager on this computer?\n\n"
                "Prepared files and catalog records stay exactly as they are.",
                parent=self):
            return
        forgotten = forget_credentials()
        self.refresh_status()
        self._set_detail("Stored Lulu credentials removed." if forgotten
                         else "There were no stored Lulu credentials to remove.")

    def connect_cloudflare(self) -> None:
        CloudflareCoverGeneratorDialog(self, on_done=self.refresh_status)

    def forget_cloudflare(self) -> None:
        from integrations.wincred import delete_secret
        if not messagebox.askyesno("Forget cover generator", "Remove the saved Cloudflare cover-generator credentials from Windows Credential Manager?\n\nExisting approved background art and book files will stay exactly as they are.", parent=self):
            return
        forgotten = delete_secret("CloudflareWorkersAI")
        self.refresh_status()
        self._set_detail("Saved cover-generator credentials removed." if forgotten else "There were no stored cover-generator credentials to remove.")

    def connect_gemini(self) -> None:
        GeminiListingDialog(self, on_done=self.refresh_status)

    def forget_gemini(self) -> None:
        from integrations.wincred import delete_secret
        if not messagebox.askyesno("Forget Gemini", "Remove the saved Gemini API key from Windows Credential Manager? Local listing generation will continue to work.", parent=self): return
        delete_secret("GeminiListingAI"); self.refresh_status(); self._set_detail("Saved Gemini credentials removed.")


class GeminiListingDialog(tk.Toplevel):
    def __init__(self, parent, on_done=None) -> None:
        super().__init__(parent); self.on_done=on_done; self.title("Configure Gemini listing assistance"); self.geometry("680x400"); self.configure(background="#1f1f1f"); self.transient(parent)
        root=ttk.Frame(self,padding=22,style="Publish.TFrame"); root.pack(fill="both",expand=True); root.columnconfigure(1,weight=1)
        ttk.Label(root,text="Gemini listing assistance",style="Publish.Title.TLabel").grid(row=0,column=0,columnspan=2,sticky="w")
        ttk.Label(root,text="Gemini is used first for an AI-assisted listing draft when configured. Your API key is saved in Windows Credential Manager and is never shown, written into book files, or logged. Verified product facts stay in control, and the local listing generator takes over safely if Gemini cannot be used.",style="Publish.Subtitle.TLabel",wraplength=620).grid(row=1,column=0,columnspan=2,sticky="w",pady=(5,14))
        self.key=tk.StringVar(); self.model=tk.StringVar(value="gemini-3.5-flash-lite")
        ttk.Label(root,text="Gemini API key",style="Publish.TLabel").grid(row=2,column=0,sticky="w",pady=6); ttk.Entry(root,textvariable=self.key,show="•",style="Publish.TEntry").grid(row=2,column=1,sticky="ew",pady=6)
        ttk.Label(root,text="Model",style="Publish.TLabel").grid(row=3,column=0,sticky="w",pady=6); ttk.Entry(root,textvariable=self.model,style="Publish.TEntry").grid(row=3,column=1,sticky="ew",pady=6)
        buttons=ttk.Frame(root,style="Publish.TFrame"); buttons.grid(row=4,column=0,columnspan=2,sticky="ew",pady=(18,0)); ttk.Button(buttons,text="Cancel",command=self.destroy,style="Publish.Action.TButton").pack(side="right"); ttk.Button(buttons,text="Save securely",command=self.save,style="Publish.Primary.TButton").pack(side="right",padx=(0,7)); ttk.Button(buttons,text="Test connection",command=self.test,style="Publish.Action.TButton").pack(side="left")
    def save(self):
        from integrations.wincred import store_secret
        if not self.key.get().strip(): messagebox.showwarning("Check Gemini key","Enter a Gemini API key.",parent=self); return
        try: store_secret("GeminiListingAI",{"api_key":self.key.get().strip(),"model":self.model.get().strip() or "gemini-3.5-flash-lite"})
        except Exception as exc: messagebox.showwarning("Could not save Gemini key",str(exc),parent=self); return
        if self.on_done: self.on_done()
        messagebox.showinfo("Gemini saved","Gemini listing assistance is saved securely. It remains optional.",parent=self); self.destroy()
    def test(self):
        from .listing_intelligence import GeminiCredentials, GeminiListingProvider, ListingProviderError
        creds=GeminiCredentials(api_key=self.key.get().strip(),model=self.model.get().strip() or "gemini-3.5-flash-lite")
        if not creds.api_key: messagebox.showwarning("Check Gemini key","Enter a Gemini API key before testing.",parent=self); return
        try:
            GeminiListingProvider(creds,timeout=20).generate_listing({"title":"Connection check","puzzle_count":1,"format":"downloadable PDF","platform":"payhip","digital":True,"solutions_included":True})
            messagebox.showinfo("Gemini connected","Gemini returned a small structured response successfully.",parent=self)
        except ListingProviderError as exc: messagebox.showwarning("Gemini connection",str(exc),parent=self)


class CloudflareCoverGeneratorDialog(tk.Toplevel):
    """Local credential editor for the optional approved-background generator."""

    def __init__(self, parent, on_done=None) -> None:
        super().__init__(parent); self.on_done = on_done
        self.title("Configure cover background generator"); self.geometry("700x445"); self.minsize(610, 400)
        self.configure(background="#1f1f1f"); self.transient(parent)
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1)
        ttk.Label(root, text="Configure cover background generator", style="Publish.Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(root, text=("Optional: connect Cloudflare Workers AI to create original cover-background candidates. Your Account ID and API token are saved only in Windows Credential Manager on this computer. The app never displays, writes, or logs the token. Generation does not begin just by saving this screen."), style="Publish.Subtitle.TLabel", wraplength=650, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 14))
        self.account_id = tk.StringVar(); self.api_token = tk.StringVar(); self.model = tk.StringVar(value="@cf/black-forest-labs/flux-1-schnell")
        for row, label, variable, masked in ((2, "Cloudflare Account ID", self.account_id, False), (3, "Workers AI API token", self.api_token, True), (4, "Model", self.model, False)):
            ttk.Label(root, text=label, style="Publish.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(root, textvariable=variable, show="•" if masked else "", style="Publish.TEntry").grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="Use an API token restricted to Workers AI. Leave the model at the recommended default unless you intentionally change providers.", style="Publish.Status.TLabel", wraplength=650).grid(row=5, column=0, columnspan=2, sticky="w", pady=(9, 0))
        buttons = ttk.Frame(root, style="Publish.TFrame"); buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy, style="Publish.Action.TButton").pack(side="right")
        ttk.Button(buttons, text="Save securely", command=self.save, style="Publish.Primary.TButton").pack(side="right", padx=(0, 7))

    def save(self) -> None:
        from integrations.wincred import store_secret
        account_id, api_token, model = self.account_id.get().strip(), self.api_token.get().strip(), self.model.get().strip()
        if not account_id or not api_token:
            messagebox.showwarning("Check generator details", "Enter both the Cloudflare Account ID and the Workers AI API token.", parent=self); return
        try:
            store_secret("CloudflareWorkersAI", {"account_id": account_id, "api_token": api_token, "model": model})
        except Exception as exc:
            messagebox.showwarning("Could not save generator details", str(exc), parent=self); return
        if self.on_done: self.on_done()
        messagebox.showinfo("Cover generator saved", "Your Cloudflare credentials were saved securely. Background generation remains off until you request it.", parent=self)
        self.destroy()


class LuluConnectDialog(tk.Toplevel):
    """Simple local-only Lulu credential editor backed by Windows Credential Manager."""

    def __init__(self, parent, on_done=None) -> None:
        super().__init__(parent)
        self.on_done = on_done
        self.title("Configure Lulu"); self.geometry("660x430"); self.minsize(580, 390)
        self.configure(background="#1f1f1f"); self.transient(parent)
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        ttk.Label(root, text="Configure Lulu", style="Publish.Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            root,
            text=("Paste the Client Key and Client Secret from your Lulu developer app. They are saved only in "
                  "Windows Credential Manager on this computer and are never shown again, written into a book, "
                  "or added to logs. Start with Sandbox until you are ready for live production."),
            style="Publish.Subtitle.TLabel", wraplength=610, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 14))
        self.environment = tk.StringVar(value="Sandbox")
        self.client_key = tk.StringVar()
        self.client_secret = tk.StringVar()
        ttk.Label(root, text="Environment", style="Publish.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Combobox(root, textvariable=self.environment, values=("Sandbox", "Production"), state="readonly", style="Publish.TCombobox").grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="Client Key", style="Publish.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.client_key, style="Publish.TEntry").grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="Client Secret", style="Publish.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.client_secret, show="•", style="Publish.TEntry").grid(row=4, column=1, sticky="ew", pady=6)
        self.message = tk.StringVar(value="Saved credentials are intentionally not displayed here.")
        ttk.Label(root, textvariable=self.message, style="Publish.Status.TLabel", wraplength=610).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))
        buttons = ttk.Frame(root, style="Publish.TFrame"); buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy, style="Publish.Action.TButton").pack(side="right")
        ttk.Button(buttons, text="Save securely", command=self.save, style="Publish.Primary.TButton").pack(side="right", padx=(0, 7))

    def save(self) -> None:
        from integrations.errors import IntegrationError
        from integrations.lulu.session import LuluCredentials, save_credentials

        try:
            save_credentials(LuluCredentials(
                client_key=self.client_key.get(),
                client_secret=self.client_secret.get(),
                environment=self.environment.get(),
            ))
        except IntegrationError as exc:
            messagebox.showwarning("Check Lulu details", getattr(exc, "message", str(exc)), parent=self)
            return
        except Exception as exc:
            messagebox.showwarning("Could not save Lulu details", str(exc), parent=self)
            return
        if self.on_done:
            self.on_done()
        messagebox.showinfo("Lulu saved", "Your Lulu credentials were saved securely in Windows Credential Manager.", parent=self)
        self.destroy()


class EtsyConnectDialog(tk.Toplevel):
    """Guided OAuth connection: browser approval, paste the redirect back.

    Etsy requires an HTTPS callback that exactly matches the app registration,
    so desktop flow is: open the approval page, approve, then paste the URL
    the browser landed on.  Only ``shops_r listings_r listings_w`` scopes are
    requested — never the destructive ``listings_d``.
    """

    def __init__(self, parent, on_done=None) -> None:
        super().__init__(parent)
        self.parent_dialog = parent; self.on_done = on_done
        self.pkce = None; self.oauth_state = ""; self.keystring_value = ""
        self.title("Connect Etsy"); fit_dialog_to_screen(self, 720, 600, 600, 500)
        self.configure(background="#1f1f1f"); self.transient(parent)
        root = ttk.Frame(self, padding=22, style="Publish.TFrame"); root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1); root.rowconfigure(7, weight=1)
        ttk.Label(root, text="Connect your Etsy shop", style="Publish.Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            root,
            text=("Step 1 · Open etsy.com/developers/your-apps and copy your app's keystring and shared secret.\n"
                  "Step 2 · Make sure one callback URL is registered there (must start with https://).\n"
                  "Step 3 · Fill the three boxes below, open the approval page, then paste the address your "
                  "browser lands on after you approve."),
            style="Publish.Subtitle.TLabel", wraplength=660, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        rows = (("App keystring", "keystring"), ("Shared secret", "shared_secret"), ("Callback URL", "callback"))
        self.vars = {}
        for row_index, (label, name) in enumerate(rows, start=2):
            ttk.Label(root, text=label, style="Publish.TLabel").grid(row=row_index, column=0, sticky="w", pady=5)
            var = tk.StringVar(value="https://" if name == "callback" else "")
            entry = ttk.Entry(root, textvariable=var, show="•" if name == "shared_secret" else "", style="Publish.TEntry")
            entry.grid(row=row_index, column=1, sticky="ew", pady=5)
            self.vars[name] = var
        ttk.Label(root, text=self._scope_text(), style="Publish.Status.TLabel", wraplength=650).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        self.open_button = ttk.Button(root, text="Open Etsy approval page", command=self.open_approval, style="Publish.Primary.TButton")
        self.open_button.grid(row=6, column=0, columnspan=2, sticky="w")
        self.paste_var = tk.StringVar(value="")
        ttk.Label(root, text="Pasted redirect URL", style="Publish.TLabel").grid(row=7, column=0, sticky="nw", pady=(12, 5))
        paste_entry = ttk.Entry(root, textvariable=self.paste_var, style="Publish.TEntry")
        paste_entry.grid(row=7, column=1, sticky="ew", pady=(12, 0))
        self.finish_button = ttk.Button(root, text="Finish connecting", command=self.finish_connect, style="Publish.Primary.TButton", state="disabled")
        self.finish_button.grid(row=8, column=1, sticky="e", pady=(10, 0))
        self.result_box = tk.Text(root, height=7, wrap="word", state="disabled", background="#292929",
                                  foreground="#d9f5ee", relief="flat", padx=10, pady=10)
        self.result_box.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(12, 0))

    @staticmethod
    def _scope_text() -> str:
        from integrations.etsy.auth import DRAFT_SCOPES

        return (
            "Permissions requested: " + ", ".join(DRAFT_SCOPES) + ".\n"
            "This app can create drafts and attach your PDF/image; it can never publish, edit live listings, or delete anything."
        )

    def _set_result(self, text: str) -> None:
        self.result_box.configure(state="normal"); self.result_box.delete("1.0", "end")
        self.result_box.insert("end", text); self.result_box.configure(state="disabled")

    def open_approval(self) -> None:
        import secrets

        from integrations.etsy.auth import (
            DRAFT_SCOPES,
            build_authorization_url,
            generate_pkce_pair,
        )
        from integrations.errors import IntegrationError

        keystring = self.vars["keystring"].get().strip()
        callback = self.vars["callback"].get().strip()
        if not keystring:
            messagebox.showwarning("Add the keystring", "Paste your app's keystring from etsy.com/developers first.", parent=self)
            return
        if not callback.lower().startswith("https://"):
            messagebox.showwarning("HTTPS callback needed", "Etsy only accepts callback URLs that start with https:// and match your app registration exactly.", parent=self)
            return
        try:
            self.pkce = generate_pkce_pair()
            self.oauth_state = secrets.token_urlsafe(16)
            url = build_authorization_url(client_id=keystring, redirect_uri=callback,
                                          code_challenge=self.pkce.challenge,
                                          state=self.oauth_state, scopes=DRAFT_SCOPES)
        except IntegrationError as exc:
            messagebox.showwarning("Check details", exc.message, parent=self)
            return
        self.keystring_value = keystring
        webbrowser.open(url)
        self.finish_button.configure(state="normal")
        self._set_result("The Etsy approval page opened in your browser.\n"
                         "Approve access, then copy the full address your browser lands on and paste it here.")

    def finish_connect(self) -> None:
        from integrations.etsy.auth import extract_state_and_code
        from integrations.errors import IntegrationError
        from integrations.etsy.session import (
            EtsyCredentials,
            exchange_authorization_code,
            save_credentials,
        )

        pasted = self.paste_var.get().strip()
        if not pasted or self.pkce is None:
            messagebox.showwarning("Not ready", "Open the approval page and approve access first, then paste the redirect URL.", parent=self)
            return
        state, code, error = extract_state_and_code(pasted)
        if error:
            self._set_result(f"Etsy reported: {error}. Nothing was saved; you can close this window or start again.")
            return
        if not code:
            messagebox.showwarning("That link looks incomplete", "Paste the full address from the browser address bar after approving (it contains ?code=…).", parent=self)
            return
        if not state or state != self.oauth_state:
            messagebox.showwarning("Start again", "This approval does not match the request that was opened. For safety, nothing was saved — press “Open Etsy approval page” and try once more.", parent=self)
            return
        shared_secret = self.vars["shared_secret"].get().strip()
        callback = self.vars["callback"].get().strip()
        self.finish_button.configure(state="disabled")
        self._set_result("Exchanging the approval code with Etsy…")

        def work():
            tokens = exchange_authorization_code(
                client_id=self.keystring_value,
                authorization_code=code,
                code_verifier=self.pkce.verifier,
                redirect_uri=callback,
            )
            save_credentials(EtsyCredentials(
                api_keystring=self.keystring_value,
                shared_secret=shared_secret,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
            ))
            return tokens

        def runner():
            outcome = {}

            def execute():
                try:
                    outcome["tokens"] = work()
                except Exception as exc:  # classified or not, the UI must show it safely
                    outcome["error"] = exc
                self.after(0, done)

            threading.Thread(target=execute, daemon=True).start()

        def done():
            error = outcome.get("error")
            if error is not None:
                self.finish_button.configure(state="normal")
                if isinstance(error, IntegrationError):
                    self._set_result(f"Etsy refused the exchange ({error.message}). Nothing was changed.")
                else:
                    self._set_result(f"Unexpected problem: {error} Nothing was changed.")
                return
            tokens = outcome["tokens"]
            scope_note = f" Approved permissions: {tokens.scope}." if tokens.scope else ""
            self._set_result("Etsy connected successfully." + scope_note +
                             "\nDrafts can now be created from the Selected Book tab — publishing stays entirely in your hands.")
            if self.on_done:
                self.on_done()

        runner()
