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

顶层保留两个通用项：

- `enabled`
- `poll_interval_seconds`

其余配置改为两组嵌套对象：

- `news_push`：官方新闻推送配置
- `player_reminder`：玩家数据提醒配置

### `news_push` 关键项

- `language`：`zh-TW` / `en` / `ja` / `ko` / `zh`
- `fetch_limit`：每次拉取数量（运行时限制 1-50）
- `content_mode`：`none` / `summary` / `content`
- `max_images`：每条消息最多图片数（0-9）
- `show_publish_time`：是否显示发布时间
- `scheduled_push_groups`：推送目标列表（格式见下文）
- `push_delay_seconds`：多条推送间隔秒数（0-30）
- `push_prefix`：消息前缀

### `player_reminder` 关键项

- `enabled`：是否启用玩家提醒
- `cookie`：玩家请求 Cookie（必须是单行纯 ASCII 的 Cookie header 值）
- `outpost_fullness_threshold_percent`：前哨阈值 0-100  
`0` 表示关闭；`1-100` 表示“达到或超过阈值触发”（大于等于）
- `daily_mission_enabled`：是否启用日常未完成提醒
- `daily_mission_remind_time`：提醒时间（北京时间 `HH:MM`）
- `alert_prefix`：玩家提醒消息前缀

### 推送目标格式

`scheduled_push_groups` 支持以下写法：

- **纯数字群号**：`"957880653"` → 自动作为群消息发送
- **统一消息源格式**：`"aiocqhttp:GroupMessage:957880653"`、`"napcat:FriendMessage:2854964693"`、`"napcat:PrivateMessage:999"`

支持的消息类型：`GroupMessage`、`PrivateMessage`、`FriendMessage`。

## 消息来源

- 官方板块 ID：`43`
- 列表接口：`https://api.blablalink.com/api/ugc/direct/standalonesite/Dynamics/GetPostList`
- 详情链接格式：`https://www.blablalink.com/post/detail?post_uuid=<post_uuid>`
