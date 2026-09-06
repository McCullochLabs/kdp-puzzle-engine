# Publishing Hub 2.0

The application keeps one catalog record and turns it into a neutral **Master
Product**. Channel adapters derive their own package or listing shape from that
record. This prevents retyping a book's metadata while keeping channel rules
honest.

## Automation levels

| Channel | Level | What the app does now | What you do |
| --- | --- | --- | --- |
| Amazon KDP | 3 | Creates validated upload handoff | Upload and publish in KDP |
| Etsy | 2 | Prepares digital files; official OAuth can create/resume a draft only | Review images, details, and publish in Etsy |
| Lulu | 2 | Creates a print handoff; no print job is sent | Connect official Lulu credentials before print/fulfillment |
| Shopify | 2 | Creates product handoff | Connect a Shopify custom app before creating product drafts |
| WooCommerce | 2 | Creates product handoff | Connect WooCommerce REST API credentials before creating drafts |
| Wix | 3 | Creates product handoff | Configure the chosen Wix store integration and publish manually |
| IngramSpark | 3 | Creates a distribution/upload handoff | Build cover on current template, upload, and review |
| Barnes & Noble Press | 3 | Creates an upload handoff | Build cover on current template, upload, and review |

No adapter publishes a live listing without a future, explicitly connected
official API workflow. KDP is intentionally package-only. Etsy's current
remote path is draft-only, never live publishing or deletion.

## Product forms

The master product can carry both print and digital assets. A storefront
handoff includes a buyer-ready interior PDF and listing image; it never treats
a print-production cover wrap as a customer download. Physical storefront
products require a separately configured fulfillment route.

## Safe workflow

1. Create and approve a complete book package.
2. Open Publishing Manager and prepare the desired channel.
3. Use **Generate Export Package** for an export-only channel.
4. Read the generated listing kit and channel notes.
5. Upload or create a draft only in that channel's official seller portal.
6. Record a confirmed upload or live listing in Publishing Manager.

The catalog retains human-confirmed uploaded/published status and does not
overwrite its remote ID or link during a re-export.

## Connecting official APIs later

Etsy uses its official OAuth 2.0/PKCE flow with a registered HTTPS callback.
Keep credentials in Windows Credential Manager; do not put them in theme files
or source code. Shopify, WooCommerce, and Lulu connections are intentionally
not implemented yet because they need user-created official credentials and a
chosen fulfillment configuration. Their local packages are safe to create now.

## Sources checked August 25, 2026

- Etsy Open API v3 authentication and listings documentation
- Shopify Admin GraphQL product documentation
- WooCommerce REST API v3 product documentation

Platform rules change. Always verify the current official seller help page
before final upload, especially for print templates, fees, required fields,
and tax/fulfillment settings.
