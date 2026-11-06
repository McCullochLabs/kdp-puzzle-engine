"""Bounded conversation snapshots in the existing versioned recovery store.

Only a canonical book ID and optional pending-revision ID are saved as context.
Plans, approvals, paths and prior QA assertions are never restored as actions.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .studio_recovery import StudioDraftStore

SESSION_ID = 'studio-conversation-v1'


class _SessionStore(StudioDraftStore):
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=.2)
        connection.row_factory = sqlite3.Row
        return connection


def _messages(messages):
    if not isinstance(messages, list):
        raise ValueError('Saved conversation messages are invalid.')
    result = []
    for message in messages[-20:]:
        if not isinstance(message, dict) or message.get('role') not in ('You', 'Studio') or not isinstance(message.get('text'), str):
            raise ValueError('Saved conversation messages are invalid.')
        result.append({'role': message['role'], 'text': message['text'][:1000]})
    return result


def save_session(root, context, messages):
    selected = None
    if context and context.get('book_id'):
        identity = context['book_id']
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 200 or any(ord(c) < 32 for c in identity):
            raise ValueError('The selected project identity is invalid.')
        selected = {'book_id': identity}
        pending = context.get('pending_semantic_revision')
        if pending:
            revision = pending.get('revision_id') if isinstance(pending, dict) else None
            if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{32}', revision):
                raise ValueError('The pending revision identity is invalid.')
            selected['pending_semantic_revision'] = {'revision_id': revision}
    # Completed=True keeps this snapshot out of the unfinished-book queue.
    return _SessionStore(Path(root)/'data/books.db').save(
        SESSION_ID, 'book_plan', {'studio_session': {'version': 1, 'context': selected,
                                                   'messages': _messages(messages)}}, completed=True)


def load_session(root):
    root = Path(root).resolve()
    catalog = root/'data/books.db'
    if not catalog.is_file():
        return None
    with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro', uri=True, timeout=.2)) as db:
        db.row_factory = sqlite3.Row
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'studio_drafts', 'studio_draft_versions'}.issubset(tables):
            return None
        def draft(identity):
            row = db.execute('SELECT v.payload FROM studio_drafts d JOIN studio_draft_versions v USING(draft_id,revision) WHERE d.draft_id=?', (identity,)).fetchone()
            return json.loads(row[0]) if row else None
        payload = draft(SESSION_ID)
        if payload is None:
            return None
        saved = payload.get('studio_session', {})
        if saved.get('version') != 1:
            raise ValueError('The saved conversation version is unsupported.')
        result = {'messages': _messages(saved.get('messages')), 'context': None,
                  'pending_result': None, 'warnings': []}
        context = saved.get('context')
        if context is None:
            return result
        if not isinstance(context, dict) or not isinstance(context.get('book_id'), str):
            raise ValueError('The saved project identity is invalid.')
        if 'books' not in tables:
            result['warnings'].append('The saved project catalog is unavailable; no project was selected.')
            return result
        row = db.execute('SELECT book_id,metadata_json,package_path FROM books WHERE book_id=?', (context['book_id'],)).fetchone()
        if row is None:
            result['warnings'].append('The saved project is no longer in the catalog; no project was selected.')
            return result
        metadata = json.loads(row['metadata_json'])
        if not isinstance(metadata, dict):
            raise ValueError('The selected project metadata needs review.')
        from .studio_assistant import project_context
        result['context'] = project_context({'book_id': row['book_id'], 'metadata': metadata})
        pending = context.get('pending_semantic_revision')
        if pending:
            revision = pending.get('revision_id') if isinstance(pending, dict) else None
            if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{32}', revision):
                raise ValueError('The saved pending revision identity is invalid.')
            record = (draft(revision) or {}).get('chat_revision', {})
            plan = record.get('plan', {})
            if plan.get('source_book_id') != row['book_id'] or plan.get('revision_id') != revision:
                raise ValueError('The pending revision no longer belongs to the saved project.')
            status = record.get('status')
            if status == 'complete':
                digest = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                candidate = record.get('result', {})
                if (record.get('confirmation') != {'source': 'studio_chat.revision_button', 'plan_sha256': digest}
                        or candidate.get('source_book_id') != row['book_id'] or candidate.get('revision_id') != revision
                        or not candidate.get('candidate_sha256')):
                    raise ValueError('The pending revision confirmation is invalid.')
                result['context']['pending_semantic_revision'] = {'revision_id': revision, 'title': str(plan.get('title') or 'Pending revision')}
                result['pending_result'] = candidate
            elif status == 'adopted':
                adopted = record.get('adoption_result', {})
                if adopted.get('book_id') != row['book_id'] or Path(str(adopted.get('folder') or '')).resolve() != Path(str(row['package_path'] or '')).resolve():
                    raise ValueError('The accepted revision does not match the saved project.')
            elif status != 'rejected':
                raise ValueError('The pending revision needs explicit recovery; no original project was silently selected.')
        return result
