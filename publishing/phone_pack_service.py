"""Durable local family-pack projects/jobs in the existing catalog database."""
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import os
import sqlite3
import threading
import uuid

from .activity_packs import ActivityPackPlan, build_activity_pack
from .studio_pack_planning import prepare_pack_request, validate_pack_request


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class PackService:
    def __init__(self, root, database=None, output=None, *, start_worker=True):
        self.root = Path(root)
        self.database = Path(database) if database else self.root/'data/books.db'
        self.output = (Path(output) if output else self.root/'data/phone_packages').resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.worker = None
        self.worker_lock = None
        if start_worker:
            lock = open(str(self.database)+'.phone-worker.lock', 'a+b')
            if lock.seek(0, 2) == 0:
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock.close()
                raise ValueError('A Family Studio worker is already running. Open the existing Studio instead.')
            self.worker_lock = lock
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS phone_pack_projects (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, request TEXT NOT NULL, updated TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS phone_pack_versions (project TEXT NOT NULL, revision INTEGER NOT NULL, request TEXT NOT NULL, PRIMARY KEY(project,revision))')
            db.execute('CREATE TABLE IF NOT EXISTS phone_pack_jobs (id TEXT PRIMARY KEY, project TEXT NOT NULL, revision INTEGER NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, updated TEXT NOT NULL, folder TEXT, error TEXT NOT NULL DEFAULT \'\')')
            # Interrupted jobs require explicit retry. Never pretend incomplete files are ready.
            db.execute("UPDATE phone_pack_jobs SET status='interrupted',stage='Interrupted by restart',error='The Studio restarted. Your project is saved; choose Create pack to retry.',updated=? WHERE status='running'", (now(),))
        if start_worker:
            self.worker = threading.Thread(target=self.run, daemon=True, name='family-pack-worker')
            self.worker.start()

    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def save(self, request, project=None, revision=None):
        request = validate_pack_request(request, self.root)
        raw = json.dumps(request, sort_keys=True)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if project:
                row = db.execute('SELECT * FROM phone_pack_projects WHERE id=?', (project,)).fetchone()
                if not row:
                    raise ValueError('This project was not found.')
                if type(revision) is not int or row['revision'] != revision:
                    raise Conflict('This project changed in another window. Reopen the latest project before saving.')
                if row['request'] == raw:
                    return self.project(project)
                version = revision + 1
            else:
                project, version = uuid.uuid4().hex, 1
            db.execute('INSERT INTO phone_pack_projects VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,request=excluded.request,updated=excluded.updated',
                       (project, version, raw, now()))
            db.execute('INSERT INTO phone_pack_versions VALUES (?,?,?)', (project, version, raw))
        return self.project(project)

    def project(self, project):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM phone_pack_projects WHERE id=?', (project,)).fetchone()
            if not row:
                raise ValueError('This project was not found.')
            result = dict(row)
            result['request'] = json.loads(result['request'])
            jobs = db.execute('SELECT id,revision,status,stage,updated,error FROM phone_pack_jobs WHERE project=? ORDER BY updated DESC', (project,)).fetchall()
            result['jobs'] = [dict(job) for job in jobs]
            return result

    def projects(self):
        with closing(self.connect()) as db:
            ids = [row[0] for row in db.execute('SELECT id FROM phone_pack_projects ORDER BY updated DESC LIMIT 100')]
        return [self.project(project) for project in ids]

    def enqueue(self, project, revision):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM phone_pack_projects WHERE id=?', (project,)).fetchone()
            if not row or type(revision) is not int or row['revision'] != revision:
                raise Conflict('Reopen the latest project before creating a pack.')
            existing = db.execute("SELECT id FROM phone_pack_jobs WHERE project=? AND revision=? AND status IN ('queued','running','ready') ORDER BY updated DESC LIMIT 1", (project, revision)).fetchone()
            if existing:
                return existing['id']
            pending = db.execute("SELECT COUNT(*) FROM phone_pack_jobs WHERE status IN ('queued','running')").fetchone()[0]
            if pending >= 10:
                raise Conflict('Ten packs are already waiting. Let a pack finish before adding another.')
            job = uuid.uuid4().hex
            db.execute('INSERT INTO phone_pack_jobs (id,project,revision,request,status,stage,updated) VALUES (?,?,?,?,?,?,?)',
                       (job, project, revision, row['request'], 'queued', 'Waiting to create', now()))
        self.wake.set()
        return job

    def job(self, job):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM phone_pack_jobs WHERE id=?', (job,)).fetchone()
        if not row:
            raise ValueError('This pack was not found.')
        result = dict(row)
        result.pop('folder')
        request = json.loads(result.pop('request'))
        result['activity_count'] = request['activity_count']
        result['title'] = request['title']
        return result

    def update(self, job, **values):
        allowed = {'status','stage','folder','error'}
        if not set(values) <= allowed:
            raise ValueError('Unsupported job update.')
        values['updated'] = now()
        with closing(self.connect()) as db, db:
            db.execute('UPDATE phone_pack_jobs SET '+','.join(key+'=?' for key in values)+' WHERE id=?', (*values.values(), job))

    def process_next(self):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM phone_pack_jobs WHERE status='queued' ORDER BY updated LIMIT 1").fetchone()
            if not row:
                return False
            db.execute("UPDATE phone_pack_jobs SET status='running',stage='Checking words',updated=? WHERE id=?", (now(),row['id']))
        job = row['id']
        try:
            checked = prepare_pack_request(json.loads(row['request']), self.root)
            self.update(job, stage='Building and checking printable files')
            values = checked['plan']
            values['words'], values['formats'] = tuple(values['words']), tuple(values['formats'])
            folder = build_activity_pack(ActivityPackPlan(**values), self.output/job)
            self.update(job, status='ready', stage='Ready to preview and download', folder=str(folder))
        except ValueError as exc:
            self.update(job, status='failed', stage='Needs attention', error=str(exc))
        except Exception:
            self.update(job, status='failed', stage='Needs attention', error='The pack could not be completed. Your project is safe. Retry or use the desktop Studio.')
        return True

    def run(self):
        while not self.stop.is_set():
            if not self.process_next():
                self.wake.wait(1)
                self.wake.clear()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.worker:
            self.worker.join(timeout=5)
        if self.worker_lock and (not self.worker or not self.worker.is_alive()):
            self.worker_lock.close()
            self.worker_lock = None

    def artifact(self, job, kind):
        names = {'activities':'ACTIVITIES.pdf','answers':'ANSWERS.pdf','zip':'PRINTABLE_PACK.zip'}
        if kind not in names:
            raise ValueError('Choose activities, answers or the complete ZIP.')
        with closing(self.connect()) as db:
            row = db.execute('SELECT status,folder FROM phone_pack_jobs WHERE id=?', (job,)).fetchone()
        if not row or row['status'] != 'ready' or not row['folder']:
            raise ValueError('This pack is not ready to download.')
        folder = Path(row['folder']).resolve()
        if not folder.is_relative_to(self.output / job):
            raise ValueError('The saved pack location is invalid.')
        path = (folder/names[kind]).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError('The saved file is missing. Create a new project revision to rebuild it.')
        return path

    def preview(self, job, kind, page):
        if kind not in ('activities','answers') or type(page) is not int or not 0 <= page <= 24:
            raise ValueError('Choose a page from this pack.')
        from pypdf import PdfReader
        from .studio_preview import render_document
        path = self.artifact(job, kind)
        if page >= len(PdfReader(path).pages):
            raise ValueError('This page is outside the pack.')
        image = render_document(path, page)
        try:
            data = BytesIO()
            image.save(data, format='PNG')
            return data.getvalue()
        finally:
            image.close()


def suggest_pack(root, text, *, interpreter=None):
    """Use the existing bounded Codex adapter; proposals still need review."""
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError('Describe an activity pack in 1 to 1000 characters.')
    from .studio_providers import interpret_request
    from .studio_reader_profiles import reader_from_request
    intent = (interpreter or interpret_request)('Codex', text)
    if intent.action != 'create_pack':
        raise ValueError('Please describe a printable activity pack. Books and cover reviews are not connected here yet; you can also choose the activity buttons.')
    groups = list(intent.source_groups)
    request = {'title':(intent.topic+' Activity Pack')[:100], 'theme':intent.topic,
        'reader_profile':reader_from_request(text) or 'standard',
        'activity_count':intent.activity_count, 'formats':['Word Search','Word Scramble','Sudoku'],
        'theme_balance':'Balanced'}
    if groups:
        request['source_groups'] = groups
    # A one/two-page proposal cannot contain three formats; keep the choice explicit.
    if request['activity_count'] < 3:
        request['formats'] = ['Sudoku' if intent.kind == 'Sudoku' else 'Word Search']
    return validate_pack_request(request, root)
