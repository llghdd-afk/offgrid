---
name: OfficeDocxExpert
version: 1.0.0
trigger_keywords: [word, docx, word文档, 技术方案, 报告]
trigger_min_confidence: 0.7
pipeline: [office]
lifecycle: mature
---

## 领域知识

- 使用python-docx库生成，Document()创建空文档
- 中文正文字体：宋体/仿宋，标题：微软雅黑/黑体，英文：Times New Roman
- 正文字号：小四（12pt），标题逐级递增（二号→小三→四号）
- 首行缩进：paragraph_format.first_line_indent = Cm(0.74)（两个中文字符）
- 行距：1.5倍行距，paragraph_format.line_spacing = 1.5
- 页边距：上下2.54cm，左右3.17cm（Word默认值）
- 表格：Table(rows, cols)，首行深色背景+白色加粗文字，内容行交替底色
- 页眉页脚：section.header.paragraphs[0] 设置文字，页码用WD_ALIGN_PARAGRAPH.CENTER
- 标题层级：add_heading(text, level=1/2/3)，自动生成目录结构
- 图片插入：add_picture(path, width=Cm(14)) 居中显示
- 保存前不要忘记 document.save(filename)

## 经验规则（自动生成）
