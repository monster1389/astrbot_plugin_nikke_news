"""NIKKE 指令业务逻辑（不含 AstrBot 装饰器）。"""

import time

from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp

from player.character_service import CharacterQueryError


def _parse_refresh_args(text: str) -> tuple[bool, bool]:
    """解析 /nikke_refresh 参数，返回 (character_only, avatar_only)。"""
    arg = text.strip().lower()
    if arg in ("-c", "--character"):
        return True, False
    if arg in ("-a", "--avatar"):
        return False, True
    return False, False


def _clear_refresh_failed(plugin):
    """清除所有刷新失败锁。"""
    state = plugin._state.setdefault("player_alert_state", {})
    changed = False
    for key in ("char_refresh_failed", "avatar_refresh_failed"):
        if state.get(key):
            state[key] = False
            changed = True
    if changed:
        plugin._save_state()


HELP_TEXT = (
    "NIKKE 插件命令列表\n\n"
    "/nikke <角色名>  查询角色战力、技能、装备\n"
    "/nikke_skill <角色名>  查询角色技能详细描述\n"
    "/nikke_refresh [-c|-a]  刷新角色映射和已缓存头像\n"
    "/nikke_avatar_all  刷新头像映射并下载全部头像\n"
    "/nikke_help  显示本帮助"
)


def _recover_full_query(event: AstrMessageEvent) -> str:
    """从原始消息中提取 /nikke 后的角色名（处理多词查询）。"""
    msg = event.message_str.strip()
    for prefix in ("/nikke ", "nikke "):
        if msg.startswith(prefix):
            return msg[len(prefix) :]
    return ""


def handle_help() -> str:
    """返回 /nikke_help 帮助文本。"""
    return HELP_TEXT


async def handle_query(plugin, event: AstrMessageEvent, text: str = ""):
    """处理 /nikke <角色名> 角色查询。

    执行流程：参数提取 → 映射过期自动刷新 → 角色查找 → API 调用 →
    格式化结果 → 按需下载头像 → 组装回复。

    Args:
        plugin: NikkeNewsPlugin 实例。
        event: AstrBot 消息事件。
        text: 命令行参数文本。

    Yields:
        AstrBot plain_result 或 chain_result 消息。
    """
    if not text or not text.strip():
        text = _recover_full_query(event)
    else:
        full = _recover_full_query(event)
        if full and full != text:
            text = full

    if not text or not text.strip():
        yield event.plain_result("请提供角色名，例如：/nikke anis")
        return

    if not plugin._character_service:
        yield event.plain_result("角色服务未初始化，请等待插件启动完成。")
        return

    try:
        result_text, name_code = await plugin._character_service.query(text)

        if plugin._plugin_config.show_character_avatar() and plugin._avatar_service:
            path = plugin._avatar_service.avatar_path(name_code)
            if path and path.exists():
                chain = [
                    Comp.Image.fromFileSystem(str(path)),
                    Comp.Plain(result_text),
                ]
                yield event.chain_result(chain)
                return

            cookie = plugin._plugin_config.player_data_cookie()
            if cookie:
                if (
                    not plugin._avatar_service.exists(name_code)
                    and plugin._avatar_service.is_mapping_stale()
                ):
                    yield event.plain_result("正在刷新头像映射（约 20-30s）...")
                downloaded = await plugin._avatar_service.ensure_avatar(
                    name_code, cookie
                )
                if downloaded:
                    path = plugin._avatar_service.avatar_path(name_code)
                    if path and path.exists():
                        chain = [
                            Comp.Image.fromFileSystem(str(path)),
                            Comp.Plain(result_text),
                        ]
                        yield event.chain_result(chain)
                        return

            yield event.plain_result(
                result_text
                + "\n\n（未找到角色头像，请执行 /nikke_avatar_all 下载头像缓存。）"
            )
            return

        yield event.plain_result(result_text)
    except CharacterQueryError as exc:
        yield event.plain_result(exc.message)


