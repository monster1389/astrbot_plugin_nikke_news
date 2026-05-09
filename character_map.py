import hashlib
import json
from pathlib import Path

import httpx
from astrbot.api import logger

_CDN_BASE = "https://sg-tools-cdn.blablalink.com"
_SS = [224737, 1000639, 2654435761, 2654435769, 1000621, 4294967291]
_EN_PATH = "character/en/nikke_list_en_v2.json"

def _tr(path: str, seed: int) -> int:
    n = seed
    for ch in path:
        n = (n * 33 + ord(ch)) & 0xFFFFFFFF
    return n


def _yr(path: str, seed: int) -> str:
    s = _tr(path, seed)
    n = (s % seed + seed) % seed
    o = (n // 26) % 26
    a = n % 26
    return chr(97 + o) + chr(97 + a)


def _or(path: str, seed: int) -> str:
    a = (_tr(path, seed) % seed + seed) % seed
    return str(a % 99).zfill(2)


def _compute_cdn_url(relative_path: str) -> str:
    parts = relative_path.split("/")
    dir_segments = [
        _yr(relative_path, _SS[i]) + "-" + _or(relative_path, _SS[i])
        for i in range(len(parts) - 1)
    ]
    file_hash = hashlib.md5(relative_path.encode()).hexdigest()
    ext = relative_path.rsplit(".", 1)[-1]
    path = "/".join(dir_segments) + "/" + file_hash + "." + ext
    return _CDN_BASE + "/" + path


class CharacterMap:
    def __init__(
        self,
        data_dir: Path,
        client: httpx.AsyncClient | None = None,
        aliases: dict[str, list[str]] | None = None,
    ):
        self._data_dir = data_dir
        self._client = client
        self._cache_path = data_dir / "character_map.json"
        self._name_to_code: dict[str, int] = {}
        self._aliases = aliases or {}

    @property
    def is_loaded(self) -> bool:
        return len(self._name_to_code) > 0

    def load_cache(self) -> bool:
        if not self._cache_path.exists():
            return False
        try:
            data = json.loads(self._cache_path.read_text())
            if isinstance(data, dict) and len(data) > 0:
                self._name_to_code = {k: int(v) for k, v in data.items()}
                logger.info(f"NIKKE 角色映射已从缓存加载，共 {len(self._name_to_code)} 条。")
                return True
        except Exception as exc:
            logger.warning(f"NIKKE 角色映射缓存加载失败：{exc}")
        return False

    def save_cache(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._name_to_code, ensure_ascii=False, indent=2)
            )
            logger.info(f"NIKKE 角色映射已缓存，共 {len(self._name_to_code)} 条。")
        except Exception as exc:
            logger.warning(f"NIKKE 角色映射缓存保存失败：{exc}")

    async def refresh_from_cdn(self) -> str:
        if not self._client:
            msg = "HTTP 客户端未就绪，无法刷新角色数据。"
            logger.warning(msg)
            return msg

        url = _compute_cdn_url(_EN_PATH)
        logger.info(f"NIKKE 正在从 CDN 拉取角色列表：{url}")
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            msg = f"CDN 角色列表下载失败：{exc}"
            logger.warning(msg)
            return msg

        if not isinstance(data, list):
            msg = "CDN 角色列表格式异常，请稍后再试。"
            logger.warning(msg)
            return msg

        self._name_to_code.clear()
        for item in data:
            name = (item.get("name_localkey") or {}).get("name", "")
            code = item.get("name_code")
            if name and isinstance(code, int):
                self._name_to_code[name] = code

        self.save_cache()
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
