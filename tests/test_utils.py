from core.utils import (
    ReadableHtmlParser,
    is_video_post,
    safe_float,
)


class TestSafeFloat:
    def test_valid(self):
        assert safe_float("3.14") == 3.14

    def test_int_string(self):
        assert safe_float("42") == 42.0

    def test_none(self):
        assert safe_float(None) == 0.0

    def test_invalid(self):
        assert safe_float("abc") == 0.0

    def test_empty_string(self):
        assert safe_float("") == 0.0


class TestIsVideoPost:
    def test_true(self):
        assert is_video_post({"type": 3}) is True

    def test_false(self):
        assert is_video_post({"type": 1}) is False

    def test_missing_type(self):
        assert is_video_post({}) is False


class TestReadableHtmlParser:
    def test_plain_text(self):
        p = ReadableHtmlParser()
        p.feed("<div>hello</div>")
        assert p.text() == "hello"

    def test_nested_ignored(self):
        html = "<div>ok</div><script>skip</script><style>skip</style><div>ok</div>"
        p = ReadableHtmlParser()
        p.feed(html)
        assert p.text() == "ok\nok"

    def test_consecutive_breaks(self):
        p = ReadableHtmlParser()
        p.feed("<br><br><br>")
        assert p.text() == ""

    def test_break_with_text(self):
        p = ReadableHtmlParser()
        p.feed("line1<br>line2")
        assert p.text() == "line1\nline2"

    def test_only_ignored(self):
        p = ReadableHtmlParser()
        p.feed("<script>console.log(1)</script>")
        assert p.text() == ""

    def test_entity_refs(self):
        p = ReadableHtmlParser()
        p.feed("Price: &lt; 10 &amp;&amp; &gt; 5")
        assert "&lt;" in p.text() or p.text() == "Price: < 10 && > 5"
