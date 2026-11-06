import json
from pathlib import Path
import time
import tkinter as tk

import pytest
import word_search_creator as studio
from publishing.activity_pack_ui import ActivityPackDialog
from publishing.family_studio import FamilyBookDialog
from publishing.studio_assistant import AssistantIntent


@pytest.fixture
def app(monkeypatch, tmp_path):
    import gc
    gc.collect()
    monkeypatch.setattr(studio, 'load_app_preferences', lambda: {})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models', lambda self: [])
    try:
        window = studio.WordSearchCreator()
    except tk.TclError as exc:
        pytest.skip(f'Desktop display unavailable: {exc}')
    errors = []
    window.APP_DIR = tmp_path
    window.report_callback_exception = lambda *args: errors.append(args)
    window.update()
    yield window
    window.destroy()
    del window
    gc.collect()
    assert not errors


def test_startup_is_lazy_and_family_routes_work_at_small_size(app, monkeypatch):
    assert not app._advanced_built
    app.geometry('800x560')
    app.update()
    family = app.family_studio
    assert [family.nav_menu.entrycget(i, 'label') for i in range(5)] == ['Home', 'Create', 'My books', 'Covers', 'Settings']
    assert family.menu_button.winfo_viewable()
    assert not family.manual_choices.winfo_manager()
    family._toggle_manual_choices(); app.update()
    assert family.manual_choices.winfo_viewable()
    family._toggle_manual_choices(); app.update()
    family.show_create(); app.update()
    family.show_covers(); app.update()
    family.show_settings(); app.update()
    family.show_home(); app.update()
    assert family.entry.winfo_viewable()
    assert family.send_button.winfo_viewable()
    assert family.entry.winfo_rooty()+family.entry.winfo_height() <= app.winfo_rooty()+app.winfo_height()
    assert not app._advanced_built


def test_assistant_only_proposes_and_passes_details_to_review_dialog(app):
    family = app.family_studio
    family.prompt.set('Make a birthday activity pack for Emma')
    family.send(); app.update()
    assert family.intent.topic == 'Birthday'
    assert family.proposal.winfo_viewable()
    assert not any(isinstance(child, ActivityPackDialog) for child in app.winfo_children())
    family._open_proposal(); app.update()
    dialog = next(child for child in app.winfo_children() if isinstance(child, ActivityPackDialog))
    assert dialog.recipient.get() == 'Emma'
    assert dialog.theme.get() == 'Birthday'
    dialog._next(); dialog._next(); app.update()
    assert dialog.step == 2 and dialog.create_button.winfo_viewable()
    assert dialog.create_button.winfo_rooty()+dialog.create_button.winfo_height() <= dialog.winfo_rooty()+dialog.winfo_height()
    dialog.destroy()


def test_catalog_result_is_ignored_after_navigation(app, monkeypatch):
    family = app.family_studio
    monkeypatch.setattr('publishing.database.PublishingDatabase.list_books', lambda *args: [])
    family.show_books(); family.show_home()
    family.results.put(('books', (family.epoch-1, [{'book_id': 'old'}], '')))
    family._poll()
    assert family.home.winfo_manager() == 'grid'


def test_ai_failure_retains_provider_without_disabling_navigation(app, monkeypatch):
    family = app.family_studio
    family.local_ai_enabled = True
    family.provider = 'Ollama'
    family.model = 'missing-model'
    def fail(*args): raise RuntimeError('Local AI not running')
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.interpret', fail)
    family.prompt.set('make a pack'); family.send()
    deadline = time.monotonic()+3
    while family.busy and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    assert not family.busy and family.local_ai_enabled
    assert family.provider == 'Ollama'
    assert family.retry_button.winfo_manager()
    assert str(family.send_button.cget('state')) == 'normal'
    assert 'Local AI' in family.mode.get()


def test_book_topic_is_not_silently_replaced(app, monkeypatch):
    dialog = FamilyBookDialog(app, AssistantIntent(action='create_book', kind='Cryptogram', topic='A made up topic'))
    opened = []
    monkeypatch.setattr(app, '_ensure_advanced_workspace', lambda **kwargs: opened.append(True))
    dialog.continue_to_plan(); app.update()
    assert not opened
    assert dialog.topic.get() == 'A made up topic'
    assert hasattr(dialog, 'theme_choices')
    dialog.destroy()


def test_simple_puzzle_studio_uses_existing_generator_and_cover_checks(app):
    from puzzle_book_studio import PuzzleBookStudio
    dialog = PuzzleBookStudio(app, initial_kind='Sudoku', simple_mode=True)
    app.update()
    assert dialog.kind.get() == 'Sudoku'
    assert dialog.cover_photo.get() == 'Automatic matching'
    assert dialog.count.get() >= 24
    dialog.destroy()


