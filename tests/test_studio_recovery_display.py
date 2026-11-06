import gc
import pytest
from test_studio_chat_revisions import owned

@pytest.mark.parametrize("kind",["creation","revision"])
def test_open_failed_draft_preserves_saved_evidence(owned,monkeypatch,kind):
    import tkinter as tk
    import word_search_creator as desktop
    from publishing.studio_recovery import StudioDraftStore
    from publishing.studio_chat_creation import sudoku_chat_plan,save_creation_plan,_checkpoint
    from publishing.studio_assistant import guide_request
    from publishing.studio_chat_revisions import revision_plan,save_revision_plan,_state
    root,context,*_=owned
    if kind=="creation":
        request="Create a 24-puzzle Sudoku book with seed 42"
        plan=sudoku_chat_plan(request,guide_request(request));save_creation_plan(root,plan)
        _checkpoint(root,plan,"failed",error="Saved failure must remain visible")
        identity=plan.draft_id;field="chat_creation"
    else:
        plan=revision_plan(root,'Change title to "Failed revision fixture"',context);save_revision_plan(root,plan)
        _state(root,plan,"failed",error="Saved failure must remain visible")
        identity=plan.revision_id;field="chat_revision"
    store=StudioDraftStore(root/"data/books.db");before=store.load(identity)
    monkeypatch.setattr(desktop,"load_app_preferences",lambda:{"assistant_provider":"Guide","local_ai_enabled":False})
    monkeypatch.setattr(desktop.WordSearchCreator,"APP_DIR",root,raising=False)
    monkeypatch.setattr("publishing.family_studio.LocalAssistant.models",lambda self:[])
    monkeypatch.setattr("publishing.studio_chat_creation.create_chat_book",lambda *a,**k:pytest.fail("Resume generated book"))
    monkeypatch.setattr("publishing.studio_chat_revisions.stage_revision",lambda *a,**k:pytest.fail("Resume staged revision"))
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.resume_draft();app.update()
        assert store.load(identity)==before
        assert store.load(identity)["payload"][field]["status"]=="failed"
        assert "Saved failure must remain visible" in f.chat.get("1.0","end")
        assert not f.busy
        if kind=="creation":
            from publishing.studio_chat_creation import confirm_creation_plan
            confirm_creation_plan(root,plan)
        else:
            from publishing.studio_chat_revisions import confirm_revision_plan
            confirm_revision_plan(root,plan,context)
        assert store.load(identity)["payload"][field]["status"]=="confirmed"
    finally:app.destroy();gc.collect()
