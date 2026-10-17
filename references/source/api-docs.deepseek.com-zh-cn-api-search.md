[跳到主要内容](https://api-docs.deepseek.com/zh-cn/api/search/#__docusaurus_skipToContent_fallback)

Search / Fetch API 已上线，使用自研搜索引擎，支持网页搜索与抓取， [点此查看使用指南。](https://api-docs.deepseek.com/zh-cn/guides/search)

# 网页搜索

```
POST https://api.deepseek.com/v1/tools/search
```

按 query 搜索网页，返回结构化的结果列表。支持的搜索语法、错误处理和计费说明请参考 [网页搜索与抓取指南](https://api-docs.deepseek.com/zh-cn/guides/search)。

## Request [​](https://api-docs.deepseek.com/zh-cn/api/search/\#request "Request的直接链接")

- application/json

### Body

**required**

**query** stringrequired

**Possible values:**`non-empty` and `<= 128 characters`

搜索词。支持 `site:`、`-site:`、引号等搜索语法。必须为 1～128 个 Unicode 字符，且不能全为空白。

**count** integer

**Possible values:**`>= 1` and `<= 50`

**Default value:**`10`

返回条数，取值在 1 到 50 之间，默认为 10。

**ori\_question** stringnullable

**Possible values:**`non-empty` and `<= 128 characters`

触发搜索的用户原始问题，1～128 个字符。提供该字段有助于更好地理解搜索意图；传 `null` 视为未提供。

**localization** string

用于优先返回本地化搜索结果的 IP 地址，默认为空字符串。

**need\_content** boolean

是否在 `content` 中返回网页正文。默认为 `false`；为 `false` 时，`content` 恒为空字符串。

## Responses [​](https://api-docs.deepseek.com/zh-cn/api/search/\#responses "Responses的直接链接")

- 200

OK, 返回搜索结果。

- application/json

- Schema
- Example (from schema)
- Example

**Schema**

**results**
object\[\]

required

搜索结果；没有匹配结果时为空数组。

Array \[\
\
**rerank\_score** floatrequired\
\
**Possible values:**`<= 3`\
\
排序分数，0～3 分，综合考虑相关性、权威性、时效性等维度。大于等于 1.5 分为优质结果。\
\
**title** stringrequired\
\
搜索结果标题。\
\
**url** stringrequired\
\
搜索结果链接。\
\
**snippet** stringrequired\
\
短摘要，与 query 相关，通常为 100～200 字符，适用于前端展现。\
\
**summary** stringrequired\
\
长摘要，与 query 相关，通常为 600～800 字符，适用于给模型阅读。\
\
**content** stringrequired\
\
网页正文。`need_content` 为 `false` 或正文缺失时为空字符串。\
\
**site\_name** stringnullablerequired\
\
站点名称；缺失时为 `null`。\
\
**site\_icon** stringnullablerequired\
\
站点图标 URL；缺失时为 `null`。\
\
**date** date-timenullablerequired\
\
发布时间，统一为 UTC 的 RFC 3339 格式；未知时为 `null`。\
\
**authority** integerrequired\
\
**Possible values:**`>= -1` and `<= 4`\
\
网页权威性，0～4（`-1` 表示未知）；大于等于 3 为极权威结果。\
\
\]

```json
{
  "results": [\
    {\
      "rerank_score": 0,\
      "title": "string",\
      "url": "string",\
      "snippet": "string",\
      "summary": "string",\
      "content": "string",\
      "site_name": "string",\
      "site_icon": "string",\
      "date": "2026-10-17T09:00:12.122Z",\
      "authority": 0\
    }\
  ]
}
```

```json
{
  "results": [\
    {\
      "rerank_score": 2.4,\
      "title": "DeepSeek V4 model released",\
      "url": "https://example.com/deepseek-v4",\
      "snippet": "DeepSeek V4 is now available, with tool calling and long-context support.",\
      "summary": "DeepSeek has released the V4 model. The release adds improved tool calling and long-context support for agent workflows.",\
      "content": "DeepSeek V4 is now generally available...",\
      "site_name": "Example News",\
      "site_icon": "https://example.com/favicon.ico",\
      "date": "2026-06-01T00:00:00+00:00",\
      "authority": 3\
    }\
  ]
}
```

- curl
- python
- go
- nodejs
- java

- CURL

```bash
curl -L -X POST 'https://api.deepseek.com/v1/tools/search' \
-H 'Content-Type: application/json' \
-H 'Accept: application/json' \
-H 'Authorization: Bearer <TOKEN>' \
--data-raw '{
  "query": "string",
  "count": 10,
  "ori_question": "string",
  "localization": "string",
  "need_content": false
}'
```