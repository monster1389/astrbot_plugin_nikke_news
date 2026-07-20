"""推送目标解析：支持纯数字群号和 platform:type:id 格式。"""

from astrbot.api import logger
from astrbot.api.star import StarTools

from .constants import SUPPORTED_TARGET_TYPES


def parse_push_target(value: str) -> dict[str, str] | None:
    """解析目标字符串：纯数字→群号，"platform:type:id"→三元组。"""
    if value.isdigit():
        return {
            "platform": "aiocqhttp",
            "target_type": "GroupMessage",
            "target_id": value,
        }

    parts = value.split(":")
    if len(parts) == 3 and parts[2].isdigit():
        platform, msg_type = parts[0], parts[1]
        if msg_type in SUPPORTED_TARGET_TYPES:
            return {
                "platform": platform,
                "target_type": msg_type,
                "target_id": parts[2],
            }

    return None


def enabled_targets(config: dict) -> list[dict[str, str]]:
    """从配置中提取已启用的推送目标列表。

    兼容新格式（scheduled_push_groups）和旧格式（targets）。

    Args:
        config: 新闻配置子字典。

    Returns:
        [{"platform": ..., "target_type": ..., "target_id": ...}, ...] 列表。
    """
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

        enabled.append(
            {
                "platform": "aiocqhttp",
                "target_type": target_type,
                "target_id": target_id,
            }
        )

    return enabled


async def broadcast_to_targets(
    targets: list[dict[str, str]], chain, label: str
) -> bool:
    """向所有目标群发送消息链，各目标独立容错。

    Args:
        targets: [{"platform": ..., "target_type": ..., "target_id": ...}] 列表。
        chain: AstrBot MessageChain 实例。
        label: 日志标签（如 "新闻"、"玩家提醒"）。

    Returns:
        True 如果至少一个目标发送成功。
    """
    success = False
    for target in targets:
        try:
            session = (
                f"{target['platform']}:{target['target_type']}:{target['target_id']}"
            )
            await StarTools.send_message(session, chain)
            success = True
        except Exception as exc:
            logger.warning(
                f"NIKKE {label}发送失败："
                f"target={target['target_type']}:{target['target_id']} "
                f"type={type(exc).__name__} error={exc}"
            )
    return success
