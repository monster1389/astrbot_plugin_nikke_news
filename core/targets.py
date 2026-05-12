from astrbot.api import logger

from .constants import SUPPORTED_TARGET_TYPES


def parse_push_target(value: str) -> dict[str, str] | None:
    if value.isdigit():
        return {"target_type": "GroupMessage", "target_id": value}

    parts = value.split(":")
    if len(parts) == 3 and parts[2].isdigit():
        msg_type = parts[1]
        if msg_type in SUPPORTED_TARGET_TYPES:
            return {"target_type": msg_type, "target_id": parts[2]}

    return None


def enabled_targets(config: dict) -> list[dict[str, str]]:
    enabled: list[dict[str, str]] = []
    group_targets = config.get("scheduled_push_groups", []) or []

    for item in group_targets:
        item_str = str(item or "").strip()
        if not item_str:
            continue
        parsed = parse_push_target(item_str)
        if not parsed:
            logger.warning(f"NIKKE 跳过无效推送目标：{item_str}")
            continue
        enabled.append(parsed)

    if enabled:
        return enabled

    legacy_targets = config.get("targets", []) or []
    for target in legacy_targets:
        if not isinstance(target, dict) or not target.get("enabled", True):
            continue

        target_type = str(target.get("target_type", "")).strip()
        target_id = str(target.get("target_id", "")).strip()
        if target_type not in SUPPORTED_TARGET_TYPES or not target_id:
            logger.warning(f"NIKKE 跳过无效旧版推送目标：{target}")
            continue

        enabled.append({"target_type": target_type, "target_id": target_id})

    return enabled
