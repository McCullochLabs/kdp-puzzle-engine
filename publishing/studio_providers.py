"""One explicit provider interface and cancellation gate for Studio requests."""
from __future__ import annotations
import threading
from .studio_assistant import LocalAssistant, guide_request, refers_to_current
from .studio_codex import CodexAssistant, RequestCancelled

_OLLAMA_INFLIGHT = threading.Lock()

PROVIDERS = ('Codex (ChatGPT sign-in)', 'Ollama (this computer)', 'Guide (no AI)')


def interpret_request(provider, text, model='', history=None, context=None, previous=None, cancel=None):
    if cancel and cancel.is_set(): raise RequestCancelled('Request cancelled.')
    if refers_to_current(text) and not context: return guide_request('', None)
    if provider == 'Codex':
        intent = CodexAssistant().interpret(text, history=history, context=context, cancel=cancel)
    elif provider == 'Ollama':
        if not _OLLAMA_INFLIGHT.acquire(blocking=False):
            from .studio_codex import ProviderUnavailable
            raise ProviderUnavailable('The previous local request is still finishing. Wait a moment or use the manual buttons.')
        try:
            intent = LocalAssistant().interpret(text, model, history, context)
        finally:
            _OLLAMA_INFLIGHT.release()
    elif provider == 'Guide':
        intent = guide_request(text, previous, context)
    else:
        raise ValueError('Choose Codex, Ollama, or Guide in Settings.')
    if cancel and cancel.is_set(): raise RequestCancelled('Request cancelled.')
    return intent


class RequestGate:
    """Ignore results after cancellation, selection changes, or provider changes."""
    def __init__(self):
        self.serial = 0
        self.cancel = threading.Event()
        self.active = None

    def begin(self, provider, context):
        if self.active is not None: raise ValueError('A request is already running.')
        self.serial += 1
        self.cancel = threading.Event()
        self.active = (self.serial, provider, dict(context) if context else None)
        return self.active, self.cancel

    def stop(self):
        self.cancel.set()
        self.active = None

    def accepts(self, ticket, provider, context):
        return (not self.cancel.is_set() and ticket == self.active and
                ticket[1:] == (provider, dict(context) if context else None))
