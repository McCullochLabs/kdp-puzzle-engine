from dataclasses import asdict
import json
import threading
import pytest
from publishing.studio_assistant import AssistantIntent, SCHEMA, validate_intent, guide_request
from publishing.studio_providers import RequestGate, interpret_request
from publishing.studio_codex import CodexAssistant, ProviderUnavailable, RequestCancelled, process_options


def test_providers_share_strict_validation(monkeypatch):
    from publishing.studio_assistant import parse_proposal
    valid = asdict(AssistantIntent(action='create_pack', topic='Space'))
    monkeypatch.setattr(CodexAssistant, 'request', lambda *a, **k: valid)
    assert interpret_request('Codex', 'make a space pack').topic == 'Space'
    for changes in ({'command': 'anything'}, {'action': 'publish'}, {'source_groups': ['x'] * 7},
                    {'source_groups': ['a', 'a']}, {'source_groups': ['a\nb']}):
        with pytest.raises(ValueError): parse_proposal(valid | changes, 'make a pack')


def test_codex_receives_only_bounded_context_and_no_paths(monkeypatch):
    requests = []
    def request(self, prompt, schema, **kwargs):
        requests.append((prompt, schema))
        return asdict(AssistantIntent(action='covers'))
    monkeypatch.setattr(CodexAssistant, 'request', request)
    interpret_request('Codex', 'Change its cover', history=[{'role': 'user', 'content': 'x' * 2000}] * 20,
        context={'title': 'Garden days', 'topic': 'Garden', 'path': 'PRIVATE_PATH'})
    prompt, schema = requests[0]
    assert 'PRIVATE_PATH' not in prompt and len(json.loads(prompt)) == 8
    assert schema == SCHEMA
    requests.clear()
    assert interpret_request('Codex', 'Change its cover').action == 'clarify'
    assert not requests


def test_gate_duplicate_cancellation_provider_and_project_changes():
    gate = RequestGate(); context = {'book_id': 'a'}
    ticket, cancel = gate.begin('Codex', context)
    assert gate.accepts(ticket, 'Codex', context)
    with pytest.raises(ValueError): gate.begin('Codex', context)
    assert not gate.accepts(ticket, 'Ollama', context)
    assert not gate.accepts(ticket, 'Codex', {'book_id': 'b'})
    gate.stop(); assert cancel.is_set() and not gate.accepts(ticket, 'Codex', context)
    new, _ = gate.begin('Ollama', context)
    assert not gate.accepts(ticket, 'Ollama', context) and gate.accepts(new, 'Ollama', context)


def test_failure_and_usage_limits_never_fallback_or_retry(monkeypatch):
    calls = []
    def unavailable(self, *args, **kwargs):
        calls.append('Codex'); raise ProviderUnavailable('Codex usage limit reached')
    monkeypatch.setattr(CodexAssistant, 'interpret', unavailable)
    monkeypatch.setattr('publishing.studio_providers.LocalAssistant.interpret', lambda *a: calls.append('Ollama'))
    with pytest.raises(ProviderUnavailable, match='usage limit'): interpret_request('Codex', 'make a pack')
    assert calls == ['Codex']
    assert interpret_request('Guide', 'make a space pack').action == 'create_pack'


def test_cancelled_request_never_calls_a_model(monkeypatch):
    cancel = threading.Event(); cancel.set()
    monkeypatch.setattr(CodexAssistant, 'interpret', lambda *a, **k: pytest.fail('Must not call model'))
    with pytest.raises(RequestCancelled): interpret_request('Codex', 'hello', cancel=cancel)


def test_process_configuration_disables_execution_and_billing_routes():
    settings = process_options()
    for flag in ('features.shell_tool=false', 'features.unified_exec=false', 'features.apps=false',
                 'features.plugins=false', 'features.computer_use=false', 'features.code_mode_host=false',
                 'forced_login_method="chatgpt"', 'web_search="disabled"', 'sandbox_mode="read-only"'):
        assert flag in settings


def test_context_pack_revision_uses_actual_supported_count():
    context = {'action': 'create_pack', 'topic': 'Space', 'activity_count': 6}
    assert guide_request('Use fewer puzzles', context=context).activity_count == 3
    assert guide_request('Make another version', context=context).action == 'create_pack'
    assert guide_request('Audit its cover', context={'book_id': 'a'}).action == 'audit_cover'


def test_provider_selection_retained_on_failure_and_switch_is_explicit():
    # Gate retains the original ticket; alternate-provider execution requires a new submission.
    gate = RequestGate(); ticket, _ = gate.begin('Codex', None)
    assert not gate.accepts(ticket, 'Ollama', None)
    assert ticket[1] == 'Codex'
