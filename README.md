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
- 支持 `/nikke <角色名>` 查询玩家角色数据。
- 支持用 Playwright/Chromium 按需刷新角色名和装备词条映射。

## 前置要求

- AstrBot 已启用 `aiocqhttp` 平台适配器。
- NapCat 已连接 AstrBot，且机器人有权限向配置的群或私聊发送消息。
- 插件依赖 `httpx` 和 `playwright`，安装插件依赖时会读取 `requirements.txt`。
- 玩家角色查询依赖 Blablalink 登录 Cookie。
- 自动刷新玩家映射需要运行环境已安装 Playwright Python 包及 Chromium 浏览器。`requirements.txt` 会安装 Python 包；Chromium 浏览器本体需由 AstrBot Docker 镜像或运行环境提供。

## 配置

### 顶层配置

| 键 | 类型 | 默认值 | 说明 |
|---|------|--------|------|
| `enabled` | bool | `true` | 启用 NIKKE 官方消息推送 |
| `poll_interval_seconds` | int | `300` | 轮询间隔秒数（最低 60） |

### `news_push` 新闻推送配置

| 键 | 类型 | 默认值 | 说明 |
|---|------|--------|------|
| `language` | string | `zh-TW` | 消息语言：`zh-TW` / `en` / `ja` / `ko` |
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
| `mapping_language` | string | `en` | `/nikke` 玩家查询的角色名和装备词条映射语言 |
| `mapping_cache_ttl_hours` | int | `168` | 玩家映射缓存有效期，过期后按需刷新 |
| `auto_refresh_mapping` | bool | `true` | 查询时缓存缺失/过期则尝试启动 Chromium 刷新 |
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

### 玩家角色查询

- `/nikke <角色名>` 查询账号内角色战力、技能、装备等级和 T10 词条。
- `/nikke refresh` 或 `/nikke_refresh` 刷新角色名和词条映射。
- 词条映射刷新会按需使用运行环境中的 Playwright/Chromium 打开 Blablalink 页面并监听静态 JSON；未安装 Playwright 时会返回明确提示。
- 玩家映射缓存保存在 AstrBot 插件数据目录的 `player_mappings.json`。

查询示例：

```text
/nikke anis
/nikke rapi rh
/nikke refresh
```

查询流程：

1. 使用 `player_mappings.json` 将输入角色名匹配到 `name_code`。
2. 调用 `Game/GetUserCharacters` 确认该角色在账号中存在。
3. 调用 `Game/GetUserCharacterDetails` 获取技能等级、装备等级、装备词条 ID 和 `state_effects`。
4. 使用 `player_mappings.json` 中的词条映射把词条 ID 转为可读名称。
5. 按 Blablalink 前端逻辑格式化词条数值：`abs(function_value) / 100`，显示为百分比。

装备词条说明：

- 相同 `function_type` 的 T10 词条会聚合显示，例如多条 `StatAtk` 会合并为一行。
- 词条排序参考 Blablalink 前端：元素伤害、攻击、弹夹、蓄力、命中、暴击、防御。
- 如果缓存中缺少某个词条描述，插件会尽量使用接口返回的 `function_details` 字段兜底。

### 玩家映射缓存

`player_mappings.json` 由插件自动写入 AstrBot 插件数据目录，不建议提交到仓库。缓存内容包括：

- `language`：映射语言，默认 `en`。
- `updated_at`：刷新时间。
- `sources`：刷新时捕获到的 CDN JSON URL、ETag、Last-Modified。
- `characters`：英文角色名到 `name_code` 的映射。
- `character_names`：`name_code` 到目标语言显示名的映射（英文时为空）。
- `state_effect_options`：装备词条 `state_effect_id` 到描述、分组、类型的映射。

刷新策略：

- `auto_refresh_mapping=true` 时，查询发现缓存缺失或超过 `mapping_cache_ttl_hours` 会尝试自动刷新。
- 手动执行 `/nikke refresh` 会重新加载本地角色表，并尝试用 Chromium 刷新玩家映射。
- Chromium 只用于刷新映射，不参与每次玩家查询主链路。

常见问题：

- 提示“当前环境未安装 Playwright”：确认插件依赖已安装，AstrBot Docker 容器内可导入 `playwright`，并且 Chromium 已安装。
- 提示“未从页面网络响应中捕获到角色或词条映射”：通常是 Cookie 失效、页面未登录、页面资源加载失败或 Blablalink 前端资源结构变化。
- `/nikke <角色名>` 找不到角色：先执行 `/nikke refresh`，或在 `character_alias` 中添加别名。
- 有词条 ID 但没有词条名：删除数据目录中的 `player_mappings.json` 后执行 `/nikke refresh`。

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
- 玩家角色列表：`https://api.blablalink.com/api/game/proxy/Game/GetUserCharacters`
- 玩家角色详情：`https://api.blablalink.com/api/game/proxy/Game/GetUserCharacterDetails`
- 玩家工具页：`https://www.blablalink.com/shiftyspad/nikke-list?type=combat`
