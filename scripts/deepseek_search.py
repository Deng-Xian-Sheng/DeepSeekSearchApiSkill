#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek Search / Fetch API 命令行封装。

用法：
    python3 deepseek_search.py search "查询词" [选项]
    python3 deepseek_search.py fetch "https://example.com" [选项]

仅依赖 Python 3.8+ 标准库，无需安装第三方包。
API 文档：https://api-docs.deepseek.com/zh-cn/guides/search
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.deepseek.com"
SEARCH_PATH = "/v1/tools/search"
FETCH_PATH = "/v1/tools/fetch"

# 这些状态码表示服务端临时不可用，可以安全重试（请求为只读）
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_RETRY_DELAY = 30.0

# 常见错误码的处理提示
ERROR_HINTS = {
    400: "请求参数不合法；脚本已在本地做基础校验，请检查 query/url 等内容。",
    401: "Agent 中配置的 DeepSeek API Key 无效，请检查该 Agent 的 DeepSeek 供应商配置。",
    402: "账号余额不足，请先充值再重试。",
    403: "Fetch 请求被目标站点的安全策略拒绝，可换一个来源。",
    404: "Fetch 未能获取可用的网页内容：URL 不可用、被站点拦截、类型不支持或没有正文。",
    408: "读取请求体超时，稍等后重试。",
    413: "请求体超过大小限制。",
    429: "触发了 QPS 限制（Search 与 Fetch 各 5 QPS），请降低频率后重试。",
    500: "服务器内部错误，稍等后重试。",
    504: "下游请求超时，稍等后重试。",
}

# 支持的 Agent 名称及其别名
AGENT_ALIASES = {
    "opencode": "opencode",
    "open-code": "opencode",
    "claude": "claude",
    "claude-code": "claude",
    "codex": "codex",
}

EXAMPLES = """\
示例：
  # 基础搜索（默认 5 条结果）
  python3 deepseek_search.py search "DeepSeek V4 发布" --agent opencode

  # 使用搜索语法：限定站点、语言、时间
  python3 deepseek_search.py search "DeepSeek site:github.com lang:zh after:2025" --agent opencode

  # 同时返回网页正文，并限制每条正文最多 3000 字符
  python3 deepseek_search.py search "Agent 框架对比" --content --content-max-chars 3000 --agent opencode

  # 抓取单个网页（Markdown 正文）
  python3 deepseek_search.py fetch "https://api-docs.deepseek.com/zh-cn/guides/search" --agent opencode

  # 输出原始 JSON，便于 jq 等工具处理
  python3 deepseek_search.py search "DeepSeek" --json --agent opencode
"""


# ---------------------------------------------------------------------------
# 异常类型
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """本地参数或配置错误，不发起 API 请求，退出码为 2。"""


class ApiError(Exception):
    """API 或网络错误，退出码为 1。"""

    def __init__(self, status: Optional[int], message: str, code: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """构造 argparse 解析器；公共选项通过 parent parser 复用。"""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--agent",
        required=True,
        help="当前 Agent 名称：opencode、claude（Claude Code）或 codex；"
        "用于自动读取该 Agent 已配置的 DeepSeek API Key",
    )
    common.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="API 根地址（默认 %(default)s），一般无需修改",
    )
    common.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="单次 HTTP 请求超时秒数（默认 30）",
    )
    common.add_argument(
        "--retries",
        type=int,
        default=2,
        help="遇到 408/429/5xx 或网络错误时的重试次数（默认 2）",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="输出 API 原始 JSON，不做 Markdown 格式化",
    )

    parser = argparse.ArgumentParser(
        prog="deepseek_search.py",
        description="调用 DeepSeek 官方 Search / Fetch API 搜索网页、抓取网页正文。",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="deepseek-search-skill 1.0.0")

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="{search,fetch}",
        help="可用子命令",
    )
    subparsers.required = True

    search = subparsers.add_parser(
        "search",
        parents=[common],
        help="按 query 搜索网页",
        description="按查询词搜索网页，返回结构化结果。",
    )
    search.add_argument("query", help="搜索词，1～128 个 Unicode 字符，支持 site: 等搜索语法")
    search.add_argument(
        "--count",
        type=int,
        default=5,
        help="返回条数，1～50（默认 5；条数不影响单次计费）",
    )
    search.add_argument(
        "--content",
        action="store_true",
        help="在结果中返回网页正文（会增加响应大小与上下文占用）",
    )
    search.add_argument(
        "--content-max-chars",
        type=int,
        default=4000,
        help="每条正文最多显示的字符数，0 表示不限制（默认 4000）",
    )
    search.add_argument(
        "--ori-question",
        help="触发搜索的用户原始问题，1～128 个字符，有助于理解搜索意图",
    )
    search.add_argument(
        "--localization",
        default="",
        help="用于优先返回本地化结果的 IP 地址（默认空）",
    )

    fetch = subparsers.add_parser(
        "fetch",
        parents=[common],
        help="抓取单个网页并返回 Markdown 正文",
        description="抓取单个网页，以 Markdown 形式返回正文。",
    )
    fetch.add_argument("url", help="要抓取的 HTTP/HTTPS URL，长度不超过 8192")
    fetch.add_argument(
        "--max-chars",
        type=int,
        default=20000,
        help="正文最多显示的字符数，0 表示不限制（默认 20000）",
    )

    return parser


