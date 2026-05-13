from main import NikkeNewsPlugin
from core.message_builder import MessageBuilder
from core.utils import (
    clean_html_with_linebreaks,
    clean_text,
    format_timestamp,
    safe_int,
)

PLUGIN = NikkeNewsPlugin(context=None, config={})


# ---------------------------------------------------------------------------
# clean_text – HTML stripped
# ---------------------------------------------------------------------------
def test_clean_text_strips_html():
    raw = '1. Follow <span>@NIKKE_en</span> on <a href="https://x.com">X</a>!'
    result = clean_text(raw)
    assert "<span>" not in result
    assert "<a" not in result
    assert "Follow @NIKKE_en on X!" in result


# ---------------------------------------------------------------------------
# clean_text – HTML entities unescaped
# ---------------------------------------------------------------------------
def test_clean_text_unescapes():
    raw = "Hello &amp; welcome &lt;3"
    result = clean_text(raw)
    assert "Hello & welcome <3" in result


# ---------------------------------------------------------------------------
# clean_text – whitespace collapsed
# ---------------------------------------------------------------------------
def test_clean_text_collapse_whitespace():
    raw = "Hello    world\n\nnew  line"
    result = clean_text(raw)
    assert result == "Hello world new line"


# ---------------------------------------------------------------------------
# clean_text – None/empty
# ---------------------------------------------------------------------------
def test_clean_text_none():
    assert clean_text(None) == ""
    assert clean_text("") == ""


# ---------------------------------------------------------------------------
# clean_html_with_linebreaks – block tags preserved
# ---------------------------------------------------------------------------
def test_clean_html_with_linebreaks():
    raw = (
        "<div>Line one</div><div>Line <b>two</b><br>Line three</div>"
        '<div><img src="https://example.com/a.png">After image</div>'
    )
    result = clean_html_with_linebreaks(raw)
    assert result == "Line one\nLine two\nLine three\nAfter image"


