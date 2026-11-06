"""Versioned unfinished forms in the existing catalog database."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


class StudioDraftStore:
    def __init__(self, database_path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS studio_drafts (draft_id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS studio_draft_versions (draft_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(draft_id, revision))')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def save(self, draft_id, kind, payload, completed=False):
        if kind not in ('activity_pack', 'book_plan') or not isinstance(payload, dict):
            raise ValueError('Unsupported draft.')
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(raw.encode('utf-8')) > 256000:
            raise ValueError('This draft is too large to autosave. Reduce the word list.')
        draft_id = draft_id or uuid.uuid4().hex
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT d.*, v.payload FROM studio_drafts d JOIN studio_draft_versions v USING(draft_id, revision) WHERE draft_id=?', (draft_id,)).fetchone()
            if current and current['kind'] != kind:
                raise ValueError('Draft type does not match the saved work.')
            if current and current['payload'] == raw and bool(current['completed']) == completed:
                return draft_id
            revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM studio_draft_versions WHERE draft_id=?', (draft_id,)).fetchone()[0]
            db.execute('INSERT INTO studio_draft_versions VALUES (?,?,?)', (draft_id, revision, raw))
            db.execute('INSERT INTO studio_drafts VALUES (?,?,?,?,?) ON CONFLICT(draft_id) DO UPDATE SET revision=excluded.revision, updated_at=excluded.updated_at, completed=excluded.completed',
                       (draft_id, kind, revision, datetime.now(timezone.utc).isoformat(), int(completed)))
        return draft_id

    def load(self, draft_id):
        with closing(self._connect()) as db:
            row = db.execute('SELECT d.*, v.payload FROM studio_drafts d JOIN studio_draft_versions v USING(draft_id, revision) WHERE draft_id=?', (draft_id,)).fetchone()
            if row:
                result = dict(row)
                result['payload'] = json.loads(result['payload'])
                return result

    def pending(self, *, offset=0):
        if type(offset) is not int or not 0<=offset<=1000000:
            raise ValueError('Invalid unfinished draft page.')
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute('SELECT draft_id,kind,revision,updated_at FROM studio_drafts WHERE completed=0 ORDER BY updated_at DESC,draft_id DESC LIMIT 20 OFFSET ?', (offset,))]

    def is_pending(self,draft_id):
        if not isinstance(draft_id,str) or not draft_id or len(draft_id)>200 or any(ord(c)<32 for c in draft_id):return False
        with closing(self._connect()) as db:
            return db.execute('SELECT 1 FROM studio_drafts WHERE draft_id=? AND completed=0',(draft_id,)).fetchone() is not None

    def undo(self, draft_id):
        """Move back through saved forms without deleting any version."""
        current = self.load(draft_id)
        if not current:
            return None
        with closing(self._connect()) as db:
            raw = json.dumps(current['payload'], sort_keys=True, ensure_ascii=False)
            row = db.execute('SELECT revision FROM studio_draft_versions WHERE draft_id=? AND revision<? AND payload<>? ORDER BY revision DESC LIMIT 1', (draft_id, current['revision'], raw)).fetchone()
        if row:
            with closing(self._connect()) as db, db:
                changed = db.execute('UPDATE studio_drafts SET revision=?,completed=0 WHERE draft_id=? AND revision=?', (row['revision'], draft_id, current['revision']))
                if changed.rowcount != 1:
                    raise ValueError('This draft changed in another window. Reopen the latest saved work before restoring an edit.')
        return self.load(draft_id)


def draft_store_for(app):
    """Use the same data root as the catalog; never create a second project DB."""
    if not hasattr(app, '_studio_drafts'):
        root = Path(getattr(app, 'APP_DIR', Path(__file__).resolve().parents[1]))
        app._studio_drafts = StudioDraftStore(root / 'data' / 'books.db')
    return app._studio_drafts


def attach_book_recovery(dialog, store, draft_id, kind, topic, fields, text_widget=None):
    """Autosave the simple book editors without changing production records."""
    if store is None: return
    state = {'job': None, 'restoring': True}
    def snapshot():
        result = {'kind': kind, 'topic': topic, 'editor': {name: variable.get() for name, variable in fields.items()}}
        if hasattr(dialog, '_reader_profile'): result.update(reader_profile=dialog._reader_profile, theme_balance=dialog._theme_balance)
        if hasattr(dialog, '_family_source_groups'): result['source_groups'] = list(dialog._family_source_groups)
        if text_widget is not None: result['words'] = text_widget.get('1.0', 'end-1c')
        return result
    def flush():
        if state['job']:
            dialog.after_cancel(state['job']); state['job'] = None
        try:
            store.save(draft_id, 'book_plan', snapshot())
            return True
        except Exception as exc:
            dialog.status.set(f'Draft could not be saved: {exc}')
            return False
    dialog.flush_draft = flush
    def schedule(*args):
        if state['restoring']: return
        if state['job']: dialog.after_cancel(state['job'])
        state['job'] = dialog.after(800, flush)
    saved = store.load(draft_id)
    if saved:
        form = saved['payload']
        for name, value in (form.get('editor') or {}).items():
            if name in fields:
                try: fields[name].set(value)
                except Exception: pass
        if text_widget is not None and 'words' in form:
            text_widget.delete('1.0', 'end'); text_widget.insert('1.0', form['words'])
    for variable in fields.values(): variable.trace_add('write', schedule)
    if text_widget is not None:
        text_widget.edit_modified(False)
        def modified(event):
            if text_widget.edit_modified():
                text_widget.edit_modified(False); schedule()
        text_widget.bind('<<Modified>>', modified, add='+')
    state['restoring'] = False
    def close():
        if getattr(dialog, '_creating', False):
            dialog._on_close()
        elif flush(): dialog.destroy()
    dialog.protocol('WM_DELETE_WINDOW', close)
    def destroyed(event):
        if event.widget == dialog and state['job']:
            dialog.after_cancel(state['job']); state['job'] = None
    dialog.bind('<Destroy>', destroyed, add='+')
