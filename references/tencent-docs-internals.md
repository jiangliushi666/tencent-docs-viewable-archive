# Tencent Docs Internals Notes

This reference records verified observations only.

## Page Metadata

Tencent Docs pages can expose base64 JSON in `window.basicClientVars`. One observed form:

```javascript
window.basicClientVars=JSON.parse(decodeURIComponent(escape(atob("..."))))
```

Useful values found in this object include:

- `title` or related title fields
- `domainId`
- `padId`
- `subId`
- document type fields such as `padType`, `docType`, or URL path segments

For some APIs, the global pad id is:

```text
<domainId>$<padId>
```

## Verified Mind Map Path

For `https://docs.qq.com/mind/...?...subId=...`:

```text
https://docs.qq.com/dop-api/get/mind?padId=<urlencoded-global-pad-id>&subId=<subId>&rev=-1&xsrf=
```

The complete current document was observed in:

```text
data.initialAttributedText.text
```

That string parses as JSON. The root topic is:

```text
content[0].rootTopic
```

Child groups include:

```text
children.attached
children.detached
children.summary
```

Topic text is in `title`.
