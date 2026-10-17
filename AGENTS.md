## 项目描述

2026年10月17日，deepseek发布了DeepSeek-V4.1-Flash-1017模型、网页搜索与抓取API。

网页搜索与抓取API在deepseek harness（dsh）中原生可用，在claude code和codex等深度求索官方支持的agent中也有一定的支持，但是在opencode中，它目前还没有得到支持。

opencode有websearch内置工具，我预测未来如果opencode官方支持deepseek的网页搜索与抓取API，那么有三种方法：
- websearch内置工具的新供应商
- mcp
- skill

深度求索目前暂未提供网页搜索与抓取API的mcp服务。

无论未来情况如何，开发一个skill以实现给opencode等支持skill的其他agent提供deepseek的网页搜索与抓取API支持，都是一个存在潜在用户的好主意。

deepseek的网页搜索与抓取API的文档在：
https://api-docs.deepseek.com/zh-cn/guides/search/
https://api-docs.deepseek.com/zh-cn/api/search

但是你不要访问它！

因为它完全没有Markdown支持，只有html

为此，我将其转换成了Markdown并放在了项目下的references/中。

你可以参考文档，根据SKILL目录结构规范，在项目目录下开发一个skill。

如果可以直接放在项目目录下，则尽可能的直接放在项目目录下。如果不能，则放在子目录下。

本项目我会推送到GitHub并开源，所以自述文件必不可少。

## 要求&约束

- 代码注释使用中文
- 你当前在虚拟机里，有两个限制：
    + 虚拟机存储空间有限，不能过多的占用
    + 有的文件路径或者服务部署在宿主机上，在虚拟机里不方便访问

    于是，有的程序可以在虚拟机里跑，但有的程序[1]需要你在虚拟机里开发并测试好，还要准备好requirements.txt，然后我去实体机克隆代码并运行[2]。

    [1]占用大量存储空间的、需要访问宿主机文件路径或服务的程序。
    [2]除非我显式要求，否则你不能执行会对git仓库产生修改的git命令。这种命令由我来做。

## 开发记录

在此处以简短的标题记录开发过程中发生的重大变更或开发进度。标题后面引用记录了详细信息的文档（如有）（只有复杂或难以简短描述的信息才需要写并引用详细文档）。

例如：
- [短标题](记录详细信息的文档.md)

请在下方记录：

```markdown
- 2026-10-17：完成 skill
  - 根目录 `SKILL.md`、`scripts/deepseek_search.py`、`references/`、`tests/`
  - 通过 `--agent` 自动读取 OpenCode / Claude Code / Codex 已配置的 DeepSeek Key；不读环境变量、不接收手动 Key
  - `README.md` 中英双语并精简，安装地址为实际仓库地址
  - 31 项 mock 测试通过；已用 OpenCode 中配置的真实 Key 跑通 Search 和 Fetch 成功路径
```
