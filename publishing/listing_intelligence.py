"""Gemini-first listing copy with verified-facts validation and local fallback.

When Gemini is configured, it receives only a small verified fact sheet and is
asked for a structured draft first.  The deterministic local generator takes
over only when Gemini is unavailable, its response fails validation, or the
feature is intentionally disabled.
"""
from __future__ import annotations
import json, os, re, time, urllib.error, urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from integrations.wincred import load_secret
from .listing_copy import listing_copy_text

DEFAULT_MODEL = "gemini-3.5-flash-lite"
PROMPT_VERSION = "listing-v2-gemini-first"

class ListingProviderError(RuntimeError): pass
class AuthError(ListingProviderError): pass
class QuotaError(ListingProviderError): pass
class ListingAIProvider(Protocol):
    provider_name: str
    def available(self) -> bool: ...
    def generate_listing(self, facts: dict) -> dict: ...

def _now(): return datetime.now().isoformat(timespec="seconds")
def _tokens(value): return {item for item in re.findall(r"[a-z0-9]+", str(value).casefold()) if len(item) > 2}

LISTING_FIELDS = {"subtitle", "description", "amazon_keywords", "etsy_tags", "website_tags", "platform_descriptions", "ingram_subjects", "marketing_hooks", "short_ad_copy", "capcut_prompt"}

def _human_fields(meta: dict) -> set[str]:
    """Read the lightweight ownership markers without guessing from copy text."""
    owners = meta.get("listing_field_ownership") if isinstance(meta.get("listing_field_ownership"), dict) else {}
    explicit = meta.get("human_edited_listing_fields") if isinstance(meta.get("human_edited_listing_fields"), list) else []
    return {str(name) for name in explicit} | {str(name) for name, owner in owners.items() if str(owner).casefold() in {"human", "locked", "manual"}}

def _semantic_unique(values, facts, limit, max_length=50):
    """Keep distinct discovery angles, not simple word-order rewrites."""
    selected=[]; seen=[]; title=_tokens(facts.get("title"))
    for value in values or []:
        phrase=" ".join(str(value).split()).strip(); tokens=_tokens(phrase)
        if not phrase or len(phrase)>max_length or tokens <= title: continue
        if any(tokens and len(tokens & prior) / max(1, min(len(tokens), len(prior))) >= .8 for prior in seen): continue
        selected.append(phrase); seen.append(tokens)
        if len(selected)>=limit: break
    return selected

@dataclass(frozen=True)
class GeminiCredentials:
    api_key: str
    model: str = DEFAULT_MODEL
    @classmethod
    def load(cls):
        key = os.environ.get("GEMINI_API_KEY", "").strip(); model = os.environ.get("GEMINI_LISTING_MODEL", "").strip() or DEFAULT_MODEL
        if key: return cls(key, model)
        saved = load_secret("GeminiListingAI") or {}; key = str(saved.get("api_key") or "").strip(); model = str(saved.get("model") or DEFAULT_MODEL).strip()
        return cls(key, model) if key else None

def verified_facts(book: dict, platform: str) -> dict:
    meta = book.get("metadata") or {}; prices = meta.get("price") if isinstance(meta.get("price"), dict) else {}
    kind = str(meta.get("puzzle_type") or "Word Search")
    digital = platform in {"payhip", "etsy", "website"}
    features = []
    if "large print" in " ".join(str(meta.get(k) or "") for k in ("title", "subtitle", "format_label")).casefold(): features.append("large print")
    if int(meta.get("puzzle_count") or 0) >= 100: features.append("100-puzzle Signature-scale collection")
    if bool(meta.get("no_repeat_words") or meta.get("unique_words_verified")): features.append("verified no-repeat word promise")
    return {"product_id": str(book.get("book_id") or ""), "title": str(meta.get("title") or ""), "subtitle": str(meta.get("subtitle") or ""), "topic": str(meta.get("theme") or meta.get("detected_topic") or ""), "puzzle_type": kind, "puzzle_count": int(meta.get("puzzle_count") or 0), "difficulty": str(meta.get("difficulty") or meta.get("difficulty_label") or "Standard"), "audience": str(meta.get("audience") or "adults and teens"), "page_count": int(meta.get("page_count") or 0), "format": "downloadable PDF" if digital else "paperback puzzle book", "trim": str(meta.get("trim_size") or "8.5x11"), "large_print": "large print" in features, "solutions_included": True, "series": str(meta.get("series") or ""), "author": str(meta.get("author") or ""), "platform": platform, "price": prices.get(platform) or prices.get("payhip" if digital else "amazon"), "digital": digital, "bundle_contents": [], "meaningful_features": features, "actual_puzzle_groups": list(meta.get("puzzle_groups") or [])[:12], "category_context": list(meta.get("ingram_subjects") or meta.get("categories") or [])[:4], "human_controlled_fields": sorted(_human_fields(meta))}

