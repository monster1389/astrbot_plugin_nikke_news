# CONTEXT.md

本插件的领域词汇表。架构评审、测试命名、接口命名统一用这里的词。

## 工作约定

- 本项目的流程类 skill 走 **mattpocock** 系列（improve-codebase-architecture、grilling、tdd、code-review 等）。
- **不使用 superpowers** 系列 skill，不生成 `docs/superpowers/` 下的 spec/plan 文档。

## 领域词汇

| 词 | 含义 |
|---|---|
| 新闻推送 | 拉取 Blablalink 官方板块新帖，推送到配置的目标群 |
| 玩家提醒 | 前哨基地满仓 + 日常任务完成情况的周期性提醒 |
| 角色查询 | `/nikke` 按角色名查战力、技能等级、装备、T10 词条 |
| 角色映射 | `name_code → 角色名` + 词条 option 元数据 + `name_code → resource_id`，持久化在 `player_mappings_{lang}.json` |
| 头像映射 | `name_code → CDN 头像 URL`，持久化在 `avatar_mappings.json`；图片懒下载到 `avatars/` |
| 技能缓存 | 每角色每语言的技能详情 JSON，持久化在 `skills/{name_code}_{lang}.json`，查询时触发 |
| 轮询 | `PollCoordinator` 每 `poll_interval_seconds` 跑一次新闻 + 玩家 + 缓存刷新 |
| CDN 响应采集 | 拦截 Playwright 网络响应、让出事件循环、逐个吐出解析后 JSON 的机制原语（`CdnResponseCollector`） |

## 机制原语

- `CdnResponseCollector.next()` — 三个 scraper（头像/角色映射/技能）共用的响应采集机制。只负责「拦截 → pending 队列 → `wait_for_timeout` 让出 → pop + `json()` 解析」，停止/stall/判定由调用方决定。
