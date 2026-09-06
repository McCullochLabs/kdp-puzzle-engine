"""Optional image-provider boundary. The project works normally without it."""
from __future__ import annotations

import base64, json, os, urllib.error, urllib.request
from dataclasses import dataclass
from typing import Protocol
from integrations.wincred import load_secret

DEFAULT_CLOUDFLARE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
class ProviderError(RuntimeError): pass
class ProviderNotConfigured(ProviderError): pass
class ProviderAuthenticationError(ProviderError): pass
class ProviderRateLimitedError(ProviderError): pass


class BackgroundProvider(Protocol):
    """Small provider contract; a future local or hosted provider can slot in."""
    name: str
    def generate(self, prompt: str, *, steps: int = 4) -> bytes: ...

@dataclass(frozen=True)
class CloudflareCredentials:
    account_id: str
    api_token: str
    model: str = DEFAULT_CLOUDFLARE_MODEL
    @classmethod
    def load(cls):
        account_id, api_token = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(), os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        model = os.environ.get("CLOUDFLARE_WORKERS_AI_MODEL", "").strip() or DEFAULT_CLOUDFLARE_MODEL
        if account_id and api_token: return cls(account_id, api_token, model)
        saved = load_secret("CloudflareWorkersAI") or {}
        account_id, api_token = str(saved.get("account_id") or "").strip(), str(saved.get("api_token") or "").strip()
        model = str(saved.get("model") or DEFAULT_CLOUDFLARE_MODEL).strip()
        return cls(account_id, api_token, model) if account_id and api_token else None

class CloudflareWorkersAIProvider:
    name = "cloudflare_workers_ai"
    def __init__(self, credentials=None, timeout: int = 90): self.credentials, self.timeout = credentials or CloudflareCredentials.load(), timeout
    @property
    def configured(self): return self.credentials is not None
    def generate(self, prompt: str, *, steps: int = 4) -> bytes:
        if not self.credentials: raise ProviderNotConfigured("Cloudflare image generation is not connected. Add credentials in Connections first.")
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.credentials.account_id}/ai/run/{self.credentials.model}"
        request = urllib.request.Request(url, data=json.dumps({"prompt": prompt, "steps": max(1, min(int(steps), 8))}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.credentials.api_token}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response: body, content_type = response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403): raise ProviderAuthenticationError("Cloudflare did not accept the saved image-generation credentials.") from None
            if exc.code == 429: raise ProviderRateLimitedError("Cloudflare temporarily limited image generation. The request was paused safely.") from None
            raise ProviderError(f"Cloudflare image generation could not finish (HTTP {exc.code}).") from None
        except urllib.error.URLError: raise ProviderError("Cloudflare could not be reached. Check your connection and try again.") from None
        if content_type.startswith("image/"): return body
        try:
            parsed = json.loads(body.decode("utf-8")); result = parsed.get("result", parsed); encoded = result.get("image") if isinstance(result, dict) else None
            if isinstance(encoded, str): return base64.b64decode(encoded)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError): pass
        raise ProviderError("Cloudflare returned an image response the studio could not verify.")