def _schema() -> dict:
    item = {"type": "string"}
    return {"type": "object", "properties": {"subtitle": item, "description": item, "short_description": item, "product_summary": item, "feature_bullets": {"type": "array", "items": item}, "buyer_benefits": {"type": "array", "items": item}, "audience_positioning": item, "differentiators": {"type": "array", "items": item}, "keywords": {"type": "array", "items": item}, "tags": {"type": "array", "items": item}, "marketing_hooks": {"type": "array", "items": item}, "short_ad_copy": item, "capcut_prompt": item, "category_suggestions": {"type": "array", "items": item}}, "required": ["subtitle", "description", "keywords", "tags", "marketing_hooks", "short_ad_copy", "capcut_prompt"], "additionalProperties": False}

def _prompt(facts: dict) -> str:
    return ("You are the primary listing-intelligence writer for a puzzle-book publisher. Adapt the writing specifically for the verified marketplace in the facts. Amazon needs accurate physical-book detail-page copy and seven backend phrases; Etsy needs readable merchandising copy, 13 concise tags, use cases, download instructions, and explicit digital disclosure; Payhip needs distinct branded landing-page copy and cross-sell direction; bookstore/distribution channels need professional bibliographic copy. Write specific, varied, customer-friendly copy from ONLY the verified facts below. Do not invent or change counts, features, audience, format, solution status, author, claims, market rules, shipping, ISBN, or bundle items. Do not use generic AI filler or repeat title words as keyword permutations. Never claim search volume, competition, sales, rank, profit, or bestseller likelihood. The subtitle is a recommendation only and must not silently rename a finished book. Return JSON only matching the supplied schema.\n\nVERIFIED FACTS:\n" + json.dumps(facts, ensure_ascii=False))

class GeminiListingProvider:
    provider_name = "Gemini"
    def __init__(self, credentials=None, timeout=15): self.credentials, self.timeout = credentials or GeminiCredentials.load(), timeout
    def available(self): return self.credentials is not None
    def generate_listing(self, facts: dict) -> dict:
        if not self.credentials: raise ListingProviderError("Gemini is not configured.")
        # Interactions are intentionally not stored server-side.  A listing
        # request contains only verified product facts, but there is no reason
        # to retain even that short request in the provider's interaction
        # history.
        body = {
            "model": self.credentials.model,
            "input": _prompt(facts),
            "store": False,
            "generation_config": {"max_output_tokens": 1800, "thinking_level": "minimal"},
            "response_format": {"type": "text", "mime_type": "application/json", "schema": _schema()},
        }
        request = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions", data=json.dumps(body).encode(), headers={"x-goog-api-key": self.credentials.api_key, "Content-Type": "application/json"}, method="POST")
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response: payload = json.loads(response.read().decode())
                text = _interaction_output_text(payload)
                return json.loads(text)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403): raise AuthError("Gemini did not accept the saved API key.") from None
                if exc.code in (429, 402): raise QuotaError("Gemini quota or rate limit reached; using local copy instead.") from None
                raise ListingProviderError(f"Gemini is unavailable (HTTP {exc.code}); using local copy instead.") from None
            except (urllib.error.URLError, TimeoutError):
                # A network outage must not turn an ordinary handoff into a
                # long UI freeze. The local route is intentionally immediate.
                raise ListingProviderError("Gemini timed out or is unreachable; using local copy instead.") from None
            except (json.JSONDecodeError, ValueError):
                if attempt: raise ListingProviderError("Gemini returned no usable structured copy; using local copy instead.") from None
                time.sleep(.4)

    def critique_listing(self, facts: dict, content: dict) -> dict:
        """Optional bounded second pass; failures leave valid primary copy intact."""
        if not self.credentials: raise ListingProviderError("Gemini is not configured.")
        schema = {"type":"object","properties":{"issues":{"type":"array","items":{"type":"string"}},"repair":{"type":"object","properties":_schema()["properties"],"additionalProperties":False}},"required":["issues"],"additionalProperties":False}
        prompt = ("Review this puzzle-book listing against the verified facts. Flag generic language, redundant keywords, unsupported claims, and marketplace mismatches. If a safe improvement is needed, return only changed fields in repair. Do not invent facts. Return JSON only.\n\nVERIFIED FACTS:\n" + json.dumps(facts, ensure_ascii=False) + "\n\nPRIMARY LISTING:\n" + json.dumps(content, ensure_ascii=False))
        body={"model":self.credentials.model,"input":prompt,"store":False,"generation_config":{"max_output_tokens":900,"thinking_level":"minimal"},"response_format":{"type":"text","mime_type":"application/json","schema":schema}}
        request=urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions",data=json.dumps(body).encode(),headers={"x-goog-api-key":self.credentials.api_key,"Content-Type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response: return json.loads(_interaction_output_text(json.loads(response.read().decode())))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            raise ListingProviderError("Gemini critic was unavailable; retained the locally validated primary listing.") from None


