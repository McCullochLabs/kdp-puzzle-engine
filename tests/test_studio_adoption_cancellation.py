from pathlib import Path
import threading
import pytest
from test_studio_chat_revisions import owned
from test_studio_revision_adoption import staged
from publishing.studio_recovery import StudioDraftStore
from publishing.studio_revision_adoption import confirm_adoption,adopt_revision,_tree


@pytest.mark.parametrize("boundary",["before_work","after_copy","after_final_check"])
def test_adoption_cancellation_has_consistent_catalog_and_recovery(staged,monkeypatch,boundary):
    import publishing.studio_revision_adoption as adoption
    root,context,original,service,plan,result,pending=staged
    confirm_adoption(root,plan.revision_id,pending)
    from publishing.studio_session import save_session,load_session
    save_session(root,pending,[{"role":"You","text":"Accept staged revision"}])
    store=StudioDraftStore(root/"data/books.db")
    before=service.db.get_book(context["book_id"]);original_hashes=_tree(original)
    destination=root/"out/studio_adopted_revisions"/plan.revision_id
    cancel=threading.Event()
    if boundary=="before_work":cancel.set()
    elif boundary=="after_copy":
        copy=adoption.shutil.copytree
        def copied(*args,**kwargs):
            value=copy(*args,**kwargs);cancel.set();return value
        monkeypatch.setattr(adoption.shutil,"copytree",copied)
    else:
        save=adoption._save_version
        def saving(*args,**kwargs):
            cancel.set();return save(*args,**kwargs)
        monkeypatch.setattr(adoption,"_save_version",saving)
    if boundary!="after_final_check":
        with pytest.raises(ValueError,match="cancelled before commit"):adopt_revision(root,plan.revision_id,cancel)
        assert service.db.get_book(context["book_id"])==before
        assert store.load(plan.revision_id)["payload"]["chat_revision"]["status"]=="complete"
        restored=load_session(root)
        assert restored["context"]["pending_semantic_revision"]["revision_id"]==plan.revision_id
        assert restored["pending_result"]["revision_id"]==plan.revision_id
        if boundary=="before_work":assert not destination.exists()
        else:assert _tree(destination)==_tree(Path(result["folder"]))
        cancel.clear()
        if boundary=="after_copy":monkeypatch.setattr(adoption.shutil,"copytree",copy)
        adopted=adopt_revision(root,plan.revision_id,cancel)
    else:adopted=adopt_revision(root,plan.revision_id,cancel)
    current=service.db.get_book(context["book_id"])
    draft=store.load(plan.revision_id)["payload"]["chat_revision"]
    original_draft=store.load(current["metadata"]["studio_chat_creation"]["draft_id"])["payload"]["chat_creation"]
    assert current["package_path"]==adopted["folder"] and draft["status"]=="adopted"
    restored=load_session(root)
    assert restored["context"]["book_id"]==context["book_id"]
    assert restored["context"]["title"]==adopted["title"]
    assert "pending_semantic_revision" not in restored["context"] and restored["pending_result"] is None
    assert restored["messages"]==[{"role":"You","text":"Accept staged revision"}]
    assert original_draft["adopted_revision"]["revision_id"]==plan.revision_id
    assert original_draft["result"]["folder"]==current["package_path"]
    assert current["statuses"]==before["statuses"] and _tree(original)==original_hashes
    cancel.clear();version=store.load(plan.revision_id)["revision"]
    assert adopt_revision(root,plan.revision_id,cancel)==adopted
    assert store.load(plan.revision_id)["revision"]==version
