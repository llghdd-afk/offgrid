"""doc_generator 模块的测试套件。

测试覆盖：
- MarkdownParser: 各节点类型解析 + 混合内容
- HTMLRenderer: 各节点类型渲染
- TOCBuilder: 嵌套标题、id 生成、TOC HTML 渲染
- 集成测试: parse -> render 完整流程
- 结构测试: 验证拆分后的模块文件存在 + re-export
"""

import os
import sys
import pytest

# 确保任务目录在 sys.path 中
TASK_DIR = os.path.dirname(os.path.abspath(__file__))
if TASK_DIR not in sys.path:
    sys.path.insert(0, TASK_DIR)

from doc_generator import MarkdownParser, HTMLRenderer, TOCBuilder


# ============================================================
# Parser Tests
# ============================================================

class TestMarkdownParser:
    def setup_method(self):
        self.parser = MarkdownParser()

    def test_parse_heading(self):
        nodes = self.parser.parse("# Title")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'heading'
        assert nodes[0]['level'] == 1
        assert nodes[0]['content'] == 'Title'

    def test_parse_heading_levels(self):
        md = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
        nodes = self.parser.parse(md)
        assert len(nodes) == 6
        for i, node in enumerate(nodes, 1):
            assert node['level'] == i

    def test_parse_paragraph(self):
        nodes = self.parser.parse("This is a paragraph.")
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'paragraph'
        assert nodes[0]['content'] == 'This is a paragraph.'

    def test_parse_multiline_paragraph(self):
        md = "Line one\nLine two\nLine three"
        nodes = self.parser.parse(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'paragraph'
        assert nodes[0]['content'] == 'Line one Line two Line three'

    def test_parse_code_block_with_language(self):
        md = "```python\ndef hello():\n    print('hi')\n```"
        nodes = self.parser.parse(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'code_block'
        assert nodes[0]['language'] == 'python'
        assert "def hello():" in nodes[0]['content']

    def test_parse_code_block_no_language(self):
        md = "```\nsome code\n```"
        nodes = self.parser.parse(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'code_block'
        assert nodes[0]['language'] is None

    def test_parse_unordered_list(self):
        md = "- Apple\n- Banana\n- Cherry"
        nodes = self.parser.parse(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'unordered_list'
        assert nodes[0]['items'] == ['Apple', 'Banana', 'Cherry']

    def test_parse_ordered_list(self):
        md = "1. First\n2. Second\n3. Third"
        nodes = self.parser.parse(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'ordered_list'
        assert nodes[0]['items'] == ['First', 'Second', 'Third']

    def test_parse_blockquote(self):
        md = "> This is a quote\n> Second line"
        nodes = self.parser.parse(md)
        assert len(nodes) == 1
        assert nodes[0]['type'] == 'blockquote'
        assert 'This is a quote' in nodes[0]['content']

    def test_parse_horizontal_rule(self):
        for hr in ['---', '***', '___']:
            nodes = self.parser.parse(hr)
            assert len(nodes) == 1
            assert nodes[0]['type'] == 'horizontal_rule'

    def test_parse_mixed_content(self):
        md = """# Welcome

This is intro text.

```python
x = 1
```

- item A
- item B

> A quote

---

## Section Two

1. One
2. Two"""
        nodes = self.parser.parse(md)
        types = [n['type'] for n in nodes]
        assert types == [
            'heading', 'paragraph', 'code_block',
            'unordered_list', 'blockquote', 'horizontal_rule',
            'heading', 'ordered_list',
        ]

    def test_empty_input(self):
        nodes = self.parser.parse("")
        assert nodes == []

    def test_only_blank_lines(self):
        nodes = self.parser.parse("\n\n\n")
        assert nodes == []


# ============================================================
# Renderer Tests
# ============================================================

class TestHTMLRenderer:
    def setup_method(self):
        self.renderer = HTMLRenderer()

    def test_render_heading(self):
        node = {'type': 'heading', 'level': 2, 'content': 'Hello World'}
        html = self.renderer.render_node(node)
        assert '<h2' in html
        assert 'Hello World' in html
        assert 'id="hello-world"' in html

    def test_render_paragraph(self):
        node = {'type': 'paragraph', 'content': 'Some text here.'}
        html = self.renderer.render_node(node)
        assert html == '<p>Some text here.</p>'

    def test_render_code_block_with_lang(self):
        node = {'type': 'code_block', 'language': 'js', 'content': 'let x = 1;'}
        html = self.renderer.render_node(node)
        assert 'class="language-js"' in html
        assert 'let x = 1;' in html
        assert '<pre><code' in html

    def test_render_code_block_no_lang(self):
        node = {'type': 'code_block', 'language': None, 'content': 'plain code'}
        html = self.renderer.render_node(node)
        assert '<pre><code>plain code</code></pre>' == html

    def test_render_unordered_list(self):
        node = {'type': 'unordered_list', 'items': ['A', 'B']}
        html = self.renderer.render_node(node)
        assert '<ul>' in html
        assert '<li>A</li>' in html
        assert '<li>B</li>' in html

    def test_render_ordered_list(self):
        node = {'type': 'ordered_list', 'items': ['X', 'Y']}
        html = self.renderer.render_node(node)
        assert '<ol>' in html
        assert '<li>X</li>' in html

    def test_render_blockquote(self):
        node = {'type': 'blockquote', 'content': 'wise words'}
        html = self.renderer.render_node(node)
        assert '<blockquote>' in html
        assert 'wise words' in html

    def test_render_horizontal_rule(self):
        node = {'type': 'horizontal_rule'}
        assert self.renderer.render_node(node) == '<hr>'

    def test_render_html_escaping(self):
        node = {'type': 'paragraph', 'content': '<script>alert("xss")</script>'}
        html = self.renderer.render_node(node)
        assert '<script>' not in html
        assert '&lt;script&gt;' in html
        assert '&quot;' in html

    def test_render_document(self):
        nodes = [
            {'type': 'heading', 'level': 1, 'content': 'Doc'},
            {'type': 'paragraph', 'content': 'Hello'},
        ]
        html = self.renderer.render_document(nodes)
        assert '<!DOCTYPE html>' in html
        assert '<html>' in html
        assert '<body>' in html
        assert '<h1' in html
        assert '<p>Hello</p>' in html

    def test_render_unknown_type(self):
        node = {'type': 'unknown_thing'}
        assert self.renderer.render_node(node) == ''


# ============================================================
# TOC Tests
# ============================================================

class TestTOCBuilder:
    def setup_method(self):
        self.toc_builder = TOCBuilder()

    def test_build_toc_from_headings(self):
        nodes = [
            {'type': 'heading', 'level': 1, 'content': 'Intro'},
            {'type': 'paragraph', 'content': 'text'},
            {'type': 'heading', 'level': 2, 'content': 'Details'},
        ]
        toc = self.toc_builder.build_toc(nodes)
        assert len(toc) == 2
        assert toc[0] == {'level': 1, 'text': 'Intro', 'id': 'intro'}
        assert toc[1] == {'level': 2, 'text': 'Details', 'id': 'details'}

    def test_build_toc_empty(self):
        nodes = [{'type': 'paragraph', 'content': 'no headings'}]
        toc = self.toc_builder.build_toc(nodes)
        assert toc == []

    def test_toc_id_generation(self):
        nodes = [
            {'type': 'heading', 'level': 1, 'content': 'Hello World'},
            {'type': 'heading', 'level': 2, 'content': 'API Reference!'},
        ]
        toc = self.toc_builder.build_toc(nodes)
        assert toc[0]['id'] == 'hello-world'
        assert toc[1]['id'] == 'api-reference'

    def test_render_toc_html(self):
        toc = [
            {'level': 1, 'text': 'Intro', 'id': 'intro'},
            {'level': 2, 'text': 'Sub', 'id': 'sub'},
        ]
        html = self.toc_builder.render_toc_html(toc)
        assert '<ul>' in html
        assert '<a href="#intro">Intro</a>' in html
        assert '<a href="#sub">Sub</a>' in html

    def test_render_toc_html_empty(self):
        assert self.toc_builder.render_toc_html([]) == ''

    def test_render_toc_nested(self):
        toc = [
            {'level': 1, 'text': 'A', 'id': 'a'},
            {'level': 2, 'text': 'B', 'id': 'b'},
            {'level': 3, 'text': 'C', 'id': 'c'},
            {'level': 1, 'text': 'D', 'id': 'd'},
        ]
        html = self.toc_builder.render_toc_html(toc)
        # Should have nested structure: open/close tags balanced
        assert html.count('<ul>') == html.count('</ul>')
        assert '<a href="#a">A</a>' in html
        assert '<a href="#d">D</a>' in html


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    def test_parse_and_render_full_document(self):
        md = """# My Document

Welcome to the doc.

## Code Example

```python
print("hello")
```

## Features

- Fast
- Simple
- Reliable

> Built with love

---

## Conclusion

That's all folks."""

        parser = MarkdownParser()
        renderer = HTMLRenderer()
        toc_builder = TOCBuilder()

        nodes = parser.parse(md)
        assert len(nodes) > 0

        html = renderer.render_document(nodes)
        assert '<!DOCTYPE html>' in html
        assert '<h1' in html
        assert 'My Document' in html
        assert 'language-python' in html
        assert '<ul>' in html
        assert '<hr>' in html

        toc = toc_builder.build_toc(nodes)
        assert len(toc) == 4  # h1 + 3 h2s
        toc_html = toc_builder.render_toc_html(toc)
        assert '<a href="#my-document">' in toc_html

    def test_roundtrip_preserves_content(self):
        """确保解析后渲染不会丢失内容。"""
        md = "# Title\n\nParagraph with special chars: <div> & \"quotes\""
        parser = MarkdownParser()
        renderer = HTMLRenderer()

        nodes = parser.parse(md)
        html = renderer.render_document(nodes)

        assert 'Title' in html
        assert '&lt;div&gt;' in html
        assert '&amp;' in html
        assert '&quot;quotes&quot;' in html


# ============================================================
# Structural Tests (post-refactor verification)
# ============================================================

class TestStructure:
    """验证重构后的模块结构。"""

    def test_parser_module_exists(self):
        parser_path = os.path.join(TASK_DIR, 'parser.py')
        assert os.path.isfile(parser_path), \
            f"parser.py should exist at {parser_path}"

    def test_renderer_module_exists(self):
        renderer_path = os.path.join(TASK_DIR, 'renderer.py')
        assert os.path.isfile(renderer_path), \
            f"renderer.py should exist at {renderer_path}"

    def test_toc_builder_module_exists(self):
        toc_path = os.path.join(TASK_DIR, 'toc_builder.py')
        assert os.path.isfile(toc_path), \
            f"toc_builder.py should exist at {toc_path}"

    def test_doc_generator_reexports_parser(self):
        from doc_generator import MarkdownParser as MP
        from parser import MarkdownParser as DirectMP
        assert MP is DirectMP, \
            "doc_generator.MarkdownParser should be re-exported from parser module"

    def test_doc_generator_reexports_renderer(self):
        from doc_generator import HTMLRenderer as HR
        from renderer import HTMLRenderer as DirectHR
        assert HR is DirectHR, \
            "doc_generator.HTMLRenderer should be re-exported from renderer module"

    def test_doc_generator_reexports_toc_builder(self):
        from doc_generator import TOCBuilder as TB
        from toc_builder import TOCBuilder as DirectTB
        assert TB is DirectTB, \
            "doc_generator.TOCBuilder should be re-exported from toc_builder module"
