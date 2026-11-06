"""Optional image-provider boundary. The project works normally without it."""
from __future__ import annotations

import base64, json, os, urllib.error, urllib.request
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class GeminiImageCredentials:
    api_key: str = field(repr=False)
    model: str = 'gemini-nano-banana-2.1'
    @classmethod
    def load(cls):
        saved = load_secret('GeminiCoverAI') or load_secret('GeminiListingAI') or {}
        key = str(saved.get('api_key') or '').strip()
        # Listing models cannot generate images. Reuse only the securely stored key.
        model = str(saved.get('image_model') or 'gemini-nano-banana-2.1').strip()
        return cls(key,model) if key else None


class GeminiImageProvider:
    """Explicit paid image request; never falls back or retries a billable call."""
    name = 'gemini_api'
    provenance_name = 'Gemini API'
    def __init__(self,credentials=None,*,allow_paid=False,timeout=120):
        self.credentials=credentials or GeminiImageCredentials.load()
        self.allow_paid=allow_paid is True
        self.timeout=timeout
    @property
    def configured(self):return self.credentials is not None
    def generate(self,prompt: str,*,steps: int=4)->bytes:
        if not self.credentials:raise ProviderNotConfigured('Gemini image generation needs a saved Gemini API key in Connections.')
        if not self.allow_paid:raise ProviderNotConfigured('Gemini image generation is paid-only. Explicit paid-call permission is required before sending this request.')
        allowed={'gemini-nano-banana-2.1','gemini-3.1-flash-image','gemini-3-pro-image'}
        if self.credentials.model not in allowed:raise ProviderError('Choose a supported Gemini image model; the listing model cannot create cover artwork.')
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>12000:raise ProviderError('Provide a bounded cover-art prompt.')
        body={'model':self.credentials.model,'input':prompt,'store':False,
              'generation_config':{'max_output_tokens':8192},
              'response_format':{'type':'image','mime_type':'image/png','aspect_ratio':'3:4','image_size':'4K'}}
        request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/interactions',
            data=json.dumps(body).encode('utf-8'),headers={'x-goog-api-key':self.credentials.api_key,'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response:
                raw=response.read(64*1024*1024+1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):raise ProviderAuthenticationError('Gemini did not accept the image request. Check the saved key, image-model access and billing configuration.') from None
            if exc.code in (402,429):raise ProviderRateLimitedError('Gemini image quota or billing limit reached. The request was paused; no retry or alternate provider was used.') from None
            raise ProviderError(f'Gemini image generation failed (HTTP {exc.code}); no automatic retry was made.') from None
        except (urllib.error.URLError,TimeoutError):raise ProviderError('Gemini image generation timed out or was unreachable. No automatic retry was made.') from None
        if len(raw)>64*1024*1024:raise ProviderError('Gemini returned an oversized image response.')
        try:
            payload=json.loads(raw.decode('utf-8'))
            if not isinstance(payload,dict):raise ValueError('Malformed interaction')
            if isinstance(payload.get('interaction'),dict):payload=payload['interaction']
            if payload.get('status') not in (None,'completed'):raise ValueError('incomplete')
            images=[block for step in payload.get('steps',[]) if isinstance(step,dict) and step.get('type')=='model_output'
                    for block in step.get('content',[]) if isinstance(block,dict) and block.get('type')=='image' and block.get('mime_type') in ('image/png','image/jpeg')]
            if len(images)!=1:raise ValueError('Expected one completed image')
            return base64.b64decode(images[0]['data'],validate=True)
        except (ValueError,KeyError,TypeError,UnicodeDecodeError):raise ProviderError('Gemini did not return one complete supported image; no candidate was approved.') from None
