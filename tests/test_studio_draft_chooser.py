import gc,time
import pytest
from test_studio_chat_revisions import owned


@pytest.mark.parametrize("page_two",[False,True])
def test_actual_chooser_opens_older_failed_draft_without_rewriting(owned,monkeypatch,page_two):
    import tkinter as tk
    from tkinter import ttk
    import word_search_creator as desktop
    from publishing.studio_chat_creation import sudoku_chat_plan,save_creation_plan,_checkpoint
    from publishing.studio_assistant import guide_request
    from publishing.studio_recovery import StudioDraftStore
    root,*_=owned;plans=[];store=StudioDraftStore(root/"data/books.db")
    for seed in (41,42):
        text=f"Create a 24-puzzle Sudoku book with seed {seed}"
        plan=sudoku_chat_plan(text,guide_request(text));save_creation_plan(root,plan);_checkpoint(root,plan,"failed",error=f"Saved error {seed}");plans.append(plan)
    if page_two:
        for seed in range(100,120):
            text=f"Create a 24-puzzle Sudoku book with seed {seed}"
            filler=sudoku_chat_plan(text,guide_request(text));save_creation_plan(root,filler)
    latest=store.pending()[0]['draft_id']
    before={p.draft_id:store.load(p.draft_id) for p in plans}
    monkeypatch.setattr(desktop,"load_app_preferences",lambda:{"assistant_provider":"Guide","local_ai_enabled":False})
    monkeypatch.setattr(desktop.WordSearchCreator,"APP_DIR",root,raising=False)
    monkeypatch.setattr("publishing.family_studio.LocalAssistant.models",lambda self:[])
    monkeypatch.setattr("publishing.studio_chat_creation.create_chat_book",lambda *a,**k:pytest.fail("Chooser generated book"))
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.prompt.set("Show unfinished drafts");f.send();deadline=time.monotonic()+3
        if page_two:
            while time.monotonic()<deadline and str(f.unfinished_next.cget('state'))!='normal':app.update();time.sleep(.01)
            f.unfinished_next.invoke();deadline=time.monotonic()+3
        cards=[]
        while time.monotonic()<deadline:
            app.update();cards=[w for w in f._unfinished_rows.winfo_children() if isinstance(w,ttk.Frame)]
            if len(cards)>=2 and all(any(c.winfo_children()[0].cget("text")==p.title for c in cards) for p in plans):break
            time.sleep(.01)
        assert len(cards)>=2
        card=next(c for c in cards if c.winfo_children()[0].cget("text")==plans[0].title)
        next(w for w in card.winfo_children() if isinstance(w,ttk.Button)).invoke();app.update()
        assert f._chat_creation_plan.draft_id==plans[0].draft_id and not f.page
        assert "Saved error 41" in f.chat.get("1.0","end")
        assert all(store.load(identity)==value for identity,value in before.items())
        f.resume_draft();assert f._chat_creation_plan.draft_id==latest
        f.resume_draft("../untrusted")
        assert "no longer unfinished" in f.chat.get("1.0","end")
        assert all(store.load(identity)==value for identity,value in before.items())
    finally:app.destroy();gc.collect()


def test_unfinished_query_does_not_accept_compound_action():
    from publishing.studio_project_queries import project_query
    assert project_query("Show unfinished drafts")=="unfinished_drafts"
    assert project_query("Show unfinished drafts and generate them") is None


def test_pending_pages_are_bounded_stable_and_identity_scoped(tmp_path):
    from publishing.studio_recovery import StudioDraftStore
    store=StudioDraftStore(tmp_path/"books.db")
    for i in range(22):store.save(f"draft{i:02}","book_plan",{"editor":{"title":str(i)}})
    with store._connect() as db:db.execute("UPDATE studio_drafts SET updated_at='2026-01-01'")
    first=store.pending();second=store.pending(offset=20)
    assert len(first)==20 and len(second)==2
    assert [row['draft_id'] for row in first+second]==[f"draft{i:02}" for i in range(21,-1,-1)]
    assert store.is_pending("draft00") and not store.is_pending("' OR 1=1 --")
    store.save("draft00","book_plan",{"editor":{"title":"Done"}},completed=True)
    assert not store.is_pending("draft00")
    for offset in (True,-1,"20",20.0,1000001):
        with pytest.raises(ValueError):store.pending(offset=offset)