def _interaction_output_text(payload: dict) -> str:
    """Read the REST Interaction result without relying on SDK-only helpers."""
    text = str(payload.get("output_text") or "")
    if text:
        return text
    if str(payload.get("status") or "").casefold() in {"failed", "cancelled", "incomplete"}:
        raise ListingProviderError("Gemini did not complete the listing request; using local copy instead.")
    fragments = []
    for step in payload.get("steps", []):
        if str(step.get("type") or "") != "model_output":
            continue
        for content in step.get("content", []):
            if content.get("type") == "text":
                fragments.append(str(content.get("text") or ""))
    if not fragments:
        raise ListingProviderError("Gemini returned no usable structured copy; using local copy instead.")
    return "".join(fragments)

def validate_output(result: dict, facts: dict) -> tuple[bool, list[str], dict]:
    """Reject unsupported factual claims while allowing normal persuasive language."""
    issues=[]; text=" ".join(str(result.get(k) or "") + " " + " ".join(map(str, result.get(k, []) if isinstance(result.get(k), list) else [])) for k in ("subtitle","description","keywords","tags","marketing_hooks","short_ad_copy","capcut_prompt"))
    count=int(facts.get("puzzle_count") or 0); pages=int(facts.get("page_count") or 0)
    # Validate actual factual claims instead of rejecting harmless numbers in
    # prices, dates, or ordinary marketing language.
    for match in re.finditer(r"\b(\d{1,4})\s*(?:large[- ]print\s*)?(puzzles?|pages?)\b", text, re.I):
        value, label = int(match.group(1)), match.group(2).casefold()
        expected = count if label.startswith("puzzle") else pages
        if expected and value != expected:
            issues.append(f"Copy introduced an unsupported {label.rstrip('s')} count.")
            break
    lower=text.casefold()
    if facts.get("digital") and any(term in lower for term in ("paperback shipped", "ships to your door", "physical book")): issues.append("Digital product copy contradicts the verified download format.")
    if not facts.get("digital") and any(term in lower for term in ("instant download", "downloadable pdf", "no physical product")): issues.append("Print product copy contradicts the verified format.")
    if not facts.get("large_print") and "large print" in lower: issues.append("Copy claims large print without a verified large-print fact.")
    if not facts.get("solutions_included") and "solutions included" in lower: issues.append("Copy claims solutions without a verified fact.")
    cleaned={key: (value if isinstance(value, str) else [" ".join(str(item).split()) for item in value if str(item).strip()] if isinstance(value, list) else "") for key,value in result.items()}
    cleaned["keywords"]=_semantic_unique(cleaned.get("keywords", []), facts, 7); cleaned["tags"]=_semantic_unique(cleaned.get("tags", []), facts, 13, max_length=20)
    return not issues, issues, cleaned

def _unique(values, facts, limit):
    title_tokens=_tokens(facts.get("title")); selected=[]; seen=set()
    for value in values:
        phrase=" ".join(str(value).split()).strip(); key=phrase.casefold()
        if not phrase or key in seen or len(phrase)>50 or _tokens(phrase) <= title_tokens: continue
        selected.append(phrase); seen.add(key)
        if len(selected)>=limit: break
    return selected

