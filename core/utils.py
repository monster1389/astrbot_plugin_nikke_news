"""通用工具：HTML 清洗、安全类型转换、时间戳格式化。"""

import html
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any


class ReadableHtmlParser(HTMLParser):
    """HTML 清洗解析器，提取纯文本内容并折叠空白。

    Attributes:
        _parts: 累积的文本片段列表。
        _ignored_depth: 当前忽略标签嵌套深度。
    """

    _BREAK_TAGS = {"br"}
    _BLOCK_TAGS = {"div", "p", "section", "article", "header", "footer", "li"}
    _IGNORED_CONTAINER_TAGS = {"script", "style"}
    _IGNORED_VOID_TAGS = {"img"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        if tag in self._IGNORED_VOID_TAGS:
            return
        if tag in self._IGNORED_CONTAINER_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in self._BREAK_TAGS or tag in self._BLOCK_TAGS:
            self._newline()

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self._IGNORED_CONTAINER_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag in self._BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str):
        if self._ignored_depth:
            return
        self._parts.append(data)

    def handle_entityref(self, name: str):
        if not self._ignored_depth:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str):
        if not self._ignored_depth:
            self._parts.append(f"&#{name};")

    def _newline(self):
        if self._parts and self._parts[-1] != "\n":
            self._parts.append("\n")

    def text(self) -> str:
        """返回清洗后的纯文本，多行去重并折叠空白。

        Returns:
            清洗后的文本字符串。
        """
        raw = html.unescape("".join(self._parts))
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        compact_lines = [line for line in lines if line]
        return "\n".join(compact_lines)


def clean_text(value: Any) -> str:
    """去除 HTML 标签并折叠空白，返回纯文本。

    Args:
        value: 输入值，非字符串会被转为字符串。

    Returns:
        清洗后的单行纯文本。
    """
    text = re.sub(r"<[^>]*>", "", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


def clean_html_with_linebreaks(value: Any) -> str:
    """清理 HTML 标签，保留换行结构。

    Args:
        value: 输入值。

    Returns:
        保留换行的清洗后文本。
    """
    parser = ReadableHtmlParser()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def datetime_is_stale(iso_string: str, ttl_hours: int) -> bool:
    """检查 ISO 时间戳是否超过 TTL 小时数。

    Args:
        iso_string: ISO 格式时间字符串。
        ttl_hours: TTL 小时数。

    Returns:
        True 表示过期、无效或时间戳为空。
    """
    if not iso_string:
        return True
    try:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - dt > timedelta(hours=ttl_hours)


def safe_int(value: Any) -> int:
    """安全转换为 int，失败返回 0。

    Args:
        value: 任意输入值。

    Returns:
        转换后的 int，或 0。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    """安全转换为 float，失败返回 0.0。

    Args:
        value: 任意输入值。

    Returns:
        转换后的 float，或 0.0。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_timestamp(value: Any) -> str:
    """Unix 时间戳转日期字符串。

    Args:
        value: Unix 时间戳。

    Returns:
        YYYY-MM-DD HH:MM 格式字符串，无效时返回"未知"。
    """
    timestamp = safe_int(value)
    if timestamp <= 0:
        return "未知"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def is_video_post(post: dict[str, Any]) -> bool:
    """判断帖子是否为视频类型。

    Args:
        post: 帖子数据 dict。

    Returns:
        True 表示视频帖。
    """
    return safe_int(post.get("type")) == 3


def accept_language(language: str) -> str:
    """根据语言代码返回 Accept-Language 请求头值。

    Args:
        language: 语言代码（en、zh-TW、ja、ko）。

    Returns:
        Accept-Language 头字符串。
    """
    if language == "en":
        return "en-US,en;q=0.9,zh-CN;q=0.6,zh;q=0.5"
    if language == "zh-TW":
        return "zh-TW,zh;q=0.9,en;q=0.6"
    return f"{language};q=1.0,en;q=0.7"


def parse_cookie_pairs(cookie_header: str) -> list[tuple[str, str]]:
    """解析 Cookie 头字符串为 (name, value) 对列表。

    Args:
        cookie_header: "key1=val1; key2=val2" 格式的 Cookie 头。

    Returns:
        (name, value) 元组列表，跳过无效段。
    """
    pairs: list[tuple[str, str]] = []
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            pairs.append((name, value))
    return pairs
