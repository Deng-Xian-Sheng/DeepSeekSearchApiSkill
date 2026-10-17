---
name: deepseek-search
description: 通过 DeepSeek 官方 Search/Fetch API 搜索实时网页并抓取网页 Markdown 正文。当用户需要联网搜索、查询最新新闻/版本/价格/文档、核实事实、抓取指定 URL，或明确要求使用 DeepSeek 搜索时使用。通过 --agent 自动读取 OpenCode、Claude Code 或 Codex 已配置的 DeepSeek API Key。关键词：网页搜索、联网搜索、抓取网页、网页正文、web search、DeepSeek search、fetch URL。
---

# DeepSeek 网页搜索与抓取

封装 DeepSeek 官方 API：Search 返回结构化搜索结果，Fetch 返回 Markdown 网页正文。命令中的脚本路径相对本技能目录。

## 自动读取 API Key

调用时用 `--agent` 指定你所在的 Agent，脚本会自动读取你配置给该 Agent 的 DeepSeek 官方 API Key：

| `--agent` | 读取位置 |
| --- | --- |
| `opencode` | `~/.local/share/opencode/auth.json` 中的 `deepseek` 供应商 |
| `claude` | `~/.claude/settings.json` 或项目 `.claude/settings*.json` 的 `env` 中，`ANTHROPIC_BASE_URL` 指向 DeepSeek 时的 `ANTHROPIC_AUTH_TOKEN` |
| `codex` | `~/.codex/config.toml` 中 DeepSeek 供应商的 `experimental_bearer_token` |

把 `--agent` 换成你自己的名字（OpenCode → `opencode`，Claude Code → `claude`，Codex → `codex`）。不需要设置环境变量，也不需要向用户索要或粘贴 Key。

## 搜索

```bash
python3 scripts/deepseek_search.py search "DeepSeek V4 发布" --agent opencode

# 返回正文（每条默认截断 4000 字符）
python3 scripts/deepseek_search.py search "Agent 框架对比" --agent opencode --content

# 原始 JSON
python3 scripts/deepseek_search.py search "DeepSeek" --agent opencode --json
```

常用参数：`--count`（1～50，默认 5）、`--content`、`--content-max-chars`、`--ori-question`、`--localization`、`--json`。

搜索语法直接写在 query 中：

| 语法 | 示例 | 说明 |
| --- | --- | --- |
| `site:` / `-site:` | `DeepSeek site:github.com` | 限定/排除站点；多个站点用 `OR` 连接 |
| `-` / `-"..."` | `DeepSeek -广告` | 排除关键词或短语 |
| `"..."` | `DeepSeek "精确短语"` | 精确匹配 |
| `lang:` | `DeepSeek lang:zh,en` | 限定语言 |
| `after:` / `before:` | `DeepSeek after:2025` | 限定发布日期 |

## 抓取网页

```bash
python3 scripts/deepseek_search.py fetch "https://example.com/article" --agent opencode

# 输出完整正文（默认最多 20000 字符）
python3 scripts/deepseek_search.py fetch "https://example.com/article" --agent opencode --max-chars 0
```

## 成本与限制

- Search、Fetch 均按成功请求计费：5 元 / 1000 次；无结果、无正文或失败的请求不计费。
- `count` 不影响单次价格；需要多篇正文时用 `search --content`（1 次请求）通常比逐篇 `fetch` 便宜。
- Search、Fetch 各限 5 QPS；脚本会自动重试 408/429/5xx。
- 401 表示 Agent 中配置的 DeepSeek Key 无效；402 表示余额不足；429 表示触发限速。

完整字段、错误码和计费说明见 `references/api-reference.md`。
