"""Behavior tests for the dialog when a desktop display is available."""
from dataclasses import replace
import time
import tkinter as tk

import pytest

from publishing import activity_pack_ui as ui


@pytest.fixture(scope='module')
def ui_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f'Desktop display unavailable: {exc}')
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def dialog(ui_root):
    import gc
    window = ui.ActivityPackDialog(ui_root)
    yield window
    if window.winfo_exists(): window.destroy()
    del window
    gc.collect()


def test_preset_and_custom_inputs_reach_the_plan(dialog):
    dialog.theme.set('Birthday')
    dialog._preset()
    assert dialog._plan().theme == 'Birthday'
    assert 'BIRTHDAY' in dialog._plan().words
    dialog.recipient.set('For Jordan')
    assert dialog._plan().recipient == 'For Jordan'
    dialog.selected['Word Search'].set(False)
    dialog.selected['Word Scramble'].set(False)
    dialog.words.delete('1.0', 'end')
    assert dialog._plan().formats == ('Sudoku',)


def test_worker_result_updates_ui_and_error_recovery(dialog, monkeypatch, tmp_path):
    # Exercise the real thread/queue handoff without generating PDFs in a GUI test.
    monkeypatch.setattr(ui, 'build_activity_pack', lambda *args: tmp_path)
    dialog.output.set(str(tmp_path))
    dialog._create()
    deadline = time.monotonic() + 5
    while dialog.busy and time.monotonic() < deadline:
        dialog.update()
        time.sleep(.01)
    assert not dialog.busy and dialog.last_package == tmp_path
    assert dialog.pack_title.get() == 'Road Trip Activity Pack'
    assert all(str(widget.cget('state')) == ('disabled' if widget is dialog.back_button else state) for widget, state in dialog.controls)
    errors = []
    monkeypatch.setattr(ui.messagebox, 'showerror', lambda *args, **kwargs: errors.append(args))
    def fail(*args):
        raise ValueError('test failure')
    monkeypatch.setattr(ui, 'build_activity_pack', fail)
    dialog._create()
    deadline = time.monotonic() + 5
    while dialog.busy and time.monotonic() < deadline:
        dialog.update()
        time.sleep(.01)
    assert not dialog.busy and errors
    assert dialog.last_package == tmp_path


def test_autosave_resume_and_undo_restore_unfinished_inputs(dialog, tmp_path):
    from publishing.studio_recovery import StudioDraftStore
    store = StudioDraftStore(tmp_path/'books.db')
    dialog.draft_store = store
    dialog.pack_title.set('First title'); dialog.flush_draft()
    dialog.pack_title.set('Second title'); dialog.count.set('')
    assert dialog.flush_draft()
    key = dialog.draft_id
    resumed = ui.ActivityPackDialog(dialog.master, draft_store=store, draft_id=key)
    assert resumed.pack_title.get() == 'Second title' and resumed.count.get() == ''
    resumed._undo_draft()
    assert resumed.pack_title.get() == 'First title'
    resumed._close()
    assert store.pending()


def test_preview_is_actual_and_refreshes_after_an_edit(dialog):
    from publishing.studio_preview import StudioPreview
    dialog.seed.set('42')
    dialog._preview()
    preview = next(w for w in dialog.winfo_children() if isinstance(w, StudioPreview))
    deadline = time.monotonic()+5
    while not preview.images and time.monotonic() < deadline:
        dialog.update(); time.sleep(.02)
    assert len(preview.images) == 3
    first = preview.fingerprint
    dialog.recipient.set('For Emma')
    deadline = time.monotonic()+5
    while (preview.fingerprint == first or not preview.images) and time.monotonic() < deadline:
        dialog.update(); time.sleep(.02)
    assert preview.fingerprint != first and preview.images
    preview.destroy()


def test_library_group_automatically_supplies_pack_words_and_ignores_old_results(dialog, monkeypatch):
    words = ['PLANET', 'ORBIT', 'ROCKET', 'GALAXY', 'COMET', 'METEOR', 'MOON', 'SOLAR', 'LUNAR', 'SATURN', 'JUPITER', 'VENUS', 'MARS', 'EARTH', 'NEBULA', 'COSMOS']
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch', lambda *args, **kwargs: {'words': words})
    dialog._load_library_topic('Space & Astronomy')
    deadline = time.monotonic() + 3
    while dialog._loading_words and time.monotonic() < deadline:
        dialog.update(); time.sleep(.01)
    assert set(dialog._plan().words) == set(words)
    assert dialog._snapshot_form()['library_topic'] == 'Space & Astronomy'
    old = dialog._word_epoch
    dialog.theme.set('Birthday'); dialog._preset()
    dialog.word_results.put((old, ('Space & Astronomy', '6', ()), words, ''))
    dialog._poll()
    assert 'BIRTHDAY' in dialog._plan().words



def test_large_preset_automatically_uses_checked_bank(dialog, monkeypatch):
    selected = []
    def prepare(root, topic, *args, **kwargs):
        selected.append(topic)
        return {'words': ['PLANET', 'ORBIT']}
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch', prepare)
    dialog.theme.set('Space'); dialog._preset(); dialog.count.set('24')
    dialog._poll()
    assert dialog._library_topic == 'Space & Astronomy'
    deadline = time.monotonic() + 3
    while dialog._loading_words and time.monotonic() < deadline:
        dialog.update(); time.sleep(.01)
    assert selected == ['Space & Astronomy']
    # A deliberately insufficient mock result is stopped instead of inventing words.
    assert 'fewer' in dialog.status.get()