async def handle_refresh(plugin, event: AstrMessageEvent, text: str = ""):
    """处理 /nikke_refresh 刷新角色映射和/或头像映射。

    支持 -c/--character（仅角色映射）、-a/--avatar（仅头像），
    无参数则并发刷新两者。

    Args:
        plugin: NikkeNewsPlugin 实例。
        event: AstrBot 消息事件。
        text: 命令行参数文本。

    Yields:
        AstrBot plain_result 进度消息。
    """
    char_only, avatar_only = _parse_refresh_args(text)

    if not plugin._character_service:
        yield event.plain_result("角色服务模块未初始化。")
        return

    if not plugin._player_poller:
        yield event.plain_result("玩家服务未初始化。")
        return

    need_cookie = avatar_only or (not char_only and not avatar_only)
    if need_cookie:
        from core.cookie_status import CookieStatus

        status = plugin._player_poller.cookie_status()
        if status == CookieStatus.DISABLED:
            yield event.plain_result("玩家数据功能未启用，请在插件配置中启用。")
            return
        if status == CookieStatus.EMPTY:
            yield event.plain_result(
                "未配置玩家 Cookie，请先在插件配置中设置玩家状态提醒的 Cookie。"
            )
            return
        if status == CookieStatus.INVALID:
            yield event.plain_result("登录态已失效，请更新 player_data_cookie。")
            return

    t0 = time.monotonic()

    if char_only:
        yield event.plain_result("正在刷新角色映射（约 20-30s）...")
        msg, _ = await plugin._character_service.refresh_mappings(force=True)
        elapsed = time.monotonic() - t0
        yield event.plain_result(f"{msg}\n总耗时 {elapsed:.0f}s")
        _clear_refresh_failed(plugin)
        return

    if avatar_only:
        yield event.plain_result("正在刷新头像映射（约 20-30s）...")
        cookie = plugin._plugin_config.player_data_cookie()
        msg, _ = await plugin._avatar_service.refresh_cached(cookie, force=True)
        elapsed = time.monotonic() - t0
        yield event.plain_result(f"{msg}\n总耗时 {elapsed:.0f}s")
        _clear_refresh_failed(plugin)
        return

    yield event.plain_result("正在刷新角色映射和头像映射（约 20-30s）...")
    result = await plugin._cache_refresher.refresh(force=True)
    if result is None:
        yield event.plain_result("刷新失败：Cookie 不可用或正在刷新中。")
        return
    msg, _, _ = result
    yield event.plain_result(msg)
    _clear_refresh_failed(plugin)


async def handle_avatar_refresh_all(plugin, event: AstrMessageEvent):
    """处理 /nikke_avatar_all 刷新头像映射并下载全部头像。

    Args:
        plugin: NikkeNewsPlugin 实例。
        event: AstrBot 消息事件。

    Yields:
        AstrBot plain_result 消息。
    """
    if not plugin._avatar_service:
        yield event.plain_result("头像服务未初始化。")
        return
    cookie = plugin._plugin_config.player_data_cookie()
    if not cookie:
        yield event.plain_result(
            "未配置玩家 Cookie，无法获取角色头像。"
            "请先在插件配置中设置玩家状态提醒的 Cookie。"
        )
        return
    yield event.plain_result("正在抓取角色头像列表并下载全部头像（首次约需 20-30s）...")
    msg = await plugin._avatar_service.refresh_all(cookie)
    yield event.plain_result(msg)


def _recover_skill_query(event: AstrMessageEvent) -> str:
    """从原始消息中提取 /nikke_skill 后的角色名。"""
    msg = event.message_str.strip()
    for prefix in ("/nikke_skill ", "nikke_skill "):
        if msg.startswith(prefix):
            return msg[len(prefix) :]
    return ""


async def handle_skill(plugin, event: AstrMessageEvent, text: str = ""):
    """处理 /nikke_skill <角色名> 技能查询。

    执行流程：参数提取 → 映射检查 → 角色查找 → 技能获取（缓存/抓取）
    → API 查等级 → 格式化输出。

    Args:
        plugin: NikkeNewsPlugin 实例。
        event: AstrBot 消息事件。
        text: 命令行参数文本。

    Yields:
        AstrBot plain_result 消息。
    """
    if not text or not text.strip():
        text = _recover_skill_query(event)
    else:
        full = _recover_skill_query(event)
        if full and full != text:
            text = full

    if not text or not text.strip():
        yield event.plain_result("请提供角色名，例如：/nikke_skill anis")
        return

    if not plugin._character_service:
        yield event.plain_result("角色服务未初始化，请等待插件启动完成。")
        return

    if not plugin._skill_service:
        yield event.plain_result("技能服务未初始化。")
        return

    cookie = plugin._plugin_config.player_data_cookie()
    if not cookie:
        yield event.plain_result(
            "未配置玩家 Cookie，无法查询角色技能。"
            "请先在插件配置中设置玩家状态提醒的 Cookie。"
        )
        return

    try:
        matches = plugin._character_service.lookup(text)
        if not matches:
            yield event.plain_result(f"未找到角色「{text}」，请检查名称是否正确。")
            return

        if len(matches) > 1:
            names = "、".join(f"「{n}」" for _, n in matches[:10])
            hint = "\n请提供更精确的名称。" if len(matches) > 10 else ""
            yield event.plain_result(f"找到 {len(matches)} 个匹配：\n{names}{hint}")
            return

        name_code, display_name = matches[0]

        if not plugin._skill_service.is_cached(name_code):
            yield event.plain_result("正在获取技能数据，预计 10 秒...")

        area_id = plugin._plugin_config.player_data_area_id()
        language = plugin._plugin_config.player_mapping_language()
        game_id = plugin._plugin_config.player_game_id()

        result_text = await plugin._skill_service.get_skill_text(
            cookie=cookie,
            name_code=name_code,
            display_name=display_name,
            area_id=area_id,
            language=language,
            game_id=game_id,
        )

        yield event.plain_result(result_text)

    except Exception as exc:
        from player.skill_service import SkillError

        if isinstance(exc, CharacterQueryError):
            yield event.plain_result(exc.message)
        elif isinstance(exc, SkillError):
            yield event.plain_result(exc.message)
        else:
            yield event.plain_result(f"技能查询失败：{exc}")