# ---------------------------------------------------------------------------
# 配置与校验
# ---------------------------------------------------------------------------


def normalize_base_url(value: str) -> str:
    """校验并规范化 API 根地址。"""
    value = (value or "").strip().rstrip("/")
    if not value:
        raise UsageError("--base-url 不能为空")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise UsageError("--base-url 必须是合法的 http(s) 地址")
    return value


# ---------------------------------------------------------------------------
# 从各 Agent 的配置中读取 DeepSeek API Key
# ---------------------------------------------------------------------------


def normalize_agent(value: str) -> str:
    """把 Agent 名称或别名规范化为 opencode/claude/codex。"""
    key = re.sub(r"[\s_]+", "-", (value or "").strip().lower())
    agent = AGENT_ALIASES.get(key)
    if not agent:
        raise UsageError(
            "不支持的 Agent：%s（可用：opencode、claude、codex）" % value
        )
    return agent


def read_text_file(path: Path, label: str) -> str:
    """读取文本文件；不把文件内容放进错误信息，避免泄露密钥。"""
    if not path.is_file():
        raise UsageError("找不到 %s：%s" % (label, path))
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError("读取 %s 失败：%s" % (label, exc))


def load_json_file(path: Path, label: str) -> Dict[str, Any]:
    """读取并解析 JSON 对象。"""
    text = read_text_file(path, label)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise UsageError("%s 不是合法的 JSON：%s" % (label, path))
    if not isinstance(data, dict):
        raise UsageError("%s 格式不正确：%s" % (label, path))
    return data


def validate_token(token: Any, source: str) -> str:
    """校验取到的 Token，拒绝空值和未替换的占位符。"""
    if not isinstance(token, str) or not token.strip():
        raise UsageError("在 %s 中没有找到有效的 DeepSeek API Key" % source)
    token = token.strip()
    if token.startswith("<") and token.endswith(">"):
        raise UsageError("在 %s 中仍然是占位符，请替换为真实的 DeepSeek API Key" % source)
    if "\n" in token or "\r" in token:
        raise UsageError("在 %s 中的 DeepSeek API Key 格式不正确" % source)
    return token


def opencode_auth_path() -> Path:
    """OpenCode 的 auth.json 路径（遵循 XDG_DATA_HOME）。"""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "opencode" / "auth.json"


