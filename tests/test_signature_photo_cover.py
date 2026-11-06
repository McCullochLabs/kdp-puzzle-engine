import json
from types import SimpleNamespace
import pytest
import cover


def test_signature_cover_rejects_inaccurate_puzzle_count(tmp_path):
    source=tmp_path/'source.json'
    source.write_text(json.dumps({'puzzles':[{'words':['HARVEST']*12}]*48}))
    args=SimpleNamespace(theme_file=str(source),puzzle_count=48)
    with pytest.raises(ValueError,match='100 puzzles'):
        cover.signature_photo_cover(None,args,{})


def test_signature_cover_rejects_false_no_repeat_claim(tmp_path):
    source=tmp_path/'source.json'
    words=['HARVEST','FALL','FAMILY','THANKS','TREE','LEAF','APPLE','PUMPKIN','PIE','CIDER','CORN','FEAST']
    source.write_text(json.dumps({'puzzles':[{'words':words}]*100}))
    args=SimpleNamespace(theme_file=str(source),puzzle_count=100)
    with pytest.raises(ValueError,match='repeated targets'):
        cover.signature_photo_cover(None,args,{})


def test_signature_cover_requires_complete_source():
    with pytest.raises(ValueError,match='complete 100-puzzle source'):
        cover.signature_photo_cover(None,SimpleNamespace(theme_file=None),{})
