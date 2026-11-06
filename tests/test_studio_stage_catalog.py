from types import SimpleNamespace
import pytest
import puzzle_book_studio as studio


def test_stage_option_is_forwarded_without_changing_default():
    calls=[]
    def builder(*args, sync_catalog=True):
        calls.append(sync_catalog)
        return "package"
    wrapped=studio._record_package_failure(builder)
    args=("Sudoku", "Test", "", "Jordan M. Slade", 24, "Easy", 1)
    assert wrapped(*args)=="package"
    assert wrapped(*args,sync_catalog=False)=="package"
    assert calls==[True,False]


def test_staged_package_does_not_construct_catalog_service(monkeypatch,tmp_path):
    import publishing
    def forbidden(*args,**kwargs):
        raise AssertionError("Staged revisions must not scan or mutate catalog identities")
    monkeypatch.setattr(publishing,"PublishingService",forbidden)
    studio._sync_completed_package(tmp_path,None,{},sync_catalog=False)
    assert list(tmp_path.iterdir())==[]


def test_normal_package_keeps_registration_default(monkeypatch,tmp_path):
    import publishing
    events=[]
    monkeypatch.setattr(publishing,"PublishingService",lambda app:SimpleNamespace(sync_output_packages=lambda:events.append("sync")))
    autopilot=SimpleNamespace(stage_fingerprint=lambda facts,stage:"fingerprint",complete=lambda *args:events.append(args[0]))
    studio._sync_completed_package(tmp_path,autopilot,{})
    assert events==["sync","register"]


def test_staged_flag_does_not_bypass_content_gate(monkeypatch,tmp_path):
    monkeypatch.setattr(studio,"APP",tmp_path)
    monkeypatch.setattr(studio,"content_check",lambda kind,theme:(False,"deliberately invalid content",0))
    def forbidden(*args,**kwargs):
        raise AssertionError("Invalid content must not reach generation")
    monkeypatch.setattr(studio,"make_interior",forbidden)
    with pytest.raises(ValueError,match="Content Library Verification"):
        studio.create_package("Cryptogram","Stage gate test","","Jordan M. Slade",60,"Mixed",1,"Nature & Outdoors",sync_catalog=False)


@pytest.mark.parametrize("sync_catalog,expected_writes",[(False,0),(True,1)])
def test_wordsearch_stage_keeps_artwork_gate_and_controls_failure_catalog_write(monkeypatch,tmp_path,sync_catalog,expected_writes):
    import publishing
    import word_search_creator as wordstudio
    writes=[];outcomes=[]
    service=SimpleNamespace(db=SimpleNamespace(set_approval_status_for_source=lambda *args:writes.append(args)))
    monkeypatch.setattr(publishing,"PublishingService",lambda root:service)
    monkeypatch.setattr(wordstudio,"log_plain_error",lambda *args:None)
    runner=object.__new__(wordstudio.WordSearchCreator)
    runner.after=lambda delay,callback,*args:callback(*args)
    runner._studio_package_finished=lambda *args:outcomes.append(args)
    kwargs={"sync_catalog":False} if not sync_catalog else {}
    runner._run_studio_package({"art":"","theme":str(tmp_path/"source.json"),"title":"Stage test"},1,tmp_path/"new",**kwargs)
    assert len(writes)==expected_writes
    assert outcomes and outcomes[0][0] is False
    assert "COVER ART REQUIRED" in outcomes[0][2]
    assert not (tmp_path/"new").exists()