def read_opencode_key() -> str:
    """读取 OpenCode auth.json 中 deepseek 供应商的 API Key。"""
    path = opencode_auth_path()
    data = load_json_file(path, "OpenCode auth.json")

    # 只认供应商 ID 含 deepseek 的条目，避免拿到 OpenAI/Anthropic 的 Key
    candidates = [
        (name, entry)
        for name, entry in data.items()
        if isinstance(entry, dict) and "deepseek" in name.lower()
    ]
    if not candidates:
        raise UsageError("OpenCode 未配置 DeepSeek 供应商：%s" % path)

    # 精确名为 deepseek 的供应商优先
    candidates.sort(key=lambda item: (item[0].lower() != "deepseek", item[0].lower()))
    for name, entry in candidates:
        auth_type = str(entry.get("type") or "api").lower()
        if auth_type != "api":
            continue
        key = entry.get("key")
        if isinstance(key, str) and key.strip():
            return validate_token(key, "OpenCode 的 DeepSeek 供应商（%s）" % path)

    raise UsageError(
        "OpenCode 的 DeepSeek 供应商没有 API Key（需要 type=api 和 key 字段）：%s"
        % path
    )


def claude_settings_paths() -> List[Path]:
    """Claude Code 设置文件，按优先级从低到高排列。"""
    home = Path.home()
    cwd = Path.cwd()
    return [
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
        cwd / ".claude" / "settings.json",
        cwd / ".claude" / "settings.local.json",
    ]


def read_claude_key() -> str:
    """读取 Claude Code 中指向 DeepSeek 的 ANTHROPIC_AUTH_TOKEN。"""
    merged_env: Dict[str, str] = {}
    existing: List[str] = []

    # 低优先级文件先合并，高优先级文件覆盖，模拟 Claude Code 的 settings 优先级
    for path in claude_settings_paths():
        if not path.is_file():
            continue
        existing.append(str(path))
        data = load_json_file(path, "Claude Code 配置")
        env = data.get("env")
        if isinstance(env, dict):
            for key, value in env.items():
                if isinstance(value, str):
                    merged_env[key] = value

    if not existing:
        raise UsageError(
            "未找到 Claude Code 配置文件（~/.claude/settings.json 或项目 .claude/settings.json）；"
            "本技能不读取环境变量"
        )

    base_url = merged_env.get("ANTHROPIC_BASE_URL", "")
    host = (urllib.parse.urlsplit(base_url).hostname or "").lower()
    if "deepseek" not in host:
        raise UsageError(
            "Claude Code 当前未指向 DeepSeek（host=%s），不会读取其他供应商的 Key"
            % (host or "未设置")
        )

    token = merged_env.get("ANTHROPIC_AUTH_TOKEN") or merged_env.get(
        "ANTHROPIC_API_KEY"
    )
    if not token:
        raise UsageError(
            "Claude Code 已指向 DeepSeek，但没有配置 ANTHROPIC_AUTH_TOKEN"
        )
    if token.strip().startswith("$"):
        raise UsageError(
            "Claude Code 的 DeepSeek Key 使用了环境变量引用，本技能不读取环境变量；"
            "请把 Key 直接写入 settings.json 的 env.ANTHROPIC_AUTH_TOKEN"
        )
    return validate_token(token, "Claude Code 的 DeepSeek 配置")


def codex_config_path() -> Path:
    """Codex 的 config.toml 路径（遵循 CODEX_HOME）。"""
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home) if codex_home else Path.home() / ".codex"
    return base / "config.toml"


def parse_toml_string(raw: str) -> Optional[str]:
    """解析 config.toml 中的单行字符串值；不支持多行字符串。"""
    raw = raw.strip()
    if raw.startswith("'"):
        end = raw.find("'", 1)
        return raw[1:end] if end != -1 else None
    if raw.startswith('"'):
        chars: List[str] = []
        escaped = False
        for char in raw[1:]:
            if escaped:
                chars.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                return "".join(chars)
            else:
                chars.append(char)
        return None
    return None


def parse_codex_providers(text: str) -> Dict[str, Dict[str, str]]:
    """从 Codex config.toml 中提取 [model_providers.*] 配置段。

    只解析读取 Token 所需的一层键值，避免引入第三方 TOML 依赖。
    """
    providers: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(
            r"^\[model_providers\.([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$", line
        )
        if match:
            current = match.group(1)
            providers.setdefault(current, {})
            continue
        if line.startswith("["):
            current = None
            continue
        if current is None:
            continue

        match = re.match(r"^([A-Za-z0-9_-]+)\s*=\s*(.+)$", line)
        if not match:
            continue
        key, raw_value = match.group(1), match.group(2)
        value = parse_toml_string(raw_value)
        if value is not None:
            providers[current][key] = value

    return providers


