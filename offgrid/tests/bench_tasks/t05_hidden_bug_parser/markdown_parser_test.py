import pytest
from markdown_parser import MarkdownParser


@pytest.fixture
def parser():
    return MarkdownParser()


class TestHeadings:
    def test_h1(self, parser):
        assert parser.parse("# Hello") == "<h1>Hello</h1>"

    def test_h3(self, parser):
        assert parser.parse("### Third") == "<h3>Third</h3>"

    def test_heading_with_inline(self, parser):
        result = parser.parse("# Hello **world**")
        assert "<h1>" in result
        assert "<strong>world</strong>" in result


class TestInlineFormatting:
    def test_bold(self, parser):
        result = parser.parse("This is **bold** text")
        assert "<strong>bold</strong>" in result

    def test_italic(self, parser):
        result = parser.parse("This is *italic* text")
        assert "<em>italic</em>" in result

    def test_multiple_italics(self, parser):
        """多个斜体片段应各自独立"""
        result = parser.parse("*first* and *second*")
        assert "<em>first</em>" in result
        assert "<em>second</em>" in result
        assert "*" not in result.replace("</em>", "").replace("<em>", "")

    def test_bold_and_italic(self, parser):
        result = parser.parse("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_inline_code(self, parser):
        result = parser.parse("Use `print()` here")
        assert "<code>print()</code>" in result

    def test_link(self, parser):
        result = parser.parse("[Google](https://google.com)")
        assert '<a href="https://google.com">Google</a>' in result

    def test_inline_code_preserves_stars(self, parser):
        """行内代码中的 * 不应被解析为斜体"""
        result = parser.parse("Use `**kwargs` in Python")
        assert "<code>**kwargs</code>" in result
        assert "<strong>" not in result


class TestLists:
    def test_unordered_list(self, parser):
        md = "- item 1\n- item 2\n- item 3"
        result = parser.parse(md)
        assert "<ul>" in result
        assert "</ul>" in result
        assert result.count("<li>") == 3

    def test_ordered_list(self, parser):
        md = "1. first\n2. second\n3. third"
        result = parser.parse(md)
        assert "<ol>" in result
        assert "</ol>" in result
        assert result.count("<li>") == 3

    def test_list_with_inline(self, parser):
        md = "- **bold** item\n- *italic* item"
        result = parser.parse(md)
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_list_closes_before_paragraph(self, parser):
        md = "- item 1\n- item 2\n\nA paragraph"
        result = parser.parse(md)
        assert "</ul>" in result
        assert "<p>A paragraph</p>" in result
        # ul 应该在 paragraph 之前关闭
        ul_close = result.index("</ul>")
        p_start = result.index("<p>")
        assert ul_close < p_start


class TestCodeBlocks:
    def test_code_block(self, parser):
        md = "```\nprint('hello')\n```"
        result = parser.parse(md)
        assert "<pre><code>" in result
        assert "</code></pre>" in result
        assert "print" in result

    def test_code_block_with_language(self, parser):
        md = "```python\ndef foo():\n    pass\n```"
        result = parser.parse(md)
        assert 'class="language-python"' in result

    def test_code_block_escapes_html(self, parser):
        md = "```\n<div>test</div>\n```"
        result = parser.parse(md)
        assert "&lt;div&gt;" in result
        assert "<div>" not in result

    def test_code_block_preserves_markdown(self, parser):
        """代码块内的 markdown 语法不应被解析"""
        md = "```\n# not a heading\n**not bold**\n```"
        result = parser.parse(md)
        assert "<h1>" not in result
        assert "<strong>" not in result


class TestListSwitching:
    def test_switching_list_types_with_blank(self, parser):
        """ul 和 ol 之间有空行时应正确切换"""
        md = "- unordered\n\n1. ordered"
        result = parser.parse(md)
        assert "</ul>" in result
        assert "<ol>" in result
        ul_close = result.index("</ul>")
        ol_open = result.index("<ol>")
        assert ul_close < ol_open

    def test_switching_list_types_no_blank(self, parser):
        """ul 直接跟 ol（无空行）时应正确处理"""
        md = "- unordered 1\n- unordered 2\n1. ordered 1\n2. ordered 2"
        result = parser.parse(md)
        assert "</ul>" in result
        assert "<ol>" in result
        assert result.count("<ul>") == 1
        assert result.count("<ol>") == 1
        # ul 必须在 ol 之前关闭
        ul_close = result.index("</ul>")
        ol_open = result.index("<ol>")
        assert ul_close < ol_open

    def test_ol_to_ul_no_blank(self, parser):
        """ol 直接跟 ul（无空行）时应关闭 ol 再开 ul"""
        md = "1. ordered\n- unordered"
        result = parser.parse(md)
        assert "</ol>" in result
        assert "<ul>" in result
        ol_close = result.index("</ol>")
        ul_open = result.index("<ul>")
        assert ol_close < ul_open


class TestHeadingEdgeCases:
    def test_hashtag_without_space(self, parser):
        """#tag 不是标题，应该当作普通段落"""
        result = parser.parse("#hashtag")
        assert "<h1>" not in result
        assert "<p>#hashtag</p>" in result

    def test_hash_with_space_is_heading(self, parser):
        result = parser.parse("# heading")
        assert "<h1>heading</h1>" in result

    def test_multiple_hashes_no_space(self, parser):
        """##notaheading 不是标题"""
        result = parser.parse("##notaheading")
        assert "<h2>" not in result


class TestMixed:
    def test_horizontal_rule(self, parser):
        assert "<hr>" in parser.parse("---")

    def test_paragraph(self, parser):
        assert parser.parse("Hello world") == "<p>Hello world</p>"

    def test_mixed_document(self, parser):
        md = """# Title

A paragraph with **bold** and *italic*.

- item 1
- item 2

## Subtitle

1. ordered 1
2. ordered 2

---

```python
x = 1
```

Final paragraph."""
        result = parser.parse(md)
        assert "<h1>Title</h1>" in result
        assert "<h2>Subtitle</h2>" in result
        assert "<ul>" in result
        assert "<ol>" in result
        assert "<hr>" in result
        assert 'language-python' in result
        assert "<p>Final paragraph.</p>" in result
