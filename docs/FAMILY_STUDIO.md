# Family Studio

Start the normal desktop launcher. Home starts with a conversation and a collapsed **Use buttons instead** choice. One **Menu** contains:

- **Home:** describe an idea or choose one of four starting actions.
- **Create:** printable activity packs or complete puzzle books.
- **My books:** search the existing catalog and open a book's established review/preparation tools.
- **Covers:** enter a topic for the existing artwork generator, or select a book for its cover workflow.
- **Settings:** appearance, AI provider selection, advanced production, and error logs.

## Everyday flow

Try “Make a birthday activity pack for Emma”. The guide proposes a plan; choose **Review this request**, adjust the three-step pack form, and create the printable files. Requests never generate or publish files by themselves.

Full books open simpler presentations of the existing checked creators. Unsupported content themes are not silently changed to general content. Word-search approval becomes unavailable again after the plan's title, topic, subtitle, or vocabulary changes.

The owner can open **Settings → Advanced workspace** for all established production, series, word-bank, marketplace, and maintenance tools. **Back to simple Studio** returns to the family interface. Detailed controls are loaded on demand, so startup does not scan the entire theme library.

## Choose the assistant in Settings

Select **Codex**, **Ollama**, or **Guide**. This selection is saved with the existing app preferences on normal close. Changing providers cancels pending interpretation; it never resends a request automatically. All creation buttons work without AI.

- **Codex** uses the installed Codex app-server over local stdio and its existing managed **ChatGPT sign-in**. Studio does not read or copy tokens, accept API keys, enable API billing, or change global Codex configuration. Requests run in ephemeral sessions with executable integrations disabled, read-only sandboxing, and all tool requests denied. Only bounded request/context text and category names are supplied. A requested visual cover review supplies up to two temporary rendered cover previews. This is online inference through Codex, not a general-purpose API entitlement.
- **Ollama** uses an explicitly selected installed model at `http://127.0.0.1:11434`. It bypasses proxies, rejects redirects, and excludes cloud/remote models. It downloads no models. The HP's `qwen2.5:3b` path is supported. The installed text-only models cannot visually inspect a cover.
- **Guide** uses transparent rules for common requests, with no inference service.

Both model providers return the same strictly validated proposal schema. Models cannot generate executable code, run commands, approve artwork, change the word bank, publish, or perform arbitrary file operations. Studio's existing tools execute reviewed plans and report actual results. Failed requests retain the provider and draft; retry or choose another provider explicitly. Codex usage-limit errors stop without retries. Requests have a 90-second deadline and cancellation; stale project/provider results and duplicate submissions are ignored.

Examples: “Make a space activity pack”, “Use fewer puzzles”, “Make another version”, “Change its cover”, “Audit its cover”, and “Open my last project”. Select a saved book first for its cover. Pack revisions open a fresh plan and preserve the original output. Age-specific word difficulty is not certified; Sudoku difficulty remains a real supported setting. Non-word book creators retain their own supported content themes.

Supported route references: [Codex app-server](https://developers.openai.com/codex/app-server), [managed authentication](https://developers.openai.com/codex/auth), and [Codex application integration](https://developers.openai.com/blog/codex-as-a-platform).

## Automatic groups and combined themes

**Browse all topics** searches all 82 topic entries and 110 pack entries (170 distinct names). Existing words are selected automatically through the store, protected-term rules, independent topic profiles, and book quality checks. No bank or approval metadata is rewritten to force a result.

The assistant can propose up to six existing source groups for a theme. **Homesteading** also has a deterministic shared recipe: Homesteading, Gardening, Home and Household, Farm Country and Rural Life, and Baking and Food. It works with Codex, Ollama, or Guide. Books keep the source for each puzzle, avoid repeated words, and display the actual groups used. Small packs may use fewer groups because they contain fewer word activities; unavailable groups and editorial limitations are reported.

When a group has enough checked words for a short pack but not a full book, the book planner offers **Make a shorter activity pack**. Fourteen groups still need independent content evidence; they explain the limitation and suggest explicit different themes. The family is never asked to repair the bank, and the app does not silently replace their requested theme.

## Cover review

Use **My books → Review cover**, or select/preview a book and ask to audit its cover. The review reads the actual saved front and wrap. Existing preflight supplies page-count and print-geometry evidence. Codex can additionally critique visible title hierarchy, thumbnail readability, contrast, spacing, artwork fit, back cover, and spine, with prioritized suggested changes.

AI design suggestions are separate from measured package checks. A preview cannot establish physical print alignment, rights clearance, or artwork approval. Reviews never alter covers or approval status. **Preview actual cover** and **Open book cover tools** lead back to the established workflow. Guide/Ollama continue to offer measured checks and clearly explain when visual review is unavailable.

## Windows acceptance checks

- Start normally on the HP; verify responsive Home, keyboard entry, and reachable controls at the family's actual Windows scaling setting.
- Create, inspect, and sample-print a personalized activity pack. Test Back, changing themes, insufficient words, repeated creation, and opening the finished folder.
- Open an existing book, review its cover, and verify the canonical approved artwork is used.
- Try both Word Search and a non-word book using existing known-good content and artwork; confirm production/proof gates still run.
- Verify Advanced workspace and return navigation; verify saved themes and confirmed marketplace statuses remain intact.
- Select an installed local model, test several everyday requests and follow-ups, then stop Ollama and verify useful fallback.
- Have the wife/children try the workflow without coaching; record actual confusion before declaring it intuitive.

Cloud desktop smoke tests are useful evidence but do not substitute for these Windows/human checks.

## Preview, selected projects, and recovery

- **Preview actual pages and answers** on the pack review step opens real rendered PDFs. It refreshes after valid edits, preserving the plan's seed so the sample matches generation. No catalog record or commercial package is created for a preview.
- **Preview saved pages / cover** in My books reads the selected book's actual files and refreshes if those files change. Missing artwork is reported; there is no synthetic replacement or implicit approval.
- Opening or previewing a catalog book selects it for the assistant. “Change its cover” routes to that exact saved book; “make another version” starts a new plan with its topic and type. Requests about “it” without a selection require clarification. The model receives only bounded title/topic/type text, not file paths or credentials.
- Family pack forms and simple book editors save unfinished inputs in versioned tables inside the existing `data/books.db`. **Continue unfinished work** reopens the most recently saved unfinished draft. Invalid intermediate values, such as an empty count while typing, are preserved. **Undo saved edit** restores a previous pack draft without deleting versions or overwriting completed outputs.
- Closing the main app flushes unfinished forms. A failed save keeps the app open with an actionable message. Pack generation completion marks that draft completed; book editor drafts remain recoverable and never establish production approval.
- A sole installed local Ollama model is discovered automatically for an unconfigured interface. Multiple models require selection. Explicit Guide mode is respected. No download, cloud model, paid API, or inference occurs during discovery.

## Check the HP

Use **Settings → Check this computer** for read-only runtime, artwork, and Ollama discovery. Or run:

```
.venv\Scripts\python.exe tools\check_studio.py
```

An explicit harmless local-inference test is available after choosing an installed model name:

```
.venv\Scripts\python.exe tools\check_studio.py --model YOUR_INSTALLED_MODEL --smoke-local-ai
```

This classifies one request; it does not generate or publish anything. Exit 1 means a reported readiness or inference check needs attention. The report never re-approves missing artwork or downloads a replacement model.