def test_simple_wordsearch_builder_keeps_editable_vocabulary_and_approval(app, monkeypatch):
    monkeypatch.setattr(studio, 'load_master_word_bank', lambda: {'topics': {'Space': ['PLANET', 'ORBIT']}, 'topic_packs': {'Space': ['Space']}})
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch', lambda *args, **kwargs: {'topic': 'Space', 'words': ['PLANET', 'ORBIT'], 'groups': [{'name': 'Puzzle 1', 'words': ['PLANET', 'ORBIT']}], 'source_topics': ['Space'], 'seed': 42})
    dialog = studio.GuidedBookBuilderDialog(app, initial_topic='Space', initial_pack='Space', simple_mode=True)
    deadline = time.monotonic() + 3
    while getattr(dialog, '_family_loading', False) and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    app.update()
    assert 'PLANET' in dialog.words.get('1.0', 'end')
    assert str(dialog.approve.cget('state')) == 'disabled'
    dialog.created_path = Path('existing-plan.json')
    dialog.approve.configure(state='normal')
    dialog.title_value.set('Updated title')
    assert dialog.created_path is None and str(dialog.approve.cget('state')) == 'disabled'
    dialog.destroy()


def test_advanced_workspace_is_available_and_returns_to_simple_home(app, monkeypatch):
    monkeypatch.setattr(app, '_load_theme_list', lambda: None)
    monkeypatch.setattr(app, '_load_library_summary_async', lambda: None)
    app._ensure_advanced_workspace(show=True)
    app.update()
    assert app._advanced_built and app._advanced_shell.winfo_viewable()
    app._show_family_home(); app.update()
    assert app.family_studio.winfo_viewable()
    assert not app._advanced_shell.winfo_viewable()


def test_cover_generator_actions_fit_their_window(app, monkeypatch):
    monkeypatch.setattr(studio.BackgroundGeneratorDialog, 'refresh', lambda self: None)
    dialog = studio.BackgroundGeneratorDialog(app, topic='Space', palette='nature')
    app.update()
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    buttons = [widget for widget in descendants(dialog) if widget.winfo_class() == 'TButton']
    assert len(buttons) == 7
    for button in buttons:
        assert button.winfo_rootx()+button.winfo_width() <= dialog.winfo_rootx()+dialog.winfo_width()
        assert button.winfo_width() >= button.winfo_reqwidth()
    dialog.destroy()


def test_selected_cover_request_opens_the_selected_book_only(app, monkeypatch):
    family = app.family_studio
    family.context = {'book_id': 'chosen-book', 'title': 'Garden days', 'topic': 'Garden', 'kind': 'Word Search'}
    opened = []
    monkeypatch.setattr(app, '_open_book_control_center', opened.append)
    family.prompt.set('Change its cover'); family.send()
    family.context = {'book_id': 'different-book', 'title': 'Other', 'topic': 'Space', 'kind': 'Sudoku'}
    family._open_proposal()
    assert opened == ['chosen-book']


def test_single_installed_local_model_connects_but_explicit_guide_mode_is_respected(app):
    family = app.family_studio
    family.results.put(('startup_models', ['small:local']))
    family._poll()
    assert family.local_ai_enabled and family.model == 'small:local'
    family.show_settings(); family._disable_ai()
    family.results.put(('startup_models', ['small:local']))
    family._poll()
    assert not family.local_ai_enabled


def test_family_catalog_uses_existing_alias_grouping_and_truthful_status(app, monkeypatch):
    rows = [{'book_id': key, 'package_path': 'missing-family-test-package',
             'metadata': {'title': 'Same saved book'}, 'statuses': {}} for key in ('first', 'alias')]
    monkeypatch.setattr('publishing.database.PublishingDatabase.list_books', lambda *args: rows)
    path = app.APP_DIR / 'data' / 'books.db'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    family = app.family_studio
    family.show_books()
    deadline = time.monotonic() + 20
    while not family.catalog and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    assert len(family.catalog) == 1, {'epoch': family.epoch, 'queue': list(family.results.queue), 'labels': [str(widget.cget('text')) for widget in family.book_rows.winfo_children() if 'text' in widget.keys()]}
    assert family.catalog[0]['catalog_alias_count'] == 1
    assert family.catalog[0]['studio_catalog_state']['status'] == 'Missing package'


