---
name: tencent-docs-viewable-archive
description: Archive Tencent Docs URLs that the current user can already open and view when the normal download/export button is unavailable or disabled. Use for authorized local preservation of docs.qq.com online documents, including mind maps, and for quickly diagnosing other Tencent Docs types without re-discovering page metadata or internal IDs. Do not use to access documents the user cannot view, bypass account authentication, or defeat Tencent Docs access control.
---

# Tencent Docs Viewable Archive

Use this skill when the user has a Tencent Docs link that opens in the browser, but Tencent's UI does not offer a usable download/export action. Keep the boundary explicit: archive only content the user is authorized to view.

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
5. Do not attempt password guessing, token theft, private API abuse, or account/ACL bypass.

## Notes

- A raw Cookie header may be provided with `--cookie-file` only when the user has authorization to view the document in that browser session.
- For Tencent mind maps, do not reconstruct from `rev=0` or `actionlist`; observed `actionlist` data can contain only recent UI actions such as collapsed nodes.
- Keep new exporters type-specific. Add the smallest route needed for the detected document kind rather than rewriting the whole script.
