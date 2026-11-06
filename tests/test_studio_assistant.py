from dataclasses import asdict
import json
import pytest

from publishing.studio_assistant import AssistantIntent, LocalAIUnavailable, LocalAssistant, _NoRedirect, guide_request, validate_intent


def test_guide_supports_common_family_requests_without_a_model():
    intent = guide_request('Make a birthday activity pack for Emma')
    assert intent.action == 'create_pack' and intent.topic == 'Birthday'
    assert intent.recipient == 'Emma'
    assert guide_request('Find my garden books').action == 'find_books'
    assert guide_request('Create a space cover').action == 'covers'
    assert guide_request('Make a space Sudoku book').kind == 'Sudoku'
    assert guide_request('Publish all my books').action == 'help'
    assert guide_request('make 99 activities').action == 'clarify'
    assert guide_request('Space', AssistantIntent(action='create_book')).topic == 'Space'


@pytest.mark.parametrize('changes', [
    {'action': 'run_shell'}, {'kind': 'Maze'}, {'activity_count': True},
    {'activity_count': 100}, {'topic': 'x'*81}, {'recipient': 'a\nb'},
    {'confidence': float('nan')}, {'confidence': .5},
])
def test_model_output_cannot_authorize_unsupported_actions(changes):
    data = asdict(AssistantIntent(action='create_pack', topic='Space')) | changes
    if changes == {'confidence': .5}:
        assert validate_intent(data).action == 'clarify'
    else:
        with pytest.raises(ValueError): validate_intent(data)


def test_model_output_rejects_extra_executable_fields():
    with pytest.raises(ValueError):
        validate_intent(asdict(AssistantIntent()) | {'command': 'anything'})


def test_local_only_model_list_excludes_remote_and_cloud_entries(monkeypatch):
    client = LocalAssistant()
    monkeypatch.setattr(client, '_request', lambda *args: {'models': [
        {'name': 'small:local', 'size': 123}, {'name': 'huge:cloud', 'size': 123},
        {'name': 'other', 'size': 123, 'remote_host': 'somewhere'},
        {'name': 'empty', 'size': 0}, {'name': 'remote', 'size': 123, 'remote_model': 'other'},
    ]})
    assert client.models() == ['small:local']


def test_local_interpretation_uses_bounded_schema_and_never_executes_actions(monkeypatch):
    client = LocalAssistant()
    calls = []
    monkeypatch.setattr(client, 'models', lambda: ['small:local'])
    def request(path, payload=None, timeout=4):
        calls.append((path, payload, timeout))
        return {'done': True, 'message': {'content': json.dumps(asdict(AssistantIntent(action='create_pack', topic='Space')))}}
    monkeypatch.setattr(client, '_request', request)
    result = client.interpret('make a space pack', 'small:local', [{'role': 'user', 'content': 'x'*2000}]*20)
    assert result.action == 'create_pack'
    path, payload, timeout = calls[0]
    assert path == '/api/chat' and payload['stream'] is False
    assert payload['format']['additionalProperties'] is False
    assert len(payload['messages']) == 8
    assert all(len(item['content']) <= 1000 for item in payload['messages'][1:])
    assert payload['options']['num_predict'] == 256 and timeout == 90
    with pytest.raises(LocalAIUnavailable): client.interpret('hello', 'uninstalled')


def test_redirect_to_another_host_is_blocked():
    with pytest.raises(LocalAIUnavailable):
        _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')


def test_malformed_or_incomplete_generation_is_not_used(monkeypatch):
    client = LocalAssistant()
    monkeypatch.setattr(client, 'models', lambda: ['small:local'])
    monkeypatch.setattr(client, '_request', lambda *args, **kwargs: {'done': False})
    with pytest.raises(LocalAIUnavailable): client.interpret('hello', 'small:local')
    monkeypatch.setattr(client, '_request', lambda *args, **kwargs: {'done': True, 'message': {'content': 'not json'}})
    with pytest.raises(LocalAIUnavailable): client.interpret('hello', 'small:local')


def test_current_project_references_require_selection_and_preserve_its_topic():
    from publishing.studio_assistant import project_context
    context = project_context({'book_id': 'garden1', 'metadata': {'title': 'Garden days', 'theme': 'Garden', 'puzzle_type': 'Cryptogram'}})
    assert guide_request('Change its cover').action == 'clarify'
    assert guide_request('Change its cover', context=context).topic == 'Garden'
    intent = guide_request('Make another version', context=context)
    assert intent.action == 'create_book' and intent.kind == 'Cryptogram' and intent.topic == 'Garden'


def test_local_model_receives_bounded_project_context_without_file_paths(monkeypatch):
    client = LocalAssistant()
    monkeypatch.setattr(client, 'models', lambda: ['small:local'])
    captured = []
    def request(path, payload=None, timeout=4):
        captured.append(payload)
        return {'done': True, 'message': {'content': json.dumps(asdict(AssistantIntent(action='covers', topic='Garden')))}}
    monkeypatch.setattr(client, '_request', request)
    client.interpret('Change its cover', 'small:local', context={'title': 'Garden', 'topic': 'Garden', 'kind': 'Word Search', 'path': '/private/file'})
    assert '/private/file' not in json.dumps(captured)
    assert 'Selected project' in captured[0]['messages'][0]['content']


@pytest.mark.parametrize('prompt,recipient,expected', [
    ('Make a space activity pack', 'Space', ''),
    ('Make a birthday pack for Emma', 'Emma', 'Emma'),
    ('Make a birthday pack for Emma', 'Birthday', ''),
])
def test_model_personalization_requires_explicit_user_text(monkeypatch, prompt, recipient, expected):
    client = LocalAssistant()
    monkeypatch.setattr(client, 'models', lambda: ['small:local'])
    result = asdict(AssistantIntent(action='create_pack', topic='Space', recipient=recipient))
    monkeypatch.setattr(client, '_request', lambda *args, **kwargs: {'done': True, 'message': {'content': json.dumps(result)}})
    assert client.interpret(prompt, 'small:local').recipient == expected
