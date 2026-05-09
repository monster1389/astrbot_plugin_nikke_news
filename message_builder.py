from datetime import datetime
from typing import Any

from astrbot.api.event import MessageChain
import astrbot.api.message_components as Comp

from config import PluginConfig
from constants import CST, POST_DETAIL_URL, SUMMARY_MAX_LENGTH
from utils import clean_html_with_linebreaks, clean_text, format_timestamp, is_video_post


class MessageBuilder:
    def __init__(self, config: PluginConfig):
        self._config = config

    def format_post_message(self, post: dict[str, Any]) -> str:
        title = clean_text(post.get("title")) or "NIKKE 官方消息"
        body = self._format_post_body(post)

        created_on = format_timestamp(post.get("created_on"))
        detail_url = POST_DETAIL_URL.format(post_uuid=post.get("post_uuid"))

        prefix = self._config.push_prefix()
        parts = [prefix, title] if prefix else [title]
        if body:
            parts.append(body)
        if self._config.show_publish_time():
            parts.append(f"发布时间：{created_on}")
        parts.append(f"链接：{detail_url}")
        return "\n\n".join(parts)

    def format_post_message_chain(self, post: dict[str, Any]) -> MessageChain:
        chain = MessageChain().message(self.format_post_message(post))
        for image_url in self.post_image_urls(post):
            chain.chain.append(Comp.Image.fromURL(image_url))
        return chain

    def _format_post_body(self, post: dict[str, Any]) -> str:
        mode = self._config.content_mode()
        if mode == "none":
            return ""

        if mode == "content":
            return clean_html_with_linebreaks(post.get("content"))

        summary = clean_text(post.get("content_summary"))
        if len(summary) > SUMMARY_MAX_LENGTH:
            summary = summary[:SUMMARY_MAX_LENGTH].rstrip() + "..."
        return summary

    def post_image_urls(self, post: dict[str, Any]) -> list[str]:
        if is_video_post(post):
            return []

        max_images = self._config.max_images()
        if max_images <= 0:
            return []

        pic_urls = post.get("pic_urls", [])
        if not isinstance(pic_urls, list):
            return []

        urls: list[str] = []
        for value in pic_urls:
            url = str(value or "").strip()
            if not url.startswith(("http://", "https://")) or url in urls:
                continue
            urls.append(url)
            if len(urls) >= max_images:
                break
        return urls

    def format_player_alert_message(self, lines: list[str]) -> str:
        prefix = self._config.player_alert_prefix()
        parts = [prefix] if prefix else []
        parts.extend(lines)
        parts.append(f"时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M')} (UTC+8)")
        return "\n\n".join(parts)

    @staticmethod
    def format_character_stats(
        char_info: dict[str, Any],
        char_detail: dict[str, Any],
        name_map: dict[str, str],
        state_effects: list[dict[str, Any]] | None = None,
    ) -> str:
        en_name = name_map.get("en", "")
        zh_name = name_map.get("zh", "")

        name_line = en_name
        if zh_name and zh_name != en_name:
            name_line += f"（{zh_name}）"

        combat = char_info.get("combat", "?")

        skill1 = str(_safe_int(char_detail.get("skill1_lv", char_detail.get("s1_lv", "?"))))
        skill2 = str(_safe_int(char_detail.get("skill2_lv", char_detail.get("s2_lv", "?"))))
        burst = str(_safe_int(
            char_detail.get("burst_skill_lv",
            char_detail.get("skill3_lv",
            char_detail.get("s3_lv", "?")))
        ))
        skills = f"{skill1}/{skill2}/{burst}"

        head_lv = _safe_int(char_detail.get("head_equip_lv", 0))
        arm_lv = _safe_int(char_detail.get("arm_equip_lv", 0))
        torso_lv = _safe_int(char_detail.get("torso_equip_lv", 0))
        leg_lv = _safe_int(char_detail.get("leg_equip_lv", 0))
        equips = f"{head_lv}/{arm_lv}/{torso_lv}/{leg_lv}"

        option_lines = _extract_equip_options(char_detail, state_effects or [])

        lines = [name_line, f"Power: {combat}", f"Skills: {skills}", f"Equipments: {equips}"]
        lines.extend(option_lines)

        return "\n".join(lines)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_equip_options(
    char_detail: dict[str, Any], state_effects: list[dict[str, Any]]
) -> list[str]:
    effect_map: dict[str, dict[str, Any]] = {}
    for se in state_effects:
        sid = str(se.get("id", ""))
        if sid:
            effect_map[sid] = se

    lines: list[str] = []
    slots = ["head", "arm", "torso", "leg"]
    for slot in slots:
        for idx in (1, 2, 3):
            key = f"{slot}_equip_option{idx}_id"
            opt_id = str(char_detail.get(key, "") or "")
            if not opt_id or opt_id == "0":
                continue
            se = effect_map.get(opt_id)
            if se:
                text = se.get("function_description", se.get("text", ""))
                value = se.get("function_value", se.get("value", ""))
                if text:
                    line = str(text)
                    if value:
                        line += f": {value}"
                    lines.append(line)

    return lines
