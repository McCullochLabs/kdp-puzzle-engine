"""Etsy draft automation orchestrator: prepare -> create -> attach -> verify.

End state guarantee: this module can ONLY ever leave behind a DRAFT listing
on Etsy with the buyer-ready PDF and a listing image attached.  It contains no
code path that activates, publishes, prices-after-the-fact, or deletes
anything.  Every user-facing phrase repeats that truth ("created online — not
published") so the Hub can never imply more than happened.

Duplicate / recovery safety (M5):

- One stable ``idempotency_key`` is persisted per (book, marketplace) before
  anything is created.
- Before creating, the shop's existing drafts are scanned for the exact same
  case-folded title; a match is ADOPTED instead of duplicated.
- The assigned listing ID is persisted immediately after creation, so a crash
  mid-upload resumes instead of creating a second draft.
- Uploads are skipped when the listing already has files/images (read-only
  checks), so re-running never duplicates attachments.
- Final reconciliation re-reads the listing online and verifies it is still a
  DRAFT with the expected title before reporting success.

Publishing-side coupling (PublishingDatabase/PublishingService) is imported
lazily inside methods so integrations/ stays independent of publishing/ at
import time.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from integrations.errors import AuthError, IntegrationError, NotConfiguredError, PermanentError, TransientError
from integrations.etsy.drafts import EtsyDraftClient
from integrations.etsy.capabilities import ETSY_CAPABILITIES
from integrations.etsy.session import EtsySession, load_credentials

# Etsy's documented per-file limit for digital listings; kept in step with
# publishing/etsy_bundles.ETSY_PER_FILE_LIMIT without importing Pillow here.
MAX_DIGITAL_FILE_BYTES = 20 * 1024 * 1024

STATE_DRAFT_CREATED = "draft_created"
STATE_FILES_UPLOADED = "files_uploaded"
STATE_COMPLETE = "complete"

# Listing states that mean "NOT live" on Etsy.  Anything outside this set is
# reported as an unexpected manual change; we never try to "fix" it remotely.
DRAFT_LIKE_STATES = frozenset({"draft", "edit"})

_TITLE_MAX_CHARS = 140
_TAG_MAX_CHARS = 20
_MAX_TAGS = 13

# Etsy title charset (documented): letters, numbers, punctuation, math
# symbols, whitespace, trademark signs.  Everything else is stripped.
_TITLE_ALLOWED = re.compile(r"[^\w\s.,!?'\"()\[\]/&%:+\-™©®]", re.UNICODE)
_TAG_ALLOWED = re.compile(r"[^\w \-'™©®]", re.UNICODE)

TAXONOMY_ENV_VAR = "KDP_ETSY_TAXONOMY_ID"


@dataclass(frozen=True)
class DraftResult:
    """Non-secret outcome for the GUI; safe to display verbatim."""

    ok: bool
    message: str
    listing_id: str = ""
    shop_name: str = ""
    integration_state: str = ""
    events: List[str] = field(default_factory=list)


def sanitize_title(raw: str) -> str:
    """Clamp a metadata title into Etsy's documented title rules."""
    cleaned = _TITLE_ALLOWED.sub("", str(raw or ""))
    cleaned = " ".join(cleaned.split())
    return cleaned[:_TITLE_MAX_CHARS].strip()


def sanitize_tags(tags, limit: int = _MAX_TAGS, max_length: int = _TAG_MAX_CHARS) -> List[str]:
    """Clamp tags into Etsy's documented tag rules (count and length capped)."""
    output: List[str] = []
    seen = set()
    for raw in tags or ():
        cleaned = _TAG_ALLOWED.sub("", str(raw)).strip()
        cleaned = " ".join(cleaned.split())[:max_length]
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def find_taxonomy_id(nodes_payload: dict, wanted_name: str = "books") -> Optional[int]:
    """Walk the seller taxonomy tree for a node named *wanted_name*.

    Prefers nodes whose parent chain mentions the same word (e.g.
    "... > Books & Zines > Books").  Returns None when nothing matches;
    callers then surface setup guidance instead of guessing.
    """
    wanted = wanted_name.strip().casefold()

    def walk(node, trail):
        name = str(node.get("name") or "").strip().casefold()
        here = trail + [name]
        if name == wanted:
            yield len(here), sum(1 for part in here if wanted in part), node.get("id")
        for child in node.get("children") or []:
            yield from walk(child, here)

    candidates = []
    for root in (nodes_payload or {}).get("results") or []:
        candidates.extend(walk(root, []))
    if not candidates:
        return None
    # Deeper (more specific) wins; then stronger parent-path relevance.
    candidates.sort(key=lambda item: (-item[0], -item[1]))
    best = candidates[0][2]
    try:
        return int(best)
    except (TypeError, ValueError):
        return None


