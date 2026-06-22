---
name: tencent-docs-viewable-archive
description: Archive Tencent Docs URLs that the current user can already open and view through normal authorization, for local backup and preservation. Use for authorized preservation of docs.qq.com online documents, including mind maps, and for quickly diagnosing other Tencent Docs types without re-discovering page metadata or internal IDs. Do not use to access documents the user cannot view, bypass authentication, defeat Tencent Docs access control, reverse engineer clients, or evade platform security policy.
---

# Tencent Docs Viewable Archive

Use this skill when the user has a Tencent Docs link that opens in the browser through normal authorization and needs a local backup/archive. Keep the boundary explicit: archive only content the user is authorized to view.

## Quick Start

Run the bundled script first:

```powershell
python "$env:USERPROFILE\.codex\skills\tencent-docs-viewable-archive\scripts\archive_tencent_doc.py" "https://docs.qq.com/..."
```

On macOS/Linux:

```bash
python ~/.codex/skills/tencent-docs-viewable-archive/scripts/archive_tencent_doc.py "https://docs.qq.com/..."
```

The script defaults to `~/Documents/<title>_<YYYY-MM-DD>`.

Useful options:

```powershell
python archive_tencent_doc.py URL --output-dir ./export
python archive_tencent_doc.py URL --formats md,docx
python archive_tencent_doc.py URL --cookie-file ./cookie.txt
python archive_tencent_doc.py URL --diagnose-only
```

## Current Coverage

- `mind`: implemented and verified. Exports `.json`, `.md`, `.html`, `.txt`, and `.docx`.
- Other Tencent Docs kinds: detected and saved as a diagnostic package (`*.diagnostic.json` plus page HTML) so a future run can add the specific exporter without repeating metadata discovery.

For the known `mind` path, the script decodes `window.basicClientVars`, builds the global pad id, requests `dop-api/get/mind` with `rev=-1`, and parses `data.initialAttributedText.text` as the complete current mind-map JSON.

## Workflow

1. Confirm the URL opens for the current user. If the page itself is inaccessible, stop and ask for a valid accessible link or user-provided cookies.
2. Run `archive_tencent_doc.py URL`.
3. If it exports files, report the output folder and formats.
4. If it exits with an unsupported kind diagnostic, inspect the diagnostic JSON and page HTML before adding a new exporter.
5. Do not attempt password guessing, token theft, client reverse engineering, private API abuse, account bypass, access-control bypass, or platform-policy evasion.

## Notes

- A raw Cookie header may be provided with `--cookie-file` only when the user has authorization to view the document in that browser session.
- For Tencent mind maps, do not reconstruct from `rev=0` or `actionlist`; observed `actionlist` data can contain only recent UI actions such as collapsed nodes.
- Keep new exporters type-specific. Add the smallest route needed for the detected document kind rather than rewriting the whole script.