# ---------------------------------------------------------------------------
# _format_post_message – full post
# ---------------------------------------------------------------------------
def test_format_post_full():
    plugin = NikkeNewsPlugin(context=None, config={})
    post = {
        "post_uuid": "test-uuid",
        "title": "My Title",
        "content_summary": "This is a summary.",
        "created_on": 1712345678,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert msg.startswith("My Title")
    assert "This is a summary." in msg
    assert "发布时间：" in msg
    assert "链接：" in msg
    assert "test-uuid" in msg


# ---------------------------------------------------------------------------
# _format_post_message – no summary
# ---------------------------------------------------------------------------
def test_format_post_no_summary():
    plugin = NikkeNewsPlugin(context=None, config={})
    post = {
        "post_uuid": "test-uuid",
        "title": "Title Only",
        "content_summary": "",
        "created_on": 0,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert "Title Only" in msg
    assert "发布时间：未知" in msg
    assert "链接：" in msg


# ---------------------------------------------------------------------------
# _format_post_message – summary truncated
# ---------------------------------------------------------------------------
def test_format_post_summary_truncated():
    plugin = NikkeNewsPlugin(context=None, config={})
    long_summary = "X" * 500
    post = {
        "post_uuid": "u",
        "title": "T",
        "content_summary": long_summary,
        "created_on": 1,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert len(msg) < len(long_summary) + 200
    assert "..." in msg


# ---------------------------------------------------------------------------
# _format_post_message – no content
# ---------------------------------------------------------------------------
def test_format_post_content_mode_none():
    plugin = NikkeNewsPlugin(context=None, config={"新闻": {"content_mode": "none"}})
    post = {
        "post_uuid": "u",
        "title": "Title",
        "content_summary": "Summary",
        "content": "<div>Body</div>",
        "created_on": 1,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert "Title" in msg
    assert "Summary" not in msg
    assert "Body" not in msg
    assert "链接：" in msg


# ---------------------------------------------------------------------------
# _format_post_message – content mode preserves linebreaks
# ---------------------------------------------------------------------------
def test_format_post_content_mode_body_preserves_linebreaks():
    plugin = NikkeNewsPlugin(context=None, config={"新闻": {"content_mode": "content"}})
    post = {
        "post_uuid": "u",
        "title": "Title",
        "content_summary": "Summary",
        "content": "<div>First paragraph</div><div>Second<br>line</div>",
        "created_on": 1,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert "Summary" not in msg
    assert "First paragraph\nSecond\nline" in msg


# ---------------------------------------------------------------------------
# _format_post_message – publish time hidden
# ---------------------------------------------------------------------------
def test_format_post_hide_publish_time():
    plugin = NikkeNewsPlugin(
        context=None, config={"新闻": {"show_publish_time": False}}
    )
    post = {
        "post_uuid": "u",
        "title": "Title",
        "content_summary": "Summary",
        "created_on": 1,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert "发布时间：" not in msg
    assert "链接：" in msg


# ---------------------------------------------------------------------------
# _format_post_message – with prefix
# ---------------------------------------------------------------------------
def test_format_post_with_prefix():
    plugin = NikkeNewsPlugin(
        context=None, config={"新闻": {"push_prefix": "【PREFIX】"}}
    )
    post = {
        "post_uuid": "u",
        "title": "Title",
        "content_summary": "Summary",
        "created_on": 1,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert msg.startswith("【PREFIX】")


# ---------------------------------------------------------------------------
# _format_post_message – HTML in title cleaned
# ---------------------------------------------------------------------------
def test_format_post_html_title_cleaned():
    plugin = NikkeNewsPlugin(context=None, config={})
    post = {
        "post_uuid": "u",
        "title": "<b>Bold Title</b>",
        "content_summary": "<i>Italic</i> summary",
        "created_on": 1,
    }
    msg = MessageBuilder(plugin._plugin_config).format_post_message(post)
    assert "<b>" not in msg
    assert "<i>" not in msg
    assert "Bold Title" in msg
    assert "Italic summary" in msg


# ---------------------------------------------------------------------------
# safe_int
# ---------------------------------------------------------------------------
def test_safe_int():
    assert safe_int("123") == 123
    assert safe_int(None) == 0
    assert safe_int("abc") == 0
    assert safe_int(0) == 0
    assert safe_int(-5) == -5


# ---------------------------------------------------------------------------
# format_timestamp
# ---------------------------------------------------------------------------
def test_format_timestamp():
    result = format_timestamp(1712345678)
    assert "2024" in result
    assert "-" in result

    assert format_timestamp(0) == "未知"
    assert format_timestamp(None) == "未知"


# ── post_image_urls ──────────────────────────────────────────────


def test_post_image_urls_non_list():
    plugin = NikkeNewsPlugin(context=None, config={})
    mb = MessageBuilder(plugin._plugin_config)
    urls = mb.post_image_urls({"pic_urls": "oops"})
    assert urls == []


def test_post_image_urls_filters_invalid():
    plugin = NikkeNewsPlugin(context=None, config={})
    mb = MessageBuilder(plugin._plugin_config)
    urls = mb.post_image_urls(
        {"pic_urls": ["http://good.png", "ftp://bad", "", "https://also.good.jpg"]}
    )
    assert urls == ["http://good.png", "https://also.good.jpg"]


def test_post_image_urls_dedup():
    plugin = NikkeNewsPlugin(context=None, config={})
    mb = MessageBuilder(plugin._plugin_config)
    urls = mb.post_image_urls(
        {"pic_urls": ["http://a.png", "http://a.png", "http://b.png"]}
    )
    assert urls == ["http://a.png", "http://b.png"]


def test_post_image_urls_video():
    plugin = NikkeNewsPlugin(context=None, config={})
    mb = MessageBuilder(plugin._plugin_config)
    urls = mb.post_image_urls({"type": 3, "pic_urls": ["http://example.com/a.png"]})
    assert urls == []


def test_post_image_urls_respects_max_images():
    plugin = NikkeNewsPlugin(context=None, config={"新闻": {"max_images": 1}})
    mb = MessageBuilder(plugin._plugin_config)
    urls = mb.post_image_urls({"pic_urls": ["http://a.png", "http://b.png"]})
    assert urls == ["http://a.png"]


# ── format_player_alert_message ──────────────────────────────────


def test_format_player_alert_with_prefix():
    plugin = NikkeNewsPlugin(
        context=None,
        config={"玩家": {"状态提醒": {"alert_prefix": "【提醒】"}}},
    )
    mb = MessageBuilder(plugin._plugin_config)
    msg = mb.format_player_alert_message(["line1", "line2"])
    assert msg.startswith("【提醒】")
    assert "line1" in msg
    assert "line2" in msg


def test_format_player_alert_default_prefix():
    plugin = NikkeNewsPlugin(context=None, config={})
    mb = MessageBuilder(plugin._plugin_config)
    msg = mb.format_player_alert_message(["line1"])
    assert msg.startswith("【NIKKE 玩家状态提醒】")
    assert "line1" in msg
    assert "UTC+8" in msg