def test_library_worker_never_schedules_tk_from_a_background_thread(monkeypatch):
    import threading
    finished = threading.Event()
    calls = []
    class Window:
        library_summary = None
        def after(self, delay, callback):
            calls.append(threading.get_ident())
            return 'test-job'
        def bind(self, *args, **kwargs): pass
    monkeypatch.setattr(studio, 'load_master_word_bank', lambda: {})
    def summary():
        finished.set()
        return {'ready_48': 0, 'needs_expansion': 0}
    monkeypatch.setattr(studio, 'library_intelligence_summary', summary)
    main = threading.get_ident()
    studio.WordSearchCreator._load_library_summary_async(Window())
    assert finished.wait(3)
    assert calls == [main]


def test_every_topic_and_pack_is_searchable_without_word_editing(app, monkeypatch):
    from publishing.family_studio import TopicPicker
    bank = {'topics': {'Gardening': [], 'Space': []}, 'topic_packs': {'Garden & Space': ['Gardening', 'Space']}, 'pack_families': {'Family': ['Garden & Space']}}
    monkeypatch.setattr(studio, 'load_master_word_bank', lambda: bank)
    chosen = []
    picker = TopicPicker(app, chosen.append)
    deadline = time.monotonic() + 3
    while len(picker.rows) != 3 and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    assert {row[1] for row in picker.rows} == {'Gardening', 'Space', 'Garden & Space'}
    picker.query.set('family space'); app.update()
    assert picker.visible == [('Family / Garden & Space', 'Garden & Space')]
    picker.listbox.selection_set(0); picker._choose()
    assert chosen == ['Garden & Space']


def test_automatic_count_promise_tracks_settings_but_preserves_custom_subtitle(app):
    from puzzle_book_studio import PuzzleBookStudio
    dialog = PuzzleBookStudio(app, initial_kind='Sudoku', simple_mode=True)
    dialog.count.set(24)
    assert '24' in dialog.subtitle.get() and '60' not in dialog.subtitle.get()
    dialog.subtitle.set('My custom description')
    dialog.count.set(36)
    assert dialog.subtitle.get() == 'My custom description'
    dialog.destroy()


def test_provider_choice_persists_with_existing_preferences(app, monkeypatch):
    captured = []
    monkeypatch.setattr(studio, 'save_app_preferences', captured.append)
    original_destroy = app.destroy
    monkeypatch.setattr(app, 'destroy', lambda: None)
    app._app_preferences['unrelated_setting'] = 'keep'
    family = app.family_studio
    family.show_settings(); family.provider_choice.set('Codex'); family._select_provider()
    app._on_close()
    monkeypatch.setattr(app, 'destroy', original_destroy)
    assert captured[-1]['assistant_provider'] == 'Codex'
    assert captured[-1]['unrelated_setting'] == 'keep'


def test_duplicate_request_and_provider_switch_keep_draft_and_ignore_result(app, monkeypatch):
    import threading
    release = threading.Event(); calls = []
    def pending(*args):
        calls.append(args[0]); release.wait(2)
        return AssistantIntent(action='create_pack', topic='Space')
    monkeypatch.setattr('publishing.family_studio.interpret_request', pending)
    family = app.family_studio; family.provider = 'Codex'
    family.prompt.set('make a space pack'); family.send()
    family.prompt.set('second request'); family.send()
    assert len(calls) <= 1
    family.show_settings(); family.provider_choice.set('Guide'); family._select_provider()
    release.set()
    deadline = time.monotonic() + 3
    while family.results.empty() and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    family._poll()
    assert family.provider == 'Guide' and not family.busy
    assert family.prompt.get() == 'second request'
    assert family.intent is None


def test_short_group_offers_activity_pack_without_lowering_book_threshold(app, monkeypatch):
    def prepare(root, topic, *args, **kwargs):
        if kwargs.get('minimum_puzzles') == 1: return {'words': ['PLANET'] * 16}
        raise ValueError('Not enough checked words for a full book.')
    monkeypatch.setattr('word_intelligence.pipeline.prepare_family_wordsearch', prepare)
    dialog = studio.GuidedBookBuilderDialog(app, initial_topic='Cat Lover', simple_mode=True)
    deadline = time.monotonic() + 3
    while dialog._family_loading and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    assert dialog.short_pack_button.winfo_manager()
    assert dialog._family_plan is None
    assert str(dialog.approve.cget('state')) == 'disabled'
    dialog.destroy()


def test_custom_group_mix_survives_draft(app, monkeypatch, tmp_path):
    from publishing.studio_recovery import StudioDraftStore
    store = StudioDraftStore(tmp_path / 'draft-groups.db')
    groups = ('Gardening', 'Home and Household')
    dialog = FamilyBookDialog(app, AssistantIntent(action='create_book', topic='Homesteading', source_groups=groups), draft_store=store)
    assert dialog.flush_draft()
    assert store.load(dialog.draft_id)['payload']['source_groups'] == list(groups)
    dialog.destroy()