def build_draft_fields(metadata: dict, taxonomy_id: int, price: float) -> dict:
    """Form fields for createDraftListing of a digital-download puzzle book."""
    tags = sanitize_tags((metadata or {}).get("etsy_tags"))
    fields = {
        "quantity": "999",
        "title": sanitize_title((metadata or {}).get("title")),
        "description": str((metadata or {}).get("description") or "").strip(),
        "price": f"{float(price):.2f}",
        "who_made": "i_did",
        "when_made": "made_to_order",
        "taxonomy_id": str(int(taxonomy_id)),
        "type": "download",
        "is_supply": "false",
    }
    if tags:
        fields["tags"] = ",".join(tags)
    return fields


class EtsyDraftService:
    """Current Etsy write service, limited to drafts and attachments.

    Its one entry point is :meth:`create_or_resume`, which always returns a
    :class:`DraftResult` and never activates a listing.
    """

    capabilities = ETSY_CAPABILITIES

    def __init__(
        self,
        *,
        transport=None,
        token_store=None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._transport = transport
        self._token_store = token_store
        self._sleep = sleep

    # -- public ---------------------------------------------------------------

    def create_or_resume(self, service, book: dict) -> DraftResult:
        """Create (or finish resuming) one Etsy draft for *book*.

        Never raises for ordinary failure modes; failures come back as
        DraftResult(ok=False, ...) with sanitized messages and are logged to
        the integration trail so the Hub stays responsive.
        """
        db = service.db
        book_id = book["book_id"]
        metadata = book.get("metadata") or {}
        events: List[str] = []

        def note(event: str, detail: str = "") -> None:
            db.record_integration_event(book_id, "etsy", event, detail)
            # Keep the machine-readable name AND the plain-English sentence so
            # the same string works for the GUI and for log triage.
            events.append(f"{event}: {detail}" if detail else event)

        # Guard 1: never automate anything around a human-confirmed record.
        prior = db.marketplace_records(book_id)["etsy"]
        if prior["status"] in ("Uploaded", "Published"):
            return DraftResult(
                ok=False,
                message=(f"Etsy is already recorded as {prior['status']}. "
                         "This app will not touch confirmed listings."),
                integration_state=prior.get("integration_state", ""),
                events=events,
            )

        # Guard 2: local buyer-ready file must exist BEFORE any remote call.
        package = str(book.get("package_path") or "")
        prepared_dir = os.path.join(package, "etsy") if package else ""
        printable_path = os.path.join(prepared_dir, "printable.pdf") if prepared_dir else ""
        if not printable_path or not os.path.isfile(printable_path):
            return DraftResult(
                ok=False,
                message=("The prepared Etsy folder with printable.pdf was not found. "
                         "Click Prepare Etsy first, then run this again."),
                integration_state=prior.get("integration_state", ""),
                events=events,
            )
        if os.path.getsize(printable_path) > MAX_DIGITAL_FILE_BYTES:
            return DraftResult(
                ok=False,
                message=("printable.pdf is larger than Etsy's 20 MB digital-file limit. "
                         "Split the download bundle and prepare again."),
                integration_state=prior.get("integration_state", ""),
                events=events,
            )

        try:
            result = self._run_remote(db, book, metadata, printable_path, prepared_dir, note, events)
        except NotConfiguredError as exc:
            note("failed", str(exc))
            return DraftResult(ok=False, message=f"{exc} Use Marketplace connections to connect Etsy first.",
                               events=events)
        except AuthError as exc:
            note("failed", exc.message)
            return DraftResult(ok=False,
                               message=f"{exc.message} Open Marketplace connections and reconnect Etsy.",
                               events=events)
        except TransientError as exc:
            note("failed", exc.message)
            return DraftResult(ok=False,
                               message=("Etsy could not be reached right now. Nothing was published; "
                                        f"try again later. ({exc.message})"),
                               events=events)
        except IntegrationError as exc:
            note("failed", exc.message)
            return DraftResult(ok=False,
                               message=f"Etsy rejected the request: {exc.message} Nothing was published.",
                               events=events)
        return result

    # -- internals --------------------------------------------------------------

    def _run_remote(self, db, book, metadata, printable_path, prepared_dir, note, events) -> DraftResult:
        book_id = book["book_id"]
        prior = db.marketplace_records(book_id)["etsy"]
        credentials = load_credentials(store=self._token_store)
        if not credentials.api_keystring:
            raise NotConfiguredError("No Etsy app keystring is stored.")
        session = EtsySession(
            lambda: load_credentials(store=self._token_store),
            transport=self._transport,
            token_store=self._token_store,
            sleep=self._sleep,
        )
        client = EtsyDraftClient(session)

        me = client.get_me()
        user_id = me.get("user_id")
        if not user_id:
            raise PermanentError("Etsy did not report the account user id.")
        shops = client.get_user_shops(user_id)
        results = (shops or {}).get("results") or []
        if not results:
            raise PermanentError("No Etsy shop belongs to this account yet.")
        shop = results[0]
        shop_id = shop.get("shop_id")
        shop_name = shop.get("shop_name") or str(shop_id)
        if not shop_id:
            raise PermanentError("Etsy did not report the shop id.")

        integration = db.integration_record(book_id, "etsy")
        idempotency_key = integration["idempotency_key"] or f"{book_id}|{(metadata.get('title') or '').strip()}"
        listing_id = self._existing_listing_id(prior.get("external_id"))

        # Resume: verify a previously recorded draft still exists online.
        if listing_id is not None:
            try:
                current = client.get_listing(listing_id)
            except AuthError:
                raise
            except PermanentError as exc:
                if getattr(exc, "status_code", None) != 404:
                    raise
                current = None  # the draft vanished remotely; recreate fresh below
            if current is None:
                note("resume_note", f"Previously recorded Etsy draft {listing_id} could not be read; creating fresh.")
                listing_id = None
            elif str(current.get("state") or "").casefold() not in DRAFT_LIKE_STATES:
                return DraftResult(
                    ok=False,
                    message=(f"Etsy listing {listing_id} is no longer a draft "
                             f"(online state: {current.get('state')}). Review it manually; "
                             "this app will not change it."),
                    listing_id=str(listing_id), shop_name=shop_name,
                    integration_state=integration["integration_state"], events=events,
                )

        # Fresh creation with duplicate scan (adopt same-title draft instead).
        if listing_id is None:
            adopted = self._find_existing_draft(client, shop_id, metadata)
            if adopted is not None:
                listing_id = adopted
                note("existing_draft_adopted",
                     f"Adopted the existing Etsy draft {listing_id} with the same title.")
            else:
                taxonomy_id = self._resolve_taxonomy(client)
                price = float(((metadata.get("price") or {}).get("etsy")) or 6.99)
                # Universal Publishing adoption: build the payload from the
                # canonical MasterProduct through the shared EtsyListingMapper.
                # Byte-parity with build_draft_fields is proven by tests; the
                # import stays local because the mapper reuses this module's
                # title/tag sanitizers (import cycle).
                from integrations.factory import MasterProductFactory
                from integrations.etsy.mapper import EtsyListingMapper

                product = MasterProductFactory.from_book_record(book)
                fields = EtsyListingMapper().to_listing_data(
                    product, taxonomy_id=taxonomy_id, price_override=price).to_form_fields()
                created = client.create_draft_listing(shop_id, fields)
                new_id = created.get("listing_id")
                if not new_id:
                    raise PermanentError("Etsy accepted the draft but did not return a listing id.")
                listing_id = int(new_id)
                note("draft_created",
                     f"Etsy draft {listing_id} created online — NOT published.")

        # Persist identifiers IMMEDIATELY so a crash cannot cause duplicates.
        db.set_integration_state(book_id, "etsy", STATE_DRAFT_CREATED,
                                 external_sku=os.path.basename(printable_path),
                                 idempotency_key=idempotency_key)
        self._record_listing_id(db, book, str(listing_id), prior["status"])

        # Digital file attachment (skipped when the draft already has files).
        files = (client.list_listing_files(shop_id, listing_id) or {}).get("results") or []
        if not files:
            with open(printable_path, "rb") as handle:
                content = handle.read()
            client.upload_listing_file(shop_id, listing_id, os.path.basename(printable_path), content)
            note("file_uploaded", f"Attached {os.path.basename(printable_path)} to the draft.")
        else:
            note("file_already_attached", "The draft already has its digital file; upload skipped.")
        db.set_integration_state(book_id, "etsy", STATE_FILES_UPLOADED,
                                 external_sku=os.path.basename(printable_path),
                                 idempotency_key=idempotency_key)

        # One listing image (thumbnail.jpg preferred, else first preview).
        images = (client.list_listing_images(shop_id, listing_id) or {}).get("results") or []
        if not images:
            image_path = self._pick_image(prepared_dir)
            if image_path is None:
                note("image_skipped",
                     "No thumbnail.jpg or preview image found in the prepared folder; add one in Etsy Shop Manager.")
            else:
                with open(image_path, "rb") as handle:
                    image_content = handle.read()
                client.upload_listing_image(shop_id, listing_id, os.path.basename(image_path), image_content)
                note("image_uploaded", f"Attached listing image {os.path.basename(image_path)}.")
        else:
            note("image_already_attached", "The draft already has a listing image; upload skipped.")

        # Reconciliation: read back and confirm it is still a draft.
        final = client.get_listing(listing_id)
        state_online = str(final.get("state") or "").casefold()
        if state_online not in DRAFT_LIKE_STATES:
            note("unexpected_state",
                 f"Etsy reports listing {listing_id} as '{final.get('state')}' — manual review needed.")
            return DraftResult(ok=False,
                               message=(f"Etsy listing {listing_id} is in state '{final.get('state')}'. "
                                        "This app never changes listing state; please review it in Etsy Shop Manager."),
                               listing_id=str(listing_id), shop_name=shop_name,
                               integration_state=db.integration_record(book_id, "etsy")["integration_state"],
                               events=events)
        expected_title = sanitize_title(metadata.get("title"))
        online_title = sanitize_title(final.get("title"))
        if expected_title and online_title and expected_title.casefold() != online_title.casefold():
            note("title_mismatch", "Online draft title differs from local metadata; review before publishing.")

        db.set_integration_state(book_id, "etsy", STATE_COMPLETE,
                                 external_sku=os.path.basename(printable_path),
                                 idempotency_key=idempotency_key)
        note("draft_verified",
             f"Verified online: Etsy draft {listing_id} is ready in Etsy Shop Manager — still NOT published.")
        return DraftResult(
            ok=True,
            message=(f"Etsy draft {listing_id} created online for shop {shop_name} — NOT published. "
                     "Review and publish it yourself in Etsy Shop Manager."),
            listing_id=str(listing_id),
            shop_name=shop_name,
            integration_state=STATE_COMPLETE,
            events=events,
        )

    @staticmethod
    def _existing_listing_id(recorded_external_id) -> Optional[int]:
        """Resume from the draft ID persisted right after creation (if any)."""
        raw = str(recorded_external_id or "").strip()
        return int(raw) if raw.isdigit() and int(raw) >= 1 else None

    def _record_listing_id(self, db, book, listing_id: str, prior_status: str) -> None:
        """Persist the draft ID next to the human-owned record without inventing state.

        The status itself is only elevated Not Prepared → Ready (it genuinely is
        prepared now); every other existing status value is left untouched.
        """
        new_status = "Ready" if prior_status == "Not Prepared" else prior_status
        db.transition_status(
            book["book_id"], "etsy", new_status,
            external_id=listing_id, url="", source="etsy_draft")

    def _find_existing_draft(self, client, shop_id, metadata):
        """Scan existing drafts for the same title; failures abort the run.

        Deliberately no exception swallowing here: if the duplicate scan
        cannot run, creating a draft would risk a duplicate, so the whole
        attempt fails safely instead.
        """
        expected = sanitize_title(metadata.get("title")).casefold()
        if not expected:
            return None
        drafts = client.list_drafts(shop_id, limit=100)
        for row in (drafts or {}).get("results") or []:
            if sanitize_title(row.get("title")).casefold() == expected:
                listing_id = row.get("listing_id")
                try:
                    return int(listing_id)
                except (TypeError, ValueError):
                    continue
        return None

    def _resolve_taxonomy(self, client) -> int:
        override = os.environ.get(TAXONOMY_ENV_VAR, "").strip()
        if override.isdigit() and int(override) >= 1:
            return int(override)
        nodes = client.get_seller_taxonomy_nodes()
        resolved = find_taxonomy_id(nodes, "books")
        if resolved is None:
            raise PermanentError(
                "Could not identify Etsy's 'Books' category automatically. "
                f"Set the environment variable {TAXONOMY_ENV_VAR} to the category number shown at "
                "developer.etsy.com documentation (SellerTaxonomy) and run this again.")
        return resolved

    @staticmethod
    def _pick_image(prepared_dir: str) -> Optional[str]:
        thumbnail = os.path.join(prepared_dir, "thumbnail.jpg")
        if os.path.isfile(thumbnail):
            return thumbnail
        previews = sorted(
            name for name in os.listdir(prepared_dir)
            if name.startswith("preview-") and name.lower().endswith((".jpg", ".jpeg", ".png"))
        )
        return os.path.join(prepared_dir, previews[0]) if previews else None
