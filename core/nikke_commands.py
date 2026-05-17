"""NIKKE 指令业务逻辑（不含 AstrBot 装饰器）。"""

from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp

from player.character_service import CharacterQueryError

HELP_TEXT = (
    "NIKKE 插件命令列表\n\n"
    "/nikke <角色名>  查询角色战力、技能、装备\n"
    "/nikke_refresh  刷新角色映射和已缓存头像\n"
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
    """处理 /nikke <角色名> 角色查询。"""
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

    if plugin._plugin_config.player_auto_refresh_mapping() and plugin._character_service.is_mapping_stale():
        yield event.plain_result("正在刷新角色映射（约 10-15s）...")

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


async def handle_refresh(plugin, event: AstrMessageEvent):
    """处理 /nikke_refresh 刷新角色映射和头像映射。"""
    if not plugin._character_service:
        yield event.plain_result("角色服务模块未初始化。")
        return

    messages: list[str] = []
    plugin._character_service._load_caches()
    count = plugin._character_service.count()
    messages.append(
        f"已重载本地角色列表，共 {count} 个角色。"
        if count
        else "本地角色列表加载失败，请执行 /nikke_refresh 刷新。"
    )

    yield event.plain_result("正在刷新角色映射（约 10-15s）...")
    messages.append(await plugin._character_service.refresh_mappings(force=True))

    # 刷新头像映射和已缓存头像
    if plugin._avatar_service:
        cookie = plugin._plugin_config.player_data_cookie()
        if cookie:
            if plugin._avatar_service.is_mapping_stale():
                yield event.plain_result("正在刷新头像映射（约 20-30s）...")
            msg = await plugin._avatar_service.refresh_cached(cookie)
            messages.append(msg)
        else:
            messages.append("未配置玩家 Cookie，跳过头像刷新。")
    else:
        messages.append("头像服务未初始化，跳过头像刷新。")

    yield event.plain_result("\n".join(messages))


async def handle_avatar_refresh_all(plugin, event: AstrMessageEvent):
    """处理 /nikke_avatar_all 刷新头像映射并下载全部头像。"""
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
