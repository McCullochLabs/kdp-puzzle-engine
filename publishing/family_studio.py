"""Family-facing navigation over the existing studio, not a second backend."""
from __future__ import annotations

from dataclasses import asdict
import json
import re
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .studio_reader_profiles import READER_PROFILES, READER_LABELS, BALANCES, reader_from_request
from .studio_providers import RequestGate, interpret_request
from .activity_packs import ActivityPackPlan, FORMATS, PRESETS
from .studio_assistant import AssistantIntent, BOOK_TYPES, LocalAssistant, guide_request, project_context, refers_to_current


class ScrollPage(ttk.Frame):
    """A page with a visible scrollbar and window-local wheel handling."""
    def __init__(self, parent):
        super().__init__(parent, style='App.TFrame')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        background = ttk.Style(self).lookup('App.TFrame', 'background') or '#f5f2eb'
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=background)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body = ttk.Frame(self.canvas, padding=24, style='App.TFrame')
        item = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(item, width=event.width))
        self.bind('<Destroy>', self._cancel, add='+')
        self._wheel_job = self.after_idle(self._bind_wheel)

    def _bind_wheel(self):
        def bind_tree(widget):
            if not isinstance(widget, (tk.Text, ttk.Treeview, tk.Listbox)) and not getattr(widget, '_family_wheel_bound', False):
                widget._family_wheel_bound = True
                widget.bind('<MouseWheel>', self._wheel, add='+')
                widget.bind('<Button-4>', lambda event: self.canvas.yview_scroll(-1, 'units'), add='+')
                widget.bind('<Button-5>', lambda event: self.canvas.yview_scroll(1, 'units'), add='+')
            for child in widget.winfo_children(): bind_tree(child)
        bind_tree(self.body)
        self.canvas.bind('<MouseWheel>', self._wheel)

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def _cancel(self, event):
        if event.widget == self:
            try: self.after_cancel(self._wheel_job)
            except tk.TclError: pass