def listing_critic(content: dict, facts: dict) -> list[str]:
    """A local second pass that never changes verified facts or copy on its own."""
    notes = []
    description = " ".join(str(content.get("description") or "").split())
    keywords = list(content.get("keywords") or [])
    if len(description) < 120: notes.append("Description is brief; add a clearer buyer benefit if this is an AI suggestion you plan to use.")
    if len(set(str(value).casefold() for value in keywords)) != len(keywords): notes.append("Keyword phrases repeat; keep only distinct discovery phrases.")
    title_terms = _tokens(facts.get("title"))
    if keywords and all(_tokens(value) <= title_terms for value in keywords): notes.append("Keywords only repeat title words; add topic, audience, or use-case discovery terms.")
    if not facts.get("topic"): notes.append("No verified topic is available; keep listing language broad until the book facts are completed.")
    return notes or ["Local listing critic found no obvious generic, duplicate, or fact-risk issue."]

def local_fallback_content(book: dict, facts: dict) -> dict:
    """Specific offline copy for when Gemini is unavailable—not a flat template."""
    meta = book.get("metadata") or {}; title=str(facts.get("title") or "Puzzle Book"); topic=str(facts.get("topic") or "this theme")
    kind=str(facts.get("puzzle_type") or "Puzzle Book"); count=int(facts.get("puzzle_count") or 0); audience=str(facts.get("audience") or "puzzle lovers")
    experiences = {
        "Word Search": "scan the grid for familiar theme words and settle into a satisfying paper-and-pencil break",
        "Sudoku": "work through orderly logic challenges at a comfortable pace",
        "Cryptogram": "follow clues, spot patterns, and uncover each encoded message",
        "Word Scramble + Trivia": "unscramble a themed word, then use the paired trivia to deepen the challenge",
        "Mixed Brain Games": "switch between varied challenges for a more flexible, screen-free puzzle session",
    }
    experience=experiences.get(kind, "enjoy a focused, screen-free puzzle session")
    large=" The large-print presentation keeps the pages easy to follow." if facts.get("large_print") else ""
    core=(f"{title} brings {topic} to the puzzle table with {count} {kind.lower()} challenges for {audience}. "
                 f"Readers can {experience}. Every challenge is organized for easy pick-up-and-put-down solving, with solutions available when it is time to check an answer.{large}\n\n"
                 f"This is a focused collection for readers who genuinely enjoy {topic}—not a catch-all puzzle book. Start anywhere, work at your own rhythm, and return whenever you want a clear, enjoyable mental break.")
    platform = str(facts.get("platform") or "amazon").casefold()
    if platform == "etsy":
        description = (f"A printable {topic} puzzle experience for {audience}. {core}\n\n"
                       f"WHAT YOU RECEIVE\n• One downloadable PDF\n• {count} {kind.lower()} challenges\n• Complete solutions\n\n"
                       "DIGITAL DOWNLOAD — NO PHYSICAL PRODUCT. Download access is provided by the marketplace after purchase; printing results depend on your printer and settings.")
    elif platform == "payhip":
        description = (f"Make room for a focused, screen-free {topic} break. {core}\n\n"
                       "Your purchase includes a customer-ready downloadable PDF with the complete puzzle collection and solutions. Save it for personal use and print the pages you want according to the included use guidance.")
    elif platform in {"ingram", "barnes_noble"}:
        description = (f"{title} is a professionally organized {kind.lower()} collection focused on {topic}. "
                       f"It contains {count} puzzles for {audience}, uses a {facts.get('difficulty') or 'Standard'} difficulty level, and includes complete solutions. "
                       "The edition is designed for clear navigation and dependable paper-and-pencil use.")
    elif platform in {"lulu", "bookvault", "website", "direct"}:
        description = (f"A direct-sale {topic} puzzle collection with clear product specifications: {count} {kind.lower()} challenges, complete solutions, and a {facts.get('trim') or 'verified'} page format. " + core)
    else:
        description = core
    subject = (title + " " + topic).casefold()
    niche_map = [
        (("car", "vehicle", "automotive", "road trip"), ["vintage car word games", "road trip activity book", "car enthusiast gift", "classic truck puzzles", "highway travel word find"]),
        (("garden", "kitchen", "food"), ["garden themed puzzles", "kitchen table games", "home hobby activity", "food lover word games", "screen free hobby book"]),
        (("space", "celestial", "stargazer", "astronomy"), ["astronomy puzzle book", "space themed brain games", "stargazing activity book", "planet lover puzzles", "cosmic logic challenges"]),
        (("heritage", "history", "american"), ["american history puzzles", "heritage activity book", "history lover brain games", "usa trivia challenge", "screen free history gift"]),
        (("vocabulary", "grade", "study", "school"), ["grade school vocabulary", "student word practice", "classroom brain break", "learning activity book", "school word games"]),
        (("wild", "nature", "outdoor"), ["nature themed brain games", "outdoor activity book", "wildlife puzzle collection", "national park style puzzles", "screen free nature gift"]),
    ]
    niche = next((phrases for triggers, phrases in niche_map if any(trigger in subject for trigger in triggers)), [])
    type_angles = {"Word Search":["adult word find book", "large print word games" if facts.get("large_print") else "themed word search book"], "Sudoku":["symbol sudoku puzzles", "logic puzzle activity book"], "Cryptogram":["code breaking puzzles", "cipher challenge book"], "Word Scramble + Trivia":["word scramble trivia", "themed trivia challenge"], "Mixed Brain Games":["variety puzzle collection", "brain game activity book"]}
    existing = [*niche, *type_angles.get(kind, []), f"{kind.lower()} for {audience}", "screen free puzzle break", *(meta.get("amazon_keywords") or [])]
    tags = [*niche, *type_angles.get(kind, []), topic, "printable puzzle pdf", "puzzle book gift", *(meta.get("etsy_tags") or [])]
    return {"description":description,"subtitle":str(facts.get("subtitle") or ""),"keywords":_semantic_unique(existing, facts, 7),"tags":_semantic_unique(tags, facts, 13,20),"marketing_hooks":[f"A focused {topic} puzzle break.", f"{count} challenges for readers who enjoy {topic}."],"short_ad_copy":f"A focused {topic} puzzle break with {count} {kind.lower()} challenges.","capcut_prompt":f"Use the verified cover and real interior pages to show {title}; do not add unverified claims."}

