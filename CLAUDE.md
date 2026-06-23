# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

This is an [AstrBot](https://github.com/AstrBotDevs/AstrBot) plugin — it runs inside the AstrBot framework, not standalone. The framework SDK (`astrbot.api.*`) is provided by the runtime, not installed locally.

**Entrypoint**: `main.py` — `NikkeNewsPlugin(Star)` registered via `@register(...)`. Commands registered via `@filter.command(...)`.

**Packages**:
- `core/` — config, constants, state, targets, time_utils, utils, message_builder, nikke_commands, poll_coordinator, cache_refresher, cookie_status
- `news/` — news_client (Blablalink API), news_poller (diff + push)
- `player/` — player_client, player_poller, character_service, character_formatter, player_mapping_cache, player_mapping_refresher, avatar_mapping_cache, avatar_scraper, avatar_service

**Dependencies** (`requirements.txt`): `httpx>=0.28.1`, `playwright>=1.44.0`. Chromium binaries are provided by the runtime Docker image.

**Runtime data**: persisted as JSON files in AstrBot's data directory (`StarTools.get_data_dir()`):
- `state.json` — seen post UUIDs (capped at 500), initialized flag, player alert dedup state (cookie_invalid_notified, char_refresh_failed, avatar_refresh_failed, day keys)
- `player_mappings_{lang}.json` — character name→code mappings and T10 option metadata (version 2, per-language)
- `avatar_mappings.json` — name_code → CDN image URL (version 1, TTL 同 mapping_cache_ttl_hours)
- `avatars/` — downloaded `.webp` character avatar images
- `skills/` — cached skill detail JSONs per character per language (`{name_code}_{lang}.json`, TTL 同 mapping_cache_ttl_hours)

## Commands

```bash
# Run all tests (uses venv)
.venv/bin/python -m pytest tests/ -v

# Run a single test file
.venv/bin/python -m pytest tests/test_character_service.py -v

# Run a single test file
.venv/bin/python -m pytest tests/test_skill_service.py -v

# Lint
.venv/bin/ruff check .

# Format
.venv/bin/ruff format .
```

Tests mock the entire AstrBot SDK surface in `tests/conftest.py` so they run without the framework. `AstrBotConfig` is aliased to `dict`. Sent messages are captured in a global `_SENT_MESSAGES` list via a recording `StarTools.send_message_by_id`.

## Plugin lifecycle and key behaviors

1. `__init__` → `initialize()` (async) → poll loop / commands → `terminate()` (async, on unload/disable)
2. `initialize()` creates an `asyncio.Task` running `PollCoordinator.run()` every `poll_interval_seconds` (min 60s, default 300s)
3. **First poll**: marks all currently available posts as "seen" without pushing
4. **Per-poll state reload**: `_poll_once()` calls `_load_state()` at the top of every cycle, so manual edits to `state.json` take effect without restart
5. `terminate()` cancels the poll task, closes `httpx.AsyncClient`, saves state
6. News and player poll failures are independently caught — one failure doesn't block the other
7. **Per-poll cache refresh**: `_poll_once()` runs `CacheRefresher.refresh(force=False)` after player poll — TTL-expired character + avatar mappings get concurrently refreshed via Playwright. Refresh failures set independent `char_refresh_failed` / `avatar_refresh_failed` locks (no further attempts for that component until `/nikke_refresh` succeeds). `refresh_cached()` checks `is_mapping_stale()` and skips when fresh.

## Cache TTL

只有一个可配置 TTL：`player.mapping_cache_ttl_hours`（默认 168h = 7 天，下限 1h），复用于三类缓存。过期判断统一走 `core/utils.py:datetime_is_stale()`，比较 `updated_at` 与当前 UTC 时间。

| 缓存 | 刷新触发方式 |
|---|---|
| 角色映射 `player_mappings_{lang}.json` | **poll 后台并发自动刷新** — `PollCoordinator` 每轮通过 `CacheRefresher.refresh(force=False)` 检查 TTL，过期时用 `asyncio.gather` 并发 Playwright 重新抓取。失败后推送并锁止，`/nikke_refresh` 成功解除 |
| 头像映射 `avatar_mappings.json` | **poll 后台并发自动刷新** — 同上，与角色映射并发。`refresh_cached()` 先检查 `is_mapping_stale()`，未过期静默跳过。只刷新 URL 映射不下载图片，图片仍为查询时 lazy download |
| 技能缓存 `skills/{name_code}_{lang}.json` | **查询触发** — `/nikke_skill` 时，`skill_service._load_cache()` 发现过期则抓取该角色技能并缓存 |

## Key conventions

- The `@register(name, author, desc, version)` decorator in `main.py` and the fields in `metadata.yaml` **must match**. If you change one, update the other.
- Command handlers must be **async generators**: `yield event.plain_result(...)` for text replies, `yield event.chain_result([...])` for mixed content (text + images).
- Messages are sent via `StarTools.send_message_by_id()`, bypassing the LLM reply pipeline.
- Playwright/Chromium is only used for mapping refresh — never put it on the hot path for `/nikke` queries.
- Character query stages: load caches from disk → alias lookup → `fetch_characters()` → `fetch_character_details()` → format stats → optionally ensure portrait. No auto-refresh blocking — poll keeps caches fresh in background.
- `/nikke_skill` follows the same character lookup pattern as `/nikke`.
- Equipment T10 options with the same `function_type` are aggregated before display; option values use `abs(function_value) / 100` formatted as percentage.
- Push targets accept plain group IDs (`"957880653"`) or unified format (`"aiocqhttp:GroupMessage:957880653"`). Supported types: `GroupMessage`, `PrivateMessage`, `FriendMessage`.
- Cookie config accepts both structured JSON (new) and raw header string (legacy). Character aliases accept both native dict and JSON string.
- Time helpers use BJT (UTC+8) with a 4am day boundary for player alert dedup.
- `player_mapping_refresher.py` navigates to `https://www.blablalink.com/shiftyspad/nikke-list?type=combat` and intercepts `sg-tools-cdn.blablalink.com` JSON responses via Playwright's response event.
- `avatar_scraper.py` scrapes avatar URLs via two-phase Playwright collection (default + obtained skin), injecting Vue store to expand the virtual list; `avatar_service.py` orchestrates scrape → download → per-request ensure.
- `/nikke_refresh` 支持参数：`-c`/`--character` 只刷角色映射，`-a`/`--avatar` 只刷头像映射，无参数全刷
- Cookie 校验统一入口 `PlayerPoller.cookie_status()`，返回 `CookieStatus` 枚举
- `CacheRefresher` 负责 poll 后台缓存刷新调度
- 映射刷新失败后通过 `char_refresh_failed` / `avatar_refresh_failed` 状态分别锁止，`/nikke_refresh`（含 `-c`/`-a`）成功解除
- `refresh_mappings()` 和 `refresh_cached()` 返回 `(消息文本, 是否失败)` 元组；`CacheRefresher.refresh()` 返回 `(消息文本, 角色是否失败, 头像是否失败)` 或 None。均无内部重试。
