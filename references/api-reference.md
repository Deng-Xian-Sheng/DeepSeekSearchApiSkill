# DeepSeek Search / Fetch API 参考

> 本文由 `references/source/` 中的 DeepSeek 官方文档整理而成，供 Agent 快速查阅。
> 当本文与官方文档冲突时，以 [官方文档](https://api-docs.deepseek.com/zh-cn/guides/search) 为准。

## 概览

| API | Endpoint | 用途 |
| --- | --- | --- |
| Search | `POST https://api.deepseek.com/v1/tools/search` | 按 query 搜索网页，返回结构化结果 |
| Fetch | `POST https://api.deepseek.com/v1/tools/fetch` | 抓取单个网页，返回 Markdown 正文 |

两者都是只读的原始 JSON API，使用与 DeepSeek 模型 API 相同的 Bearer 鉴权。

## 鉴权

| 请求头 | 必填 | 值 |
| --- | --- | --- |
| `Authorization` | 是 | `Bearer <DeepSeek API Key>` |
| `Content-Type` | 是 | `application/json` |

## Search 接口

### 请求字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | - | 搜索词，1～128 个 Unicode 字符，不能全为空白，支持搜索语法 |
| `count` | integer | 否 | `10` | 返回条数，1～50；不影响单次计费 |
| `ori_question` | string | 否 | - | 触发搜索的用户原始问题，1～128 字符；传 `null` 视为未提供 |
| `localization` | string | 否 | `""` | 用于优先返回本地化搜索结果的 IP 地址 |
| `need_content` | boolean | 否 | `false` | 是否在 `content` 中返回网页正文；为 `false` 时 `content` 恒为空字符串 |

请求体中的未知字段会被忽略。

### 响应字段

成功时返回 HTTP 200 与 `results` 数组；没有匹配结果时返回空数组。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rerank_score` | number | 排序分数，0～3，综合考虑相关性、权威性、时效性；≥1.5 为优质结果 |
| `title` | string | 标题 |
| `url` | string | 结果链接 |
| `snippet` | string | 短摘要，与 query 相关，通常 100～200 字符，适合前端展示 |
| `summary` | string | 长摘要，与 query 相关，通常 600～800 字符，适合给模型阅读 |
| `content` | string | 网页正文；`need_content` 为 `false` 或正文缺失时为空字符串 |
| `site_name` | string 或 null | 站点名称，缺失时为 `null` |
| `site_icon` | string 或 null | 站点图标 URL，缺失时为 `null` |
| `date` | string 或 null | 发布时间，UTC 的 RFC 3339 格式；未知时为 `null` |
| `authority` | integer | 网页权威性，0～4（`-1` 表示未知）；≥3 为极权威结果 |

### 响应示例

```json
{
  "results": [
    {
      "rerank_score": 2.4,
      "title": "DeepSeek V4 模型发布",
      "url": "https://example.com/deepseek-v4",
      "snippet": "DeepSeek V4 已上线，支持工具调用与长上下文。",
      "summary": "DeepSeek 发布了 V4 模型。此次发布改进了工具调用与长上下文能力，适合 Agent 工作流。",
      "content": "DeepSeek V4 现已正式上线……",
      "site_name": "Example News",
      "site_icon": "https://example.com/favicon.ico",
      "date": "2026-06-01T00:00:00+00:00",
      "authority": 3
    }
  ]
}
```

## Search 搜索语法

搜索语法写在 `query` 中，会原样传递给搜索服务；可在一个 query 中组合多个操作符。

| 操作符 | 示例 | 说明 |
| --- | --- | --- |
| `site:` | `DeepSeek site:github.com` | 将结果限制在指定站点；多个站点用空格分隔并通过 `OR` 连接，如 `site:github.com OR site:huggingface.co` |
| `-site:` | `DeepSeek -site:example.com` | 排除指定站点，多个用空格分隔 |
| `-` | `DeepSeek -广告` | 排除包含指定关键词的网页，多个用空格分隔 |
| `-"..."` | `DeepSeek -"release notes"` | 排除包含指定短语的网页，短语内可含空格 |
| `"..."` | `DeepSeek "精确短语"` | 精确匹配指定短语，多个用空格分隔 |
| `lang:` | `DeepSeek lang:zh,en` | 限制结果语言，多种语言用逗号分隔 |
| `after:` | `DeepSeek after:2025` 或 `after:2025-01-01` | 限制为指定日期之后发布的网页 |
| `before:` | `DeepSeek before:2026` 或 `before:2026-06-01` | 限制为指定日期之前发布的网页 |

组合示例：

```json
{
  "query": "DeepSeek 模型 site:github.com OR site:huggingface.co lang:zh after:2025",
  "count": 10
}
```

## Fetch 接口

### 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `url` | string | 是 | 要抓取的网页地址，长度 ≤8192，必须是含 host 的 HTTP/HTTPS URL，且不能携带用户名或密码 |

### 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | string | 页面标题，缺失时为空字符串 |
| `content` | string | 抓取后的 Markdown 正文 |

Fetch 结果受目标站点可用性和访问策略影响。

```json
{
  "title": "Example article",
  "content": "# Example article\n\nArticle content."
}
```

## 错误处理

错误响应使用 OpenAI 兼容格式，`param` 字段恒为 `null`：

```json
{
  "error": {
    "message": "'count' must be between 1 and 50",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_request_error"
  }
}
```

| HTTP 状态码 | 说明 | 是否可重试 |
| --- | --- | --- |
| 400 | 请求头或请求体不合法，包括 JSON 格式错误或字段值无效 | 否（修改请求后重试） |
| 401 | API Key 缺失或无效 | 否（修正 Key） |
| 402 | 账号余额不足 | 否（充值后重试） |
| 403 | Fetch 请求被安全策略拒绝 | 否 |
| 404 | Fetch 未能获取可用网页内容（URL 不可用、被拦截、站点报错、类型不支持或没有可提取正文） | 否 |
| 408 | 读取请求体超时 | 是 |
| 413 | 请求体超过大小限制 | 否 |
| 429 | 超过 Search 或 Fetch 的 QPS 限制 | 是（等待后重试） |
| 500 | 服务器内部错误 | 是 |
| 504 | 下游请求超时 | 是 |

遇到 408、429 或 5xx 时应等待后重试；遇到 402 先充值；其它 4xx 不修改请求则不应重试。
`scripts/deepseek_search.py` 已内置 408/429/5xx 与网络错误的重试和指数退避。

## 计费

Search 和 Fetch 按请求次数计费，不按 token 或结果条数计费：

| API | 计费单位 | 价格 |
| --- | --- | --- |
| Search | 每 1,000 次成功请求 | 5 元 |
| Fetch | 每 1,000 次成功请求 | 5 元 |

- 只有返回 HTTP 200 且产生结果的请求才计费：Search 的 `results` 必须非空，Fetch 必须返回网页正文。
- 请求失败、搜索无结果或超时不计费。
- `count` 只控制返回条数，不影响单次请求价格。
- 在 DeepSeek Harness / Claude Code / Codex 中通过 Server 端工具调用访问 Search/Fetch 目前未计费，自北京时间 2026-11-01 00:00 起按次收费。

## 限速

每个账号的 Search 与 Fetch 分别独立限速，互不占用额度：

| API | QPS 限制 |
| --- | --- |
| Search | 5 |
| Fetch | 5 |

- QPS 按账号粒度计算，与使用哪个 API Key 无关，也与模型并发限制无关。
- 超过账号级 QPS 会收到 HTTP 429。
- Fetch 还对目标域名有独立 QPS 限制，超过同样返回 429。