class FamilyStudio(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='App.TFrame')
        self.app = app
        self.results = Queue()
        self.history = []
        self._session_messages = []
        self._session_ready = False
        self._session_restoring = False
        self._session_save_job = None
        self.intent = None
        self._request_reader = 'standard'
        self._request_balance = 'Balanced'
        self.busy = False
        self.page = None
        self.epoch = 0
        self.catalog = []
        self.context = None
        self._open_latest = False
        self._proposal_context = None
        self._holiday_reuse_plan = None
        self.model = str(app._app_preferences.get('local_ai_model') or '')
        self.local_ai_enabled = bool(app._app_preferences.get('local_ai_enabled', False)) and bool(self.model)
        self.provider = str(app._app_preferences.get('assistant_provider') or ('Ollama' if self.local_ai_enabled else 'Guide'))
        if self.provider not in ('Codex', 'Ollama', 'Guide'): self.provider = 'Guide'
        self.request_gate = RequestGate()
        self._cover_cancels = []
        self._cover_windows = {}
        self._auto_ai = 'assistant_provider' not in app._app_preferences and app._app_preferences.get('local_ai_enabled') is not False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self, padding=(20, 12), style='Family.Card.TFrame')
        top.grid(row=0, column=0, sticky='ew')
        brand = ttk.Label(top, text='SladePuzzleCo', style='Family.Brand.TLabel')
        brand.pack(side='left', padx=(0, 18))
        self.nav_buttons = {}  # Detailed routes remain behind one menu.
        self.menu_button = ttk.Menubutton(top, text='Menu', style='Family.Nav.TButton')
        self.menu_button.pack(side='right')
        self.nav_menu = tk.Menu(self.menu_button, tearoff=False)
        for label, command in (('Home', self.show_home), ('Create', self.show_create), ('My books', self.show_books), ('Covers', self.show_covers), ('Settings', self.show_settings)):
            self.nav_menu.add_command(label=label, command=command)
        self.menu_button.configure(menu=self.nav_menu)
        self.content = ttk.Frame(self, style='App.TFrame')
        self.content.grid(row=1, column=0, sticky='nsew')
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.home = ttk.Frame(self.content, padding=(30, 20), style='App.TFrame')
        self.home.columnconfigure(0, weight=1)
        self.home.rowconfigure(4, weight=1)
        ttk.Label(self.home, text='What would you like to make?', style='Family.Title.TLabel', wraplength=700).grid(row=0, column=0, sticky='w')
        ttk.Label(self.home, text='Describe your idea. I’ll prepare a plan for you to review.', style='Family.Body.TLabel', wraplength=650).grid(row=1, column=0, sticky='w', pady=(5, 14))
        manual = ttk.Frame(self.home, style='App.TFrame')
        manual.grid(row=2, column=0, sticky='ew')
        self.manual_button = ttk.Button(manual, text='Use buttons instead', command=self._toggle_manual_choices)
        self.manual_button.pack(anchor='w', pady=(0, 8))
        quick = ttk.Frame(manual, style='App.TFrame')
        self.manual_choices = quick
        quick.columnconfigure((0, 1), weight=1)
        for index, (label, command) in enumerate((('Make an activity pack', self.open_pack), ('Create a puzzle book', self.open_book), ('Continue a saved book', self.show_books), ('Work on a cover', self.show_covers))):
            ttk.Button(quick, text=label, command=command, style='Family.Choice.TButton').grid(row=index//2, column=index%2, sticky='ew', padx=(0, 8), pady=(0, 8))
        self.mode = tk.StringVar(self)
        ttk.Label(self.home, textvariable=self.mode, style='Family.Muted.TLabel').grid(row=3, column=0, sticky='w', pady=(8, 6))
        self.chat = ScrolledText(self.home, height=5, wrap='word', relief='flat', borderwidth=0, padx=16, pady=14, font=('Segoe UI', 12), state='disabled')
        self.chat.grid(row=4, column=0, sticky='nsew')
        self.proposal = ttk.Frame(self.home, padding=(0, 10), style='App.TFrame')
        self.proposal.grid(row=5, column=0, sticky='ew')
        self.proposal.columnconfigure(0, weight=1)
        self.proposal_text = tk.StringVar(self)
        ttk.Label(self.proposal, textvariable=self.proposal_text, style='Family.Body.TLabel', wraplength=650).grid(row=0, column=0, sticky='w')
        self.proposal_button = ttk.Button(self.proposal, text='Review this request', command=self._open_proposal, style='Primary.TButton')
        self.proposal_button.grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.proposal.grid_remove()
        self.retry_button = ttk.Button(self.home, text='Retry with selected AI', command=self._retry_local_ai)
        self._last_request = ''
        self.cancel_button = ttk.Button(self.home, text='Cancel request', command=self.cancel_request)
        self._build_stop_owner = None
        self._revision_worker_owner = None
        self.build_stop_button = ttk.Button(self.home, text='Stop after current step', command=self._stop_active_build)
        composer = ttk.Frame(self.home, style='App.TFrame')
        composer.grid(row=6, column=0, sticky='ew')
        composer.columnconfigure(0, weight=1)
        self.prompt = tk.StringVar(self)
        self.entry = ttk.Entry(composer, textvariable=self.prompt, font=('Segoe UI', 12))
        self.entry.grid(row=0, column=0, sticky='ew', ipady=8)
        self.entry.bind('<Return>', lambda event: self.send())
        self.send_button = ttk.Button(composer, text='Send', command=self.send, style='Primary.TButton')
        self.send_button.grid(row=0, column=1, padx=(10, 0))
        ttk.Label(self.home, text='Try: “Make a birthday activity pack for Emma” or “Find my garden books”.', style='Family.Muted.TLabel', wraplength=750).grid(row=7, column=0, sticky='w', pady=(8, 0))
        footer = ttk.Frame(self, padding=(20, 8), style='Family.Card.TFrame')
        footer.grid(row=2, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=app.status, style='Family.CardText.TLabel', wraplength=700).grid(row=0, column=0, sticky='w')
        self._say('Studio', 'What would you like to make? Tell me the topic and who it is for. You’ll review the plan before I create anything.')
        self.refresh_style()
        self.show_home()
        self.resume_button = ttk.Button(quick, text='Continue unfinished work', command=self.resume_draft)
        self.resume_button.grid(row=2, column=0, columnspan=2, sticky='w', pady=4)
        self.draft_chooser_button=ttk.Button(quick,text='Choose unfinished work',command=self.show_unfinished_drafts)
        self.draft_chooser_button.grid(row=3,column=0,columnspan=2,sticky='w',pady=4)
        self._session_restore_job = self.after_idle(self._restore_session)
        self._discovery_job = self.after(150, self._discover_local_ai)
        self._poll_job = self.after(100, self._poll)
        self.bind('<Destroy>', self._destroyed, add='+')

    def _handle_project_query(self, text):
        from .studio_project_queries import project_query, selected_project, project_status_text, preview_project, solution_preview_project
        action=project_query(text)
        if not action:return False
        if action=='unfinished_drafts':
            self.show_unfinished_drafts()
            return True
        if action=='title_page_designs':
            from .studio_project_queries import title_page_designs_text
            self._say('Studio',title_page_designs_text())
            return True
        if action in ('themes','duplicates'):
            ticket,cancel=self.request_gate.begin(self.provider,dict(self.context) if self.context else None)
            self.busy=True;self.send_button.configure(state='disabled')
            self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
            self.mode.set('Reading the saved-theme catalog locally…')
            root=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]));results=self.results
            def work():
                try:
                    from .studio_theme_catalog import project_theme_catalog,theme_catalog_text
                    text=theme_catalog_text(project_theme_catalog(root),duplicates=action=='duplicates')
                    results.put(('theme_query_result',(ticket,text,'')))
                except Exception as exc:results.put(('theme_query_result',(ticket,'',str(exc))))
            threading.Thread(target=work,daemon=True).start()
            return True
        if action=='save_session':
            if not self._session_ready or self._session_restoring:
                self._say('Studio','Conversation recovery is still starting; wait before saving.')
                return True
            self._flush_session()
            if self._session_save_error:
                self._say('Studio','Save needs attention: '+self._session_save_error+'. The earlier saved session was not replaced.')
            else:
                self._say('Studio','Saved the conversation and selected project reference for reopening. Generated book files and approval states were not changed.')
            return True
        if action=='resume':
            self.resume_draft()
            return True
        if self.busy:return True
        from copy import deepcopy
        context=deepcopy(self.context)
        ticket,cancel=self.request_gate.begin(self.provider,context)
        self.busy=True;self.send_button.configure(state='disabled')
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Checking the selected project locally…')
        root=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        results=self.results
        def work():
            try:
                if action=='select_project':
                    from .studio_project_queries import select_catalog_project
                    project=select_catalog_project(root,text)
                elif action=='solutions':project=solution_preview_project(root,context)
                else:project=(preview_project if action in ('interior','cover') else selected_project)(root,context)
                if not cancel.is_set():results.put(('project_query_result',(ticket,action,project,'')))
            except Exception as exc:
                if not cancel.is_set():results.put(('project_query_result',(ticket,action,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()
        return True

    def _receive_project_query_result(self,ticket,action,project,error):
        # File hashing and catalog reads finish off-thread; Tk and previews stay
        # on this thread, and a late result cannot reopen a cancelled project.
        if not self.request_gate.accepts(ticket,self.provider,self.context):
            if ticket==self.request_gate.active:self.cancel_request()
            return
        self.cancel_request()
        if error:
            self._say('Studio',error)
            return
        try:
            if action=='select_project':
                self.context=project_context(project)
                self._proposal_context=dict(self.context)
                self._schedule_session_save()
                self._say('Studio','Selected saved project: '+self.context['title']+' ('+self.context['book_id']+'). No generation, QA or approval was performed. Any earlier staged candidate remains in saved recovery history.')
            elif action=='files':self._say('Studio',f"Saved package: {project['folder']}")
            elif action=='status':
                from .studio_project_queries import project_status_text
                self._say('Studio',project_status_text(project))
            else:
                label='Interior' if action in ('interior','solutions') else 'Cover'
                documents=[document for document in project['documents'] if document[0]==label]
                if not documents:raise ValueError(f'The selected project has no available {label.lower()} PDF.')
                from .studio_preview import StudioPreview
                StudioPreview(self.app,documents=documents)
                if action=='solutions':self._say('Studio',f"Opened the first recorded solutions at PDF page {project['solution_start_page']} for {project['metadata'].get('title') or 'this project'}.")
                else:self._say('Studio',f"Opened the saved {label.lower()} for {project['metadata'].get('title') or 'this project'}.")
        except Exception as exc:self._say('Studio',str(exc))

    def _schedule_session_save(self):
        if not self._session_ready or self._session_restoring:return
        if self._session_save_job:
            try:self.after_cancel(self._session_save_job)
            except tk.TclError:pass
        self._session_save_job=self.after(500,self._flush_session)

    def _flush_session(self):
        self._session_save_job=None
        if not self._session_ready or self._session_restoring:return
        try:
            from .studio_session import save_session
            root=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
            save_session(root,self.context,self._session_messages)
            self._session_save_error=''
        except Exception as exc:
            self._session_save_error=str(exc)
            try:self.app.status.set('Conversation autosave needs attention: '+str(exc))
            except tk.TclError:pass

    def _restore_session(self):
        self._session_restoring=True
        try:
            from .studio_session import load_session
            root=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
            saved=load_session(root)
            if saved:
                self.chat.configure(state='normal');self.chat.delete('1.0','end');self.chat.configure(state='disabled')
                for message in saved['messages']:self._say(message['role'],message['text'])
                self._session_messages=saved['messages']
                self.history=[{'role':'user','content':row['text']} for row in saved['messages'] if row['role']=='You'][-6:]
                self.context=saved['context'];self._proposal_context=dict(self.context) if self.context else None
                if saved['pending_result']:self._receive_staged_revision(saved['pending_result'])
                self._say('Studio','Restored saved conversation and project context. Earlier responses are history, not fresh QA or approval. No action was replayed.')
                for warning in saved['warnings']:self._say('Studio',warning)
            self._session_ready=True
        except Exception as exc:
            self.context=None
            self._say('Studio','Saved conversation needs recovery: '+str(exc)+'. Saved records were preserved; no project action was replayed.')
        finally:self._session_restoring=False

    def _draft_store(self):
        from .studio_recovery import draft_store_for
        return draft_store_for(self.app)

    def show_unfinished_drafts(self,offset=0):
        body=self._new_page('Home','Choose unfinished work',f'Unfinished drafts, page {offset//20+1}. Up to 20 per page. Opening reviews saved work; it does not generate, adopt or publish.')
        controls=ttk.Frame(body);controls.pack(fill='x',pady=4)
        self.unfinished_previous=ttk.Button(controls,text='Newer drafts',state='normal' if offset else 'disabled',command=lambda:self.show_unfinished_drafts(max(0,offset-20)))
        self.unfinished_previous.pack(side='left')
        self.unfinished_next=ttk.Button(controls,text='Older drafts',state='disabled',command=lambda:self.show_unfinished_drafts(offset+20))
        self.unfinished_next.pack(side='left',padx=8)
        self._unfinished_rows=ttk.Frame(body);self._unfinished_rows.pack(fill='both',expand=True)
        ttk.Label(self._unfinished_rows,text='Reading saved drafts…').pack(anchor='w')
        epoch=self.epoch;store=self._draft_store();results=self.results
        def work():
            try:
                rows=[]
                for row in store.pending(offset=offset):
                    draft=store.load(row['draft_id'])
                    if not draft or draft.get('completed'):continue
                    payload=draft['payload'];saved=payload.get('chat_creation') or payload.get('chat_revision') or {}
                    plan=saved.get('plan') or {};editor=payload.get('editor') or {}
                    rows.append({'draft_id':draft['draft_id'],'title':str(plan.get('title') or editor.get('title') or 'Untitled saved draft')[:150],
                                 'kind':str(plan.get('kind') or payload.get('kind') or draft['kind']),
                                 'status':str(saved.get('status') or 'Unfinished form'),'error':str(saved.get('error') or '')[:1000]})
                results.put(('unfinished_drafts',(epoch,rows,'',bool(store.pending(offset=offset+20)))))
            except Exception as exc:results.put(('unfinished_drafts',(epoch,[],str(exc),False)))
        threading.Thread(target=work,daemon=True).start()

    def _receive_unfinished_drafts(self,epoch,rows,error,has_more=False):
        if epoch!=self.epoch or not self.page:return
        self.unfinished_next.configure(state='normal' if has_more and not error else 'disabled')
        for child in self._unfinished_rows.winfo_children():child.destroy()
        if error or not rows:
            ttk.Label(self._unfinished_rows,text=('Saved drafts could not be read: '+error) if error else 'No unfinished drafts are available.').pack(anchor='w');return
        for row in rows:
            description=f"{row['kind']} · {row['status']} · ID: {row['draft_id']}"
            if row['error']:description+='\nPrevious failure: '+row['error']
            self._card(self._unfinished_rows,row['title'],description,lambda identity=row['draft_id']:self._open_unfinished_draft(identity),'Review saved draft')

    def _open_unfinished_draft(self,identity):
        self.show_home()
        self.resume_draft(identity)

    def resume_draft(self,draft_id=None):
        try:
            store = self._draft_store()
            rows = store.pending()
            if not rows:
                self._say('Studio', 'There is no unfinished draft yet. Your completed books and packs are unchanged.')
                return
            identity=rows[0]['draft_id'] if draft_id is None else draft_id
            if not store.is_pending(identity):
                raise ValueError('That draft is no longer unfinished. Refresh the list before choosing it.')
            draft = store.load(identity)
            if not draft or draft.get('completed'):raise ValueError('That draft is no longer unfinished. Refresh the list.')
            for child in self.app.winfo_children():
                if getattr(child, 'draft_id', None) == draft['draft_id']:
                    child.lift()
                    child.focus_set()
                    return
            if draft['kind'] == 'activity_pack':
                from .activity_pack_ui import ActivityPackDialog
                ActivityPackDialog(self.app, draft_store=store, draft_id=draft['draft_id'])
            elif 'chat_revision' in draft['payload']:
                from .studio_chat_revisions import load_revision_plan
                saved=draft['payload']['chat_revision'];plan=load_revision_plan(saved['plan'])
                self.context=dict(plan.selected_context)
                if saved.get('status')=='adopted':self._receive_adopted_revision(saved['adoption_result'])
                elif saved.get('status')=='rejected':self._say('Studio','This staged revision was rejected; original project selected.')
                elif saved.get('status')=='complete':self._receive_staged_revision(saved['result'])
                else:self._show_chat_revision_plan(plan,persist=False)
                if saved.get('status')=='failed':self._say('Studio','Previous revision attempt failed: '+str(saved.get('error') or 'No saved error detail.')[:1000]+'. Opening this draft does not retry it; the saved failure and artifacts remain preserved.')
            elif 'chat_creation' in draft['payload']:
                from .studio_chat_creation import _validated_saved_plan
                saved=draft['payload']['chat_creation']
                if saved.get('status')=='complete':
                    self._receive_created_book(saved['result'],restored=True)
                else:
                    self._show_chat_creation_plan(_validated_saved_plan(saved), saved.get('selected_context'),persist=False)
                    if saved.get('status')=='failed':self._say('Studio','Previous creation attempt failed: '+str(saved.get('error') or 'No saved error detail.')[:1000]+'. Opening this draft does not retry it; the saved failure and artifacts remain preserved.')
            else:
                FamilyBookDialog(self.app, draft_store=store, draft_id=draft['draft_id'])
        except Exception as exc: self._say('Studio', f'Your draft could not be opened: {exc}. No saved work was changed.')

    def _discover_local_ai(self):
        # Existing local installations only; never download or pick between models.
        if self.local_ai_enabled or not self._auto_ai: return
        results = self.results
        def work():
            try: results.put(('startup_models', LocalAssistant().models()))
            except Exception: pass
        threading.Thread(target=work, daemon=True).start()

    def _destroyed(self, event):
        if event.widget == self:
            for job in (self._session_save_job,self._session_restore_job):
                if job:
                    try:self.after_cancel(job)
                    except tk.TclError:pass
            self._flush_session()
            self.request_gate.stop()
            self.after_cancel(self._discovery_job)
            try: self.after_cancel(self._poll_job)
            except tk.TclError: pass

    def refresh_style(self):
        dark = self.app.dark_mode.get()
        self.chat.configure(background='#202333' if dark else '#ffffff', foreground='#f3f2f8' if dark else '#243047', insertbackground='#f3f2f8' if dark else '#243047')
        self.mode.set('Codex · ChatGPT sign-in · online' if self.provider == 'Codex' else (f'Local AI · {self.model}' if self.provider == 'Ollama' else 'Guide mode · common requests and all buttons work without AI'))
        if self.page:
            self.page.canvas.configure(background=self.app.cget('background'))

    def _say(self, role, text):
        if role in ('You','Studio') and not self._session_restoring:
            self._session_messages.append({'role':role,'text':str(text)[:1000]})
            self._session_messages=self._session_messages[-20:]
            self._schedule_session_save()
        self.chat.configure(state='normal')
        self.chat.insert('end', f'{role}\n{text}\n\n')
        if len(self.chat.get('1.0', 'end')) > 20000:
            self.chat.delete('1.0', '100.0')
        self.chat.see('end')
        self.chat.configure(state='disabled')

    def _toggle_manual_choices(self):
        if self.manual_choices.winfo_manager():
            self.manual_choices.pack_forget()
            self.manual_button.configure(text='Use buttons instead')
        else:
            self.manual_choices.pack(fill='x')
            self.manual_button.configure(text='Hide creation buttons')

    def _select(self, name):
        self.menu_button.configure(text='Menu' if name == 'Home' else name + ' · Menu')

    def show_home(self):
        self.epoch += 1
        if self.page:
            self.page.destroy()
            self.page = None
        self.home.grid(row=0, column=0, sticky='nsew')
        self._select('Home')

    def _new_page(self, name, heading, description):
        self.epoch += 1
        self.home.grid_remove()
        if self.page: self.page.destroy()
        self.page = ScrollPage(self.content)
        self.page.grid(row=0, column=0, sticky='nsew')
        self.page.canvas.configure(background=self.app.cget('background'))
        body = self.page.body
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=heading, style='Family.Title.TLabel', wraplength=700).pack(anchor='w')
        ttk.Label(body, text=description, style='Family.Body.TLabel', wraplength=700).pack(anchor='w', pady=(6, 22))
        self._select(name)
        return body

    def _card(self, parent, title, description, command, button='Open'):
        card = ttk.Frame(parent, padding=18, style='Family.Card.TFrame')
        card.pack(fill='x', pady=(0, 12))
        ttk.Label(card, text=title, style='Family.CardTitle.TLabel', wraplength=650).pack(anchor='w')
        ttk.Label(card, text=description, style='Family.CardText.TLabel', wraplength=650).pack(anchor='w', pady=(5, 12))
        ttk.Button(card, text=button, command=command, style='Primary.TButton').pack(anchor='w')
        return card

    def show_create(self):
        body = self._new_page('Create', 'Start with something simple', 'Choose the result you want. The next screen asks only for the details it needs.')
        self._card(body, 'Printable activity pack', 'A short collection of puzzles for home, a party, a trip, or a gift. Separate answer sheets and a ZIP are included.', self.open_pack, 'Make a pack')
        self._card(body, 'Puzzle book', 'A complete book using the existing content checks, cover pipeline, and publishing preparation.', self.open_book, 'Plan a book')

    def open_pack(self, intent=None):
        from .activity_pack_ui import ActivityPackDialog
        initial = None
        if isinstance(intent, AssistantIntent):
            topic = next((name for name in PRESETS if name.casefold() == intent.topic.casefold()), 'Custom')
            words = tuple(PRESETS[topic].split()) if topic in PRESETS else ()
            import secrets
            initial = ActivityPackPlan(reader_profile=self._request_reader, theme_balance=self._request_balance, seed=secrets.randbelow(2**31), title=f'{intent.topic or "My"} Activity Pack', words=words, theme=topic,
                                       recipient=intent.recipient, activity_count=intent.activity_count,
                                       formats=('Sudoku',) if intent.kind == 'Sudoku' else
                                       ('Word Scramble',) if intent.kind == 'Word Scramble + Trivia' else
                                       FORMATS[:min(3, intent.activity_count)])
        try:
            dialog = ActivityPackDialog(self.app, initial_plan=initial, draft_store=self._draft_store())
            if initial and (initial.theme == 'Custom' or intent.source_groups) and intent.topic:
                dialog._load_library_topic(intent.topic, intent.source_groups)
        except Exception as exc: self._say("Studio", f"The pack could not open: {exc}")

    def open_book(self, intent=None):
        FamilyBookDialog(self.app, intent if isinstance(intent, AssistantIntent) else None, draft_store=self._draft_store(), initial_reader=self._request_reader if intent else 'standard', initial_balance=self._request_balance if intent else 'Balanced')

    def send(self):
        if self.busy: return
        text = self.prompt.get().strip()
        if not text: return
        if len(text) > 1000:
            self._say('Studio', 'Please shorten the request to 1000 characters or fewer.')
            return
        try:
            self._request_reader = reader_from_request(text) or (self.context or {}).get('reader_profile', 'standard')
        except ValueError as exc:
            self._say('Studio', str(exc)); return
        lower = text.casefold()
        self._request_balance = next((name for name in BALANCES if name.casefold() in lower), (self.context or {}).get('theme_balance', 'Balanced'))
        self.prompt.set('')
        self._last_request = text
        self.retry_button.grid_remove()
        self._say('You', text)
        import re
        if self._handle_revision_decision(text):return
        if self._handle_project_query(text):return
        if re.fullmatch(r'open (?:my |the )?last (?:project|book)[.!?]?', text, re.I):
            drafts = self._draft_store().pending()
            if drafts:
                self.resume_draft()
            else:
                self._open_latest = True
                self.show_books()
            return
        previous = self.intent
        scope = dict(self.context) if self.context and refers_to_current(text) else None
        self._proposal_context = scope
        history = list(self.history)
        self.history.append({'role': 'user', 'content': text})
        self.history = self.history[-6:]
        self.proposal.grid_remove()
        from .studio_chat_revisions import is_revision_request
        if is_revision_request(text):
            self._prepare_revision_plan(text)
            return
        if self.provider == 'Guide':
            self._receive_intent(guide_request(text, previous, self.context))
            return
        self.busy = True
        self.send_button.configure(state='disabled')
        self.cancel_button.grid(row=7, column=0, sticky='w', pady=4)
        self.mode.set(self.provider + ' is reading your request… You can cancel or use Menu.')
        model, provider = self.model, self.provider
        selected_context = dict(self.context) if self.context else None
        ticket, cancel = self.request_gate.begin(provider, selected_context)
        results = self.results
        def work():
            try:
                intent = interpret_request(provider, text, model, history, selected_context, previous, cancel)
                results.put(('request_result', (ticket, intent, scope, '')))
            except Exception as exc:
                results.put(('request_result', (ticket, None, scope, str(exc))))
        threading.Thread(target=work, daemon=True).start()

    def cancel_request(self):
        self.request_gate.stop()
        self.busy = False
        self.send_button.configure(state='normal')
        self.cancel_button.grid_remove()
        self.refresh_style()

    def _retry_local_ai(self):
        if self.busy or self.provider == 'Guide' or not self._last_request: return
        self.prompt.set(self._last_request)
        self.send()

    def _receive_intent(self, intent):
        from .studio_assistant import negates_local_action
        if intent.action in ('create_pack','create_book','check_book','export_book','audit_cover','covers') and negates_local_action(getattr(self,'_last_request','')):
            self.intent=AssistantIntent(action='help')
            self._chat_creation_plan=None;self._chat_revision_plan=None
            self._say('Studio','Your request explicitly says not to perform that action. No creation, check or export was started.')
            return
        self.intent = intent
        self._chat_creation_plan = None
        self._chat_revision_plan = None
        self._adoption_revision_id = None
        self._holiday_reuse_plan = None
        if hasattr(self,'reject_revision_button'):self.reject_revision_button.grid_remove()
        self.proposal_button.configure(text='Review this request')
        from .studio_assistant import requests_wordsearch_sudoku
        if requests_wordsearch_sudoku(self._last_request) or (intent.action=='create_book' and intent.kind=='Word Search + Sudoku'):
            self._prepare_holiday_reuse()
            return
        if intent.action=='create_book' and intent.kind=='Word Search':
            from .studio_chat_wordsearch import needs_guided_wordsearch
            # Literal standard requests use the new direct path. Known reader,
            # design and page variants retain the explicit guided review.
            if intent.topic and re.search(r'\bword[ -]search\b',self._last_request,re.I) and not needs_guided_wordsearch(self._last_request):
                self._prepare_wordsearch_plan(intent)
                return
        if intent.action=='create_book' and intent.kind in ('Sudoku','Cryptogram','Word Scramble + Trivia','Mixed Brain Games'):
            from .studio_chat_creation import sudoku_chat_plan
            from .studio_chat_families import studio_family_chat_plan
            try:
                parser=sudoku_chat_plan if intent.kind=='Sudoku' else studio_family_chat_plan
                plan=parser(self._last_request,intent)
                self._show_chat_creation_plan(plan,self.context)
            except Exception as exc:
                self._say('Studio',str(exc)+' Use Create → Puzzle book for other supported guided settings.')
            return
        if intent.action in ('check_book', 'export_book'):
            if (self.context or {}).get('pending_semantic_revision') and not re.fullmatch(r'(?:check|export|verify|audit|inspect|review|prepare)(?:\s+(?:the|my))?\s+(?:original|source)(?:\s+(?:book|project|files|package))?[.!?]*',self._last_request.strip(),re.I):
                self._say('Studio','A staged revision candidate is pending and is not adopted. I did not check or export the old original. Accept or reject the staged candidate, or explicitly choose the original in My books before checking/exporting it.')
                return
            selected = self._proposal_context or self.context
            self._proposal_context = dict(selected) if selected else None
            self._check_selected_book(self._proposal_context, export=intent.action == 'export_book')
            return
        if intent.action == 'help':
            self._say('Studio', 'I can help you plan a printable pack or puzzle book, find saved books, check a selected book\'s local print and puzzle quality, and open the existing cover workshop. Publishing and file management stay in their reviewed tools.')
            return
        if intent.action == 'clarify':
            self._say('Studio', 'Choose a saved book first for requests such as its cover, or tell me whether you want a new activity pack, puzzle book, or cover.')
            return
        if intent.action in ('create_pack', 'create_book') and not intent.topic:
            self._say('Studio', 'What topic would you like? For example: Space, Garden, Birthday, or Road Trip.')
            return
        description = {'create_pack': f'Plan a {intent.topic} activity pack with {intent.activity_count} activity pages.',
                       'create_book': f'Plan a {intent.kind} book about {intent.topic}.',
                       'find_books': f'Search your catalog for {intent.topic or "all saved books"}.',
                       'audit_cover': 'Review the selected saved cover and its measured print checks.',
                       'covers': f'Open the existing cover workshop{": " + intent.topic if intent.topic else ""}.'}[intent.action]
        if intent.action == 'create_book':
            page_target = re.search(r'\b(\d+)\s*(?:[-]\s*)?pages?\b', self._last_request, re.I)
            if page_target:
                description += f' You requested {page_target.group(1)} pages. Guided creation does not yet enforce an exact page count; final pages depend on puzzle settings, front matter, and answers. Review those settings before creating the book.'
        if self._proposal_context: description += ' Selected project: ' + self._proposal_context['title'] + '.'
        if intent.source_groups: description += ' Proposed word groups: ' + ', '.join(intent.source_groups) + '.'
        if intent.action == 'create_pack': description += ' Reader profile: ' + READER_PROFILES[self._request_reader]['label'] + '. Preview for the individual reader; these controls do not certify a reading age.'
        if intent.recipient: description += f' Personalization: {intent.recipient}.'
        self.proposal_text.set(description)
        self.proposal.grid()
        self._say('Studio', description + ' Use “Review this request” to continue.')
        self.history.append({'role': 'assistant', 'content': json.dumps(asdict(intent))})
        self.history = self.history[-6:]

    def _open_proposal(self):
        if getattr(self,'_holiday_reuse_plan',None):
            self._confirm_holiday_reuse();return
        if getattr(self,'_adoption_revision_id',None):
            self._decide_staged_revision(True);return
        if getattr(self,'_chat_revision_plan',None):
            self._create_confirmed_revision();return
        if not self.intent: return
        intent = self.intent
        if intent.action == 'create_pack':
            self.context = {'action': 'create_pack', 'title': intent.topic + ' activity pack', 'topic': intent.topic, 'kind': intent.kind, 'activity_count': intent.activity_count, 'source_groups': intent.source_groups, 'reader_profile': self._request_reader, 'theme_balance': self._request_balance}
            self.open_pack(intent)
        elif intent.action == 'create_book':
            if getattr(self,'_chat_creation_plan',None): self._create_confirmed_chat_book()
            else: self.open_book(intent)
        elif intent.action == 'find_books': self.show_books(query=intent.topic)
        elif intent.action == 'audit_cover':
            selected = self._proposal_context or self.context
            book = next((book for book in self.catalog if selected and book['book_id'] == selected.get('book_id')), None)
            if book: self._audit_book(book)
            else:
                self._say('Studio', 'Choose a saved book and use Review cover to audit its actual files.')
                self.show_books()
        elif intent.action == 'covers':
            if self._proposal_context and self._proposal_context.get('book_id'):
                self.app._open_book_control_center(self._proposal_context['book_id'])
            else: self.show_covers(topic=intent.topic)

    def _prepare_revision_plan(self,text):
        from copy import deepcopy
        from .studio_chat_revisions import revision_plan
        context=deepcopy(self.context)
        ticket,cancel=self.request_gate.begin(self.provider,context)
        self.busy=True;self.send_button.configure(state='disabled')
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Checking the selected project and preparing its revision…')
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        results=self.results
        def work():
            try:
                plan=revision_plan(project,text,context)
                if not cancel.is_set():results.put(('revision_plan_result',(ticket,plan,'')))
            except Exception as exc:
                if not cancel.is_set():results.put(('revision_plan_result',(ticket,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _receive_revision_plan(self,ticket,plan,error):
        if not self.request_gate.accepts(ticket,self.provider,self.context):
            if ticket==self.request_gate.active:self.cancel_request()
            return
        self.cancel_request()
        if error:self._say('Studio',error)
        else:
            try:self._show_chat_revision_plan(plan)
            except Exception as exc:self._say('Studio','Revision plan needs attention: '+str(exc))

    def _show_chat_revision_plan(self,plan,*,persist=True):
        self._holiday_reuse_plan=None
        self._adoption_revision_id=None
        if hasattr(self,'reject_revision_button'):self.reject_revision_button.grid_remove()
        from .studio_chat_revisions import revision_text,save_revision_plan
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        if persist:save_revision_plan(project,plan)
        self._chat_revision_plan=plan;self._chat_creation_plan=None
        self.proposal_text.set(revision_text(plan));self.proposal.grid()
        self.proposal_button.configure(text='Create staged revision')
        self._say('Studio',revision_text(plan))

    def _create_confirmed_revision(self):
        if self.busy:return
        if getattr(self,'_revision_worker_owner',None) or getattr(self,'_build_stop_owner',None):
            self._say('Studio','The previous book worker is still finishing. Wait for it before starting another change.');return
        plan=self._chat_revision_plan
        if not plan:return
        from .studio_chat_revisions import confirm_revision_plan,stage_revision
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        from copy import deepcopy
        context=deepcopy(self.context)
        if dict(context or {})!=plan.selected_context:
            self._say('Studio','The selected project changed. Submit the revision again before confirming it.');return
        ticket,cancel=self.request_gate.begin(self.provider,context)
        self.busy=True;self.send_button.configure(state='disabled');self.proposal.grid_remove()
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Building a staged revision… Original stays selected. Cancel dismisses this response; draft production continues.')
        self._say('Studio','Creating the confirmed staged candidate. The original package, catalog and approvals remain unchanged.')
        self._revision_worker_owner=ticket
        results=self.results
        def work():
            try:
                if cancel.is_set():raise ValueError('Revision cancelled before confirmation.')
                confirm_revision_plan(project,plan,context)
                results.put(('book_revision_result',(ticket,stage_revision(project,plan.revision_id,cancel),'')))
            except Exception as exc:results.put(('book_revision_result',(ticket,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _receive_staged_revision(self,result):
        self._holiday_reuse_plan=None
        self._chat_revision_plan=None
        self._adoption_revision_id=result['revision_id']
        self.context={**dict(self.context or {}),'pending_semantic_revision':{'revision_id':result['revision_id'],'title':result['title']}}
        self._proposal_context=dict(self.context)
        self.proposal_text.set(f"Accept {result['title']!r}: {result['puzzles']} puzzles, {result['pages']} pages? This updates the selected catalog book while preserving its identity and all original files. Publication and owner quality approval remain separate.")
        self.proposal_button.configure(text='Accept staged revision')
        if not hasattr(self,'reject_revision_button'):
            self.reject_revision_button=ttk.Button(self.proposal,text='Reject staged revision',command=lambda:self._decide_staged_revision(False))
        self.reject_revision_button.grid(row=1,column=1,sticky='w',padx=8,pady=(8,0))
        self.proposal.grid()
        self._say('Studio',f"Staged revision candidate: {result['title']}, {result['puzzles']} puzzles, {result['pages']} pages. Files: {result['folder']}. Original files and catalog remain unchanged. Inspect the candidate, then choose Accept or Reject staged revision.")

    def _handle_revision_decision(self,text):
        from .studio_chat_revisions import revision_decision
        decision=revision_decision(text)
        if decision is None:return False
        pending=(self.context or {}).get('pending_semantic_revision') or {}
        identity=pending.get('revision_id') if isinstance(pending,dict) else None
        if not identity or identity!=getattr(self,'_adoption_revision_id',None):
            self._say('Studio','No matching staged revision decision is open. Reopen its saved decision before accepting or rejecting it.')
            return True
        self._decide_staged_revision(decision=='accept')
        return True

    def _decide_staged_revision(self,accept):
        if self.busy:return
        if getattr(self,'_revision_worker_owner',None) or getattr(self,'_build_stop_owner',None):
            self._say('Studio','The previous book worker is still finishing. Wait for it before starting another change.');return
        from .studio_revision_adoption import confirm_adoption,adopt_revision,reject_revision
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        identity=getattr(self,'_adoption_revision_id',None)
        if not identity:return
        try:
            if not accept:
                self.context=reject_revision(project,identity,self.context)
                self._proposal_context=dict(self.context);self._adoption_revision_id=None
                self.proposal.grid_remove();self.reject_revision_button.grid_remove()
                self._say('Studio','Staged revision rejected. Original project remains selected; candidate files and decision history are preserved.')
                return
            confirm_adoption(project,identity,self.context)
        except Exception as exc:self._say('Studio','Revision decision needs attention: '+str(exc));return
        ticket,cancel=self.request_gate.begin(self.provider,dict(self.context))
        self.busy=True;self.send_button.configure(state='disabled');self.proposal.grid_remove()
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Validating and adopting the accepted revision locally…')
        self._revision_worker_owner=ticket
        results=self.results
        def work():
            try:results.put(('book_adoption_result',(ticket,adopt_revision(project,identity,cancel),'')))
            except Exception as exc:results.put(('book_adoption_result',(ticket,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _finish_revision_worker(self,ticket):
        if getattr(self,'_revision_worker_owner',None)==ticket:
            self._revision_worker_owner=None

    def _receive_adopted_revision(self,result):
        self.context={key:result[key] for key in ('book_id','title','topic','kind')}
        self._proposal_context=dict(self.context);self._adoption_revision_id=None
        self.proposal.grid_remove()
        if hasattr(self,'reject_revision_button'):self.reject_revision_button.grid_remove()
        self._say('Studio',f"Accepted revision: {result['title']}, {result['puzzles']} puzzles, {result['pages']} pages. The same catalog book is now selected. Original files and approval/marketplace states were preserved. Files: {result['folder']}. Owner and platform review remain pending.")

    def _prepare_wordsearch_plan(self,intent):
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        context=dict(self.context) if self.context else None;request=self._last_request
        ticket,cancel=self.request_gate.begin(self.provider,context)
        self.busy=True;self.send_button.configure(state='disabled');self.proposal.grid_remove()
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Preparing exact checked Word Search groups and approved art locally…')
        results=self.results
        def work():
            try:
                from .studio_chat_wordsearch import wordsearch_chat_plan
                plan=wordsearch_chat_plan(request,intent,project)
                results.put(('wordsearch_plan_result',(ticket,plan,context,'')))
            except Exception as exc:results.put(('wordsearch_plan_result',(ticket,None,context,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _prepare_holiday_reuse(self):
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        context=dict(self.context or {});request=self._last_request
        ticket,cancel=self.request_gate.begin(self.provider,dict(self.context) if self.context else None)
        self.busy=True;self.send_button.configure(state='disabled');self.proposal.grid_remove()
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Inspecting the existing fixed holiday recipe locally…')
        results=self.results
        def work():
            try:
                from .studio_holiday_reuse import prepare_holiday_reuse
                results.put(('holiday_plan_result',(ticket,prepare_holiday_reuse(project,request,context),'')))
            except Exception as exc:results.put(('holiday_plan_result',(ticket,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _confirm_holiday_reuse(self):
        if self.busy:return
        plan=self._holiday_reuse_plan
        if not plan:return
        if json.dumps(self.context or {},sort_keys=True,ensure_ascii=False)!=plan.selected_context_json:
            self._say('Studio','Selected project changed. Review a fresh holiday reuse proposal.');return
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        ticket,cancel=self.request_gate.begin(self.provider,dict(self.context) if self.context else None)
        self.busy=True;self.send_button.configure(state='disabled');self.proposal.grid_remove()
        self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        self.mode.set('Running actual QA/preflight on the existing holiday book…')
        results=self.results
        def work():
            try:
                from .studio_holiday_reuse import confirm_holiday_reuse
                results.put(('holiday_reuse_result',(ticket,confirm_holiday_reuse(project,plan,cancel),'')))
            except Exception as exc:results.put(('holiday_reuse_result',(ticket,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _show_chat_creation_plan(self,plan,selected_context=None,*,persist=True):
        self._holiday_reuse_plan=None
        self._adoption_revision_id=None
        if hasattr(self,'reject_revision_button'):self.reject_revision_button.grid_remove()
        from .studio_chat_creation import plan_text,save_creation_plan
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        if persist:save_creation_plan(project,plan,selected_context)
        self._chat_creation_plan=plan
        self._chat_creation_context=dict(selected_context or {})
        self.intent=AssistantIntent(action='create_book',kind=plan.kind,topic=plan.topic)
        self.proposal_text.set(plan_text(plan));self.proposal.grid()
        self.proposal_button.configure(text='Create this book')
        self._say('Studio',plan_text(plan))

    def _stop_active_build(self):
        owner=self._build_stop_owner
        if not owner:return
        owner[1].set()
        self.build_stop_button.configure(state='disabled')
        self._say('Studio','Stop requested for the running build after its current safe step. The renderer is not terminated; files and the recovery draft are preserved. Wait for the worker to finish before resuming.')

    def _finish_build_stop(self, ticket):
        owner=self._build_stop_owner
        if owner and owner[0]==ticket:
            self._build_stop_owner=None
            self.build_stop_button.grid_remove()

    def _create_confirmed_chat_book(self):
        if self.busy:return
        if getattr(self,'_build_stop_owner',None) or getattr(self,'_revision_worker_owner',None):
            self._say('Studio','The earlier build is still finishing. Use Stop after current step or wait before creating another book.')
            return
        plan=self._chat_creation_plan
        if not plan:return
        from .studio_chat_creation import create_chat_book,confirm_creation_plan
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]))
        try:
            if dict(self.context or {})!=self._chat_creation_context:
                raise ValueError('The selected project changed. Submit the creation request again before approving it.')
            if plan.kind!='Word Search':confirm_creation_plan(project,plan,self.context)
        except Exception as exc:
            self._say('Studio',str(exc));return
        ticket,cancel=self.request_gate.begin(self.provider,dict(self.context) if self.context else None)
        self.busy=True;self.send_button.configure(state='disabled')
        self.proposal.grid_remove();self.cancel_button.grid(row=7,column=0,sticky='w',pady=4)
        stop_event=threading.Event()
        self._build_stop_owner=(ticket,stop_event)
        self.build_stop_button.configure(state='normal')
        self.build_stop_button.grid(row=8,column=0,sticky='w',pady=4)
        self.mode.set('Creating the confirmed book locally… Cancel dismisses this response; production and its recovery draft continue.')
        self._say('Studio',f'Creating the confirmed {plan.kind} plan with approved artwork, solutions and local QA. Nothing is published.')
        project=Path(getattr(self.app,'APP_DIR',Path(__file__).resolve().parents[1]));results=self.results
        confirmed_context=dict(self.context or {})
        def work():
            try:
                if plan.kind=='Word Search':
                    if cancel.is_set():raise ValueError('Creation cancelled before confirmation.')
                    confirm_creation_plan(project,plan,confirmed_context)
                results.put(('book_creation_result',(ticket,create_chat_book(project,plan.draft_id,cancel,stop_event=stop_event,progress=lambda message:results.put(('book_creation_progress',(ticket,str(message)[:1000])))),'')))
            except Exception as exc:results.put(('book_creation_result',(ticket,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def _receive_created_book(self,result,*,restored=False):
        self.context={key:result[key] for key in ('book_id','title','topic','kind')}
        self._proposal_context=dict(self.context)
        self._chat_creation_plan=None
        if restored:
            self._say('Studio',f"Opened saved book result: {result['title']}, {result['puzzles']} puzzles, {result['pages']} pages. Local checks were recorded at creation; ask Check this book for current QA. The same saved catalog identity is selected. No generation or approval was replayed.")
            return
        self._say('Studio',f"Created {result['title']}: {result['puzzles']} puzzles, {result['pages']} pages. "
                  f"Local preflight passed; {result['qa']['summary']['blockers']} QA blockers. "
                  f"Files: {result['folder']}. READY WITH LIMITATIONS: owner, platform preview and physical proof remain open. "
                  'This is now the selected book. Ask Check this book or Prepare the KDP files.')

    def _check_selected_book(self, selected, *, export=False):
        if not selected or not selected.get('book_id'):
            self._say('Studio', 'Choose a saved book in My books before checking its actual files.')
            return
        from .studio_book_checks import check_saved_book, export_saved_book
        snapshot = dict(selected)
        # The selected identity comes from the catalog UI, never the model.
        identity = str(snapshot['book_id'])
        if self.request_gate.active is not None:
            self.cancel_request()
        ticket, cancel = self.request_gate.begin(self.provider, dict(self.context) if self.context else None)
        self.busy = True
        self.send_button.configure(state='disabled')
        self.cancel_button.grid(row=7, column=0, sticky='w', pady=4)
        self.mode.set('Preparing a local export after QA…' if export else 'Checking local print files and puzzles… Cancel dismisses the result.')
        self._say('Studio', 'Checking saved book: ' + str(snapshot.get('title') or identity) + '…')
        project = Path(getattr(self.app, 'APP_DIR', Path(__file__).resolve().parents[1]))
        results = self.results
        def work():
            try:
                result = (export_saved_book if export else check_saved_book)(project, identity, cancel)
                results.put(('book_export_result' if export else 'book_check_result', (ticket, result, '')))
            except Exception as exc:
                results.put(('book_export_result' if export else 'book_check_result', (ticket, None, str(exc))))
        threading.Thread(target=work, daemon=True).start()

    def show_books(self, query=''):
        body = self._new_page('My books', 'Your saved books', 'Search the existing catalog. Open a book to review its files, cover, checks, and publishing preparation.')
        tools = ttk.Frame(body, style='App.TFrame')
        tools.pack(fill='x', pady=(0, 12))
        self.book_query = tk.StringVar(self, query)
        search = ttk.Entry(tools, textvariable=self.book_query, font=('Segoe UI', 12))
        search.pack(side='left', fill='x', expand=True, ipady=6)
        ttk.Button(tools, text='Search', command=self._filter_books).pack(side='left', padx=8)
        search.bind('<Return>', lambda event: self._filter_books())
        self.book_rows = ttk.Frame(body, style='App.TFrame')
        self.book_rows.pack(fill='both', expand=True)
        ttk.Label(self.book_rows, text='Reading your local catalog…', style='Family.Body.TLabel').pack(anchor='w')
        epoch = self.epoch
        results = self.results
        database = Path(getattr(self.app, 'APP_DIR', Path(__file__).resolve().parents[1]))
        path = database / 'data' / 'books.db'
        def work():
            try:
                from .database import PublishingDatabase
                books = PublishingDatabase(path).list_books() if path.is_file() else []
                from .catalog_view import collapse_catalog_books, catalog_state
                books = collapse_catalog_books(books)
                for book in books:
                    book['studio_catalog_state'] = catalog_state(book)
                results.put(('books', (epoch, books, '')))
            except Exception as exc: results.put(('books', (epoch, [], str(exc))))
        threading.Thread(target=work, daemon=True).start()
        ttk.Button(body, text='Open printable packs folder', command=self._open_pack_folder, style='Family.Nav.TButton').pack(anchor='w', pady=12)

    def _filter_books(self):
        for child in self.book_rows.winfo_children(): child.destroy()
        query = self.book_query.get().strip().casefold()
        books = [book for book in self.catalog if query in ' '.join(str(book.get('metadata', {}).get(key) or '') for key in ('title', 'theme', 'puzzle_type')).casefold()]
        if not books:
            ttk.Label(self.book_rows, text='No matching books. Try another search or start a new creation.', style='Family.Body.TLabel', wraplength=650).pack(anchor='w')
        for book in books[:30]:
            meta = book.get('metadata') or {}
            state = book.get('studio_catalog_state') or {'status': 'Review publishing status inside', 'next_action': 'Open the book to review its files'}
            self._card(self.book_rows, str(meta.get('title') or 'Untitled book'),
                       f"{meta.get('puzzle_type') or 'Puzzle book'} · {state['status']}\nBook ID: {book['book_id']}\nNext: {state['next_action']}",
                       lambda selected=book: self._open_selected_book(selected), 'Open book')
            ttk.Button(self.book_rows, text='Review cover', command=lambda selected=book: self._audit_book(selected)).pack(anchor='w', pady=(0, 5))
            ttk.Button(self.book_rows, text='Preview saved pages / cover', command=lambda selected=book: self._preview_book(selected)).pack(anchor='w', pady=(0, 12))
        if len(books) > 30:
            ttk.Label(self.book_rows, text=f'Showing 30 of {len(books)} books. Narrow the search to find another title.', style='Family.Muted.TLabel').pack(anchor='w')
        if self.page: self.page._bind_wheel()

    def _open_selected_book(self, book):
        self.context = project_context(book)
        self._schedule_session_save()
        self._say('Studio', 'Selected book: ' + self.context['title'] + '. Requests about its cover or another version now refer to this book.')
        self.app.status.set('Selected book: ' + self.context['title'])
        self.app._open_book_control_center(self.context['book_id'])

    def _preview_book(self, book):
        self.context = project_context(book)
        self._schedule_session_save()
        files = (book.get('metadata') or {}).get('files') or {}
        documents = []
        for label, keys in (('Saved puzzle pages', ('printable_pdf', 'print_interior')), ('Saved cover', ('front_cover', 'print_cover'))):
            path = next((Path(str(files[key])) for key in keys if files.get(key) and Path(str(files[key])).is_file()), None)
            if path: documents.append((label, path, 2 if label == 'Saved puzzle pages' else 0))
        if not documents:
            messagebox.showinfo('Preview not available', 'This catalog record has no available saved PDF or cover. Open the book to prepare or repair its package.', parent=self)
            return
        from .studio_preview import StudioPreview
        StudioPreview(self.app, documents=documents)

    def _preview_cover(self, book):
        from .studio_cover_audit import cover_evidence
        from .studio_preview import StudioPreview
        try:
            evidence = cover_evidence(book)
            StudioPreview(self.app, documents=[(label, path, 0) for label, path in evidence['documents']])
        except Exception as exc:
            messagebox.showinfo('Cover preview unavailable', str(exc), parent=self)

    def _open_pack_folder(self):
        from .desktop_files import open_local_path
        path = Path(__file__).resolve().parents[1] / 'out' / 'activity_packs'
        if not path.is_dir():
            messagebox.showinfo('No packs yet', 'Create a printable activity pack first. Its completed folder will be shown after creation.', parent=self)
            return
        open_local_path(path)

    def show_covers(self, topic=''):
        body = self._new_page('Covers', 'One home for cover work', 'Use the established cover generator and approved artwork library. Finished book covers still go through the existing layout, wrap, and proof checks.')
        card = ttk.Frame(body, padding=18, style='Family.Card.TFrame')
        card.pack(fill='x', pady=(0, 12))
        ttk.Label(card, text='Generate or review cover artwork', style='Family.CardTitle.TLabel').pack(anchor='w')
        ttk.Label(card, text='What is the artwork about?', style='Family.CardText.TLabel').pack(anchor='w', pady=(8, 5))
        value = tk.StringVar(self, topic)
        entry = ttk.Entry(card, textvariable=value, font=('Segoe UI', 12))
        entry.pack(fill='x', ipady=6)
        def open_generator():
            if not value.get().strip():
                messagebox.showinfo('Choose a topic', 'Enter a topic such as gardening or space.', parent=self)
                entry.focus_set()
                return
            from word_search_creator import BackgroundGeneratorDialog
            BackgroundGeneratorDialog(self.app, topic=value.get().strip(), palette='')
        ttk.Button(card, text='Open existing cover generator', command=open_generator, style='Primary.TButton').pack(anchor='w', pady=(12, 0))
        self._card(body, 'Design a book cover', 'Choose the saved book first so its title, puzzle type, artwork, and print specifications stay together.', self.show_books, 'Choose a book')

    def show_settings(self):
        body = self._new_page('Settings', 'Make the Studio comfortable', 'The everyday workflow stays simple. Detailed production and maintenance tools remain available here.')
        appearance = ttk.LabelFrame(body, text='Appearance', padding=14)
        appearance.pack(fill='x', pady=(0, 16))
        for name in ('Studio Dark', 'Paper Light', 'Neon Code Rain', 'Midnight Indigo'):
            ttk.Radiobutton(appearance, text=name, variable=self.app.ui_theme, value=name, command=self.app._apply_ui_theme).pack(anchor='w', pady=3)
        ai = ttk.LabelFrame(body, text='Assistant', padding=14)
        ai.pack(fill='x', pady=(0, 16))
        self.provider_choice = tk.StringVar(self, self.provider)
        for name, label in (('Codex', 'Codex — existing ChatGPT sign-in (online)'), ('Ollama', 'Ollama — installed model on this computer'), ('Guide', 'Guide — no AI')):
            ttk.Radiobutton(ai, text=label, variable=self.provider_choice, value=name, command=self._select_provider).pack(anchor='w', pady=3)
        ttk.Label(ai, text='Requests go only to your selected provider. No API billing or automatic fallback. Codex cover review sends up to two cover previews.', wraplength=650).pack(anchor='w', pady=8)
        self.ai_note = tk.StringVar(self, 'Selected: ' + self.provider + '. Requests are sent only after you submit.')
        ttk.Label(ai, textvariable=self.ai_note, wraplength=650).pack(anchor='w')
        self.models_frame = ttk.Frame(ai)
        self.models_frame.pack(fill='x', pady=8)
        self.model_choice = tk.StringVar(self, self.model)
        self.find_models_button = ttk.Button(ai, text='Find installed local models', command=self._find_models)
        self.find_models_button.pack(anchor='w', pady=5)
        ttk.Button(ai, text='Use guide mode', command=self._disable_ai).pack(anchor='w', pady=5)
        self._card(body, 'Detailed production tools', 'Open the existing workspace for word-bank management, batches, series, metadata, marketplace handoffs, and recovery.', lambda: self.app._ensure_advanced_workspace(show=True), 'Open advanced workspace')
        ttk.Button(body, text='Check this computer', command=self._check_computer, style='Primary.TButton').pack(anchor='w', pady=10)
        from .studio_family_trial import FamilyPractice
        self._card(body, 'Try it with your family', 'Three short practice tasks using manual controls. Save what was easy or confusing, without AI calls.', lambda: FamilyPractice(self.app, self.app.APP_DIR), 'Open family practice')
        self._card(body, 'Help with a problem', 'Read the existing startup and application error logs when a tool cannot complete its work.', self.app._open_error_log, 'Open error log')

    def _check_computer(self):
        self.app.status.set('Checking local runtime, artwork and Ollama…')
        root = Path(getattr(self.app, 'APP_DIR', Path(__file__).resolve().parents[1]))
        results = self.results
        def work():
            try:
                from .studio_health import collect_readiness, readiness_text
                results.put(('health', readiness_text(collect_readiness(root))))
            except Exception as exc: results.put(('health', f'The readiness check failed: {exc}'))
        threading.Thread(target=work, daemon=True).start()

    def _find_models(self):
        self.find_models_button.configure(state='disabled')
        self.ai_note.set('Checking Ollama on this computer…')
        epoch = self.epoch
        results = self.results
        def work():
            try: results.put(('models', (epoch, LocalAssistant().models(), '')))
            except Exception as exc: results.put(('models', (epoch, [], str(exc))))
        threading.Thread(target=work, daemon=True).start()

    def _enable_model(self):
        self.model = self.model_choice.get()
        self.local_ai_enabled = bool(self.model)
        self.provider_choice.set('Ollama')
        self._select_provider()
        self.ai_note.set(f'Local AI selected: {self.model}. Requests are sent only to Ollama on this computer.')
        self.refresh_style()

    def _disable_ai(self):
        self._auto_ai = False
        self.local_ai_enabled = False
        self.provider_choice.set('Guide')
        self._select_provider()
        self.ai_note.set('Guide mode is active. All creation buttons remain available.')
        self.refresh_style()

    def _select_provider(self):
        self.cancel_request()
        for cancel in self._cover_cancels: cancel.set()
        self._cover_cancels = []
        self.provider = self.provider_choice.get()
        self.local_ai_enabled = self.provider == 'Ollama' and bool(self.model)
        self._auto_ai = False
        self.app._app_preferences['assistant_provider'] = self.provider
        self.ai_note.set('Selected: ' + self.provider + '. Submit or retry explicitly; your draft is retained.')
        self.refresh_style()

    def _audit_book(self, book):
        # The book snapshot fixes which saved cover this explicit request reviews.
        from .studio_cover_audit import audit_cover
        key = str(book.get('book_id') or '')
        existing = self._cover_windows.get(key)
        if existing and existing.winfo_exists():
            existing.lift()
            return
        self.context = project_context(book)
        self._schedule_session_save()
        window = tk.Toplevel(self.app)
        window.title('Cover review')
        self._cover_windows[key] = window
        from word_search_creator import fit_dialog_to_screen
        fit_dialog_to_screen(window, 820, 650, 550, 420)
        note = tk.StringVar(window, 'Reading the saved cover and print package…')
        ttk.Label(window, textvariable=note, wraplength=730, padding=12).pack(fill='x')
        text = ScrolledText(window, wrap='word', padx=14, pady=14, font=('Segoe UI', 11))
        text.pack(fill='both', expand=True)
        cancel = threading.Event()
        self._cover_cancels.append(cancel)
        results = Queue()
        provider = self.provider
        def work():
            try: results.put((audit_cover(book, provider, cancel), ''))
            except Exception as exc: results.put((None, str(exc)))
        def poll():
            if not window.winfo_exists(): return
            try: result, error = results.get_nowait()
            except Empty:
                window.after(100, poll); return
            if cancel.is_set():
                note.set('Cover review cancelled. No cover was changed.')
                return
            if error:
                note.set('Cover review could not finish. No cover was changed.')
                text.insert('1.0', error + '\nChoose another provider in Settings or use Preview and the existing cover tools.')
            else:
                from .studio_cover_audit import audit_text
                note.set('Cover review complete — suggestions only; no cover or approval was changed.')
                text.insert('1.0', audit_text(result))
                self._say('Studio', 'Cover review completed for ' + result['title'] + '. Review its findings in the cover-review window.')
            text.configure(state='disabled')
        buttons = ttk.Frame(window, padding=12); buttons.pack(fill='x')
        ttk.Button(buttons, text='Preview actual cover', command=lambda: self._preview_cover(book)).pack(side='left')
        ttk.Button(buttons, text='Open book cover tools', command=lambda: self.app._open_book_control_center(book['book_id'])).pack(side='left', padx=8)
        ttk.Button(buttons, text='Close / cancel', command=window.destroy).pack(side='right')
        def destroyed(event):
            if event.widget == window:
                cancel.set()
                self._cover_windows.pop(key, None)
        window.bind('<Destroy>', destroyed, add='+')
        threading.Thread(target=work, daemon=True).start()
        window.after(100, poll)

    def _poll(self):
        try:
            while True:
                kind, value = self.results.get_nowait()
                if kind=='unfinished_drafts':
                    self._receive_unfinished_drafts(*value)
                elif kind == 'request_result':
                    ticket, intent, scope, error = value
                    if not self.request_gate.accepts(ticket, self.provider, self.context):
                        if ticket == self.request_gate.active:
                            self.cancel_request()
                            self._say('Studio', 'The selected project changed. Submit again for the current project.')
                        continue
                    self.cancel_request()
                    if error:
                        self._say('Studio', error + ' Your selected provider and draft are unchanged. Use Settings to choose another provider, or retry explicitly.')
                        self.retry_button.grid(row=5, column=0, sticky='w', pady=8)
                    else:
                        self._proposal_context = scope
                        self._receive_intent(intent)
                elif kind=='wordsearch_plan_result':
                    ticket,plan,context,error=value
                    if not self.request_gate.accepts(ticket,self.provider,self.context):
                        if ticket==self.request_gate.active:self.cancel_request()
                        continue
                    self.cancel_request()
                    if error:self._say('Studio','Word Search plan needs attention: '+error+' No book was generated and no source content was approved.')
                    else:self._show_chat_creation_plan(plan,context)
                elif kind in ('holiday_plan_result','holiday_reuse_result'):
                    ticket,result,error=value
                    if not self.request_gate.accepts(ticket,self.provider,self.context):
                        if ticket==self.request_gate.active:self.cancel_request()
                        continue
                    self.cancel_request()
                    if error:self._say('Studio','Holiday request needs attention: '+error+' No duplicate book or approval was created.')
                    elif kind=='holiday_plan_result':
                        from .studio_holiday_reuse import holiday_reuse_text
                        self._holiday_reuse_plan=result
                        self.proposal_text.set(holiday_reuse_text(result));self.proposal.grid()
                        self.proposal_button.configure(text='Use existing holiday book')
                        self._say('Studio',holiday_reuse_text(result))
                    else:
                        self._holiday_reuse_plan=None
                        self.context={key:result[key] for key in ('book_id','title','topic','kind')}
                        self._proposal_context=dict(self.context)
                        self._say('Studio',f"Reused existing fixed holiday book: {result['title']}, 200 puzzles, {result['pages']} pages. Actual local QA/preflight passed. The same catalog book is selected; no duplicate was generated. Owner and platform review remain pending. Ask Show me the interior or Prepare the KDP files.")
                elif kind=='revision_plan_result':
                    self._receive_revision_plan(*value)
                elif kind=='project_query_result':
                    self._receive_project_query_result(*value)
                elif kind=='theme_query_result':
                    ticket,text,error=value
                    if not self.request_gate.accepts(ticket,self.provider,self.context):
                        if ticket==self.request_gate.active:self.cancel_request()
                        continue
                    self.cancel_request()
                    self._say('Studio',('Theme catalog could not finish: '+error) if error else text)
                elif kind=='book_adoption_result':
                    ticket,result,error=value
                    self._finish_revision_worker(ticket)
                    if not self.request_gate.accepts(ticket,self.provider,self.context):
                        if ticket==self.request_gate.active:self.cancel_request()
                        continue
                    self.cancel_request()
                    if error:self._say('Studio','Adoption needs attention: '+error+' Use Continue unfinished work to reopen the decision.')
                    else:self._receive_adopted_revision(result)
                elif kind=='book_revision_result':
                    ticket,result,error=value
                    self._finish_revision_worker(ticket)
                    if not self.request_gate.accepts(ticket,self.provider,self.context):
                        if ticket==self.request_gate.active:self.cancel_request()
                        continue
                    self.cancel_request()
                    if error:self._say('Studio','Staged revision needs attention: '+error+' Original files and the recovery draft are preserved.')
                    else:self._receive_staged_revision(result)
                elif kind=='book_creation_progress':
                    ticket,message=value
                    if self.request_gate.accepts(ticket,self.provider,self.context):
                        self.mode.set(message+' Cancel dismisses this response; production and its recovery draft continue.')
                elif kind=='book_creation_result':
                    ticket,result,error=value
                    self._finish_build_stop(ticket)
                    if not self.request_gate.accepts(ticket,self.provider,self.context):
                        if ticket==self.request_gate.active:self.cancel_request()
                        continue
                    self.cancel_request()
                    if error:self._say('Studio','Creation needs attention: '+error+' The saved draft and any generated files are preserved. Use Open my last project to review or resume.')
                    else:self._receive_created_book(result)
                elif kind in ('book_check_result','book_export_result'):
                    ticket, result, error = value
                    if not self.request_gate.accepts(ticket, self.provider, self.context):
                        if ticket == self.request_gate.active:
                            self.cancel_request()
                            self._say('Studio', 'The selected project changed. Submit the check again for the current book.')
                        continue
                    self.cancel_request()
                    if error:
                        self._say('Studio', 'The local book check could not finish: ' + error)
                    else:
                        from .studio_book_checks import book_check_text, book_export_text
                        self._say('Studio', (book_export_text if kind=='book_export_result' else book_check_text)(result))
                elif kind == 'health':
                    window = tk.Toplevel(self.app)
                    window.title('This computer — readiness check')
                    window.geometry('720x560')
                    text = ScrolledText(window, wrap='word', padx=16, pady=16)
                    text.pack(fill='both', expand=True)
                    text.insert('1.0', value)
                    text.configure(state='disabled')
                    self.app.status.set('Readiness check complete. No files were changed.')
                elif kind == 'startup_models':
                    if self._auto_ai and not self.local_ai_enabled and len(value) == 1:
                        self.model = value[0]
                        self.provider = 'Ollama'
                        self.local_ai_enabled = True
                        self.refresh_style()
                    elif self._auto_ai and not self.local_ai_enabled and len(value) > 1:
                        self.mode.set('Local Ollama is available · choose an installed model in Settings')
                elif kind == 'books':
                    epoch, books, error = value
                    if epoch != self.epoch: continue
                    self.catalog = books
                    self._filter_books()
                    if self._open_latest:
                        self._open_latest = False
                        if books: self._open_selected_book(max(books, key=lambda book: str(book.get('updated_at') or '')))
                        else: self._say('Studio', 'No saved project is available yet. Use Create to start one.')
                    if error:
                        for child in self.book_rows.winfo_children(): child.destroy()
                        ttk.Label(self.book_rows, text='Your catalog could not be read. No books were changed. ' + error, wraplength=650).pack(anchor='w')
                elif kind == 'models':
                    epoch, models, error = value
                    if epoch != self.epoch: continue
                    self.find_models_button.configure(state='normal')
                    for child in self.models_frame.winfo_children(): child.destroy()
                    for model in models:
                        ttk.Radiobutton(self.models_frame, text=model, variable=self.model_choice, value=model, command=self._enable_model).pack(anchor='w', pady=3)
                    self.ai_note.set(error or ('Choose a model above. No downloads will occur.' if models else 'No installed local models were found. Guide mode remains available.'))
        except Empty: pass
        self._poll_job = self.after(100, self._poll)


class TopicPicker(tk.Toplevel):
    """Search every existing topic and pack without exposing word maintenance."""
    def __init__(self, parent, choose):
        super().__init__(parent)
        self.title('Browse all topics')
        from word_search_creator import fit_dialog_to_screen
        fit_dialog_to_screen(self, 700, 620)
        self.choose = choose
        self.rows = []
        self.visible = []
        self.results = Queue()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Choose a topic', style='Family.Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Search any group. The Studio chooses and checks the words for you.', wraplength=620).pack(anchor='w', pady=8)
        self.query = tk.StringVar(self)
        entry = ttk.Entry(frame, textvariable=self.query, font=('Segoe UI', 12))
        entry.pack(fill='x', pady=8)
        self.query.trace_add('write', lambda *args: self._filter())
        box = ttk.Frame(frame); box.pack(fill='both', expand=True)
        self.listbox = tk.Listbox(box, font=('Segoe UI', 11), exportselection=False)
        scrollbar = ttk.Scrollbar(box, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); self.listbox.pack(fill='both', expand=True)
        self.listbox.bind('<Double-Button-1>', lambda event: self._choose())
        self.note = tk.StringVar(self, 'Reading the existing topic groups…')
        ttk.Label(frame, textvariable=self.note, wraplength=620).pack(anchor='w', pady=8)
        ttk.Button(frame, text='Use this topic', command=self._choose, style='Primary.TButton').pack(anchor='e')
        results = self.results
        def load():
            try:
                from word_search_creator import load_master_word_bank
                bank = load_master_word_bank()
                families = {name: family for family, names in (bank.get('pack_families') or {}).items() for name in names}
                rows = [(f"Topics / {name}", name) for name in bank.get('topics', {})]
                rows += [(f"{families.get(name, 'Topic packs')} / {name}", name) for name in bank.get('topic_packs', {})]
                results.put((sorted(rows, key=lambda item: item[0].casefold()), ''))
            except Exception as exc: results.put(([], str(exc)))
        threading.Thread(target=load, daemon=True).start()
        self._job = self.after(100, self._poll)
        self.bind('<Destroy>', self._cancel, add='+')
        entry.focus_set()

    def _filter(self):
        terms = self.query.get().casefold().split()
        self.visible = [row for row in self.rows if all(term in row[0].casefold() for term in terms)]
        self.listbox.delete(0, 'end')
        for label, name in self.visible: self.listbox.insert('end', label)
        self.note.set(f'{len(self.visible)} of {len(self.rows)} groups. Words are chosen automatically; readiness is checked when you continue.')

    def _choose(self):
        selection = self.listbox.curselection()
        if selection:
            self.choose(self.visible[selection[0]][1]); self.destroy()

    def _poll(self):
        try: self.rows, error = self.results.get_nowait()
        except Empty: self._job = self.after(100, self._poll)
        else:
            self._job = None
            self._filter()
            if error: self.note.set('Topics could not be loaded: ' + error)

    def _cancel(self, event):
        if event.widget == self and self._job: self.after_cancel(self._job)


class FamilyBookDialog(tk.Toplevel):
    """Two choices followed by the existing checked creation route."""
    def __init__(self, app, intent=None, draft_store=None, draft_id=None, initial_reader='standard', initial_balance='Balanced'):
        super().__init__(app)
        self.app = app
        self.draft_store, self.draft_id = draft_store, draft_id
        self._draft_job = None
        self.reader_choice = tk.StringVar(self, READER_PROFILES[initial_reader]['label'])
        self.balance_choice = tk.StringVar(self, initial_balance)
        self.title('Plan a puzzle book')
        from word_search_creator import fit_dialog_to_screen
        fit_dialog_to_screen(self, 790, 700)
        self.transient(app)
        self.source_groups = intent.source_groups if intent else ()
        self._source_topic = intent.topic if intent else ''
        self.kind = tk.StringVar(self, intent.kind if intent else 'Word Search')
        self.topic = tk.StringVar(self, intent.topic if intent else '')
        page = ScrollPage(self)
        page.pack(fill='both', expand=True)
        body = page.body
        ttk.Label(body, text='Let’s plan your book', style='Family.Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='First choose the puzzle type. Then tell us what it is about.', style='Family.Body.TLabel', wraplength=650).pack(anchor='w', pady=(6, 20))
        for kind in BOOK_TYPES:
            ttk.Radiobutton(body, text=kind, variable=self.kind, value=kind, style='Family.Option.TRadiobutton').pack(fill='x', pady=4)
        ttk.Label(body, text='What is the topic?', style='Family.Body.TLabel').pack(anchor='w', pady=(20, 6))
        ttk.Entry(body, textvariable=self.topic, font=('Segoe UI', 13)).pack(fill='x', ipady=6)
        prefs = ttk.LabelFrame(body, text='Reader and theme mix', padding=10); prefs.pack(fill='x', pady=8)
        ttk.Label(prefs, text='Reader profile (Word Search)').pack(anchor='w')
        ttk.Combobox(prefs, textvariable=self.reader_choice, values=tuple(READER_LABELS), state='readonly').pack(fill='x', pady=3)
        ttk.Label(prefs, text='Theme balance').pack(anchor='w')
        ttk.Combobox(prefs, textvariable=self.balance_choice, values=BALANCES, state='readonly').pack(fill='x', pady=3)
        suggestions = ttk.Frame(body, style='App.TFrame')
        self.suggestions = suggestions
        suggestions.pack(fill='x', pady=10)
        for name in ('Space & Astronomy', 'Gardening', 'Travel and Geography'):
            ttk.Button(suggestions, text=name, command=lambda value=name: self.topic.set(value)).pack(anchor='w', pady=3)
        ttk.Button(suggestions, text='Browse all topics', command=lambda: TopicPicker(self, self.topic.set)).pack(anchor='w', pady=6)
        self.note = tk.StringVar(self, 'The next step uses the existing content, cover, and production checks. Nothing is published automatically.')
        ttk.Label(body, textvariable=self.note, wraplength=650).pack(anchor='w', pady=12)
        actions = ttk.Frame(self, padding=16, style='Family.Card.TFrame')
        actions.pack(fill='x')
        self.continue_button = ttk.Button(actions, text='Continue to book plan', command=self.continue_to_plan, style='Primary.TButton')
        self.continue_button.pack(side='right')
        ttk.Button(actions, text='Back', command=self._close).pack(side='left')
        self.protocol('WM_DELETE_WINDOW', self._close)
        if draft_id and draft_store:
            draft = draft_store.load(draft_id)
            if draft:
                self.kind.set(draft['payload'].get('kind', 'Word Search'))
                self.topic.set(draft['payload'].get('topic', ''))
                self._source_topic = self.topic.get()
                self.source_groups = tuple(draft['payload'].get('source_groups') or ())
                self.reader_choice.set(READER_PROFILES[draft['payload'].get('reader_profile', 'standard')]['label'])
                self.balance_choice.set(draft['payload'].get('theme_balance', 'Balanced'))
        for variable in (self.kind, self.topic, self.reader_choice, self.balance_choice): variable.trace_add('write', self._schedule_draft)
        self.bind('<Destroy>', self._cancel_draft, add='+')

    def _schedule_draft(self, *args):
        if self._draft_job: self.after_cancel(self._draft_job)
        self._draft_job = self.after(800, self.flush_draft)

    def flush_draft(self):
        if not self.draft_store: return True
        if self._draft_job:
            self.after_cancel(self._draft_job)
            self._draft_job = None
        try:
            form = {'reader_profile': READER_LABELS[self.reader_choice.get()], 'theme_balance': self.balance_choice.get(), 'kind': self.kind.get(), 'topic': self.topic.get(), 'source_groups': list(self.source_groups) if self.topic.get() == self._source_topic else []}
            previous = self.draft_store.load(self.draft_id) if self.draft_id else None
            if previous and all(previous['payload'].get(key) == value for key, value in form.items()):
                form = previous['payload'] | form
            self.draft_id = self.draft_store.save(self.draft_id, 'book_plan', form)
            return True
        except Exception as exc:
            self.note.set(f'Draft could not be saved: {exc}')
            return False

    def _cancel_draft(self, event):
        if event.widget == self and self._draft_job:
            self.after_cancel(self._draft_job)
            self._draft_job = None

    def _close(self):
        if self.flush_draft(): self.destroy()

    def continue_to_plan(self):
        topic, kind = self.topic.get().strip(), self.kind.get()
        if not topic:
            self.note.set('Add a topic, or choose one of the suggestions above.')
            return
        if len(topic) > 80:
            self.note.set('Please keep the topic to 80 characters or fewer.')
            return
        # Unsupported word-based themes must not silently become general content.
        if kind != 'Word Search':
            if READER_LABELS[self.reader_choice.get()] != 'standard' and kind != 'Sudoku':
                self.note.set('The child reader profiles support Word Search books. Choose Word Search or Standard and review the other content manually.'); return
            if self.source_groups:
                self.note.set('Combining word groups is available for Word Search books. Choose Word Search to use this mix; the other book types use their own supported themes.')
                return
            from puzzle_book_studio import AVAILABLE_THEMES
            if kind == 'Sudoku': topic = 'General Starter'
            elif topic not in AVAILABLE_THEMES:
                self.note.set('This puzzle type needs an existing content theme. Choose one below; the topic will not be silently replaced.')
                if not hasattr(self, 'theme_choices'):
                    for child in self.suggestions.winfo_children(): child.destroy()
                    self.theme_choices = self.suggestions
                    for name in AVAILABLE_THEMES:
                        if name == 'General Starter': continue
                        ttk.Radiobutton(self.theme_choices, text=name, variable=self.topic, value=name).pack(anchor='w', pady=3)
                return
        if not self.flush_draft(): return
        self.continue_button.configure(state='disabled')
        self.note.set('Opening the checked book plan…')
        self.update_idletasks()
        try:
            self.app._ensure_advanced_workspace(show=False)
            if kind == 'Word Search':
                from word_search_creator import GuidedBookBuilderDialog
                editor = GuidedBookBuilderDialog(self.app, initial_topic=topic, initial_pack=topic, initial_count=48, simple_mode=True, initial_sources=self.source_groups if topic == self._source_topic else (), initial_reader=READER_LABELS[self.reader_choice.get()], initial_balance=self.balance_choice.get())
                from .studio_recovery import attach_book_recovery
                attach_book_recovery(editor, self.draft_store, self.draft_id, kind, topic,
                    {'title': editor.title_value, 'subtitle': editor.subtitle, 'topic': editor.topic}, editor.words)
            else:
                from puzzle_book_studio import PuzzleBookStudio
                editor = PuzzleBookStudio(self.app, initial_kind=kind, initial_theme=topic, simple_mode=True)
                if READER_LABELS[self.reader_choice.get()] != 'standard' and kind == 'Sudoku': editor.difficulty.set('easy')
                from .studio_recovery import attach_book_recovery
                attach_book_recovery(editor, self.draft_store, self.draft_id, kind, topic,
                    {'title': editor.book_title, 'subtitle': editor.subtitle, 'count': editor.count, 'difficulty': editor.difficulty,
                     'cover_style': editor.cover_style, 'cover_photo': editor.cover_photo, 'interior': editor.interior_style,
                     'bonuses': editor.bonus_enabled})
        except Exception as exc:
            self.note.set(f'The plan could not open: {exc}')
            self.continue_button.configure(state='normal')
            return
        self.destroy()


def build_simple_wordsearch(dialog):
    """Present the existing word-search plan/check/approval methods calmly."""
    from word_search_creator import scrollable_dialog_page
    frame = scrollable_dialog_page(dialog, padding=22)
    ttk.Label(frame, text='Your Word Search book', style='Family.Title.TLabel').pack(anchor='w')
    ttk.Label(frame, text='Review the suggested plan. Detailed word and layout choices are optional.', wraplength=700).pack(anchor='w', pady=(6, 16))
    topic = ttk.LabelFrame(frame, text='Topic', padding=12)
    topic.pack(fill='x', pady=(0, 12))
    ttk.Label(topic, textvariable=dialog.topic, font=('Segoe UI', 14, 'bold')).pack(anchor='w')
    ttk.Label(topic, textvariable=dialog.explanation, wraplength=700, justify='left').pack(anchor='w', pady=8)
    dialog.short_pack_button = ttk.Button(topic, text='Make a shorter activity pack', command=lambda: dialog.parent.family_studio.open_pack(AssistantIntent(action='create_pack', topic=dialog.topic.get(), source_groups=getattr(dialog, '_family_source_groups', ()))))
    ttk.Button(topic, text='Choose another topic', command=lambda: TopicPicker(dialog, dialog._load_family_topic)).pack(anchor='w', pady=5)
    ttk.Label(frame, text='Book title').pack(anchor='w')
    ttk.Entry(frame, textvariable=dialog.title_value, font=('Segoe UI', 12)).pack(fill='x', ipady=6, pady=(5, 12))
    detail = ttk.Frame(frame)
    def toggle():
        detail.pack_forget() if detail.winfo_manager() else detail.pack(fill='x', pady=12, before=review)
    ttk.Button(frame, text='Change topic or book details', command=toggle).pack(anchor='w', pady=8)
    dialog.reader_style = tk.StringVar(dialog, READER_PROFILES[dialog._reader_profile]['label'])
    dialog.balance_style = tk.StringVar(dialog, dialog._theme_balance)
    def refresh_mix(event=None):
        dialog._reader_profile = READER_LABELS[dialog.reader_style.get()]
        dialog._theme_balance = dialog.balance_style.get()
        dialog._load_family_topic(dialog.topic.get(), getattr(dialog, '_family_source_groups', ()))
    ttk.Label(detail, text='Reader profile').pack(anchor='w')
    reader = ttk.Combobox(detail, textvariable=dialog.reader_style, values=tuple(READER_LABELS), state='readonly')
    reader.pack(fill='x', pady=3); reader.bind('<<ComboboxSelected>>', refresh_mix)
    ttk.Label(detail, text='Theme balance').pack(anchor='w')
    mix = ttk.Combobox(detail, textvariable=dialog.balance_style, values=BALANCES, state='readonly')
    mix.pack(fill='x', pady=3); mix.bind('<<ComboboxSelected>>', refresh_mix)
    ttk.Label(detail, text='Choose another reviewed topic').pack(anchor='w')
    choices = tk.Listbox(detail, height=5, exportselection=False)
    for label in dict.fromkeys((*dialog.master_library.get('topics', {}), *dialog.pack_choice_map)): choices.insert('end', label)
    choices.pack(fill='x', pady=5)
    def choose():
        selection = choices.curselection()
        if selection:
            dialog.topic_pack.set(choices.get(selection[0]))
            dialog._load_topic_pack(automatic=True)
    ttk.Button(detail, text='Use selected topic', command=choose).pack(anchor='w')
    for label, variable in (('Topic', dialog.topic), ('Subtitle', dialog.subtitle)):
        ttk.Label(detail, text=label).pack(anchor='w', pady=(8, 3))
        ttk.Entry(detail, textvariable=variable).pack(fill='x')
    dialog.words = ScrolledText(detail, height=7, wrap='word')
    dialog.words.pack(fill='x', pady=8)
    dialog.words.bind('<KeyRelease>', lambda event: dialog.recommend())
    # Custom vocabulary remains available in the Advanced workspace.
    dialog.words.pack_forget()
    ttk.Label(detail, text='The full word-bank and production tools remain in Settings → Advanced workspace.', wraplength=650).pack(anchor='w', pady=8)
    review = ttk.LabelFrame(frame, text='Book plan', padding=14)
    review.pack(fill='x', pady=12)
    ttk.Label(review, textvariable=dialog.review, wraplength=700, justify='left').pack(anchor='w')
    ttk.Button(frame, text='Review my book plan', command=dialog.create, style='Primary.TButton').pack(anchor='w', pady=8)
    dialog.approve = ttk.Button(frame, text='Approve plan and create checked package', command=dialog.approve_package, state='disabled', style='Primary.TButton')
    dialog.approve.pack(anchor='w', pady=8)
    ttk.Label(frame, textvariable=dialog.status, wraplength=700).pack(anchor='w', pady=12)
    def invalidate(*args):
        if dialog.created_path:
            dialog.created_path = None
            dialog.approve.configure(state='disabled')
            dialog.review.set('The plan changed. Review it again before creating a package.')
    for variable in (dialog.title_value, dialog.subtitle, dialog.topic): variable.trace_add('write', invalidate)
    # If the requested topic cannot be matched, make its recovery controls visible.
    from word_search_creator import resolve_topic_pack_choice
    if not resolve_topic_pack_choice(dialog.topic.get(), dialog.pack_choice_map):
        detail.pack(fill='x', pady=12, before=review)


def build_simple_puzzle_studio(studio):
    from word_search_creator import scrollable_dialog_page
    from puzzle_book_studio import COVER_STYLE_OPTIONS, INTERIOR_PRESETS
    root = scrollable_dialog_page(studio, padding=22)
    ttk.Label(root, text=f'Your {studio.kind.get()} book', style='Family.Title.TLabel', wraplength=750).pack(anchor='w')
    ttk.Label(root, text=f'Theme: {studio.theme.get()}. Cover artwork, layout, and proofing use the established Studio pipeline.', wraplength=700).pack(anchor='w', pady=(6, 18))
    studio.kind_buttons = {}
    for label, variable in (('Book title', studio.book_title), ('Subtitle', studio.subtitle)):
        ttk.Label(root, text=label).pack(anchor='w', pady=(8, 4))
        ttk.Entry(root, textvariable=variable, font=('Segoe UI', 12)).pack(fill='x', ipady=6)
    ttk.Label(root, text='The Studio recommends the puzzle count, interior, and matching cover. You can change them below.', wraplength=700).pack(anchor='w', pady=14)
    advanced = ttk.Frame(root)
    def toggle():
        advanced.pack_forget() if advanced.winfo_manager() else advanced.pack(fill='x', pady=10, before=actions)
    ttk.Button(root, text='Optional design and puzzle settings', command=toggle).pack(anchor='w')
    for label, variable, values in (
        ('Puzzle count', studio.count, None), ('Difficulty', studio.difficulty, ('Easy','Mixed','Standard','Hard')),
        ('Cover layout', studio.cover_style, tuple(COVER_STYLE_OPTIONS)), ('Interior', studio.interior_style, tuple(INTERIOR_PRESETS))):
        row = ttk.Frame(advanced)
        row.pack(fill='x', pady=5)
        ttk.Label(row, text=label, width=18).pack(side='left')
        widget = ttk.Entry(row, textvariable=variable) if values is None else ttk.Combobox(row, textvariable=variable, values=values, state='readonly')
        widget.pack(side='left', fill='x', expand=True)
        if label=='Difficulty':studio.difficulty_box=widget
    studio._sync_difficulty_control()
    ttk.Checkbutton(advanced, text='Include reader bonus pages', variable=studio.bonus_enabled).pack(anchor='w', pady=8)
    ttk.Button(advanced, text='Browse existing cover choices', command=studio._open_cover_gallery).pack(anchor='w')
    studio.art_note = ttk.Label(advanced, wraplength=700)
    studio.art_note.pack(anchor='w', pady=8)
    actions = ttk.LabelFrame(root, text='Review and create', padding=14)
    actions.pack(fill='x', pady=18)
    ttk.Button(actions, text='Review my book plan', command=studio._review, style='Primary.TButton').pack(anchor='w', pady=5)
    ttk.Button(actions, text='Create checked package', command=studio._create, style='Primary.TButton').pack(anchor='w', pady=5)
    ttk.Button(actions, text='Open last package', command=studio._open_last_package).pack(anchor='w', pady=5)
    ttk.Button(actions, text='Open proof report', command=studio._open_proof).pack(anchor='w', pady=5)
    ttk.Label(root, textvariable=studio.status, wraplength=700).pack(anchor='w', pady=12)
    studio._changed()
