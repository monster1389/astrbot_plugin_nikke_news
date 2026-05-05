# AGENTS.md

## Architecture

This is an [AstrBot](https://github.com/AstrBotDevs/AstrBot) plugin. The plugin runs inside the AstrBot framework — it is not a standalone app.

- **Entrypoint**: `main.py` — the sole code file
- **Metadata**: `metadata.yaml` — plugin identity (name, version, author, repo)
- **Config schema**: `_conf_schema.json` — declares plugin configuration fields for the AstrBot admin UI
- **Framework SDK**: `astrbot.api.*` (not locally installed; provided by the AstrBot runtime)
- **Runtime deps**: `requirements.txt` — only `httpx>=0.28.1`

## Plugin behavior

This is a **background polling plugin** — it has no user-facing commands. It periodically fetches the latest NIKKE official posts from the Blablalink API and pushes new ones to configured QQ targets via NapCat / aiocqhttp.

- On startup (`initialize()`), it creates a background `asyncio.Task` that loops `_poll_once()` every `poll_interval_seconds` (minimum 60s, default 300s).
- **First poll**: marks all currently available posts as "seen" without pushing anything.
- **Subsequent polls**: detects new posts (by UUID) and pushes them to `scheduled_push_groups`.
- **Per-poll state reload**: `_poll_once()` calls `_load_state()` at the top of every cycle, so manually editing `state.json` takes effect on the next poll without a plugin restart.
- State (seen post UUIDs + initialized flag) is persisted to `data/astrbot_plugin_nikke_news/state.json` via `StarTools.get_data_dir()`.
- `terminate()` cancels the poll task, closes the `httpx.AsyncClient`, and saves state.

### Configuration keys (`_conf_schema.json`)

| Key                      | Type     | Default                        | Notes                                          |
|--------------------------|----------|--------------------------------|------------------------------------------------|
| `enabled`                | bool     | `true`                         | Master switch for the plugin                   |
| `poll_interval_seconds`  | int      | `300`                          | Clamped to >= 60 at runtime                    |
| `language`               | string   | `"zh-TW"`                      | One of: `zh-TW`, `en`, `ja`, `ko`, `zh`       |
| `fetch_limit`            | int      | `10`                           | Posts per API call; clamped 1–50               |
| `content_mode`           | string   | `"summary"`                    | `"none"` (title+link only), `"summary"` (summary), `"content"` (full body with linebreaks) |
| `max_images`             | int      | `3`                            | Max images per push; clamped 0–9; 0 = no images; video posts skipped |
| `show_publish_time`      | bool     | `true`                         | Show publish timestamp in message              |
| `scheduled_push_groups`  | list     | `[]`                           | Group IDs (string) or `platform:type:id` format|
| `startup_mode`           | string   | `"mark_seen"`                  | Currently only "mark_seen" is supported        |
| `push_delay_seconds`     | int      | `2`                            | Delay between posts when pushing multiple; clamped 0–30 |
| `push_prefix`            | string   | `"【NIKKE 官方消息推送】"`      | Prefix prepended to every push message; leave empty for none |

### Push target format

New format (`scheduled_push_groups`) accepts:
- Plain group ID: `"957880653"` → internally treated as `GroupMessage`
- Unified msg origin: `"aiocqhttp:GroupMessage:957880653"`, `"napcat:FriendMessage:2854964693"`, `"napcat:PrivateMessage:999"`

Supported message types: `GroupMessage`, `PrivateMessage`, `FriendMessage`.

Legacy format (`targets`, dictionary-style with `target_type`/`target_id`/`enabled` fields) is supported as a fallback only when `scheduled_push_groups` is empty.

### Message content

- **Text**: title + body (per `content_mode`) + publish time (per `show_publish_time`) + detail link, prefixed by `push_prefix`.
- **Images**: up to `max_images` from the post's `pic_urls` field, loaded via `Comp.Image.fromURL()`. Video posts (`friend_card.type == "video"`) skip images entirely.
- **HTML cleaning**: `<span>`, `<a>`, `<br>` and other tags are stripped; `&amp;` style entities are unescaped; whitespace is collapsed (except in `content` mode where `<br>` becomes linebreaks).

## Key conventions

- The `@register(name, author, desc, version)` decorator in `main.py` and the fields in `metadata.yaml` **must match**. If you change one, update the other.
- The `name` in `metadata.yaml` should follow the `astrbot_plugin_*` prefix convention matching the repo/directory name.
- This plugin has **no `@filter.command(...)` handlers** — it runs entirely as a background task. If you add command handlers in the future, they must be **async generators**: use `yield event.plain_result(...)` to send replies, not `return`.
- Plugin lifecycle: `__init__` → `initialize()` (async) → handlers / poll loop run → `terminate()` (async, on unload/disable).
- Messages are sent via `StarTools.send_message_by_id()`, bypassing the LLM reply pipeline; they are invisible to model context.
- Messages are built as `MessageChain` with `chain.chain.append(Comp.Image.fromURL(...))` for image attachment.

## Data flow

```
[Blablalink API]
      │  POST /Dynamics/GetPostList
      ▼
  main.py::_fetch_official_posts()
      │  filters: plate_id==43, is_official==1
      ▼
  main.py::_poll_once()
      │  _load_state() ← disk (every poll)
      │  diff vs state["seen_post_uuids"]
      ▼
  main.py::_format_post_message_chain()
      │  MessageChain(message + Image.fromURL(pic_urls))
      ▼
  StarTools.send_message_by_id()  →  NapCat / aiocqhttp  →  QQ targets
```

## Development commands

- **Run tests**: `pytest tests/ -v` (requires `pytest pytest-asyncio httpx` in a venv)
- Tests mock the entire AstrBot SDK via `conftest.py` so they run without the framework.
- The AstrBot plugin development docs: <https://docs.astrbot.app/dev/star/plugin-new.html>
