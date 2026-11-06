import json
import pytest

@pytest.mark.parametrize("ready",[False,True])
def test_shared_gate_checks_reservations_before_rendering(tmp_path,monkeypatch,ready):
    import word_search_creator as studio
    source=tmp_path/"theme.json";source.write_text(json.dumps({"puzzles":[{"words":["PLANET"]}]}),encoding="utf-8")
    monkeypatch.setattr(studio,"production_stop_errors",lambda *a:([],[],[]))
    seen=[]
    def check(root,title,data):seen.append((root,title,data));return {"ready":ready}
    monkeypatch.setattr("publishing.production_intelligence.reservation_check",check)
    before=source.read_bytes()
    errors,_,_=studio.prepare_wordsearch_production_gate(source,42,{"theme":str(source),"title":"New title"})
    assert seen and seen[0][1]=="New title"
    assert bool(errors) is (not ready)
    assert source.read_bytes()==before
