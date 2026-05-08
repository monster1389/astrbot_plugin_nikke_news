import html
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any


class ReadableHtmlParser(HTMLParser):
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
        raw = html.unescape("".join(self._parts))
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        compact_lines = [line for line in lines if line]
        return "\n".join(compact_lines)


def clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]*>", "", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


def clean_html_with_linebreaks(value: Any) -> str:
    parser = ReadableHtmlParser()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_timestamp(value: Any) -> str:
    timestamp = safe_int(value)
    if timestamp <= 0:
        return "未知"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def is_video_post(post: dict[str, Any]) -> bool:
    return safe_int(post.get("type")) == 3
