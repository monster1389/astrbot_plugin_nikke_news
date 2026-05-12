# Blablalink 官方消息推送

## 功能

- 推送 Blablalink 的 Official 板块消息。
- 支持日常/收菜提醒。（需配置cookie）
- 支持 `/nikke <角色名>` 查询玩家角色数据。（需配置cookie）
- 支持 `/nikke_help` 查看所有命令。

## 前置要求

如不需要日常/收菜提醒、查询玩家角色数据，可跳过此项。

### 获取 Cookie

角色查询和玩家提醒需要 Blablalink 登录 Cookie：

1. 用浏览器打开 <https://www.blablalink.com> 并登录你的 NIKKE 账号。
2. 按 `F12` 打开开发者工具，切换到 **Application（应用程序）** 标签。
3. 左侧 Storage → Cookies → 点击 `www.blablalink.com`。
4. 在右侧 Cookies 列表中逐个找到以下字段，双击 Value 列复制：

   | 字段 | 说明 |
   |------|------|
   | `game_token` | 登录令牌 |
   | `game_openid` | 账号 OpenID |
   | `game_channelid` | 渠道 ID |
   | `game_gameid` | 游戏 ID（NIKKE） |

5. 将复制到的值填入 AstrBot 插件配置面板的 JSON 字段中。
6. 根据区服选择 `nikke_area_id`：日服=81，韩服=83，国际服=84，东南亚=85。
- **兼容方式**：也可从 Network 面板找到任意 API 请求，复制其 `Cookie` 请求头完整内容，直接填为字符串值。

### 安装 Playwright / Chromium

刷新角色映射和头像需要 Playwright + Chromium 浏览器：

- `requirements.txt` 已包含 `playwright>=1.44.0`，插件安装时会自动安装 Python 包。
- Chromium 浏览器本体需由运行环境提供（AstrBot Docker 镜像已内置，手动部署需执行 `playwright install chromium`）。

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
| `show_character_portrait` | bool | `true` | `/nikke` 查询时是否附带角色头像图片 |

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

### 玩家角色查询

- `/nikke <角色名>` 查询账号内角色战力、技能、装备等级和 T10 词条。
- `/nikke_refresh` 刷新角色名和词条映射。
- `/nikke_portrait_refresh` 用 Playwright 抓取角色头像并缓存到本地（首次启动自动缓存前 30 个）。
- `/nikke_help` 查看所有命令。

查询示例：

```text
/nikke anis
/nikke rapi rh
/nikke_refresh
/nikke_portrait_refresh
/nikke_help
```

常见问题：

- 提示“当前环境未安装 Playwright”：确认插件依赖已安装，AstrBot Docker 容器内可导入 `playwright`，并且 Chromium 已安装。
- 提示“未从页面网络响应中捕获到角色或词条映射”：通常是 Cookie 失效、页面未登录、页面资源加载失败或 Blablalink 前端资源结构变化。
- `/nikke <角色名>` 找不到角色：先执行 `/nikke_refresh`，或在 `插件设置` 中添加别名。
- 有词条 ID 但没有词条名：删除数据目录中的 `player_mappings_xx.json` 后执行 `/nikke_refresh`。

### 官方消息推送目标格式

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
