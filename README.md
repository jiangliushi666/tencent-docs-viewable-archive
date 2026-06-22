# Tencent Docs Viewable Archive

这是一个 Codex skill，用于对“当前用户已经通过正常方式授权查看”的腾讯在线文档做本地归档和备份。

本项目不涉及客户端逆向、漏洞利用、账号提权、登录绕过、访问控制绕过，也不用于获取用户无权查看的内容。它的目标是把用户已经能在浏览器中正常看到的内容，按合规、可审计的方式保存为本地文件。

适用场景：腾讯文档备份、腾讯文档归档、Tencent Docs archive、Tencent Docs backup、Codex skill、Claude Code skill、在线文档保存、团队知识库留存。

## 当前能力

- 已验证支持腾讯文档脑图 `docs.qq.com/mind/...`
- 可导出 `.json`、`.md`、`.html`、`.txt`、`.docx`
- 其他腾讯文档类型会先生成诊断包，便于后续在授权场景下扩展对应归档器

## 使用

把这个 GitHub 仓库链接和腾讯文档链接一起发给 agent 即可：

`https://github.com/jiangliushi666/tencent-docs-viewable-archive`

Codex 示例：

`使用这个 skill 仓库保存腾讯文档：https://github.com/jiangliushi666/tencent-docs-viewable-archive 文档链接：<URL>`

Claude Code 示例：

`Use this skill repo to archive the Tencent Docs URL: https://github.com/jiangliushi666/tencent-docs-viewable-archive URL: <URL>`

## 边界

此 skill 只用于归档用户已授权查看的内容。它不访问打不开的文档，不绕过账号认证，不破解腾讯文档访问控制，不进行客户端逆向或规避平台安全策略。
