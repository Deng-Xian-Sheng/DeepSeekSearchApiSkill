# -*- coding: utf-8 -*-
"""deepseek_search.py 的单元测试。

使用本地 mock HTTP 服务模拟 DeepSeek API，不消耗真实额度。
运行：python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import deepseek_search as cli  # noqa: E402


class MockHandler(BaseHTTPRequestHandler):
    """可编排响应序列的 mock 处理器，同时记录收到的请求。"""

    responses = []  # 元素：(status, payload, extra_headers)
    requests = []  # 记录请求路径、请求头与请求体

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            body = raw.decode("utf-8", errors="replace")
        type(self).requests.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )

        if type(self).responses:
            status, payload, extra_headers = type(self).responses.pop(0)
        else:
            status, payload, extra_headers = 200, {"results": []}, {}

        if isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for key, value in extra_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        """关闭默认的访问日志，保持测试输出干净。"""
        pass


class CliTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        # 避免测试环境中的代理变量干扰本地请求
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        os.environ["no_proxy"] = "127.0.0.1,localhost"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        MockHandler.responses = []
        MockHandler.requests = []
        self.tmpdir = tempfile.TemporaryDirectory()

        # 请求层测试统一注入假 Key；读取逻辑由单独的测试覆盖
        self.token_patcher = mock.patch.object(
            cli, "read_agent_token", return_value="test-key"
        )
        self.mock_read_token = self.token_patcher.start()

    def tearDown(self):
        self.token_patcher.stop()
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def run_cli(self, *args):
        """运行 CLI 并捕获输出。"""
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def base_args(self, *extra):
        """带上 mock 服务地址、Agent 名与假 Key 的公共参数。"""
        return ("--agent", "opencode", "--base-url", self.base_url, *extra)

    def write_json(self, name, data):
        path = Path(self.tmpdir.name) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def write_text(self, name, text):
        path = Path(self.tmpdir.name) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def search_payload():
        return {
            "results": [
                {
                    "rerank_score": 2.4,
                    "title": "DeepSeek V4 模型发布",
                    "url": "https://example.com/deepseek-v4",
                    "snippet": "短摘要",
                    "summary": "DeepSeek 发布了 V4 模型，改进了工具调用与长上下文能力。",
                    "content": "",
                    "site_name": "Example News",
                    "site_icon": "https://example.com/favicon.ico",
                    "date": "2026-06-01T00:00:00+00:00",
                    "authority": 3,
                },
                {
                    "rerank_score": 1.2,
                    "title": "第二篇",
                    "url": "https://example.com/second",
                    "snippet": "备用摘要",
                    "summary": "",
                    "content": "",
                    "site_name": None,
                    "site_icon": None,
                    "date": None,
                    "authority": -1,
                },
            ]
        }

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def test_search_request_and_output(self):
        MockHandler.responses = [(200, self.search_payload(), {})]

        code, stdout, stderr = self.run_cli(
            "search", "DeepSeek V4", *self.base_args()
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(len(MockHandler.requests), 1)
        self.mock_read_token.assert_called_once_with("opencode")

        request = MockHandler.requests[0]
        self.assertEqual(request["path"], "/v1/tools/search")
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(request["body"]["query"], "DeepSeek V4")
        self.assertEqual(request["body"]["count"], 5)
        self.assertFalse(request["body"]["need_content"])
        self.assertNotIn("ori_question", request["body"])

        self.assertIn("DeepSeek V4 模型发布", stdout)
        self.assertIn("https://example.com/deepseek-v4", stdout)
        self.assertIn("DeepSeek 发布了 V4 模型", stdout)
        self.assertIn("排序分：2.4", stdout)
        self.assertIn("权威性：3", stdout)
        # 第二条 summary 为空时回退到 snippet
        self.assertIn("备用摘要", stdout)
        self.assertIn("权威性：未知", stdout)

    def test_search_content_is_truncated(self):
        payload = self.search_payload()
        payload["results"][0]["content"] = "正" * 100
        MockHandler.responses = [(200, payload, {})]

        code, stdout, _ = self.run_cli(
            "search",
            "q",
            *self.base_args("--content", "--content-max-chars", "10"),
        )

        self.assertEqual(code, 0)
        self.assertTrue(MockHandler.requests[0]["body"]["need_content"])
        self.assertIn("正文已截断", stdout)
        self.assertIn("正" * 10, stdout)
        self.assertNotIn("正" * 11, stdout)

    def test_search_empty_results(self):
        MockHandler.responses = [(200, {"results": []}, {})]

        code, stdout, _ = self.run_cli("search", "没有结果", *self.base_args())

        self.assertEqual(code, 0)
        self.assertIn("0 条结果", stdout)
        self.assertIn("未找到匹配结果", stdout)

    def test_search_json_output(self):
        payload = self.search_payload()
        MockHandler.responses = [(200, payload, {})]

        code, stdout, _ = self.run_cli(
            "search", "q", *self.base_args("--json")
        )

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout), payload)

    def test_search_passes_optional_fields(self):
        MockHandler.responses = [(200, {"results": []}, {})]

        self.run_cli(
            "search",
            "q",
            *self.base_args(
                "--count",
                "50",
                "--ori-question",
                "用户原始问题",
                "--localization",
                "1.2.3.4",
            ),
        )

        body = MockHandler.requests[0]["body"]
        self.assertEqual(body["count"], 50)
        self.assertEqual(body["ori_question"], "用户原始问题")
        self.assertEqual(body["localization"], "1.2.3.4")

    def test_search_validation_rejects_bad_count_without_request(self):
        code, _, stderr = self.run_cli(
            "search", "q", *self.base_args("--count", "51")
        )

        self.assertEqual(code, 2)
        self.assertIn("--count", stderr)
        self.assertEqual(MockHandler.requests, [])

    def test_search_validation_rejects_blank_query(self):
        code, _, stderr = self.run_cli("search", "   ", *self.base_args())

        self.assertEqual(code, 2)
        self.assertIn("空白", stderr)
        self.assertEqual(MockHandler.requests, [])

    # ------------------------------------------------------------------
    # 抓取
    # ------------------------------------------------------------------

    def test_fetch_request_and_output(self):
        payload = {"title": "示例文章", "content": "# 示例文章\n\n正文内容"}
        MockHandler.responses = [(200, payload, {})]

        code, stdout, stderr = self.run_cli(
            "fetch", "https://example.com/article", *self.base_args()
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(MockHandler.requests[0]["path"], "/v1/tools/fetch")
        self.assertEqual(
            MockHandler.requests[0]["body"], {"url": "https://example.com/article"}
        )
        self.assertIn("# 示例文章", stdout)
        self.assertIn("来源：https://example.com/article", stdout)
        self.assertIn("正文内容", stdout)
        # 正文自带的同名 H1 不应重复输出
        self.assertEqual(stdout.count("# 示例文章"), 1)

    def test_fetch_truncation(self):
        MockHandler.responses = [
            (200, {"title": "长文", "content": "abcdefghij"}, {})
        ]

        code, stdout, _ = self.run_cli(
            "fetch", "https://example.com/long", *self.base_args("--max-chars", "5")
        )

        self.assertEqual(code, 0)
        self.assertIn("abcde", stdout)
        self.assertNotIn("abcdef", stdout)
        self.assertIn("内容已截断", stdout)

    def test_fetch_rejects_non_http_url_without_request(self):
        code, _, stderr = self.run_cli(
            "fetch", "ftp://example.com/file", *self.base_args()
        )

        self.assertEqual(code, 2)
        self.assertIn("http", stderr)
        self.assertEqual(MockHandler.requests, [])

    def test_fetch_rejects_url_with_credentials(self):
        code, _, stderr = self.run_cli(
            "fetch", "https://user:pass@example.com/", *self.base_args()
        )

        self.assertEqual(code, 2)
        self.assertIn("用户名或密码", stderr)
        self.assertEqual(MockHandler.requests, [])

    # ------------------------------------------------------------------
    # 错误与重试
    # ------------------------------------------------------------------

    def test_http_401_is_not_retried(self):
        error = {
            "error": {
                "message": "Authentication Fails",
                "type": "authentication_error",
                "param": None,
                "code": "invalid_api_key",
            }
        }
        MockHandler.responses = [(401, error, {})]

        code, _, stderr = self.run_cli(
            "search", "q", *self.base_args("--retries", "3")
        )

        self.assertEqual(code, 1)
        self.assertEqual(len(MockHandler.requests), 1)
        self.assertIn("HTTP 401", stderr)
        self.assertIn("Authentication Fails", stderr)
        self.assertIn("DeepSeek API Key", stderr)

    def test_retryable_500_then_success(self):
        MockHandler.responses = [
            (500, {"error": {"message": "temporary"}}, {}),
            (200, self.search_payload(), {}),
        ]

        with mock.patch.object(cli.time, "sleep", return_value=None):
            code, stdout, stderr = self.run_cli(
                "search", "q", *self.base_args("--retries", "1")
            )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(len(MockHandler.requests), 2)
        self.assertIn("重试", stderr)
        self.assertIn("DeepSeek V4 模型发布", stdout)

    def test_retry_exhausted_returns_error(self):
        MockHandler.responses = [
            (500, {"error": {"message": "still broken"}}, {}),
            (500, {"error": {"message": "still broken"}}, {}),
        ]

        with mock.patch.object(cli.time, "sleep", return_value=None):
            code, _, stderr = self.run_cli(
                "search", "q", *self.base_args("--retries", "1")
            )

        self.assertEqual(code, 1)
        self.assertEqual(len(MockHandler.requests), 2)
        self.assertIn("HTTP 500", stderr)
        self.assertIn("still broken", stderr)

    def test_retry_after_header_is_honored(self):
        MockHandler.responses = [
            (429, {"error": {"message": "rate limited"}}, {"Retry-After": "3"}),
            (200, {"results": []}, {}),
        ]

        with mock.patch.object(cli.time, "sleep") as sleep:
            code, _, _ = self.run_cli(
                "search", "q", *self.base_args("--retries", "1")
            )

        self.assertEqual(code, 0)
        sleep.assert_called_once_with(3.0)

    # ------------------------------------------------------------------
    # Agent 名称
    # ------------------------------------------------------------------

    def test_agent_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["search", "q", "--base-url", self.base_url])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(MockHandler.requests, [])

    def test_unknown_agent_is_rejected(self):
        code, _, stderr = self.run_cli(
            "search", "q", "--agent", "unknown", "--base-url", self.base_url
        )

        self.assertEqual(code, 2)
        self.assertIn("不支持的 Agent", stderr)
        self.mock_read_token.assert_not_called()
        self.assertEqual(MockHandler.requests, [])

    def test_agent_alias_is_normalized(self):
        MockHandler.responses = [(200, {"results": []}, {})]

        code, _, _ = self.run_cli(
            "search", "q", "--agent", "Claude Code", "--base-url", self.base_url
        )

        self.assertEqual(code, 0)
        self.mock_read_token.assert_called_once_with("claude")

    # ------------------------------------------------------------------
    # OpenCode 配置读取
    # ------------------------------------------------------------------

    def test_opencode_reads_deepseek_provider(self):
        path = self.write_json(
            "opencode-auth.json",
            {"deepseek": {"type": "api", "key": "sk-opencode"}},
        )
        with mock.patch.object(cli, "opencode_auth_path", return_value=path):
            self.assertEqual(cli.read_opencode_key(), "sk-opencode")

    def test_opencode_ignores_other_providers(self):
        path = self.write_json(
            "opencode-auth.json",
            {"openai": {"type": "api", "key": "sk-other-provider"}},
        )
        with mock.patch.object(cli, "opencode_auth_path", return_value=path):
            with self.assertRaises(cli.UsageError) as raised:
                cli.read_opencode_key()

        self.assertIn("DeepSeek", str(raised.exception))
        self.assertNotIn("sk-other-provider", str(raised.exception))

    def test_opencode_rejects_non_api_auth_type(self):
        path = self.write_json(
            "opencode-auth.json",
            {"deepseek": {"type": "oauth", "access": "sk-oauth-secret"}},
        )
        with mock.patch.object(cli, "opencode_auth_path", return_value=path):
            with self.assertRaises(cli.UsageError) as raised:
                cli.read_opencode_key()

        self.assertIn("API Key", str(raised.exception))
        self.assertNotIn("sk-oauth-secret", str(raised.exception))

    def test_opencode_prefers_exact_deepseek_provider(self):
        path = self.write_json(
            "opencode-auth.json",
            {
                "my-deepseek": {"type": "api", "key": "sk-custom"},
                "deepseek": {"type": "api", "key": "sk-exact"},
            },
        )
        with mock.patch.object(cli, "opencode_auth_path", return_value=path):
            self.assertEqual(cli.read_opencode_key(), "sk-exact")

    # ------------------------------------------------------------------
    # Claude Code 配置读取
    # ------------------------------------------------------------------

    def test_claude_reads_deepseek_settings(self):
        path = self.write_json(
            "claude-settings.json",
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
                    "ANTHROPIC_AUTH_TOKEN": "sk-claude",
                }
            },
        )
        with mock.patch.object(cli, "claude_settings_paths", return_value=[path]):
            self.assertEqual(cli.read_claude_key(), "sk-claude")

    def test_claude_rejects_anthropic_base_url(self):
        path = self.write_json(
            "claude-settings.json",
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
                    "ANTHROPIC_AUTH_TOKEN": "sk-anthropic-secret",
                }
            },
        )
        with mock.patch.object(cli, "claude_settings_paths", return_value=[path]):
            with self.assertRaises(cli.UsageError) as raised:
                cli.read_claude_key()

        self.assertIn("未指向 DeepSeek", str(raised.exception))
        self.assertNotIn("sk-anthropic-secret", str(raised.exception))

    def test_claude_rejects_local_proxy(self):
        path = self.write_json(
            "claude-settings.json",
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "http://localhost:8080",
                    "ANTHROPIC_AUTH_TOKEN": "sk-proxy-token",
                }
            },
        )
        with mock.patch.object(cli, "claude_settings_paths", return_value=[path]):
            with self.assertRaises(cli.UsageError):
                cli.read_claude_key()

    def test_claude_rejects_env_variable_reference(self):
        path = self.write_json(
            "claude-settings.json",
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
                    "ANTHROPIC_AUTH_TOKEN": "${DEEPSEEK_API_KEY}",
                }
            },
        )
        with mock.patch.object(cli, "claude_settings_paths", return_value=[path]):
            with self.assertRaises(cli.UsageError) as raised:
                cli.read_claude_key()

        self.assertIn("环境变量", str(raised.exception))

    def test_claude_project_settings_override_user_settings(self):
        user = self.write_json(
            "user-settings.json",
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
                    "ANTHROPIC_AUTH_TOKEN": "sk-user",
                }
            },
        )
        project = self.write_json(
            "project-settings.json",
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
                    "ANTHROPIC_AUTH_TOKEN": "sk-project",
                }
            },
        )
        with mock.patch.object(
            cli, "claude_settings_paths", return_value=[user, project]
        ):
            self.assertEqual(cli.read_claude_key(), "sk-project")

    # ------------------------------------------------------------------
    # Codex 配置读取
    # ------------------------------------------------------------------

    def test_codex_reads_deepseek_provider(self):
        path = self.write_text(
            "codex-config.toml",
            '[model_providers.deepseek]\n'
            'name = "deepseek"\n'
            'base_url = "https://api.deepseek.com/"\n'
            'experimental_bearer_token = "sk-codex"\n',
        )
        with mock.patch.object(cli, "codex_config_path", return_value=path):
            self.assertEqual(cli.read_codex_key(), "sk-codex")

    def test_codex_ignores_other_providers(self):
        path = self.write_text(
            "codex-config.toml",
            "[model_providers.openai]\n"
            'base_url = "https://api.openai.com/v1"\n'
            'experimental_bearer_token = "sk-openai-secret"\n',
        )
        with mock.patch.object(cli, "codex_config_path", return_value=path):
            with self.assertRaises(cli.UsageError) as raised:
                cli.read_codex_key()

        self.assertIn("未配置 DeepSeek", str(raised.exception))
        self.assertNotIn("sk-openai-secret", str(raised.exception))

    def test_codex_rejects_env_key(self):
        path = self.write_text(
            "codex-config.toml",
            "[model_providers.deepseek]\n"
            'base_url = "https://api.deepseek.com/"\n'
            'env_key = "DEEPSEEK_API_KEY"\n',
        )
        with mock.patch.object(cli, "codex_config_path", return_value=path):
            with self.assertRaises(cli.UsageError) as raised:
                cli.read_codex_key()

        self.assertIn("环境变量", str(raised.exception))
        self.assertIn("experimental_bearer_token", str(raised.exception))

    def test_codex_toml_parser(self):
        providers = cli.parse_codex_providers(
            "# comment\n"
            "[model_providers.deepseek] # deepseek provider\n"
            "name = 'deepseek'\n"
            'base_url = "https://api.deepseek.com/" # inline comment\n'
            'experimental_bearer_token = "sk-test"\n'
            "\n"
            "[desktop]\n"
            'enabled-reasoning-efforts = ["low"]\n'
        )

        self.assertEqual(providers["deepseek"]["name"], "deepseek")
        self.assertEqual(
            providers["deepseek"]["base_url"], "https://api.deepseek.com/"
        )
        self.assertEqual(providers["deepseek"]["experimental_bearer_token"], "sk-test")
        self.assertNotIn("desktop", providers)


if __name__ == "__main__":
    unittest.main()
