# AGENTS.md

## Architecture

This is an [AstrBot](https://github.com/AstrBotDevs/AstrBot) plugin. The plugin runs inside the AstrBot framework — it is not a standalone app.

- **Entrypoint**: `main.py` — the sole code file
- **Metadata**: `metadata.yaml` — plugin identity (name, version, author, repo)
- **Config schema**: `_conf_schema.json` — declares plugin configuration fields for the AstrBot admin UI
- **Framework SDK**: `astrbot.api.*` (not locally installed; provided by the AstrBot runtime)
- **Runtime deps**: `requirements.txt` — only `httpx>=0.28.1`

## Plugin behavior

This is a **background polling plugin** — it has no user-facing commands. It periodically fetches the latest NIKKE official posts from the Blablalink API and pushes new ones to configured QQ groups via NapCat / aiocqhttp.

- On startup (`initialize()`), it creates a background `asyncio.Task` that loops `_poll_once()` every `poll_interval_seconds` (minimum 60s, default 300s).
- **First poll**: marks all currently available posts as "seen" without pushing anything.
- **Subsequent polls**: detects new posts (by UUID) and pushes them to `scheduled_push_groups`.
- State (seen post UUIDs + initialized flag) is persisted to `data/astrbot_plugin_nikke_news/state.json` via `StarTools.get_data_dir()`.
- `terminate()` cancels the poll task, closes the `httpx.AsyncClient`, and saves state.

### Configuration keys (`_conf_schema.json`)

| Key                      | Type     | Default     | Notes                                          |
|--------------------------|----------|-------------|------------------------------------------------|
| `enabled`                | bool     | `true`      | Master switch for the plugin                   |
| `poll_interval_seconds`  | int      | `300`       | Clamped to >= 60 at runtime                    |
| `language`               | string   | `"zh-TW"`   | One of: `zh-TW`, `en`, `ja`, `ko`, `zh`       |
| `fetch_limit`            | int      | `10`        | Posts per API call; clamped 1–50               |
| `scheduled_push_groups`  | list     | `[]`        | Group IDs (string) or `platform:type:id` format|
| `startup_mode`           | string   | `"mark_seen"` | Currently only "mark_seen" is supported       |

### Push target format

New format (`scheduled_push_groups`) accepts:
- Plain group ID: `"957880653"` → internally treated as `GroupMessage`
- Unified msg origin: `"aiocqhttp:GroupMessage:957880653"`

Legacy format (`targets`, dictionary-style with `target_type`/`target_id`/`enabled` fields) is supported as a fallback only when `scheduled_push_groups` is empty.

## Key conventions

- The `@register(name, author, desc, version)` decorator in `main.py` and the fields in `metadata.yaml` **must match**. If you change one, update the other.
- The `name` in `metadata.yaml` should follow the `astrbot_plugin_*` prefix convention matching the repo/directory name.
- This plugin has **no `@filter.command(...)` handlers** — it runs entirely as a background task. If you add command handlers in the future, they must be **async generators**: use `yield event.plain_result(...)` to send replies, not `return`.
- Plugin lifecycle: `__init__` → `initialize()` (async) → handlers / poll loop run → `terminate()` (async, on unload/disable).

## Data flow

```
[Blablalink API]
      │  POST /Dynamics/GetPostList
      ▼
  main.py::_fetch_official_posts()
      │  filters: plate_id==43, is_official==1
      ▼
  main.py::_poll_once()
      │  diff vs state["seen_post_uuids"]
      ▼
  StarTools.send_message_by_id()  →  NapCat / aiocqhttp  →  QQ groups
```

## Development commands

- **Run tests**: `pytest tests/ -v` (requires `pytest pytest-asyncio httpx` in a venv)
- Tests mock the entire AstrBot SDK via `conftest.py` so they run without the framework.
- The AstrBot plugin development docs: <https://docs.astrbot.app/dev/star/plugin-new.html>