def is_deepseek_provider(name: str, config: Dict[str, str]) -> bool:
    """根据供应商 ID、显示名或 base_url 判断是否为 DeepSeek。"""
    haystack = " ".join(
        [name, config.get("name", ""), config.get("base_url", "")]
    ).lower()
    return "deepseek" in haystack


def read_codex_key() -> str:
    """读取 Codex config.toml 中 DeepSeek 供应商的 Bearer Token。"""
    path = codex_config_path()
    text = read_text_file(path, "Codex config.toml")
    providers = parse_codex_providers(text)

    deepseek = {
        name: config
        for name, config in providers.items()
        if is_deepseek_provider(name, config)
    }
    if not deepseek:
        raise UsageError("Codex 未配置 DeepSeek 供应商：%s" % path)

    # 精确名为 deepseek 的供应商优先
    ordered = sorted(
        deepseek.items(), key=lambda item: (item[0].lower() != "deepseek", item[0].lower())
    )
    env_keys: List[str] = []
    for name, config in ordered:
        token = config.get("experimental_bearer_token") or config.get("bearer_token")
        if isinstance(token, str) and token.strip():
            return validate_token(
                token, "Codex 的 DeepSeek 供应商（%s）" % path
            )
        if config.get("env_key"):
            env_keys.append(config["env_key"])

    if env_keys:
        raise UsageError(
            "Codex 的 DeepSeek Key 来自环境变量 %s；本技能不读取环境变量，"
            "请改为在 [model_providers.deepseek] 中设置 experimental_bearer_token"
            % "、".join(env_keys)
        )
    raise UsageError(
        "Codex 的 DeepSeek 供应商缺少 experimental_bearer_token：%s" % path
    )


def read_agent_token(agent: str) -> str:
    """按 Agent 读取其已配置的 DeepSeek API Key。"""
    if agent == "opencode":
        return read_opencode_key()
    if agent == "claude":
        return read_claude_key()
    if agent == "codex":
        return read_codex_key()
    raise UsageError("不支持的 Agent：%s" % agent)


def validate_search_args(args: argparse.Namespace) -> None:
    """在发请求前校验搜索参数，避免无效请求产生费用。"""
    if not args.query.strip():
        raise UsageError("搜索词不能全为空白")
    if len(args.query) > 128:
        raise UsageError("搜索词长度不能超过 128 个字符（当前 %d）" % len(args.query))
    if not 1 <= args.count <= 50:
        raise UsageError("--count 必须在 1 到 50 之间（当前 %d）" % args.count)
    if args.content_max_chars < 0:
        raise UsageError("--content-max-chars 不能为负数")
    if args.ori_question is not None:
        if not args.ori_question.strip():
            raise UsageError("--ori-question 不能为空白")
        if len(args.ori_question) > 128:
            raise UsageError("--ori-question 长度不能超过 128 个字符")


def validate_fetch_args(args: argparse.Namespace) -> None:
    """在发请求前校验 URL 与截断参数。"""
    if args.max_chars < 0:
        raise UsageError("--max-chars 不能为负数")
    if len(args.url) > 8192:
        raise UsageError("URL 长度不能超过 8192 个字符")
    try:
        parts = urllib.parse.urlsplit(args.url)
    except ValueError as exc:
        raise UsageError("URL 格式不合法：%s" % exc)
    if parts.scheme not in ("http", "https"):
        raise UsageError("URL 必须以 http:// 或 https:// 开头")
    if not parts.hostname:
        raise UsageError("URL 必须包含有效的主机名")
    if parts.username is not None or parts.password is not None:
        raise UsageError("URL 不能携带用户名或密码")


# ---------------------------------------------------------------------------
# HTTP 请求
# ---------------------------------------------------------------------------


