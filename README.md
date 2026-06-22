# Tencent Docs Viewable Archive

这是一个 Codex skill，用于把“当前用户已经能打开查看，但腾讯在线文档下载/导出按钮不可用或无下载权限”的文档归档到本地。

## 当前能力

- 已验证支持腾讯文档脑图 `docs.qq.com/mind/...`
- 可导出 `.json`、`.md`、`.html`、`.txt`、`.docx`
- 其他腾讯文档类型会先生成诊断包，便于后续扩展对应导出器

## 使用

```powershell
python "$env:USERPROFILE\.codex\skills\tencent-docs-viewable-archive\scripts\archive_tencent_doc.py" "https://docs.qq.com/..."
```

## 边界

此 skill 只用于归档用户已授权查看的内容。它不用于访问打不开的文档、不绕过账号认证、不破解腾讯文档访问控制。
