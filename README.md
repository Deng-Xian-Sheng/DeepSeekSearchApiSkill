# DeepSeek Search & Fetch Skill

## 中文

让 OpenCode、Claude Code 等支持 `SKILL.md` 的 Agent 调用 DeepSeek 官方 Search / Fetch API：Search 返回结构化搜索结果，Fetch 返回 Markdown 网页正文。

### 让Agent帮你安装

把下面这段提示词发给你的 Agent：

```text
请帮我安装 DeepSeek Search & Fetch Skill：将 https://github.com/Deng-Xian-Sheng/DeepSeekSearchApiSkill.git 克隆到你自己的 skills 目录，目录名使用 deepseek-search（OpenCode 为 ~/.config/opencode/skills/deepseek-search，Claude Code 为 ~/.claude/skills/deepseek-search）。安装后确认 SKILL.md 存在，不要修改仓库文件。
```

安装到 OpenCode：

```bash
git clone https://github.com/Deng-Xian-Sheng/DeepSeekSearchApiSkill.git ~/.config/opencode/skills/deepseek-search
```

Claude Code 安装到 `~/.claude/skills/deepseek-search`；其他支持 Agent Skills 的 Agent 放入各自的 skills 目录。

无需额外配置 API Key。调用时用 `--agent` 指定 Agent 名，脚本会自动读取你配置给该 Agent 的 DeepSeek 官方 API Key：

- `opencode`：`~/.local/share/opencode/auth.json` 中的 `deepseek` 供应商
- `claude`：`~/.claude/settings.json` 或项目 `.claude/settings*.json` 的 `env` 中，`ANTHROPIC_BASE_URL` 指向 DeepSeek 时的 `ANTHROPIC_AUTH_TOKEN`
- `codex`：`~/.codex/config.toml` 中 DeepSeek 供应商的 `experimental_bearer_token`

用法：

```bash
python3 scripts/deepseek_search.py search "DeepSeek V4 发布" --agent opencode
python3 scripts/deepseek_search.py search "DeepSeek site:github.com lang:zh" --agent opencode --count 10
python3 scripts/deepseek_search.py fetch "https://example.com/article" --agent opencode
```

Search / Fetch 均按成功请求计费，5 元 / 1000 次，各限 5 QPS。完整参数和 API 说明见 [SKILL.md](SKILL.md) 与 [references/api-reference.md](references/api-reference.md)。

测试：

```bash
python3 -m unittest discover -s tests -v
```

## English

An Agent Skill that lets OpenCode, Claude Code, and other `SKILL.md`-compatible agents call DeepSeek's official Search / Fetch APIs. Search returns structured results; Fetch returns page content as Markdown.

### Let your agent install it

Send this prompt to your agent:

```text
Install the DeepSeek Search & Fetch Skill: clone https://github.com/Deng-Xian-Sheng/DeepSeekSearchApiSkill.git into your own skills directory as deepseek-search (OpenCode: ~/.config/opencode/skills/deepseek-search; Claude Code: ~/.claude/skills/deepseek-search). Verify that SKILL.md exists and do not modify the repository files.
```

Install for OpenCode:

```bash
git clone https://github.com/Deng-Xian-Sheng/DeepSeekSearchApiSkill.git ~/.config/opencode/skills/deepseek-search
```

For Claude Code, clone into `~/.claude/skills/deepseek-search`; other Agent Skills hosts can use their own skills directory.

No additional API key setup is required. Pass the agent name with `--agent`; the script reads the DeepSeek key already configured for that agent:

- `opencode`: the `deepseek` provider in `~/.local/share/opencode/auth.json`
- `claude`: `ANTHROPIC_AUTH_TOKEN` in the `env` block of `~/.claude/settings.json` or project `.claude/settings*.json`, when `ANTHROPIC_BASE_URL` points to DeepSeek
- `codex`: `experimental_bearer_token` of the DeepSeek provider in `~/.codex/config.toml`

Usage:

```bash
python3 scripts/deepseek_search.py search "DeepSeek V4 release" --agent opencode
python3 scripts/deepseek_search.py search "DeepSeek site:github.com lang:en" --agent opencode --count 10
python3 scripts/deepseek_search.py fetch "https://example.com/article" --agent opencode
```

Search and Fetch are billed per successful request: CNY 5 per 1,000 requests, with a 5 QPS limit each. See [SKILL.md](SKILL.md) and [references/api-reference.md](references/api-reference.md) for options and API details.

Tests:

```bash
python3 -m unittest discover -s tests -v
```
