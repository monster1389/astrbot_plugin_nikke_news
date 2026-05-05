# astrbot_plugin_nikke_news

AstrBot 插件：轮询 Blablalink 的 NIKKE Official 板块，并通过 NapCat / OneBot `aiocqhttp` 主动推送到 QQ 群或私聊。

## 功能

- 定时请求 Blablalink 官方消息列表。
- 只推送 Official 板块消息。
- 首次启动只记录当前已有消息，不补发历史内容。
- 后续发现新消息时推送标题、正文/摘要、图片、发布时间和详情链接。
- 支持 `content_mode` 控制推送内容详细程度（仅标题、摘要、正文全文）。
- 支持附带帖子图片（`pic_urls`），视频帖自动跳过图片。
- 消息开头可配置前缀（`push_prefix`）。
- 多条新帖推送间可配置延迟（`push_delay_seconds`）。
- 每轮轮询自动从磁盘重读状态，手动删 `state.json` 无需重启。
- 已推送状态保存在 AstrBot 插件数据目录，避免重复推送。

## 前置要求

- AstrBot 已启用 `aiocqhttp` 平台适配器。
- NapCat 已连接 AstrBot，且机器人有权限向配置的群或私聊发送消息。
- 插件依赖 `httpx`，安装插件依赖时会读取 `requirements.txt`。

## 配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enabled` | 是否启用插件 | `true` |
| `poll_interval_seconds` | 轮询间隔秒数（最低 60） | `300` |
| `language` | 消息语言（`zh-TW` / `en` / `ja` / `ko` / `zh`） | `zh-TW` |
| `fetch_limit` | 每次拉取的消息数量（1–50） | `10` |
| `content_mode` | 推送内容模式：`none` 仅标题和链接，`summary` 含概览，`content` 正文全文保留换行 | `summary` |
| `max_images` | 每条推送最多附带图片数（0–9，0 为不发图） | `3` |
| `show_publish_time` | 是否显示发布时间 | `true` |
| `scheduled_push_groups` | 推送目标列表，见下方格式说明 | `[]` |
| `push_delay_seconds` | 多条推送间隔秒数（0–30） | `2` |
| `push_prefix` | 消息前缀，留空不加前缀 | `【NIKKE 官方消息推送】` |
| `startup_mode` | 首次启动行为（目前固定 `mark_seen`） | `mark_seen` |

### 推送目标格式

`scheduled_push_groups` 支持以下写法：

- **纯数字群号**：`"957880653"` → 自动作为群消息发送
- **统一消息源格式**：`"aiocqhttp:GroupMessage:957880653"`、`"napcat:FriendMessage:2854964693"`、`"napcat:PrivateMessage:999"`

支持的消息类型：`GroupMessage`、`PrivateMessage`、`FriendMessage`。

## 消息来源

- 官方板块 ID：`43`
- 列表接口：`https://api.blablalink.com/api/ugc/direct/standalonesite/Dynamics/GetPostList`
- 详情链接格式：`https://www.blablalink.com/post/detail?post_uuid=<post_uuid>`