def request_json(
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    api_key: str,
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    """向 DeepSeek API 发送 POST 请求并解析 JSON 响应。

    遇到 408/429/5xx 或网络错误时按指数退避重试；其余错误立即失败。
    """
    url = base_url + path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "deepseek-search-skill/1.0",
    }

    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # 服务端返回了 HTTP 错误，尽量提取结构化错误信息
            raw = exc.read()
            message, code = parse_error_body(raw)
            if exc.code in RETRYABLE_STATUS and attempt < retries:
                delay = retry_delay(exc.headers, attempt)
                print(
                    "警告：服务端返回 HTTP %d，%.0f 秒后重试（%d/%d）"
                    % (exc.code, delay, attempt + 1, retries),
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            raise ApiError(exc.code, message, code)
        except (urllib.error.URLError, OSError) as exc:
            # 包含 DNS 失败、连接被拒、超时等网络层错误
            reason = getattr(exc, "reason", exc)
            if attempt < retries:
                delay = retry_delay(None, attempt)
                print(
                    "警告：网络错误（%s），%.0f 秒后重试（%d/%d）"
                    % (reason, delay, attempt + 1, retries),
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            raise ApiError(None, "网络请求失败：%s" % reason)

        return decode_json(raw, url)

    # 正常流程不会走到这里（循环内要么返回，要么抛出）
    raise ApiError(None, "请求失败：重试次数已用尽")


def decode_json(raw: bytes, url: str) -> Dict[str, Any]:
    """解码响应 JSON；非 JSON 响应给出可读错误。"""
    text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        snippet = text.strip()[:500] or "（空响应）"
        raise ApiError(None, "%s 返回了非 JSON 内容：%s" % (url, snippet))
    if not isinstance(data, dict):
        raise ApiError(None, "%s 返回了非预期的 JSON 类型" % url)
    return data


def parse_error_body(raw: bytes) -> Tuple[str, Optional[str]]:
    """从 OpenAI 兼容错误体中提取 message 与 code。"""
    text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return (text.strip()[:500] or "服务端未返回错误详情", None)

    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        error = data["error"]
        message = str(error.get("message") or "未知错误")
        code = error.get("code")
        return (message, str(code) if code is not None else None)
    return (text.strip()[:500] or "未知错误", None)


def retry_delay(headers: Any, attempt: int) -> float:
    """计算重试等待时间，优先使用 Retry-After。"""
    if headers is not None:
        value = headers.get("Retry-After")
        if value:
            try:
                return max(0.0, min(float(value), MAX_RETRY_DELAY))
            except (TypeError, ValueError):
                pass
    return float(min(2**attempt, int(MAX_RETRY_DELAY)))


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------


def truncate(text: str, limit: int) -> Tuple[str, bool]:
    """按字符数截断文本；limit 为 0 表示不限制。"""
    if limit <= 0 or len(text) <= limit:
        return (text, False)
    return (text[:limit].rstrip() + "\n…", True)


def format_meta(item: Dict[str, Any]) -> str:
    """格式化单条搜索结果的元信息行。"""
    parts: List[str] = []

    site_name = item.get("site_name")
    parts.append("站点：%s" % site_name if site_name else "站点：未知")

    score = item.get("rerank_score")
    if isinstance(score, (int, float)):
        parts.append("排序分：%g" % score)
    else:
        parts.append("排序分：未知")

    authority = item.get("authority")
    if isinstance(authority, int) and authority >= 0:
        parts.append("权威性：%d" % authority)
    else:
        parts.append("权威性：未知")

    date = item.get("date")
    parts.append("发布日期：%s" % date if date else "发布日期：未知")

    return " | ".join(parts)


def format_search(data: Dict[str, Any], query: str, content_max_chars: int) -> str:
    """把搜索响应格式化为便于模型阅读的 Markdown。"""
    results = data.get("results")
    if not isinstance(results, list):
        results = []

    lines = ["搜索「%s」：%d 条结果" % (query, len(results))]
    if not results:
        lines.append("")
        lines.append("未找到匹配结果。")
        return "\n".join(lines)

    for index, item in enumerate(results, 1):
        if not isinstance(item, dict):
            continue
        title = " ".join(str(item.get("title") or "（无标题）").split())
        url = str(item.get("url") or "")

        lines.append("")
        lines.append("### %d. %s" % (index, title))
        if url:
            lines.append("- 链接：%s" % url)
        lines.append("- 元信息：%s" % format_meta(item))

        summary = str(item.get("summary") or "").strip() or str(
            item.get("snippet") or ""
        ).strip()
        if summary:
            lines.append("- 摘要：%s" % summary)

        content = str(item.get("content") or "")
        if content:
            shown, truncated = truncate(content, content_max_chars)
            lines.append("- 正文：")
            lines.append(shown)
            if truncated:
                lines.append(
                    "（正文已截断，仅显示前 %d 个字符）" % content_max_chars
                )

    return "\n".join(lines)


def strip_duplicate_title(content: str, title: str) -> str:
    """去掉正文开头与页面标题重复的一级标题，避免输出中出现两次。"""
    lines = content.lstrip("\n").splitlines()
    if not lines:
        return content
    first = lines[0].strip()
    if first.startswith("# ") and first[2:].strip() == title.strip():
        rest = "\n".join(lines[1:]).lstrip("\n")
        # 正文只有标题时保留原内容，避免输出为空
        return rest if rest.strip() else content
    return content


def format_fetch(data: Dict[str, Any], url: str, max_chars: int) -> str:
    """把抓取结果格式化为 Markdown。"""
    title = " ".join(str(data.get("title") or "（无标题）").split())
    content = str(data.get("content") or "")
    if not content.strip():
        raise ApiError(None, "响应中没有可用的网页正文")

    content = strip_duplicate_title(content, title)
    shown, truncated = truncate(content, max_chars)
    lines = ["# %s" % title, "", "来源：%s" % url, "", shown]
    if truncated:
        lines.extend(
            [
                "",
                "> 注：内容已截断，仅显示前 %d 个字符（原长 %d 字符）。"
                "使用 --max-chars 0 可输出完整内容。" % (max_chars, len(content)),
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------


def run_search(args: argparse.Namespace, base_url: str, api_key: str) -> int:
    validate_search_args(args)

    payload: Dict[str, Any] = {
        "query": args.query,
        "count": args.count,
        "need_content": bool(args.content),
    }
    if args.ori_question is not None:
        payload["ori_question"] = args.ori_question
    if args.localization:
        payload["localization"] = args.localization

    data = request_json(
        base_url, SEARCH_PATH, payload, api_key, args.timeout, args.retries
    )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_search(data, args.query, args.content_max_chars))
    return 0


def run_fetch(args: argparse.Namespace, base_url: str, api_key: str) -> int:
    validate_fetch_args(args)

    data = request_json(
        base_url,
        FETCH_PATH,
        {"url": args.url},
        api_key,
        args.timeout,
        args.retries,
    )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_fetch(data, args.url, args.max_chars))
    return 0


def run(args: argparse.Namespace) -> int:
    """执行子命令，完成公共参数校验。"""
    if args.timeout <= 0:
        raise UsageError("--timeout 必须大于 0")
    if args.retries < 0:
        raise UsageError("--retries 不能为负数")

    base_url = normalize_base_url(args.base_url)
    agent = normalize_agent(args.agent)
    api_key = read_agent_token(agent)

    if args.command == "search":
        return run_search(args, base_url, api_key)
    if args.command == "fetch":
        return run_fetch(args, base_url, api_key)
    raise UsageError("未知子命令：%s" % args.command)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def configure_stdio() -> None:
    """尽量把标准输出/错误切换为 UTF-8，避免 Windows 控制台编码问题。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def print_api_error(exc: ApiError) -> None:
    """把 API 错误打印为可操作的中文提示。"""
    prefix = "HTTP %d" % exc.status if exc.status else "请求失败"
    print("错误（%s）：%s" % (prefix, exc.message), file=sys.stderr)
    if exc.code and exc.code != exc.message:
        print("错误码：%s" % exc.code, file=sys.stderr)
    hint = ERROR_HINTS.get(exc.status) if exc.status else None
    if hint:
        print("提示：%s" % hint, file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    """命令行入口，返回进程退出码。"""
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return run(args)
    except UsageError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
    except ApiError as exc:
        print_api_error(exc)
        return 1
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
