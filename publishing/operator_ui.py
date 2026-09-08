"""Compact Tkinter surfaces for the Phase 5 operator workflow."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from word_intelligence.book_planning import BookPlanner, PlanRequest
from word_intelligence.capacity import REVIEW_LEGACY, REVIEW_STRICT
from word_intelligence.qualification import write_review_batch

from .operator_status import Feasibility, OperatorStatusService
from .puzzle_types import REGISTRY


def fit_dialog_to_screen(window: tk.Toplevel, width: int, height: int, min_width: int, min_height: int) -> None:
    """Size a dialog to the usable screen; its page scrollbar handles overflow."""
    usable_width = max(760, window.winfo_screenwidth() - 70)
    usable_height = max(500, window.winfo_screenheight() - 110)
    actual_width = min(width, usable_width)
    actual_height = min(height, usable_height)
    window.geometry(f"{actual_width}x{actual_height}")
    window.minsize(min(min_width, actual_width), min(min_height, actual_height))


def scrollable_dialog_page(dialog: tk.Toplevel, *, padding: int = 18) -> ttk.Frame:
    """Create a page-level scrollbar for a form that can outgrow its dialog."""
    shell = ttk.Frame(dialog)
    shell.pack(fill="both", expand=True)
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(0, weight=1)
    canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0, background="#101418")
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set, yscrollincrement=18)
    page = ttk.Frame(canvas, padding=padding)
    page_window = canvas.create_window((0, 0), window=page, anchor="nw")

    def refresh(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def fit(event) -> None:
        canvas.itemconfigure(page_window, width=event.width)
        refresh()

    def wheel(event):
        if isinstance(event.widget, (tk.Text, ttk.Treeview)):
            return None
        steps = int(event.delta / 120) if event.delta else 0
        if steps:
            canvas.yview_scroll(-steps, "units")
            return "break"
        return None

    page.bind("<Configure>", refresh)
    canvas.bind("<Configure>", fit)

    def attach() -> None:
        def bind_widget(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", wheel, add="+")
            for child in widget.winfo_children():
                bind_widget(child)
        bind_widget(page)
    dialog.after_idle(attach)
    dialog._scrollable_page = (canvas, scrollbar, page)  # type: ignore[attr-defined]
    return page


class ContentReviewDialog(tk.Toplevel):
    """Focused individual-candidate review; intentionally has no approve-all."""
    def __init__(self, parent, service: OperatorStatusService, batch_path: Path) -> None:
        super().__init__(parent); self.service, self.batch_path = service, batch_path
        self.title("Content review"); fit_dialog_to_screen(self, 920, 650, 680, 460); self.configure(background="#101418"); self.transient(parent)
        data = json.loads(batch_path.read_text(encoding="utf-8-sig")); self.topic = str(data.get("topic_id") or "")
        self.rows = {str(row.get("content_id") or ""): row for row in data.get("records") or [] if isinstance(row, dict)}
        root = ttk.Frame(self, padding=18); root.pack(fill="both", expand=True); root.columnconfigure(0, weight=1); root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Review selected content", font=("Segoe UI Semibold", 18)).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Choose individual candidates after reading their topic, source, and eligibility notes. Nothing here edits the source word bank.", wraplength=820).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self.checked: set[str] = set()
        columns = ("select", "display", "tier", "eligible", "source", "notes")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", selectmode="extended")
        for key, label, width in (("select", "Add", 45), ("display", "Candidate", 190), ("tier", "Review tier", 120), ("eligible", "Format eligible", 105), ("source", "Source", 155), ("notes", "Why", 290)):
            self.tree.heading(key, text=label); self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(root, orient="vertical", command=self.tree.yview); scroll.grid(row=2, column=1, sticky="ns"); self.tree.configure(yscrollcommand=scroll.set)
        for content_id, row in self.rows.items():
            source = row.get("source") if isinstance(row.get("source"), dict) else {}
            notes = ", ".join(row.get("reasons") or []) or "Qualified for human review"
            self.tree.insert("", "end", iid=content_id, values=("☐", row.get("display") or "", row.get("candidate_tier") or "Review Carefully", "Yes" if row.get("format_eligible") else "No", source.get("source_name") or source.get("source_id") or "", notes))
        self.tree.bind("<Button-1>", self._toggle_check, add=True)
        actions = ttk.Frame(root); actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(actions, text="Approve selected", command=lambda: self._save("approved")).pack(side="left")
        ttk.Button(actions, text="Reject selected", command=lambda: self._save("rejected")).pack(side="left", padx=7)
        ttk.Button(actions, text="Skip for now", command=lambda: self._save("needs_review")).pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        self.status = tk.StringVar(value="Select one or more candidates. There is intentionally no Approve All button.")
        ttk.Label(root, textvariable=self.status, wraplength=820).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.bind("a", lambda _event: self._save("approved"))
        self.bind("r", lambda _event: self._save("rejected"))
        self.bind("s", lambda _event: self._save("needs_review"))

    def _save(self, decision: str) -> None:
        selected = tuple(self.checked) or self.tree.selection()
        if not selected:
            messagebox.showinfo("Choose candidates", "Select the individual candidates you reviewed first.", parent=self); return
        count = self.service.record_review_decisions(self.topic, [(item, decision) for item in selected])
        self.status.set(f"Recorded {count} explicit human {decision} decision(s). Recheck availability to see the updated capacity.")

    def _toggle_check(self, event) -> None:
        """A visible checkbox column keeps review action explicit for new users."""
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if item in self.checked:
            self.checked.remove(item); mark = "☐"
        else:
            self.checked.add(item); mark = "☑"
        values = list(self.tree.item(item, "values")); values[0] = mark; self.tree.item(item, values=values)


class OperatorWorkflowDialog(tk.Toplevel):
    """A small front door for feasibility, planning, and attention.

    The dialog deliberately does not generate a book.  It shows the safe
    path first and links the user back to the existing generators afterwards.
    """
    def __init__(self, parent, project: Path | str, database=None, *, initial_topic: str = "") -> None:
        super().__init__(parent)
        self.project, self.database = Path(project), database
        self.service = OperatorStatusService(self.project, database)
        self.title("Book Readiness")
        fit_dialog_to_screen(self, 820, 720, 650, 500); self.configure(background="#101418")
        self.transient(parent)
        self.topic = tk.StringVar(value=initial_topic)
        self.puzzle_type = tk.StringVar(value="word_search")
        self.puzzle_count = tk.StringVar(value="48")
        self.items_per_puzzle = tk.StringVar(value="12")
        self.difficulty = tk.StringVar(value="standard")
        self.large_print = tk.BooleanVar(value=True)
        self.review_mode = tk.StringVar(value="Verified Content")
        self.last_request: PlanRequest | None = None
        self.last_feasibility: Feasibility | None = None
        self.last_campaign = None
        self._build()

    def _build(self) -> None:
        root = scrollable_dialog_page(self, padding=20); root.columnconfigure(0, weight=1); root.rowconfigure(4, weight=1)
        ttk.Label(root, text="Book readiness", font=("Segoe UI Semibold", 20)).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Check the exact book before creating it. This screen never lowers the puzzle count, changes the topic, or uses unreviewed content without your explicit choice.", wraplength=730).grid(row=1, column=0, sticky="w", pady=(4, 12))
        form = ttk.Labelframe(root, text="What can I make now?", padding=12); form.grid(row=2, column=0, sticky="new"); form.columnconfigure(1, weight=1); form.columnconfigure(3, weight=1)
        self._field(form, 0, "Topic", self.topic, column=0, width=30)
        self._combo(form, 0, "Puzzle type", self.puzzle_type, REGISTRY.ids_for_readiness_ui(), column=2)
        self._field(form, 1, "Puzzles", self.puzzle_count, column=0, width=10)
        self._field(form, 1, "Words/items per puzzle", self.items_per_puzzle, column=2, width=10)
        self._combo(form, 2, "Difficulty", self.difficulty, ("easy", "standard", "challenging"), column=0)
        self._combo(form, 2, "Content mode", self.review_mode, ("Verified Content", "Legacy-Compatible Content"), column=2)
        ttk.Checkbutton(form, text="Large print", variable=self.large_print).grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.mode_note = ttk.Label(form, text="Verified Content is the recommended default. It uses only editorially approved material.", wraplength=640)
        self.mode_note.grid(row=3, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.review_mode.trace_add("write", lambda *_: self._update_mode_note())
        actions = ttk.Frame(root); actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.check_button = ttk.Button(actions, text="Check availability", command=self.check_availability)
        self.check_button.pack(side="left")
        self.plan_button = ttk.Button(actions, text="Build Safe Plan", command=self.build_plan, state="disabled")
        self.plan_button.pack(side="left", padx=7)
        self.review_button = ttk.Button(actions, text="Create review batch", command=self.create_review_batch, state="disabled")
        self.review_button.pack(side="left")
        self.expand_button = ttk.Button(actions, text="Expand content", command=self.create_campaign, state="disabled")
        self.expand_button.pack(side="left", padx=7)
        self.generate_button = ttk.Button(actions, text="Generate new candidates", command=self.generate_candidates, state="disabled")
        self.generate_button.pack(side="left")
        ttk.Button(actions, text="What needs attention?", command=self.show_attention).pack(side="right")
        result = ttk.Labelframe(root, text="Result", padding=12); result.grid(row=4, column=0, sticky="nsew", pady=(12, 0)); result.columnconfigure(0, weight=1); result.rowconfigure(0, weight=1)
        self.output = tk.Text(result, wrap="word", height=16, background="#171d23", foreground="#e8f1ee", relief="flat", padx=12, pady=10, state="disabled", font=("Segoe UI", 10))
        self.output.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(result, orient="vertical", command=self.output.yview); scrollbar.grid(row=0, column=1, sticky="ns"); self.output.configure(yscrollcommand=scrollbar.set)
        self.status = tk.StringVar(value="Choose a topic and check its availability.")
        ttk.Label(root, textvariable=self.status, wraplength=730).grid(row=5, column=0, sticky="ew", pady=(10, 0))

    def _field(self, parent, row, label, variable, *, column, width=18):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable, width=width).grid(row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=4)

    def _combo(self, parent, row, label, variable, values, *, column):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").grid(row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=4)

    def _update_mode_note(self):
        if self.review_mode.get() == "Legacy-Compatible Content":
            self.mode_note.configure(text="Legacy-Compatible Content may use older unreviewed material. It is never selected automatically and will require your acknowledgement before local release readiness.")
        else:
            self.mode_note.configure(text="Verified Content is the recommended default. It uses only editorially approved material.")

    def _request(self) -> PlanRequest:
        try:
            count, items = int(self.puzzle_count.get()), int(self.items_per_puzzle.get())
        except ValueError as exc:
            raise ValueError("Puzzle count and words/items per puzzle must be whole numbers.") from exc
        policy = REVIEW_STRICT if self.review_mode.get() == "Verified Content" else REVIEW_LEGACY
        return PlanRequest(self.topic.get().strip(), self.puzzle_type.get(), count, items, difficulty=self.difficulty.get(), large_print=self.large_print.get(), review_policy=policy)

    def _write(self, lines: list[str]) -> None:
        self.output.configure(state="normal"); self.output.delete("1.0", "end"); self.output.insert("end", "\n".join(lines)); self.output.configure(state="disabled")

    def check_availability(self) -> None:
        try:
            request = self._request()
            if not request.topic_id:
                raise ValueError("Enter the topic you want the book to cover.")
        except Exception as exc:
            self.status.set("The availability check could not run. Your saved content was not changed.")
            messagebox.showerror("Availability check", str(exc), parent=self); return
        # A new title can be connected to existing, genuinely related library
        # groups once; this is saved as a small overlay, never a bank rewrite.
        planner = BookPlanner.from_project(self.project, self.service.approval_path if self.service.approval_path.is_file() else None)
        if not planner.engine.taxonomy.resolve(request.topic_id):
            from word_intelligence.topic_routing import TopicRouter
            router = TopicRouter(self.project, planner.engine.taxonomy); choices = router.suggestions(request.topic_id)
            if choices:
                labels = [planner.engine.taxonomy.topics[item].display_name for item in choices]
                if messagebox.askyesno("Connect this topic", "This is a new topic name. Use these related saved word groups?\n\n• " + "\n• ".join(labels) + "\n\nThe connection is saved for future books and does not change your Master Library.", parent=self):
                    router.save(request.topic_id, choices)
        self.check_button.configure(state="disabled"); self.plan_button.configure(state="disabled"); self.review_button.configure(state="disabled")
        self.status.set("Checking content…")
        def worker():
            try:
                result, error = self.service.feasibility(request), None
            except Exception as exc:  # worker errors are displayed safely on Tk's thread
                result, error = None, str(exc)
            self.after(0, lambda: self._availability_complete(request, result, error))
        threading.Thread(target=worker, daemon=True).start()

    def _availability_complete(self, request: PlanRequest, result: Feasibility | None, error: str | None) -> None:
        self.check_button.configure(state="normal")
        if error or not result:
            self.status.set("The availability check could not run. Your saved content was not changed.")
            messagebox.showerror("Availability check", error or "Unknown availability problem.", parent=self); return
        self.last_request, self.last_feasibility = request, result
        self._write([result.status.label.upper(), result.status.message, "", *result.display_lines()])
        ready = result.status.headline_status == "ready_to_plan"
        self.plan_button.configure(state="normal" if ready else "disabled")
        self.review_button.configure(state="normal" if not ready and request.puzzle_type != "sudoku" else "disabled")
        self.expand_button.configure(state="normal" if not ready and request.puzzle_type != "sudoku" else "disabled")
        self.status.set("Ready to build a safe plan." if ready else "This exact format is blocked until reviewed content is available. See the recommended next step above.")

    def build_plan(self) -> None:
        if not self.last_request:
            self.check_availability()
        if not self.last_request:
            return
        self.plan_button.configure(state="disabled"); self.status.set("Building plan…")
        request = self.last_request
        def worker():
            try:
                outcome, error = self.service.build_safe_plan(request), None
            except Exception as exc:
                outcome, error = None, str(exc)
            self.after(0, lambda: self._plan_complete(outcome, error))
        threading.Thread(target=worker, daemon=True).start()

    def _plan_complete(self, outcome, error: str | None) -> None:
        self.plan_button.configure(state="normal" if self.last_feasibility and self.last_feasibility.status.headline_status == "ready_to_plan" else "disabled")
        if error or not outcome:
            self.status.set("The plan could not be built. Your content was not changed.")
            messagebox.showerror("Build Safe Plan", error or "Unknown planning problem.", parent=self); return
        plan, status, path = outcome
        if not plan or not path:
            self._write([status.label.upper(), status.message, *[f"• {item}" for item in status.details]])
            self.status.set("Plan not created."); return
        lines = ["BOOK PLAN READY", "", f"Plan ID: {plan.book_plan_id}", f"{plan.format.get('puzzle_count')} puzzles · {plan.format.get('items_per_puzzle')} items each", f"Verification: {'Verified Content' if plan.review_policy == REVIEW_STRICT else 'Legacy-Compatible Content'}", f"Seed: {plan.seed}", f"Saved plan: {path}", "", "The plan is current. Use the existing creator to generate the book, then run the Production Check."]
        if plan.warnings: lines += ["", *[f"Note: {item}" for item in plan.warnings]]
        self._write(lines); self.status.set("Book Plan saved. Nothing has been generated yet.")

    def create_review_batch(self) -> None:
        if not self.last_request:
            self.check_availability()
        if not self.last_request:
            return
        try:
            self.service.feasibility(self.last_request)  # validates topic/request with the same source of truth
            planner = BookPlanner.from_project(self.project)
            topic = planner.engine.taxonomy.resolve(self.last_request.topic_id)
            records = planner.engine._topic_records(topic, self.last_request.allow_related_topics) if topic else []
            target = self.project / "reports" / "content_review_batches" / f"{self.last_request.topic_id.casefold().replace(' ', '_')}_{self.last_request.puzzle_type}.json"
            write_review_batch(target, records, topic or self.last_request.topic_id, self.last_request.puzzle_type)
            from word_intelligence.editorial_review import EditorialPriorityEngine
            priority_engine = EditorialPriorityEngine(planner)
            ranked = {row.content_id: row for row in priority_engine.candidates(self.last_request, limit=2000)}
            batch = json.loads(target.read_text(encoding="utf-8"))
            batch["target_format"] = self.last_request.format_id
            batch["priority"] = priority_engine.priority(self.last_request).__dict__
            for row in batch.get("records") or []:
                ranked_row = ranked.get(str(row.get("content_id") or ""))
                if ranked_row:
                    row["candidate_tier"] = ranked_row.tier
                    row["ranking_reasons"] = list(ranked_row.reasons)
                    row["mini_theme"] = ranked_row.mini_theme
            # Generated rows are deliberately review-only. Include them in the
            # same individual-review dialog without changing a source bank.
            from word_intelligence.expansion_campaign import ExpansionCampaignService
            generated = ExpansionCampaignService(planner, self.project).load_candidates()
            known = {str(row.get("content_id") or "") for row in batch.get("records") or []}
            for item in generated:
                if str(item.get("topic_id") or "").casefold() != str(topic or self.last_request.topic_id).casefold():
                    continue
                candidate_id = str(item.get("candidate_id") or "")
                if not candidate_id or candidate_id in known or str(item.get("status") or "") != "generated_unreviewed":
                    continue
                batch.setdefault("records", []).append({"content_id": candidate_id, "display": item.get("display") or "", "format_eligible": True,
                    "candidate_tier": item.get("tier") or "Review Carefully", "reasons": item.get("reasons") or ["Generated candidate — human review required"],
                    "source": {"source_name": item.get("provenance") or "generated"}})
            target.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Create review batch", str(exc), parent=self); return
        self.status.set(f"Review batch created: {target.name}. It changes no source content. Approve or reject only after reviewing individual candidates.")
        self._write(["CONTENT REVIEW BATCH READY", "", f"Saved: {target}", "", "This batch contains individual candidates and evidence. It does not approve anything automatically.", "Opening it lets you record explicit Approve Selected or Reject Selected decisions."])
        ContentReviewDialog(self, self.service, target)

    def create_campaign(self) -> None:
        if not self.last_request:
            self.check_availability()
            return
        try:
            from word_intelligence.expansion_campaign import ExpansionCampaignService
            planner = BookPlanner.from_project(self.project, self.service.approval_path if self.service.approval_path.is_file() else None)
            campaign_service = ExpansionCampaignService(planner, self.project)
            campaign = campaign_service.create(self.last_request)
            path = campaign_service.save(campaign)
            gathered = campaign_service.gather_existing(campaign, self.last_request)
        except Exception as exc:
            messagebox.showerror("Expand content", "The campaign could not be prepared. No source content was changed.\n\n" + str(exc), parent=self); return
        self.last_campaign = campaign
        self.generate_button.configure(state="normal" if self.last_request.puzzle_type == "word_search" else "disabled")
        lines = ["CONTENT EXPANSION CAMPAIGN READY", "", f"Goal: Unlock {campaign.topic_id} — {campaign.target_format['puzzle_count']} × {campaign.target_format['items_per_puzzle']}", f"Strict content available: {campaign.verified_capacity_before}", f"Needed: {campaign.required_capacity}", f"Approvals still needed: {campaign.minimum_deficit}", f"Review pool estimate: {campaign.review_pool_estimate} candidates", f"Screened existing candidates gathered: {len(gathered)}", "", "No external provider was called. You may now choose Generate new candidates for a confirmed Gemini request.", f"Saved: {path}"]
        self._write(lines); self.status.set("Campaign saved. Existing content remains available for review; Gemini generation is optional.")

    def generate_candidates(self) -> None:
        if not self.last_campaign or not self.last_request:
            messagebox.showinfo("Generate new candidates", "Create an expansion campaign first.", parent=self); return
        from word_intelligence.candidate_generation import CandidateGenerationService, GeminiCandidateGenerationProvider, GenerationRequest
        from word_intelligence.expansion_campaign import ExpansionCampaignService
        planner = BookPlanner.from_project(self.project, self.service.approval_path if self.service.approval_path.is_file() else None)
        campaign_service = ExpansionCampaignService(planner, self.project)
        excluded = tuple(str(row.get("normalized") or "") for row in campaign_service.load_candidates())
        provider = GeminiCandidateGenerationProvider(); generator = CandidateGenerationService(provider)
        request = GenerationRequest(self.last_campaign.campaign_id, self.last_campaign.topic_id, self.last_campaign.puzzle_type, self.last_campaign.review_pool_estimate or 24, excluded, self.last_campaign.mini_theme_gaps)
        preview = generator.preview(request, existing_supply=len(excluded), minimum_deficit=self.last_campaign.minimum_deficit)
        pilot_count = min(40, max(25, int(preview["recommended_request_count"])))
        if not provider.available():
            messagebox.showinfo("Gemini not configured", "Candidate generation provider is not configured. Existing/local content review remains available.", parent=self); return
        if not messagebox.askyesno("Generate new candidates", f"Provider: Gemini\nTopic: {request.topic_id}\nCandidates requested: {pilot_count} (small pilot)\n\nThis sends the topic and a bounded duplicate-exclusion list to Gemini and may use API quota. Generated content remains unreviewed.\n\nGenerate now?", parent=self): return
        # The first live pass is deliberately a small editorial pilot. Large
        # shortage numbers belong in the campaign, not in a single API call.
        live_request = GenerationRequest(request.campaign_id, request.topic_id, request.puzzle_type, pilot_count, excluded, request.concept_targets, True)
        self.generate_button.configure(state="disabled"); self.status.set("Requesting review-only candidates from Gemini…")
        def worker():
            try:
                result = generator.generate(live_request)
                stored = campaign_service.store_generated(self.last_campaign, result.accepted)
                error = None
            except Exception as exc:
                result, stored, error = None, 0, str(exc)
            self.after(0, lambda: self._generation_complete(result, stored, error))
        threading.Thread(target=worker, daemon=True).start()

    def _generation_complete(self, result, stored: int, error: str | None) -> None:
        self.generate_button.configure(state="normal")
        if error or not result:
            self.status.set("Gemini did not add candidates. Existing local review remains available.")
            messagebox.showerror("Candidate generation", error or "No candidates were generated.", parent=self); return
        self._write(["CANDIDATES READY FOR REVIEW", "", f"Provider: {result.provider}", f"Accepted for human review: {stored}", f"Filtered before review: {len(result.rejected)}", "", "Nothing was approved or added to the source word banks. Opening the selection list now."])
        self.status.set(f"{stored} Gemini candidates were saved as unreviewed content. Choose the words you want to add.")
        if stored:
            self.after(120, self.create_review_batch)

    def show_attention(self) -> None:
        if not self.database:
            messagebox.showinfo("What needs attention?", "Open Publishing Center to see saved product attention items.", parent=self); return
        rows = self.service.attention(self.database.list_books())
        lines = ["WHAT NEEDS MY ATTENTION?", ""]
        for row in rows[:40]:
            lines += [row.label.upper(), row.message, f"Next: {row.next_action.replace('_', ' ').title()}", ""]
        self._write(lines or ["No saved products need attention."])
