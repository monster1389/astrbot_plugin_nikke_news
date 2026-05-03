# astrbot_plugin_nikke_news

AstrBot 插件：轮询 Blablalink 的 NIKKE Official 板块，并通过 NapCat / OneBot `aiocqhttp` 主动推送到 QQ 群或私聊。

## 功能

- 定时请求 Blablalink 官方消息列表。
- 只推送 Official 板块消息。
- 首次启动只记录当前已有消息，不补发历史内容。
- 后续发现新消息时推送标题、摘要、发布时间和详情链接。
- 已推送状态保存在 AstrBot 插件数据目录，避免重复推送。

## 前置要求

- AstrBot 已启用 `aiocqhttp` 平台适配器。
- NapCat 已连接 AstrBot，且机器人有权限向配置的群或私聊发送消息。
- 插件依赖 `httpx`，安装插件依赖时会读取 `requirements.txt`。

## 配置

在 AstrBot WebUI 的插件配置中填写：

- `enabled`：是否启用插件。
- `poll_interval_seconds`：轮询间隔，最低会按 60 秒执行。
- `language`：消息语言，可选 `zh-TW`、`en`、`ja`、`ko`、`zh`。
- `fetch_limit`：每次拉取数量，运行时限制在 1 到 50。
- `targets`：QQ 推送目标列表。
  - `target_type`：`GroupMessage` 为群聊，`PrivateMessage` 为私聊。
  - `target_id`：群号或 QQ 号。
  - `enabled`：是否启用该目标。
  - `note`：备注。
- `startup_mode`：当前固定为 `mark_seen`，首次启动只记录不推送。

## 消息来源

- 官方板块 ID：`43`
- 列表接口：`https://api.blablalink.com/api/ugc/direct/standalonesite/Dynamics/GetPostList`
- 详情链接格式：`https://www.blablalink.com/post/detail?post_uuid=<post_uuid>`