def repair_output(result: dict, facts: dict) -> dict:
    """Repair individual unsafe fields without throwing away a valid AI draft."""
    repaired = dict(result or {})
    text = " ".join(str(repaired.get(key) or "") for key in ("subtitle", "description", "short_ad_copy"))
    if any(str(facts.get(key) or "") and str(facts.get(key)) not in text for key in ()):
        pass
    # Copy that contains an unsupported count or format is replaced locally;
    # discovery and marketing fields can still be safely retained.
    valid, issues, cleaned = validate_output(repaired, facts)
    if valid: return cleaned
    if any("count" in issue or "format" in issue or "large print" in issue or "solutions" in issue for issue in issues):
        fallback = listing_copy_text({"metadata": {**facts, "title": facts.get("title"), "subtitle": facts.get("subtitle"), "theme": facts.get("topic"), "puzzle_type": facts.get("puzzle_type"), "puzzle_count": facts.get("puzzle_count"), "difficulty": facts.get("difficulty")}}, facts.get("platform") or "amazon")
        repaired["description"] = " ".join(line for line in fallback.splitlines() if line and not line.isupper())
        repaired["subtitle"] = str(facts.get("subtitle") or "")
    valid, _issues, cleaned = validate_output(repaired, facts)
    return cleaned if valid else {**local_fallback_content({"metadata": {}}, facts), "keywords": _semantic_unique(result.get("keywords", []), facts, 7), "tags": _semantic_unique(result.get("tags", []), facts, 13, 20)}

def apply_listing_intelligence(metadata: dict, record: dict) -> tuple[dict, list[str]]:
    """Apply validated AI fields only where the owner is not the user."""
    meta = dict(metadata); content = record.get("content") if isinstance(record.get("content"), dict) else {}; protected = _human_fields(meta); changed=[]
    ownership = dict(meta.get("listing_field_ownership") or {})
    def set_field(name, value):
        if name in protected or not value: return
        meta[name]=value; ownership[name]="gemini" if record.get("provider") != "Deterministic local listing" else "local"; changed.append(name)
    set_field("description", str(content.get("description") or ""))
    # Keep finished titles/subtitles stable: this remains a recommendation.
    if content.get("subtitle"):
        meta["subtitle_suggestion"] = str(content["subtitle"]); ownership["subtitle_suggestion"]="gemini"; changed.append("subtitle_suggestion")
    set_field("amazon_keywords", _semantic_unique(content.get("keywords", []), meta, 7))
    set_field("etsy_tags", _semantic_unique(content.get("tags", []), meta, 13, 20))
    if "website_tags" not in protected:
        set_field("website_tags", _semantic_unique([*(content.get("keywords") or []), *(content.get("tags") or [])], meta, 20))
    platforms = dict(meta.get("platform_descriptions") or {})
    if "platform_descriptions" not in protected and content.get("description"):
        base = str(content["description"])
        target_platform = str(record.get("platform") or "").casefold()
        if target_platform:
            platforms[target_platform] = base
        else:
            # Backward compatibility for imported legacy records that predate
            # marketplace-scoped listing intelligence.
            for platform in ("amazon", "ingram", "lulu", "bookvault", "barnes_noble", "website"):
                platforms[platform] = base
            platforms["etsy"] = base + "\n\nDIGITAL PRODUCT: This listing is for a downloadable PDF. No physical product will be shipped."
            platforms["payhip"] = platforms["etsy"]
        meta["platform_descriptions"] = platforms; ownership["platform_descriptions"]="gemini" if record.get("provider") != "Deterministic local listing" else "local"; changed.append("platform_descriptions")
    for name in ("marketing_hooks", "short_ad_copy", "capcut_prompt", "feature_bullets", "buyer_benefits", "differentiators", "category_suggestions"):
        set_field(name, content.get(name))
    meta["listing_field_ownership"] = ownership
    meta["listing_intelligence"] = {"source": record.get("provider"), "validation": record.get("validation"), "generated_at": record.get("generated_at", _now()), "critic_notes": record.get("critic_notes", []), "changed_fields": changed}
    meta["marketplace_copy_source"] = "gemini_validated" if record.get("provider") != "Deterministic local listing" else "local_fallback"
    return meta, changed

