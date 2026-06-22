#!/usr/bin/env python3
"""Archive a viewable Tencent Docs URL to local files.

The mind-map exporter is implemented because it has been verified against a real
docs.qq.com/mind page. Other Tencent Docs types are detected and emitted as a
diagnostic package so a future run can add a focused exporter without repeating
page metadata discovery.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import deque
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape as xml_escape
import html as html_lib


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

CHILD_GROUPS = ("attached", "detached", "summary")
DEFAULT_FORMATS = ("json", "md", "html", "txt", "docx")
SUPPORTED_EXPORT_KINDS = {"mind"}


class ExportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive a viewable Tencent Docs URL locally. Currently exports mind maps; "
            "for other doc types it writes a diagnostic package for fast extension."
        )
    )
    parser.add_argument("url", help="Tencent Docs URL that the current user can view")
    parser.add_argument(
        "--output-dir",
        help="Exact output directory. Defaults to ~/Documents/<title>_<YYYY-MM-DD>.",
    )
    parser.add_argument(
        "--formats",
        default=",".join(DEFAULT_FORMATS),
        help="Comma-separated formats for mind maps: json,md,html,txt,docx,all. Default: all.",
    )
    parser.add_argument("--prefix", help="Output filename prefix. Defaults to <title>_<YYYY-MM-DD>.")
    parser.add_argument("--sub-id", help="Override subId instead of using the URL/metadata value.")
    parser.add_argument("--kind", help="Override detected doc kind, e.g. mind, doc, sheet, slide.")
    parser.add_argument("--diagnose-only", action="store_true", help="Only save metadata diagnostics.")
    parser.add_argument("--cookies", help="Raw Cookie header value for private documents.")
    parser.add_argument("--cookie-file", help="Text file containing a raw Cookie header or Netscape cookies.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    return parser.parse_args()


def read_cookie(args: argparse.Namespace) -> str | None:
    if args.cookies:
        return normalize_cookie_text(args.cookies)
    if args.cookie_file:
        text = Path(args.cookie_file).read_text(encoding="utf-8-sig")
        return normalize_cookie_text(text)
    return None


def normalize_cookie_text(text: str) -> str:
    text = text.strip()
    if text.lower().startswith("cookie:"):
        return text.split(":", 1)[1].strip()
    if ";" in text and "=" in text:
        return " ".join(text.split())

    pairs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
        elif "=" in line:
            pairs.append(line)
    return "; ".join(pairs) if pairs else text


def fetch_text(url: str, *, cookie: str | None, timeout: float, referer: str | None = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = "https://docs.qq.com"
    if cookie:
        headers["Cookie"] = cookie

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise ExportError(f"HTTP {exc.code} while fetching {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ExportError(f"Network error while fetching {url}: {exc.reason}") from exc


def extract_basic_client_vars(page_html: str) -> dict[str, Any]:
    patterns = (
        r"window\.basicClientVars\s*=\s*JSON\.parse\s*\(\s*decodeURIComponent\s*\(\s*escape\s*\(\s*atob\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\)\s*\)\s*\)",
        r"window\.basicClientVars\s*=\s*JSON\.parse\s*\(\s*atob\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\)",
        r"window\.basicClientVars\s*=\s*atob\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        r"window\.basicClientVars\s*=\s*['\"]([^'\"]+)['\"]",
        r"\bbasicClientVars\s*:\s*['\"]([^'\"]+)['\"]",
        r"\bbasicClientVars\s*=\s*['\"]([^'\"]+)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, page_html)
        if not match:
            continue
        encoded = html_lib.unescape(match.group(1)).strip()
        decoded = decode_maybe_base64_json(encoded)
        if isinstance(decoded, dict):
            return decoded
    raise ExportError("Could not find window.basicClientVars in the page HTML.")


def decode_maybe_base64_json(value: str) -> Any:
    if value.startswith("{"):
        return json.loads(value)

    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    errors: list[str] = []
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(padded)
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - keep both decoder errors for diagnostics.
            errors.append(str(exc))
    raise ExportError("basicClientVars was found but could not be decoded: " + " | ".join(errors))


def find_first_key(obj: Any, names: Iterable[str]) -> Any:
    wanted = {name.lower() for name in names}
    queue: deque[Any] = deque([obj])
    while queue:
        current = queue.popleft()
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).lower() in wanted and value not in (None, ""):
                    return value
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None


def scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def parse_html_title(page_html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.I | re.S)
    if not match:
        return None
    title = re.sub(r"\s+", " ", html_lib.unescape(match.group(1))).strip()
    title = re.sub(r"[-_ ]*腾讯文档.*$", "", title).strip()
    return title or None


def detect_doc_kind(url: str, vars_obj: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override.lower().strip()
    path = urllib.parse.urlparse(url).path.lower()
    for kind in ("mind", "doc", "sheet", "slide", "form", "page", "desktop"):
        if f"/{kind}/" in path or path.rstrip("/").endswith(f"/{kind}"):
            return kind
    from_meta = scalar(find_first_key(vars_obj, ("padType", "pad_type", "docType", "doc_type", "type")))
    return from_meta.lower() if from_meta else "unknown"


def metadata_from_page(
    page_html: str,
    url: str,
    sub_id_override: str | None,
    kind_override: str | None,
) -> dict[str, Any]:
    vars_obj = extract_basic_client_vars(page_html)

    title = (
        scalar(find_first_key(vars_obj, ("title", "padTitle", "docName", "name")))
        or parse_html_title(page_html)
        or "tencent-doc"
    )
    global_pad_id = scalar(find_first_key(vars_obj, ("globalPadId", "global_pad_id")))
    pad_id = scalar(find_first_key(vars_obj, ("padId", "pad_id")))
    domain_id = scalar(find_first_key(vars_obj, ("domainId", "domain_id")))

    if not global_pad_id:
        if pad_id and "$" in pad_id:
            global_pad_id = pad_id
        elif domain_id and pad_id:
            global_pad_id = f"{domain_id}${pad_id}"
        elif pad_id:
            global_pad_id = pad_id
    if not global_pad_id:
        raise ExportError("Could not determine padId/domainId from basicClientVars.")

    parsed_url = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed_url.query)
    sub_id = sub_id_override or (query.get("subId", [None])[0])
    if not sub_id:
        sub_id = scalar(find_first_key(vars_obj, ("subId", "sub_id")))
    if not sub_id and detect_doc_kind(url, vars_obj, kind_override) == "mind":
        raise ExportError("Could not determine subId. Pass --sub-id explicitly.")

    return {
        "title": title,
        "global_pad_id": global_pad_id,
        "sub_id": sub_id,
        "doc_kind": detect_doc_kind(url, vars_obj, kind_override),
        "basic_client_vars": vars_obj,
    }


def fetch_mind_json(meta: dict[str, str], *, cookie: str | None, timeout: float, referer: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "padId": meta["global_pad_id"],
            "subId": meta["sub_id"],
            "rev": "-1",
            "xsrf": "",
        }
    )
    api_url = f"https://docs.qq.com/dop-api/get/mind?{query}"
    raw = fetch_text(api_url, cookie=cookie, timeout=timeout, referer=referer)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExportError(f"Mind API did not return JSON. First 500 chars: {raw[:500]}") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    attributed = data.get("initialAttributedText") if isinstance(data, dict) else None
    text = attributed.get("text") if isinstance(attributed, dict) else None
    if not text:
        code = payload.get("retcode") or payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("msg") or payload.get("message") if isinstance(payload, dict) else None
        raise ExportError(
            "Mind API response did not include data.initialAttributedText.text. "
            f"code={code!r} message={message!r}"
        )
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        raise ExportError(f"Unexpected initialAttributedText.text type: {type(text).__name__}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExportError("initialAttributedText.text was not valid JSON.") from exc


def root_topic(mind: dict[str, Any]) -> dict[str, Any]:
    content = mind.get("content")
    if not isinstance(content, list) or not content:
        raise ExportError("Mind JSON does not contain content[0].")
    root = content[0].get("rootTopic") if isinstance(content[0], dict) else None
    if not isinstance(root, dict):
        raise ExportError("Mind JSON does not contain content[0].rootTopic.")
    return root


def children_of(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("children")
    ordered: list[dict[str, Any]] = []
    if isinstance(children, dict):
        seen = set()
        for group in CHILD_GROUPS:
            values = children.get(group)
            if isinstance(values, list):
                ordered.extend(child for child in values if isinstance(child, dict))
            seen.add(group)
        for group, values in children.items():
            if group in seen:
                continue
            if isinstance(values, list):
                ordered.extend(child for child in values if isinstance(child, dict))
    elif isinstance(children, list):
        ordered.extend(child for child in children if isinstance(child, dict))
    return ordered


def topic_title(node: dict[str, Any]) -> str:
    title = node.get("title")
    if isinstance(title, str):
        text = title
    else:
        text = scalar(find_first_key(title, ("text", "insert", "title"))) if title is not None else None
        text = text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or "(untitled)"


def flatten_topics(root: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []

    def walk(node: dict[str, Any], depth: int) -> None:
        rows.append((depth, node))
        for child in children_of(node):
            walk(child, depth + 1)

    walk(root, 0)
    return rows


def safe_filename(name: str, max_len: int = 90) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "tencent-doc"
    return name[:max_len].rstrip(" .") or "tencent-doc"


def normalize_formats(value: str) -> list[str]:
    requested = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not requested or "all" in requested:
        return list(DEFAULT_FORMATS)
    aliases = {"markdown": "md", "text": "txt"}
    result = [aliases.get(item, item) for item in requested]
    invalid = sorted(set(result) - set(DEFAULT_FORMATS))
    if invalid:
        raise ExportError(f"Unsupported format(s): {', '.join(invalid)}")
    return result


def output_paths(args: argparse.Namespace, title: str) -> tuple[Path, str]:
    today = dt.date.today().isoformat()
    prefix = safe_filename(args.prefix or f"{title}_{today}")
    if args.output_dir:
        out_dir = Path(args.output_dir).expanduser()
    else:
        documents = Path.home() / "Documents"
        parent = documents if documents.exists() else Path.cwd()
        out_dir = parent / prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir, prefix


def render_markdown(root: dict[str, Any]) -> str:
    lines = [f"# {topic_title(root).replace(chr(10), ' / ')}", ""]

    def append(node: dict[str, Any], depth: int) -> None:
        indent = "  " * depth
        text_lines = topic_title(node).split("\n") or [""]
        lines.append(f"{indent}- {text_lines[0]}")
        continuation = f"{indent}  "
        for line in text_lines[1:]:
            lines.append(continuation + line)
        for child in children_of(node):
            append(child, depth + 1)

    for child in children_of(root):
        append(child, 0)
    lines.append("")
    return "\n".join(lines)


def render_text(root: dict[str, Any]) -> str:
    lines: list[str] = []

    def append(node: dict[str, Any], depth: int) -> None:
        indent = "  " * depth
        text_lines = topic_title(node).split("\n") or [""]
        lines.append(f"{indent}- {text_lines[0]}")
        continuation = f"{indent}  "
        for line in text_lines[1:]:
            lines.append(continuation + line)
        for child in children_of(node):
            append(child, depth + 1)

    lines.append(topic_title(root))
    for child in children_of(root):
        append(child, 0)
    lines.append("")
    return "\n".join(lines)


def render_html(root: dict[str, Any], title: str) -> str:
    out = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html_lib.escape(title)}</title>",
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.55;margin:32px;}",
        "h1{font-size:28px;margin:0 0 24px;}",
        "ul{padding-left:24px;}",
        "li{margin:6px 0;}",
        ".node{white-space:pre-wrap;}",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{html_lib.escape(topic_title(root))}</h1>",
    ]

    def append_list(nodes: list[dict[str, Any]]) -> None:
        if not nodes:
            return
        out.append("<ul>")
        for node in nodes:
            out.append("<li>")
            out.append(f'<div class="node">{html_lib.escape(topic_title(node))}</div>')
            append_list(children_of(node))
            out.append("</li>")
        out.append("</ul>")

    append_list(children_of(root))
    out.extend(["</body>", "</html>", ""])
    return "\n".join(out)


def docx_text(text: str) -> str:
    parts: list[str] = []
    for index, line in enumerate(text.split("\n")):
        if index:
            parts.append("<w:br/>")
        parts.append(f'<w:t xml:space="preserve">{xml_escape(line)}</w:t>')
    return "".join(parts)


def docx_paragraph(text: str, *, depth: int, title: bool = False) -> str:
    left = max(depth, 0) * 360
    spacing = "180" if title else "80"
    size = "32" if title else "22"
    bold = "<w:b/>" if title else ""
    prefix = "" if title else "- "
    return (
        "<w:p>"
        "<w:pPr>"
        f'<w:spacing w:after="{spacing}"/>'
        f'<w:ind w:left="{left}"/>'
        "</w:pPr>"
        "<w:r>"
        f"<w:rPr>{bold}<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/></w:rPr>"
        f"{docx_text(prefix + text)}"
        "</w:r>"
        "</w:p>"
    )


def write_docx(path: Path, root: dict[str, Any]) -> None:
    paragraphs = [docx_paragraph(topic_title(root), depth=0, title=True)]

    def append(node: dict[str, Any], depth: int) -> None:
        paragraphs.append(docx_paragraph(topic_title(node), depth=depth, title=False))
        for child in children_of(node):
            append(child, depth + 1)

    for child in children_of(root):
        append(child, 0)

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        + '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        + 'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        + "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        + 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        + 'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)


def write_outputs(mind: dict[str, Any], meta: dict[str, str], args: argparse.Namespace) -> dict[str, Path]:
    root = root_topic(mind)
    out_dir, prefix = output_paths(args, meta["title"])
    formats = normalize_formats(args.formats)
    outputs: dict[str, Path] = {}

    if "json" in formats:
        path = out_dir / f"{prefix}.json"
        path.write_text(json.dumps(mind, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs["json"] = path
    if "md" in formats:
        path = out_dir / f"{prefix}.md"
        path.write_text(render_markdown(root), encoding="utf-8")
        outputs["md"] = path
    if "html" in formats:
        path = out_dir / f"{prefix}.html"
        path.write_text(render_html(root, meta["title"]), encoding="utf-8")
        outputs["html"] = path
    if "txt" in formats:
        path = out_dir / f"{prefix}.txt"
        path.write_text(render_text(root), encoding="utf-8")
        outputs["txt"] = path
    if "docx" in formats:
        path = out_dir / f"{prefix}.docx"
        write_docx(path, root)
        outputs["docx"] = path
    return outputs


def summarize_basic_vars(vars_obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "top_level_keys": sorted(str(key) for key in vars_obj.keys()),
        "title": scalar(find_first_key(vars_obj, ("title", "padTitle", "docName", "name"))),
        "domainId": scalar(find_first_key(vars_obj, ("domainId", "domain_id"))),
        "padId": scalar(find_first_key(vars_obj, ("padId", "pad_id"))),
        "globalPadId": scalar(find_first_key(vars_obj, ("globalPadId", "global_pad_id"))),
        "subId": scalar(find_first_key(vars_obj, ("subId", "sub_id"))),
        "padType": scalar(find_first_key(vars_obj, ("padType", "pad_type", "docType", "doc_type", "type"))),
    }


def write_diagnostics(
    page_html: str,
    meta: dict[str, Any],
    args: argparse.Namespace,
    reason: str,
) -> dict[str, Path]:
    out_dir, prefix = output_paths(args, meta["title"])
    diagnostic = {
        "reason": reason,
        "url": args.url,
        "title": meta["title"],
        "doc_kind": meta["doc_kind"],
        "global_pad_id": meta["global_pad_id"],
        "sub_id": meta.get("sub_id"),
        "supported_export_kinds": sorted(SUPPORTED_EXPORT_KINDS),
        "basicClientVars_summary": summarize_basic_vars(meta["basic_client_vars"]),
    }

    json_path = out_dir / f"{prefix}.diagnostic.json"
    html_path = out_dir / f"{prefix}.page.html"
    json_path.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(page_html, encoding="utf-8")
    return {"diagnostic": json_path, "page_html": html_path}


def stats(root: dict[str, Any]) -> tuple[int, int]:
    rows = flatten_topics(root)
    return len(rows), max((depth for depth, _node in rows), default=0)


def main() -> int:
    args = parse_args()
    try:
        cookie = read_cookie(args)
        page_html = fetch_text(args.url, cookie=cookie, timeout=args.timeout)
        meta = metadata_from_page(page_html, args.url, args.sub_id, args.kind)
        if args.diagnose_only or meta["doc_kind"] not in SUPPORTED_EXPORT_KINDS:
            reason = (
                "diagnose-only requested"
                if args.diagnose_only
                else f"automated exporter for Tencent Docs kind {meta['doc_kind']!r} is not implemented"
            )
            outputs = write_diagnostics(page_html, meta, args, reason)
            print(f"title: {meta['title']}")
            print(f"kind: {meta['doc_kind']}")
            print(f"padId: {meta['global_pad_id']}")
            if meta.get("sub_id"):
                print(f"subId: {meta['sub_id']}")
            print(f"status: {reason}")
            print("outputs:")
            for fmt, path in outputs.items():
                print(f"  {fmt}: {path}")
            return 2 if not args.diagnose_only else 0

        mind = fetch_mind_json(meta, cookie=cookie, timeout=args.timeout, referer=args.url)
        outputs = write_outputs(mind, meta, args)
        count, max_depth = stats(root_topic(mind))
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"title: {meta['title']}")
    print(f"kind: {meta['doc_kind']}")
    print(f"padId: {meta['global_pad_id']}")
    print(f"subId: {meta['sub_id']}")
    print(f"nodes: {count}")
    print(f"max_depth: {max_depth}")
    print("outputs:")
    for fmt, path in outputs.items():
        print(f"  {fmt}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
