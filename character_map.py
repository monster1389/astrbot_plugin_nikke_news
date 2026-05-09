import json
from pathlib import Path

import httpx
from astrbot.api import logger


class CharacterMap:
    def __init__(
        self,
        source_path: Path,
        aliases: dict[str, list[str]] | None = None,
    ):
        self._source_path = source_path
        self._name_to_code: dict[str, int] = {}
        self._aliases = aliases or {}

    @property
    def is_loaded(self) -> bool:
        return len(self._name_to_code) > 0

    def load(self) -> bool:
        if not self._source_path.exists():
            logger.warning(f"NIKKE 角色映射文件不存在：{self._source_path}")
            return False
        try:
            data = json.loads(self._source_path.read_text())
            if isinstance(data, dict) and len(data) > 0:
                self._name_to_code = {k: int(v) for k, v in data.items()}
                logger.info(f"NIKKE 角色映射已加载，共 {len(self._name_to_code)} 条。")
                return True
            logger.warning("NIKKE 角色映射文件内容为空或格式无效。")
        except Exception as exc:
            logger.warning(f"NIKKE 角色映射加载失败：{exc}")
        return False

    def save(self) -> None:
        try:
            self._source_path.parent.mkdir(parents=True, exist_ok=True)
            self._source_path.write_text(
                json.dumps(self._name_to_code, ensure_ascii=False, indent=2)
            )
            logger.info(f"NIKKE 角色映射已保存，共 {len(self._name_to_code)} 条。")
        except Exception as exc:
            logger.warning(f"NIKKE 角色映射保存失败：{exc}")

    async def refresh(self, client: httpx.AsyncClient, url: str) -> str:
        logger.info(f"NIKKE 正在从 URL 拉取角色列表：{url}")
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            msg = f"角色列表下载失败：{exc}"
            logger.warning(msg)
            return msg

        if not isinstance(data, list):
            msg = "角色列表格式异常，请检查 URL 是否指向正确的 JSON。"
            logger.warning(msg)
            return msg

        self._name_to_code.clear()
        for item in data:
            name = (item.get("name_localkey") or {}).get("name", "")
            code = item.get("name_code")
            if name and isinstance(code, int):
                self._name_to_code[name] = code

        self.save()
        msg = f"角色列表已刷新，共 {len(self._name_to_code)} 个角色。"
        logger.info(f"NIKKE {msg}")
        return msg

    def _build_alias_map(self) -> dict[str, str]:
        """Reverse the config aliases (EnglishName → [aliases]) into alias → EnglishName."""
        result: dict[str, str] = {}
        for en_name, alias_list in self._aliases.items():
            for alias in alias_list:
                key = alias.strip().lower()
                if key and key not in result:
                    result[key] = en_name
        return result

    def lookup(self, query: str) -> list[tuple[int, str]]:
        if not query or not query.strip():
            return []

        q = query.strip().lower()
        alias_map = self._build_alias_map()

        # 1. 先查配置别名表
        alias_name = alias_map.get(q)
        if alias_name and alias_name in self._name_to_code:
            return [(self._name_to_code[alias_name], alias_name)]

        # 2. 精确匹配英文名（大小写不敏感）
        for name, code in self._name_to_code.items():
            if name.lower() == q:
                return [(code, name)]

        # 3. 子串模糊匹配
        results: list[tuple[int, str]] = []
        for name, code in self._name_to_code.items():
            if q in name.lower():
                results.append((code, name))

        return results