class ListingIntelligence:
    def __init__(self, project: Path, provider=None): self.project=Path(project); self.provider=provider or GeminiListingProvider(); self.cache_path=self.project/"data"/"listing_ai_cache.json"
    def _cache(self):
        try: return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError): return {}
    def _save(self, value): self.cache_path.parent.mkdir(parents=True,exist_ok=True); temp=self.cache_path.with_suffix(".tmp"); temp.write_text(json.dumps(value,indent=2),encoding="utf-8"); temp.replace(self.cache_path)
    def generate(self, book: dict, platform: str, enabled=True) -> dict:
        facts=verified_facts(book,platform); revision=hashlib_sha(facts); key=f"{facts['product_id']}|{platform}|{PROMPT_VERSION}|{getattr(self.provider,'provider_name','local')}|{getattr(getattr(self.provider,'credentials',None),'model','local')}"
        cache=self._cache(); cached=cache.get(key)
        if cached and cached.get("revision")==revision: return {**cached,"cached":True}
        fallback={"provider":"Deterministic local listing", "platform":platform, "generated_at":_now(), "content":local_fallback_content(book, facts),"validation":"local fallback","revision":revision,"cached":False,"critic_notes":["Gemini was unavailable, disabled, or rejected; specific deterministic local copy was used."]}
        if not enabled or not self.provider.available(): return fallback
        try:
            raw=self.provider.generate_listing(facts); valid,issues,clean=validate_output(raw,facts)
            repaired = False
            if not valid:
                clean = repair_output(raw, facts)
                valid, repaired_issues, clean = validate_output(clean, facts)
                repaired = valid
                issues = issues + repaired_issues
            if not valid: return {**fallback,"validation":"rejected: "+" | ".join(issues)}
            critic_notes=listing_critic(clean,facts); critic_source="local critic"
            if hasattr(self.provider,"critique_listing"):
                try:
                    critique=self.provider.critique_listing(facts,clean); critic_source="Gemini critic + local validation"
                    critic_notes=[str(note) for note in critique.get("issues",[]) if str(note).strip()] or critic_notes
                    proposed=critique.get("repair") if isinstance(critique.get("repair"),dict) else {}
                    if proposed:
                        candidate={**clean,**proposed}; candidate_valid,_candidate_issues,candidate_clean=validate_output(candidate,facts)
                        if candidate_valid: clean=candidate_clean; repaired=True
                except ListingProviderError as exc:
                    critic_notes.append(str(exc))
            record={"provider":getattr(self.provider,"provider_name","Gemini"),"platform":platform,"model":getattr(getattr(self.provider,"credentials",None),"model",DEFAULT_MODEL),"prompt_version":PROMPT_VERSION,"generated_at":_now(),"revision":revision,"validation":"repaired" if repaired else "passed","source_status":"Gemini + local repair" if repaired else "Gemini + local validation","content":clean,"critic_notes":critic_notes,"critic_source":critic_source,"cached":False}; cache[key]=record; self._save(cache); return record
        except ListingProviderError as exc: return {**fallback,"validation":str(exc)}

def hashlib_sha(value):
    import hashlib
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
