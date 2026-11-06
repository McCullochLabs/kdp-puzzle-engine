import hashlib,json
from types import SimpleNamespace
import pytest
from publishing.studio_chat_creation import _wordsearch_package_facts,_register_draft_owned_package
from publishing.database import PublishingDatabase


def fixture(root):
    identity='e'*32
    source=root/'data/studio_wordsearch_drafts'/identity/'theme.json';source.parent.mkdir(parents=True)
    data={'detected_topic':'Nature','source_word_bank':{'seed':42},'puzzles':[{'words':['TREE','PINE']}]}
    raw=json.dumps(data);source.write_text(raw,encoding='utf-8')
    folder=root/'out/studio_wordsearch_drafts'/identity;folder.mkdir(parents=True)
    (folder/'interior.puzzles.json').write_text(json.dumps({'puzzles':[{'type':'word_search','words':['TREE','PINE']}]}))
    plan=SimpleNamespace(draft_id=identity,checked_theme_json=raw,topic='Nature',seed=42,count=1,art_sha256='approved',
        settings_json=json.dumps({'theme':str(source),'archive_after_package':False,'signature_edition':False}))
    manifest={'source_theme':str(source),'source_theme_sha256':hashlib.sha256(raw.encode()).hexdigest(),'cover_art_sha256':'approved'}
    return plan,folder,source,manifest


def test_legacy_manifest_topic_seed_derived_only_from_verified_source(tmp_path):
    plan,folder,source,manifest=fixture(tmp_path)
    result=_wordsearch_package_facts(tmp_path,plan,folder,manifest)
    assert result['theme']=='Nature' and result['puzzle_seed']==42
    assert 'theme' not in manifest and 'puzzle_seed' not in manifest


@pytest.mark.parametrize('drift',['source','source_sha','art_sha','words','folder'])
def test_wordsearch_source_artifact_drift_rejected(tmp_path,drift):
    plan,folder,source,manifest=fixture(tmp_path)
    if drift=='source':source.write_text('{}')
    elif drift=='source_sha':manifest['source_theme_sha256']='wrong'
    elif drift=='art_sha':manifest['cover_art_sha256']='wrong'
    elif drift=='words':(folder/'interior.puzzles.json').write_text(json.dumps({'puzzles':[{'type':'word_search','words':['BIRD']}]}))
    elif drift=='folder':folder=tmp_path/'out/another'
    with pytest.raises(ValueError):_wordsearch_package_facts(tmp_path,plan,folder,manifest)


def test_recovered_build_cannot_register_over_another_title_owner(tmp_path):
    db=PublishingDatabase(tmp_path/'data/books.db');db.upsert_book('owner','source',{'title':'Taken'},'')
    before=db.list_books()
    with pytest.raises(ValueError,match='owns that title'):
        _register_draft_owned_package(SimpleNamespace(db=db),'new','package:new',{'title':'taken'},tmp_path/'out/new')
    assert db.list_books()==before


@pytest.mark.parametrize('utterance,guided',[
    ('Create a 100-page large-print birdwatching word search book for seniors',True),
    ('Create a 48-puzzle Nature word search book with seed 42',False),
    ('Create a -100-page word search book',False),
    ('Create a word search book called "Easy Covers" about Nature',False),
])
def test_known_variants_keep_guided_review_and_bad_counts_still_reject(utterance,guided):
    from publishing.studio_chat_wordsearch import needs_guided_wordsearch
    assert needs_guided_wordsearch(utterance)==guided
