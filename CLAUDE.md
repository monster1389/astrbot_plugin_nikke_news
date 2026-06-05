# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

This is an [AstrBot](https://github.com/AstrBotDevs/AstrBot) plugin — it runs inside the AstrBot framework, not standalone. The framework SDK (`astrbot.api.*`) is provided by the runtime, not installed locally.

**Entrypoint**: `main.py` — `NikkeNewsPlugin(Star)` registered via `@register(...)`. Commands registered via `@filter.command(...)`.

**Packages**:
- `core/` — config, constants, state, targets, time_utils, utils, message_builder, nikke_commands, poll_coordinator
- `news/` — news_client (Blablalink API), news_poller (diff + push)
- `player/` — player_client, player_poller, character_service, character_formatter, player_mapping_cache, player_mapping_refresher, avatar_mapping_cache, avatar_scraper, avatar_service

**Dependencies** (`requirements.txt`): `httpx>=0.28.1`, `playwright>=1.44.0`. Chromium binaries are provided by the runtime Docker image.

**Runtime data**: persisted as JSON files in AstrBot's data directory (`StarTools.get_data_dir()`):
- `state.json` — seen post UUIDs (capped at 500), initialized flag, player alert dedup state
- `player_mappings_{lang}.json` — character name→code mappings and T10 option metadata (version 2, per-language)
- `avatar_mappings.json` — name_code → CDN image URL (version 1, 24h TTL)
- `avatars/` — downloaded `.webp` character avatar images
- `skills/` — cached skill detail JSONs per character per language (`{name_code}_{lang}.json`, TTL)

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

## Key conventions

- The `@register(name, author, desc, version)` decorator in `main.py` and the fields in `metadata.yaml` **must match**. If you change one, update the other.
- Command handlers must be **async generators**: `yield event.plain_result(...)` for text replies, `yield event.chain_result([...])` for mixed content (text + images).
- Messages are sent via `StarTools.send_message_by_id()`, bypassing the LLM reply pipeline.
- Playwright/Chromium is only used for mapping refresh — never put it on the hot path for `/nikke` queries.
- Character query stages: ensure mapping cache → alias lookup → `fetch_characters()` → `fetch_character_details()` → format stats → optionally ensure portrait.
- `/nikke_skill` follows the same character lookup pattern as `/nikke`.
- Equipment T10 options with the same `function_type` are aggregated before display; option values use `abs(function_value) / 100` formatted as percentage.
- Push targets accept plain group IDs (`"957880653"`) or unified format (`"aiocqhttp:GroupMessage:957880653"`). Supported types: `GroupMessage`, `PrivateMessage`, `FriendMessage`.
- Cookie config accepts both structured JSON (new) and raw header string (legacy). Character aliases accept both native dict and JSON string.
- Time helpers use BJT (UTC+8) with a 4am day boundary for player alert dedup.
- `player_mapping_refresher.py` navigates to `https://www.blablalink.com/shiftyspad/nikke-list?type=combat` and intercepts `sg-tools-cdn.blablalink.com` JSON responses via Playwright's response event.
- `avatar_scraper.py` scrapes avatar URLs via two-phase Playwright collection (default + obtained skin), injecting Vue store to expand the virtual list; `avatar_service.py` orchestrates scrape → download → per-request ensure.
