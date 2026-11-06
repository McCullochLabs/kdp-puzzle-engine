"""Guided Tkinter entry point for printable activity packs."""
from __future__ import annotations

import os
from pathlib import Path
from queue import Empty, Queue
import random
import threading
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .studio_reader_profiles import READER_PROFILES, READER_LABELS, BALANCES, word_suits_reader
from .activity_packs import ActivityPackPlan, FORMATS, PRESETS, build_activity_pack, parse_words, validate_plan


class ActivityPackDialog(tk.Toplevel):
    def __init__(self, master, initial_plan=None, draft_store=None, draft_id=None):
        super().__init__(master)
        self.title("Make a printable activity pack")
        from word_search_creator import fit_dialog_to_screen
        from .family_studio import ScrollPage
        fit_dialog_to_screen(self, 800, 730)
        self.busy = False
        self._package_in_progress = False
        self.draft_store = draft_store
        self.draft_id = draft_id or uuid.uuid4().hex
        self._draft_job = None
        self._restoring = False
        self._last_draft = None
        self.saved_status = tk.StringVar(self, '')
        self.last_package = None
        self.results = Queue()
        self.word_results = Queue()
        self._library_topic = None
        self._source_groups = ()
        self._library_signature = None
        self._loading_words = False
        self._word_epoch = 0
        self._preset_reader = 'standard'

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.pack_title = tk.StringVar(self, "Road Trip Activity Pack")
        self.recipient = tk.StringVar(self)
        self.theme = tk.StringVar(self, "Road Trip")
        self.count = tk.StringVar(self, "6")
        self.difficulty = tk.StringVar(self, "easy")
        self.seed = tk.StringVar(self)
        self.output = tk.StringVar(self, str(Path(__file__).resolve().parents[1] / "out" / "activity_packs"))
        self.status = tk.StringVar(self, "Choose a theme and give your pack a name.")
        self.selected = {kind: tk.BooleanVar(self, True) for kind in FORMATS}
        self.reader_choice = tk.StringVar(self, READER_PROFILES['standard']['label'])
        self.balance_choice = tk.StringVar(self, 'Balanced')
        self.controls = []
        self.step = 0
        self.progress = tk.StringVar(self)
        ttk.Label(self, textvariable=self.progress, padding=(20, 12), style="Family.Body.TLabel").pack(fill="x")
        self.page = ScrollPage(self)
        self.page.pack(fill="both", expand=True)
        self.pages = [ttk.Frame(self.page.body, style="App.TFrame") for _ in range(3)]
        first, second, third = self.pages
        ttk.Label(first, text="What is your pack about?", style="Family.Title.TLabel", wraplength=650).pack(anchor="w", pady=(0, 15))
        themes = ttk.Frame(first, style="App.TFrame")
        themes.pack(fill="x")
        themes.columnconfigure((0, 1), weight=1)
        for index, name in enumerate((*PRESETS, "Custom")):
            button = ttk.Radiobutton(themes, text=name, variable=self.theme, value=name, command=self._preset, style="Family.Option.TRadiobutton")
            button.grid(row=index//2, column=index%2, sticky="ew", pady=3)
            self.controls.append((button, "normal"))
        ttk.Button(first, text='Browse all topics', command=self._browse_topics).pack(anchor='w', pady=(10, 0))
        for label, variable in (("Pack title", self.pack_title), ("Made for / occasion (optional)", self.recipient)):
            ttk.Label(first, text=label, style="Family.Body.TLabel").pack(anchor="w", pady=(16, 6))
            entry = ttk.Entry(first, textvariable=variable, font=("Segoe UI", 12))
            entry.pack(fill="x", ipady=6)
            self.controls.append((entry, "normal"))
        ttk.Label(second, text="Choose your activities", style="Family.Title.TLabel", wraplength=650).pack(anchor="w")
        for kind, variable in self.selected.items():
            button = ttk.Checkbutton(second, text=kind, variable=variable)
            button.pack(anchor="w", pady=6)
            self.controls.append((button, "normal"))
        options = ttk.Frame(second, style="App.TFrame")
        options.pack(fill="x", pady=10)
        ttk.Label(options, text="Activity pages").pack(side="left")
        count = ttk.Spinbox(options, textvariable=self.count, from_=1, to=24, width=5)
        count.pack(side="left", padx=10)
        self.controls.append((count, "normal"))
        ttk.Label(second, text='Reader profile (word activities)').pack(anchor='w', pady=(8, 3))
        reader = ttk.Combobox(second, textvariable=self.reader_choice, values=tuple(READER_LABELS), state='readonly')
        reader.pack(fill='x'); self.controls.append((reader, 'readonly'))
        ttk.Label(second, text='Theme mix').pack(anchor='w', pady=(8, 3))
        balance = ttk.Combobox(second, textvariable=self.balance_choice, values=BALANCES, state='readonly')
        balance.pack(fill='x'); self.controls.append((balance, 'readonly'))
        ttk.Label(second, text='Profiles change word length, familiarity and search directions; review the preview for the individual reader.', wraplength=650).pack(anchor='w', pady=5)
        ttk.Label(second, text="Sudoku difficulty").pack(anchor="w")
        difficulties = ttk.Frame(second, style="App.TFrame")
        difficulties.pack(fill="x", pady=6)
        for value in ("easy", "medium", "hard"):
            radio = ttk.Radiobutton(difficulties, text=value.title(), variable=self.difficulty, value=value)
            radio.pack(side="left", padx=(0, 16))
            self.controls.append((radio, "normal"))
        ttk.Label(second, text="Words are chosen for you", style="Family.Body.TLabel").pack(anchor="w", pady=(12, 6))
        ttk.Label(second, text="The Studio selects the words and checks the answers. The same words may recur across different activity types. Sudoku needs no words.", wraplength=650).pack(anchor="w", pady=(0, 8))
        words_frame = ttk.Frame(second)
        def toggle_words():
            words_frame.pack_forget() if words_frame.winfo_manager() else words_frame.pack(fill="both", expand=True)
        ttk.Button(second, text='Review included words (optional)', command=toggle_words).pack(anchor='w', pady=6)
        self.words = tk.Text(words_frame, height=7, wrap="word", undo=True, font=("Segoe UI", 11))
        scroll = ttk.Scrollbar(words_frame, command=self.words.yview)
        self.words.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.words.pack(fill="both", expand=True)
        self.controls.append((self.words, "normal"))
        self.words.insert("1.0", "\n".join(PRESETS["Road Trip"].split()))
        ttk.Label(third, text="Your pack is ready to create", style="Family.Title.TLabel", wraplength=650).pack(anchor="w")
        ttk.Button(third, text="Preview actual pages and answers", command=self._preview).pack(anchor="w", pady=8)
        self.summary = tk.StringVar(self)
        ttk.Label(third, textvariable=self.summary, wraplength=650, style="Family.Body.TLabel", justify="left").pack(anchor="w", pady=18)
        ttk.Label(third, text="You will receive activity pages, separate answer sheets, printing instructions, and a ZIP. Review the PDFs and sample-print before sharing or selling.", wraplength=650).pack(anchor="w", pady=(0, 16))
        ttk.Label(third, text="Save in").pack(anchor="w")
        location = ttk.Frame(third)
        location.pack(fill="x", pady=6)
        output = ttk.Entry(location, textvariable=self.output)
        output.pack(side="left", fill="x", expand=True)
        browse = ttk.Button(location, text="Change folder", command=self._browse)
        browse.pack(side="left", padx=8)
        self.controls.extend(((output, "normal"), (browse, "normal")))
        advanced = ttk.Frame(third, style="App.TFrame")
        def toggle_advanced():
            advanced.pack_forget() if advanced.winfo_manager() else advanced.pack(fill="x", pady=8)
        ttk.Button(third, text="Optional: reproduce a previous pack", command=toggle_advanced).pack(anchor="w", pady=8)
        ttk.Label(advanced, text="Seed").pack(side="left")
        seed = ttk.Entry(advanced, textvariable=self.seed, width=18)
        seed.pack(side="left", padx=8)
        self.controls.append((seed, "normal"))
        footer = ttk.Frame(self, padding=16, style="Family.Card.TFrame")
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status, wraplength=680, style="Family.CardText.TLabel").pack(fill="x", pady=(0, 10))
        actions = ttk.Frame(footer, style="Family.Card.TFrame")
        actions.pack(fill="x")
        self.back_button = ttk.Button(actions, text="Back", command=lambda: self._show_step(self.step-1))
        self.back_button.pack(side="left")
        self.next_button = ttk.Button(actions, text="Next", command=self._next, style="Primary.TButton")
        self.next_button.pack(side="right")
        self.create_button = ttk.Button(actions, text="Create printable pack", command=self._create, style="Primary.TButton")
        ttk.Button(actions, text="Open last pack", command=self._open).pack(side="left", padx=10)
        ttk.Button(actions, text="Undo saved edit", command=self._undo_draft).pack(side="left", padx=4)
        ttk.Label(footer, textvariable=self.saved_status, wraplength=680).pack(fill="x", pady=(8, 0))
        self.controls.extend(((self.back_button, "normal"), (self.next_button, "normal"), (self.create_button, "normal")))
        if initial_plan is not None:
            self.pack_title.set(initial_plan.title)
            self.recipient.set(initial_plan.recipient)
            self.theme.set(initial_plan.theme if initial_plan.theme in PRESETS else "Custom")
            self.reader_choice.set(READER_PROFILES[initial_plan.reader_profile]['label'])
            self.balance_choice.set(initial_plan.theme_balance)
            self.count.set(str(initial_plan.activity_count))
            self.difficulty.set(initial_plan.difficulty)
            self.words.delete("1.0", "end")
            self.words.insert("1.0", "\n".join(initial_plan.words))
            for kind, variable in self.selected.items(): variable.set(kind in initial_plan.formats)
        restored_step = 0
        if draft_id and draft_store:
            draft = draft_store.load(draft_id)
            if draft:
                self._restore_form(draft['payload'])
                restored_step = 0  # Always review restored inputs before generating.
        for variable in (self.pack_title, self.recipient, self.theme, self.count, self.difficulty, self.seed, self.output, self.reader_choice, self.balance_choice, *self.selected.values()):
            variable.trace_add('write', self._draft_changed)
        self.words.bind('<<Modified>>', self._words_changed)
        self.words.edit_modified(False)
        self._show_step(restored_step)
        self._poll_job = self.after(100, self._poll)
        self.bind("<Destroy>", self._destroyed, add="+")

    def _browse_topics(self):
        from .family_studio import TopicPicker
        TopicPicker(self, self._load_library_topic)

    def _word_signature(self):
        return (self._library_topic, self.count.get(), tuple(kind for kind in FORMATS if self.selected[kind].get()), self.reader_choice.get(), self.balance_choice.get())

    def _load_library_topic(self, topic, source_groups=()):
        self._source_groups = tuple(source_groups)
        self._library_topic = topic
        self.theme.set('Custom')
        self.pack_title.set((topic + ' Activity Pack')[:100])
        self._prepare_library_words()

    def _prepare_library_words(self):
        try: count = int(self.count.get())
        except ValueError: return
        formats = tuple(kind for kind in FORMATS if self.selected[kind].get())
        if not formats or not len(formats) <= count <= 24: return
        signature = self._word_signature()
        self._library_signature = signature
        kinds = [formats[index % len(formats)] for index in range(count)]
        pages = max(kinds.count('Word Search'), kinds.count('Word Scramble'))
        self._loading_words = True
        self._word_epoch += 1
        epoch = self._word_epoch
        self.status.set('Choosing checked words from your topic group…')
        topic, results = self._library_topic, self.word_results
        source_groups = self._source_groups
        reader = READER_LABELS[self.reader_choice.get()]
        balance = self.balance_choice.get()
        root = Path(__file__).resolve().parents[1]
        def prepare():
            try:
                from word_intelligence.pipeline import prepare_family_wordsearch
                plan = prepare_family_wordsearch(root, topic, pages, 8, minimum_puzzles=1, max_word_length=18, source_groups=source_groups, reader=reader, balance=balance) if pages else {'words': []}
                if len(plan['words']) < pages * 8:
                    raise ValueError('Choose fewer activity pages or another topic. The owner can review this group in Advanced tools.')
                results.put((epoch, signature, plan, ''))
            except Exception as exc: results.put((epoch, signature, [], str(exc)))
        threading.Thread(target=prepare, daemon=True).start()

    def _snapshot_form(self):
        return {'reader_profile': READER_LABELS[self.reader_choice.get()], 'theme_balance': self.balance_choice.get(), 'library_topic': self._library_topic, 'source_groups': list(self._source_groups), 'title': self.pack_title.get(), 'recipient': self.recipient.get(), 'theme': self.theme.get(),
                'count': self.count.get(), 'difficulty': self.difficulty.get(), 'seed': self.seed.get(),
                'output': self.output.get(), 'words': self.words.get('1.0', 'end-1c'),
                'formats': [kind for kind, value in self.selected.items() if value.get()], 'step': self.step}

    def _restore_form(self, form):
        self._restoring = True
        self.reader_choice.set(READER_PROFILES[form.get('reader_profile', 'standard')]['label'])
        self.balance_choice.set(form.get('theme_balance', 'Balanced'))
        self._library_topic = form.get('library_topic')
        self._source_groups = tuple(form.get('source_groups') or ())
        try:
            for key, variable in (('title', self.pack_title), ('recipient', self.recipient), ('theme', self.theme), ('count', self.count), ('difficulty', self.difficulty), ('seed', self.seed), ('output', self.output)):
                if key in form: variable.set(str(form[key]))
            self.words.delete('1.0', 'end')
            self.words.insert('1.0', str(form.get('words', '')))
            for kind, value in self.selected.items(): value.set(kind in form.get('formats', FORMATS))
            self.words.edit_modified(False)
            self._last_draft = self._snapshot_form()
        finally: self._restoring = False

    def _words_changed(self, event=None):
        if self.words.edit_modified():
            self.words.edit_modified(False)
            self._draft_changed()

    def _draft_changed(self, *args):
        if self._restoring or not self.draft_store: return
        if self._draft_job: self.after_cancel(self._draft_job)
        self._draft_job = self.after(800, self.flush_draft)
        self.saved_status.set('Unsaved changes…')

    def flush_draft(self, completed=False):
        if not self.draft_store: return True
        if self._draft_job:
            self.after_cancel(self._draft_job)
            self._draft_job = None
        form = self._snapshot_form()
        if not completed and form == self._last_draft: return True
        try:
            self.draft_store.save(self.draft_id, 'activity_pack', form, completed=completed)
            self._last_draft = form
            self.saved_status.set('Draft saved locally.' if not completed else 'Completed pack saved; original draft history retained.')
            return True
        except Exception as exc:
            self.saved_status.set(f'Draft could not be saved: {exc}. Your previous saved version is preserved.')
            return False

    def _undo_draft(self):
        if not self.draft_store: return
        if not self.flush_draft(): return
        try:
            draft = self.draft_store.undo(self.draft_id)
            if draft:
                self._restore_form(draft['payload'])
                self._show_step(0)
                self.saved_status.set('Restored the previous saved edit. Review it before creating.')
        except Exception as exc: self.saved_status.set(f'Could not restore the saved edit: {exc}')

    def _preview(self):
        try:
            plan = self._plan()
            self.seed.set(str(plan.seed))
        except ValueError as exc:
            self.status.set(str(exc))
            return
        from .studio_preview import StudioPreview
        StudioPreview(self, plan_getter=self._plan)

    def _destroyed(self, event):
        if event.widget == self:
            if getattr(self, '_wheel_refresh_job', None): self.after_cancel(self._wheel_refresh_job)
            if self._draft_job: self.after_cancel(self._draft_job)
            try: self.after_cancel(self._poll_job)
            except tk.TclError: pass

    def _show_step(self, step):
        if self.busy: return
        self.step = max(0, min(2, step))
        for page in self.pages: page.pack_forget()
        self.pages[self.step].pack(fill="both", expand=True)
        self.progress.set(f"Step {self.step+1} of 3 · " + ("Your idea", "Activities", "Review")[self.step])
        self.back_button.configure(state="disabled" if self.step == 0 else "normal")
        self.next_button.pack_forget()
        self.create_button.pack_forget()
        (self.create_button if self.step == 2 else self.next_button).pack(side="right")
        self.page.canvas.yview_moveto(0)
        if getattr(self, '_wheel_refresh_job', None): self.after_cancel(self._wheel_refresh_job)
        self._wheel_refresh_job = self.after_idle(self.page._bind_wheel)

    def _next(self):
        if self._loading_words:
            self.status.set('Choosing checked words for your topic. Please wait a moment.')
            return
        if self.step == 0:
            if not self.pack_title.get().strip():
                self.status.set("Give your pack a title before continuing.")
                return
        if self.step == 1:
            try: plan = self._plan()
            except ValueError as exc:
                self.status.set(str(exc))
                return
            self.seed.set(str(plan.seed))
            self.summary.set(f"{plan.title}\n{plan.recipient}\n\nTheme: {plan.theme}\nReader: {READER_PROFILES[plan.reader_profile]['label']}\nTheme mix: {plan.theme_balance}\nActivity pages: {plan.activity_count}\nActivities: {', '.join(plan.formats)}\nSudoku difficulty: {plan.difficulty}\n\nEach PDF includes one introduction plus {plan.activity_count} numbered pages.")
        self.status.set(("Choose a theme and give your pack a name.", "Choose activities and review the vocabulary.", "Review your plan, then create the pack.")[min(2, self.step+1)])
        self._show_step(self.step+1)

    def _preset(self, *_):
        self._preset_reader = None
        self._library_topic = None
        self._source_groups = ()
        self._word_epoch += 1
        self._loading_words = False
        self.words.delete("1.0", "end")
        if self.theme.get() in PRESETS:
            self.words.insert("1.0", "\n".join(PRESETS[self.theme.get()].split()))
        self.pack_title.set(f"{self.theme.get()} Activity Pack")

    def _browse(self):
        folder = filedialog.askdirectory(parent=self, title="Choose where to save activity packs")
        if folder:
            self.output.set(folder)

    def _plan(self):
        if self._loading_words:
            raise ValueError("The Studio is choosing checked words. Please wait a moment.")
        try:
            count = int(self.count.get())
            seed = int(self.seed.get()) if self.seed.get().strip() else random.SystemRandom().randint(0, 2**31-1)
        except ValueError:
            raise ValueError("Activity pages and seed must be whole numbers.") from None
        return validate_plan(ActivityPackPlan(
            title=self.pack_title.get(), recipient=self.recipient.get(), theme=self.theme.get(),
            words=parse_words(self.words.get("1.0", "end")), formats=tuple(kind for kind in FORMATS if self.selected[kind].get()),
            activity_count=count, difficulty=self.difficulty.get(), seed=seed, reader_profile=READER_LABELS[self.reader_choice.get()], theme_balance=self.balance_choice.get()))

    def _review(self):
        try:
            plan = self._plan()
        except ValueError as exc:
            messagebox.showerror("Check your pack", str(exc), parent=self)
            return
        self.seed.set(str(plan.seed))
        messagebox.showinfo("Your printable pack plan", f"{plan.title}\n{plan.recipient}\n\nTheme: {plan.theme}\nActivities: {plan.activity_count}\nTypes: {', '.join(plan.formats)}\nSudoku difficulty: {plan.difficulty}\nSeed: {plan.seed}\n\nEach PDF includes an introduction plus {plan.activity_count} activity or answer pages.\nIncludes a ZIP for sharing. No book or listing will be published.", parent=self)

    def _create(self):
        if self._loading_words:
            self.status.set("Wait for the checked words before creating.")
            return
        if self.busy:
            return
        try:
            plan = self._plan()
            if not self.output.get().strip():
                raise ValueError("Choose where to save your pack.")
            output = Path(self.output.get()).expanduser()
        except ValueError as exc:
            messagebox.showerror("Check your pack", str(exc), parent=self)
            return
        self.seed.set(str(plan.seed))
        self.busy = True
        self._package_in_progress = True
        for widget, _ in self.controls:
            widget.configure(state="disabled")
        self.status.set("Creating activities, checking solutions, and preparing your printable PDFs…")
        results = self.results
        def work():
            # The worker never calls Tk. The main thread owns every UI update.
            try:
                results.put((True, build_activity_pack(plan, output)))
            except Exception as exc:
                results.put((False, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        reader = READER_LABELS[self.reader_choice.get()]
        if not self._library_topic and self.theme.get() in PRESETS and (reader != self._preset_reader):
            self._preset_reader = reader
            self.words.delete('1.0', 'end'); self.words.insert('1.0', '\n'.join(word for word in PRESETS[self.theme.get()].split() if word_suits_reader(word, reader)))
        # Large preset requests should use the checked library automatically,
        # rather than sending the family back to vocabulary maintenance.
        if not self._library_topic and not self.busy:
            aliases = {'Space': 'Space & Astronomy', 'Garden': 'Gardening', 'Road Trip': 'Travel Road Trips and Getaways'}
            try:
                count = int(self.count.get())
                formats = tuple(kind for kind in FORMATS if self.selected[kind].get())
                kinds = [formats[i % len(formats)] for i in range(count)] if formats else []
                needed = max(kinds.count('Word Search'), kinds.count('Word Scramble')) * 8
                if 1 <= count <= 24 and needed > len(parse_words(self.words.get('1.0', 'end'))) and self.theme.get() in aliases:
                    self._library_topic = aliases[self.theme.get()]
                    self._source_groups = ()
                    self._prepare_library_words()
            except (ValueError, tk.TclError): pass
        try:
            epoch, signature, words, error = self.word_results.get_nowait()
        except Empty: pass
        else:
            if epoch == self._word_epoch:
                self._loading_words = False
                if self._library_topic and signature == self._word_signature():
                    if error:
                        self.words.delete('1.0', 'end')
                        self.status.set(error)
                    else:
                        details = words if isinstance(words, dict) else {'words': words}
                        words = details['words']
                        self.words.delete('1.0', 'end'); self.words.insert('1.0', '\n'.join(words))
                        groups = details.get('source_topics', [])
                        self.status.set(f'{len(words)} checked words selected automatically.' + (' Word groups used: ' + ', '.join(groups) if groups else '') + (' ' + ' '.join(details.get('warnings', [])) if details.get('warnings') else ''))
        if self._library_topic and not self._loading_words and self._library_signature != self._word_signature():
            self._prepare_library_words()
        try:
            ok, result = self.results.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self._package_in_progress = False
            for widget, state in self.controls:
                widget.configure(state=state)
            self._show_step(self.step)
            if ok:
                self.last_package = result
                family = getattr(self.master, 'family_studio', None)
                if family:
                    family.context = (family.context or {}) | {'reader_profile': READER_LABELS[self.reader_choice.get()], 'theme_balance': self.balance_choice.get()}
                    family._say('Studio', f'Activity pack created: {self.pack_title.get()}. {self.count.get()} activities with answers. Saved in {result}')
                self.flush_draft(completed=True)
                self.status.set(f"Pack created. Review the PDFs and sample-print before distribution. Saved in {result}")
            else:
                self.status.set("Pack could not be created. Correct the issue and try again.")
                messagebox.showerror("Pack could not be created", result, parent=self)
        self._poll_job = self.after(100, self._poll)

    def _open(self):
        if not self.last_package:
            messagebox.showinfo("No pack yet", "Create a printable pack first.", parent=self)
        elif hasattr(os, "startfile"):
            os.startfile(self.last_package)
        else:
            messagebox.showinfo("Pack location", str(self.last_package), parent=self)

    def _close(self):
        if self.busy:
            messagebox.showinfo("Pack is being created", "Please let the current pack finish before closing this window.", parent=self)
            return
        if self.flush_draft(): self.destroy()
