import json
from publishing import studio_health as health


def test_missing_artwork_is_reported_without_rewriting_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(health, 'runtime_errors', lambda: [])
    assets = tmp_path/'cover_assets'; assets.mkdir()
    registry = assets/'generated_background_index.json'
    content = {'assets': [{'asset_id':'one', 'path':'missing.png', 'approval_state':'approved'},
                          {'asset_id':'old', 'path':'old.png', 'approval_state':'approved', 'retired_from_new_production':True}]}
    registry.write_text(json.dumps(content))
    before = registry.read_bytes()
    result = health.collect_readiness(tmp_path, check_ai=False)
    assert not result['ready']
    assert result['missing_artwork'] == ['missing.png']
    assert registry.read_bytes() == before


def test_readiness_lists_only_installed_models_without_inference(tmp_path, monkeypatch):
    calls=[]
    monkeypatch.setattr(health.LocalAssistant, 'models', lambda self: calls.append('models') or ['small:local'])
    monkeypatch.setattr(health.LocalAssistant, 'interpret', lambda *args: (_ for _ in ()).throw(AssertionError('must not infer')))
    result = health.collect_readiness(tmp_path)
    assert result['models'] == ['small:local'] and calls == ['models']
