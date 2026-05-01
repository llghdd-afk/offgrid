"""
Markdown 文档生成器 — 支持解析、渲染和目录生成。

包含三个核心类：
- MarkdownParser: 将 Markdown 文本解析为 AST（节点列表）
- HTMLRenderer: 将 AST 节点转换为 HTML 字符串
- TOCBuilder: 从标题节点构建目录
"""

import re
from typing import List, Dict, Any, Optional


# ============================================================
# MarkdownParser — Markdown 解析器
# ============================================================

class MarkdownParser:
    """将 Markdown 文本解析为抽象语法树（节点列表）。

    支持的节点类型：
    - heading: 标题（level 1-6）
    - paragraph: 段落
    - code_block: 代码块（可带语言标识）
    - unordered_list: 无序列表
    - ordered_list: 有序列表
    - blockquote: 引用块
    - horizontal_rule: 水平分割线
    """

    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')
    UNORDERED_RE = re.compile(r'^[-*+]\s+(.+)$')
    ORDERED_RE = re.compile(r'^\d+\.\s+(.+)$')
    CODE_FENCE_RE = re.compile(r'^```(\w*)$')
    BLOCKQUOTE_RE = re.compile(r'^>\s*(.*)$')
    HR_RE = re.compile(r'^(?:---|\*\*\*|___)$')

    def parse(self, text: str) -> List[Dict[str, Any]]:
        """解析 Markdown 文本，返回 AST 节点列表。"""
        lines = text.split('\n')
        nodes: List[Dict[str, Any]] = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # 空行跳过
            if not line.strip():
                i += 1
                continue

            # 水平分割线
            if self.HR_RE.match(line.strip()):
                nodes.append({'type': 'horizontal_rule'})
                i += 1
                continue

            # 标题
            m = self.HEADING_RE.match(line.strip())
            if m:
                level = len(m.group(1))
                content = m.group(2).strip()
                nodes.append({
                    'type': 'heading',
                    'level': level,
                    'content': content,
                })
                i += 1
                continue

            # 代码块
            m = self.CODE_FENCE_RE.match(line.strip())
            if m:
                language = m.group(1) or None
                code_lines = []
                i += 1
                while i < len(lines) and not self.CODE_FENCE_RE.match(lines[i].strip()):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing fence
                nodes.append({
                    'type': 'code_block',
                    'language': language,
                    'content': '\n'.join(code_lines),
                })
                continue

            # 引用块
            m = self.BLOCKQUOTE_RE.match(line.strip())
            if m:
                quote_lines = []
                while i < len(lines):
                    bm = self.BLOCKQUOTE_RE.match(lines[i].strip())
                    if bm:
                        quote_lines.append(bm.group(1))
                        i += 1
                    else:
                        break
                nodes.append({
                    'type': 'blockquote',
                    'content': '\n'.join(quote_lines),
                })
                continue

            # 无序列表
            m = self.UNORDERED_RE.match(line.strip())
            if m:
                items = []
                while i < len(lines):
                    um = self.UNORDERED_RE.match(lines[i].strip())
                    if um:
                        items.append(um.group(1))
                        i += 1
                    else:
                        break
                nodes.append({
                    'type': 'unordered_list',
                    'items': items,
                })
                continue

            # 有序列表
            m = self.ORDERED_RE.match(line.strip())
            if m:
                items = []
                while i < len(lines):
                    om = self.ORDERED_RE.match(lines[i].strip())
                    if om:
                        items.append(om.group(1))
                        i += 1
                    else:
                        break
                nodes.append({
                    'type': 'ordered_list',
                    'items': items,
                })
                continue

            # 段落（默认）
            para_lines = []
            while i < len(lines) and lines[i].strip():
                # 如果下一行匹配其他类型，停止段落收集
                s = lines[i].strip()
                if (self.HEADING_RE.match(s) or self.CODE_FENCE_RE.match(s) or
                        self.BLOCKQUOTE_RE.match(s) or self.UNORDERED_RE.match(s) or
                        self.ORDERED_RE.match(s) or self.HR_RE.match(s)):
                    break
                para_lines.append(lines[i].strip())
                i += 1
            if para_lines:
                nodes.append({
                    'type': 'paragraph',
                    'content': ' '.join(para_lines),
                })

        return nodes


# ============================================================
# HTMLRenderer — HTML 渲染器
# ============================================================

class HTMLRenderer:
    """将 AST 节点转换为 HTML 字符串。"""

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符。"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

    def _make_id(self, text: str) -> str:
        """将文本转换为 HTML id（小写，空格转连字符）。"""
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'\s+', '-', slug.strip())
        return slug

    def render_node(self, node: Dict[str, Any]) -> str:
        """渲染单个 AST 节点为 HTML。"""
        t = node['type']

        if t == 'heading':
            level = node['level']
            content = self._escape_html(node['content'])
            hid = self._make_id(node['content'])
            return f'<h{level} id="{hid}">{content}</h{level}>'

        if t == 'paragraph':
            return f'<p>{self._escape_html(node["content"])}</p>'

        if t == 'code_block':
            lang = node.get('language')
            escaped = self._escape_html(node['content'])
            if lang:
                return f'<pre><code class="language-{lang}">{escaped}</code></pre>'
            return f'<pre><code>{escaped}</code></pre>'

        if t == 'unordered_list':
            items_html = ''.join(
                f'<li>{self._escape_html(item)}</li>' for item in node['items']
            )
            return f'<ul>{items_html}</ul>'

        if t == 'ordered_list':
            items_html = ''.join(
                f'<li>{self._escape_html(item)}</li>' for item in node['items']
            )
            return f'<ol>{items_html}</ol>'

        if t == 'blockquote':
            return f'<blockquote><p>{self._escape_html(node["content"])}</p></blockquote>'

        if t == 'horizontal_rule':
            return '<hr>'

        return ''

    def render_document(self, nodes: List[Dict[str, Any]]) -> str:
        """渲染整个文档为完整 HTML。"""
        parts = [self.render_node(node) for node in nodes]
        body = '\n'.join(parts)
        return (
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head><meta charset="utf-8"></head>\n'
            '<body>\n'
            f'{body}\n'
            '</body>\n'
            '</html>'
        )


# ============================================================
# TOCBuilder — 目录生成器
# ============================================================

class TOCBuilder:
    """从 AST 中的标题节点构建目录（Table of Contents）。"""

    def _make_id(self, text: str) -> str:
        """将文本转换为 HTML id。"""
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'\s+', '-', slug.strip())
        return slug

    def build_toc(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从节点列表中提取标题，构建目录条目列表。

        返回: [{level: int, text: str, id: str}, ...]
        """
        toc = []
        for node in nodes:
            if node['type'] == 'heading':
                toc.append({
                    'level': node['level'],
                    'text': node['content'],
                    'id': self._make_id(node['content']),
                })
        return toc

    def render_toc_html(self, toc: List[Dict[str, Any]]) -> str:
        """将目录条目渲染为嵌套的 HTML 列表。"""
        if not toc:
            return ''

        html_parts = []
        stack: List[int] = []  # 当前嵌套层级栈

        for entry in toc:
            level = entry['level']

            while stack and stack[-1] >= level:
                stack.pop()
                html_parts.append('</li></ul>')

            if not stack or level > stack[-1]:
                html_parts.append('<ul>')
                stack.append(level)

            html_parts.append(
                f'<li><a href="#{entry["id"]}">{entry["text"]}</a>'
            )

        # 关闭所有未关闭的标签
        while stack:
            stack.pop()
            html_parts.append('</li></ul>')

        return ''.join(html_parts)
