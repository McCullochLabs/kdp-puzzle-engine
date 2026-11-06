import io
import json
import time
import threading
import pytest
from publishing.studio_codex import CodexAssistant, ProviderUnavailable, RequestCancelled


class KeepIO(io.StringIO):
    def close(self): pass


def fake_process(monkeypatch, *, account='chatgpt', ending=None, stalled=False):
    rows = [{'id': 1, 'result': {}}, {'id': 3, 'result': {'account': {'type': account}}},
            {'id': 4, 'result': {'config': {'mcp_servers': {'owner_server': {}}}}},
            {'id': 5, 'result': {'data': [{'model': 'test-model', 'isDefault': True}]}},
            {'id': 6, 'result': {'thread': {'id': 'thread-a'}}},
            {'id': 7, 'result': {'turn': {'id': 'turn-a'}}}]
    if ending is None:
        rows += [{'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': '{"ok":true}'}}},
                 {'method': 'turn/completed', 'params': {'turn': {'id': 'turn-a', 'status': 'completed'}}}]
    else: rows += ending
    class Process:
        def __init__(self):
            self.stdin = KeepIO(); self.killed = False
            self.stdout = self.lines() if stalled else KeepIO(''.join(json.dumps(row) + '\n' for row in rows))
        def lines(self):
            time.sleep(.2)
            yield ''
        def poll(self): return None if not self.killed else 0
        def kill(self): self.killed = True
        def wait(self, **kwargs): return 0
    proc = Process()
    calls = []
    monkeypatch.setattr('publishing.studio_codex.codex_command', lambda: ['codex-test'])
    monkeypatch.setattr('publishing.studio_codex.subprocess.Popen', lambda *a, **kw: calls.append(kw) or proc)
    return proc, calls


def test_completed_transport_disables_inherited_mcp_and_api_environment(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'DO_NOT_SEND')
    proc, calls = fake_process(monkeypatch)
    assert CodexAssistant().request('hello', {'type': 'object'}) == {'ok': True}
    messages = [json.loads(line) for line in proc.stdin.getvalue().splitlines()]
    start = next(row for row in messages if row['method'] == 'thread/start')['params']
    assert start['config']['mcp_servers.owner_server.enabled'] is False
    assert start['ephemeral'] and start['sandbox'] == 'read-only'
    assert 'OPENAI_API_KEY' not in calls[0]['env']
    assert proc.killed and len(calls) == 1


def test_api_auth_is_rejected_before_inference(monkeypatch):
    proc, _ = fake_process(monkeypatch, account='apiKey')
    with pytest.raises(ProviderUnavailable, match='API-key'): CodexAssistant().request('hello', {})
    assert 'turn/start' not in proc.stdin.getvalue()


@pytest.mark.parametrize('ending,match', [
    ([{'id': 99, 'method': 'item/commandExecution/requestApproval', 'params': {}}], 'unsupported tool'),
    ([{'method': 'item/started', 'params': {'item': {'type': 'commandExecution'}}}], 'tool action'),
    ([{'method': 'turn/completed', 'params': {'turn': {'status': 'failed', 'error': {'message': 'usage limit reached'}}}}], 'usage limit'),
    ([{'method': 'turn/completed', 'params': {'turn': {'status': 'interrupted'}}}], 'did not finish'),
    ([{'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': 'not JSON'}}},
      {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}}], 'invalid JSON'),
])
def test_transport_stops_failed_or_tool_requests(monkeypatch, ending, match):
    proc, calls = fake_process(monkeypatch, ending=ending)
    with pytest.raises(ProviderUnavailable, match=match): CodexAssistant().request('hello', {})
    assert proc.killed and len(calls) == 1


def test_transport_timeout_is_bounded(monkeypatch):
    proc, calls = fake_process(monkeypatch, stalled=True)
    # KeepIO supports close; a generator must have close as well.
    client = CodexAssistant(); client.timeout = .01
    with pytest.raises(ProviderUnavailable, match='timed out'): client.request('hello', {})
    assert proc.killed and len(calls) == 1
