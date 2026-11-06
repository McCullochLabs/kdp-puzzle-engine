import tkinter as tk
import pytest

def test_simple_studio_difficulty_control_reflects_supported_families(monkeypatch):
    import word_search_creator as app_module
    from puzzle_book_studio import PuzzleBookStudio
    monkeypatch.setattr(app_module,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    try:app=app_module.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    app.withdraw()
    try:
        for kind in ['Sudoku','Cryptogram','Word Scramble + Trivia','Mixed Brain Games']:
            dialog=PuzzleBookStudio(app,initial_kind=kind,simple_mode=True);app.update()
            value=dialog.difficulty.get();dialog._sync_difficulty_control()
            assert dialog.difficulty.get()==value
            assert str(dialog.difficulty_box.cget('state'))==('disabled' if kind in ['Cryptogram','Word Scramble + Trivia'] else 'readonly')
            assert tuple(dialog.difficulty_box.cget('values'))==('Easy','Mixed','Standard','Hard')
            dialog.destroy()
    finally:app.destroy()
