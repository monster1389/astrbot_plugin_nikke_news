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

### 顶层配置

| 键 | 类型 | 默认值 | 说明 |
|---|------|--------|------|
| `enabled` | bool | `true` | 启用 NIKKE 官方消息推送 |
| `poll_interval_seconds` | int | `300` | 轮询间隔秒数（最低 60） |

### `news_push` 新闻推送配置

| 键 | 类型 | 默认值 | 说明 |
|---|------|--------|------|
| `language` | string | `zh-TW` | 消息语言：`zh-TW` / `en` / `ja` / `ko` / `zh` |
| `fetch_limit` | int | `10` | 每次拉取数量（1-50） |
| `content_mode` | string | `summary` | `none` 仅标题+链接 / `summary` 概览 / `content` 正文 |
| `max_images` | int | `3` | 每条推送最多图片数（0-9，视频帖不发送图片） |
| `show_publish_time` | bool | `true` | 是否显示发布时间 |
| `scheduled_push_groups` | list | `[]` | 推送目标列表（格式见下文） |
| `startup_mode` | string | `mark_seen` | 首次启动行为（当前固定 `mark_seen`） |
| `push_delay_seconds` | int | `2` | 多条新帖推送间隔秒数（0-30） |
| `push_prefix` | string | `【NIKKE 官方消息推送】` | 消息前缀，留空则不添加 |

### `player_reminder` 玩家数据提醒配置

| 键 | 类型 | 默认值 | 说明 |
|---|------|--------|------|
| `enabled` | bool | `false` | 启用玩家数据提醒（需配置 cookie） |
| `cookie` | JSON | 见下方 | 玩家登录凭据，JSON 格式填入浏览器 Cookie 字段 |
| `outpost_fullness_threshold_percent` | int | `90` | 前哨基地满仓提醒阈值（0=关闭，1-100 表示触发百分比） |
| `daily_mission_enabled` | bool | `true` | 启用日常未完成提醒 |
| `daily_mission_remind_time` | string | `21:00` | 日常提醒时间（北京时间 `HH:MM`） |
| `alert_prefix` | string | `【NIKKE 玩家状态提醒】` | 玩家提醒消息前缀，留空则不添加 |

**`cookie` JSON 格式**（从浏览器 Cookie 中提取对应字段填入）：

```json
{
  "game_token": "",
  "game_openid": "",
  "game_channelid": "",
  "game_gameid": "",
  "nikke_area_id": 84
}
```

| 字段 | 说明 |
|------|------|
| `game_token` | 浏览器 Cookie 中的 `game_token` 值 |
| `game_openid` | 浏览器 Cookie 中的 `game_openid` 值 |
| `game_channelid` | 浏览器 Cookie 中的 `game_channelid` 值 |
| `game_gameid` | 浏览器 Cookie 中的 `game_gameid` 值 |
| `nikke_area_id` | 区服 ID：日服=81，韩服=83，国际服=84，东南亚=85 |

兼容旧版：直接填写纯字符串 Cookie header 值也可识别。

### 推送目标格式

`scheduled_push_groups` 支持以下写法：

- **纯数字群号**：`"957880653"` → 自动作为群消息发送
- **统一消息源格式**：`"aiocqhttp:GroupMessage:957880653"`、`"napcat:FriendMessage:2854964693"`、`"napcat:PrivateMessage:999"`

支持的消息类型：`GroupMessage`、`PrivateMessage`、`FriendMessage`。

## 消息来源

- 官方板块 ID：`43`
- 帖子列表：`https://api.blablalink.com/api/ugc/direct/standalonesite/Dynamics/GetPostList`
- 详情链接：`https://www.blablalink.com/post/detail?post_uuid=<post_uuid>`
- 玩家数据：`https://api.blablalink.com/api/game/proxy/Game/GetUserDailyContentsProgress`
