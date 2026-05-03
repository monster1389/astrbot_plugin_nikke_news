from main import NikkeNewsPlugin

PLUGIN = NikkeNewsPlugin(context=None, config={})


# ---------------------------------------------------------------------------
# _clean_text – HTML stripped
# ---------------------------------------------------------------------------
def test_clean_text_strips_html():
    raw = '1. Follow <span>@NIKKE_en</span> on <a href="https://x.com">X</a>!'
    result = PLUGIN._clean_text(raw)
    assert "<span>" not in result
    assert "<a" not in result
    assert "Follow @NIKKE_en on X!" in result


# ---------------------------------------------------------------------------
# _clean_text – HTML entities unescaped
# ---------------------------------------------------------------------------
def test_clean_text_unescapes():
    raw = "Hello &amp; welcome &lt;3"
    result = PLUGIN._clean_text(raw)
    assert "Hello & welcome <3" in result


# ---------------------------------------------------------------------------
# _clean_text – whitespace collapsed
# ---------------------------------------------------------------------------
def test_clean_text_collapse_whitespace():
    raw = "Hello    world\n\nnew  line"
    result = PLUGIN._clean_text(raw)
    assert result == "Hello world new line"


# ---------------------------------------------------------------------------
# _clean_text – None/empty
# ---------------------------------------------------------------------------
def test_clean_text_none():
    assert PLUGIN._clean_text(None) == ""
    assert PLUGIN._clean_text("") == ""


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
    msg = plugin._format_post_message(post)
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
    msg = plugin._format_post_message(post)
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
    msg = plugin._format_post_message(post)
    assert len(msg) < len(long_summary) + 200
    assert "..." in msg


# ---------------------------------------------------------------------------
# _format_post_message – with prefix
# ---------------------------------------------------------------------------
def test_format_post_with_prefix():
    plugin = NikkeNewsPlugin(context=None, config={"push_prefix": "【PREFIX】"})
    post = {
        "post_uuid": "u",
        "title": "Title",
        "content_summary": "Summary",
        "created_on": 1,
    }
    msg = plugin._format_post_message(post)
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
    msg = plugin._format_post_message(post)
    assert "<b>" not in msg
    assert "<i>" not in msg
    assert "Bold Title" in msg
    assert "Italic summary" in msg


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------
def test_safe_int():
    assert PLUGIN._safe_int("123") == 123
    assert PLUGIN._safe_int(None) == 0
    assert PLUGIN._safe_int("abc") == 0
    assert PLUGIN._safe_int(0) == 0
    assert PLUGIN._safe_int(-5) == -5


# ---------------------------------------------------------------------------
# _format_timestamp
# ---------------------------------------------------------------------------
def test_format_timestamp():
    result = PLUGIN._format_timestamp(1712345678)
    assert "2024" in result
    assert "-" in result

    assert PLUGIN._format_timestamp(0) == "未知"
    assert PLUGIN._format_timestamp(None) == "未知"
