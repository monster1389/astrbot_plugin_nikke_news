# 更新日志

## v1.7.1 — 2026-08-16

### 新增
- 角色映射与头像映射后台自动刷新：TTL 过期时在轮询中并发用 Playwright 重新抓取，失败自动锁止并通过推送提示，`/nikke_refresh` 成功后解除
- `/nikke_refresh` 支持 `-c`/`--character`、`-a`/`--avatar` 参数，可只刷角色映射或头像映射
- 英文 + 目标语言角色映射并发刷新，共享同一浏览器实例
- Cookie 校验统一入口（`CookieStatus`），登录态失效时给出明确提示

### 修复
- 修复 Playwright 响应采集的 TargetClosedError 竞态，改为轮询式收集
- 修复浏览器启动失败与退出时的资源清理
- 适配 AstrBot v4.26.7 SDK，`send_message_by_id` 迁移为 `send_message`
- 推送目标解析保留平台前缀，不再硬编码 aiocqhttp
- 补全 `_conf_schema` 各配置项的 hint 字段
- 头像抓取第二阶段等待循环正确排空 pending_responses
- 广播失败时不再把新闻标记为已见，避免漏推
- 若干消息文案修正

### 重构
- 统一 JSON 缓存为 JsonCache 基类；抽取浏览器上下文、CDN 响应采集、角色详情抓取、头像编排等公共原语，消除重复代码
