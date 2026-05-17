"""角色战力、技能、装备数据文本格式化。"""

from typing import Any

from core.utils import safe_float, safe_int


def format_character_stats(
    char_info: dict[str, Any],
    char_detail: dict[str, Any],
    name_map: dict[str, str],
    state_effects: list[dict[str, Any]] | None = None,
    state_effect_options: dict[str, dict[str, Any]] | None = None,
) -> str:
    """格式化角色战斗力、技能、装备及 T10 词条表格文本。"""
    en_name = name_map.get("en", "")
    zh_name = name_map.get("zh", "")

    name_line = en_name
    if zh_name and zh_name != en_name:
        name_line += f"（{zh_name}）"

    combat = char_info.get("combat", "?")

    skill1 = str(
        safe_int(char_detail.get("skill1_lv", char_detail.get("s1_lv", "?")))
    )
    skill2 = str(
        safe_int(char_detail.get("skill2_lv", char_detail.get("s2_lv", "?")))
    )
    burst = str(
        safe_int(
            char_detail.get(
                "ulti_skill_lv",
                char_detail.get(
                    "burst_skill_lv",
                    char_detail.get("skill3_lv", char_detail.get("s3_lv", "?")),
                ),
            )
        )
    )
    skills = f"{skill1}/{skill2}/{burst}"

    head_lv = safe_int(char_detail.get("head_equip_lv", 0))
    arm_lv = safe_int(char_detail.get("arm_equip_lv", 0))
    torso_lv = safe_int(char_detail.get("torso_equip_lv", 0))
    leg_lv = safe_int(char_detail.get("leg_equip_lv", 0))
    equips = f"{head_lv}/{arm_lv}/{torso_lv}/{leg_lv}"

    option_lines = _extract_equip_options(
        char_detail, state_effects or [], state_effect_options or {}
    )

    lines = [
        name_line,
        f"Power: {combat}",
        f"Skills: {skills}",
        f"Equipments: {equips}",
    ]
    lines.extend(option_lines)

    return "\n".join(lines)


def _extract_equip_options(
    char_detail: dict[str, Any],
    state_effects: list[dict[str, Any]],
    state_effect_options: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """从角色详情提取四部位 T10 词条，同 function_type 聚合。"""
    effect_map: dict[str, dict[str, Any]] = {}
    for se in state_effects:
        sid = str(se.get("id", ""))
        if sid:
            effect_map[sid] = se

    option_meta = state_effect_options or {}
    entries: dict[str, dict[str, Any]] = {}
    loose_lines: list[str] = []
    slots = ["head", "arm", "torso", "leg"]
    for slot in slots:
        for idx in (1, 2, 3):
            key = f"{slot}_equip_option{idx}_id"
            opt_id = str(char_detail.get(key, "") or "")
            if not opt_id or opt_id == "0":
                continue
            se = effect_map.get(opt_id)
            meta = option_meta.get(opt_id, {})
            if not se:
                text = str(meta.get("description", "") or "").strip()
                if text:
                    loose_lines.append(text)
                continue

            details = se.get("function_details")
            if not isinstance(details, list) or not details:
                details = [se]

            for detail in details:
                if not isinstance(detail, dict):
                    continue
                function_type = str(
                    detail.get("function_type", meta.get("function_type", ""))
                    or f"{slot}_{idx}_{opt_id}"
                )
                text = _option_description(detail, se, meta)
                raw_value = detail.get(
                    "function_value", se.get("function_value", detail.get("value", 0))
                )
                value = safe_float(raw_value)
                if not text:
                    continue
                if function_type in entries:
                    entries[function_type]["value"] += abs(value)
                    entries[function_type]["level"] = max(
                        entries[function_type]["level"],
                        safe_int(detail.get("level", 0)),
                    )
                    continue
                entries[function_type] = {
                    "text": text,
                    "value": abs(value),
                    "level": safe_int(detail.get("level", 0)),
                    "group_id": safe_int(
                        detail.get("group_id", meta.get("group_id", 0))
                    ),
                    "function_type": function_type,
                }

    sorted_entries = sorted(
        entries.values(),
        key=lambda item: (
            _OPTION_PRIORITY.get(str(item["function_type"]), 999),
            item["group_id"],
            item["text"],
        ),
    )
    lines = [
        f"{entry['text']}: {_format_option_value(entry['value'])}"
        for entry in sorted_entries
    ]
    lines.extend(loose_lines)

    return lines


def _option_description(
    detail: dict[str, Any], state_effect: dict[str, Any], meta: dict[str, Any]
) -> str:
    """从多个字段按优先级提取词条描述文本。"""
    for value in (
        meta.get("description"),
        detail.get("name_localvalues"),
        state_effect.get("function_description"),
        state_effect.get("text"),
        detail.get("function_description"),
        detail.get("text"),
        detail.get("function_type"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _format_option_value(raw_value: float) -> str:
    """将原始值格式化为百分比字符串（value / 100）。"""
    return f"{raw_value / 100:.2f}%"


_OPTION_PRIORITY = {
    "IncElementDmg": 0,
    "StatAtk": 1,
    "StatAmmoLoad": 2,
    "StatAmmo": 2,
    "StatChargeTime": 3,
    "StatChargeDamage": 4,
    "StatAccuracyCircle": 5,
    "OnHitRatio": 5,
    "StatCritical": 6,
    "StatCriticalDamage": 7,
    "StatDef": 8,
}
