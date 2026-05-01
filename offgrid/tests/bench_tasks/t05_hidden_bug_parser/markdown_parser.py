# Markdown 解析器 — 将 Markdown 转为 HTML
# 有用户报告某些格式转换不正确，请找出并修复所有 bug

class MarkdownParser:
    def parse(self, text: str) -> str:
        """将 Markdown 文本转为 HTML"""
        lines = text.split('\n')
        html_lines = []
        in_list = False
        in_code_block = False
        list_type = None  # 'ul' or 'ol'

        for line in lines:
            # 代码块
            if line.strip().startswith('```'):
                if in_code_block:
                    html_lines.append('</code></pre>')
                    in_code_block = False
                else:
                    lang = line.strip()[3:].strip()
                    if lang:
                        html_lines.append(f'<pre><code class="language-{lang}">')
                    else:
                        html_lines.append('<pre><code>')
                    in_code_block = True
                continue

            if in_code_block:
                html_lines.append(self._escape_html(line))
                continue

            # 关闭列表（如果当前行不是列表项）
            stripped = line.strip()
            is_list_item = stripped.startswith('- ') or stripped.startswith('* ')
            is_ordered = len(stripped) > 2 and stripped[0].isdigit() and '. ' in stripped[:4]

            if in_list and not is_list_item and not is_ordered:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None

            # 标题
            if stripped.startswith('#'):
                level = 0
                for ch in stripped:
                    if ch == '#':
                        level += 1
                    else:
                        break
                if level <= 6:
                    content = stripped[level:].strip()
                    content = self._parse_inline(content)
                    html_lines.append(f'<h{level}>{content}</h{level}>')
                continue

            # 无序列表
            if is_list_item:
                if not in_list:
                    html_lines.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                content = stripped[2:]
                content = self._parse_inline(content)
                html_lines.append(f'<li>{content}</li>')
                continue

            # 有序列表
            if is_ordered:
                if not in_list:
                    html_lines.append('<ol>')
                    in_list = True
                    list_type = 'ol'
                dot_pos = stripped.index('. ')
                content = stripped[dot_pos + 2:]
                content = self._parse_inline(content)
                html_lines.append(f'<li>{content}</li>')
                continue

            # 水平线
            if stripped in ('---', '***', '___'):
                html_lines.append('<hr>')
                continue

            # 空行
            if not stripped:
                html_lines.append('')
                continue

            # 普通段落
            content = self._parse_inline(stripped)
            html_lines.append(f'<p>{content}</p>')

        # 关闭未关闭的列表
        if in_list:
            html_lines.append(f'</{list_type}>')

        return '\n'.join(html_lines)

    def _parse_inline(self, text: str) -> str:
        """解析行内格式: **bold**, *italic*, `code`, [link](url)"""
        result = text

        # 行内代码 (先处理，避免内部被其他规则干扰)
        import re
        result = re.sub(r'`([^`]+)`', r'<code>\1</code>', result)

        # 粗体 **text**
        result = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', result)

        # 斜体 *text*
        result = re.sub(r'\*(.+)\*', r'<em>\1</em>', result)

        # 链接 [text](url)
        result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', result)

        return result

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))
