---
name: OfficePptxExpert
version: 1.0.0
trigger_keywords: [ppt, pptx, 幻灯片, 演示文稿, 汇报]
trigger_min_confidence: 0.7
pipeline: [office]
lifecycle: mature
---

## 领域知识

- 使用python-pptx库，Presentation()创建，slide_layouts选择版式
- 三明治结构：封面页（标题+副标题+日期）→ 内容页 → 总结页
- 不用默认白底，设置深蓝/深灰背景或渐变填充提升质感
- 商务配色：主色深蓝#003366，辅色#0066CC，强调色#FF6600，文字白色或浅灰
- 每页内容不超过5个要点，每个要点一行不超过15字
- 字号：标题28-36pt，正文18-24pt，注释14pt
- 图表嵌入：用chart_data构建，优先柱状图/饼图/折线图
- 布局：标题在顶部1/5区域，内容占中间3/5，底部留白或放页码
- 动画/切换：代码生成时不加动画（python-pptx不支持），提示用户手动添加
- 母版：如有企业模板.pptx，用Presentation(template_path)加载

## 经验规则（自动生成）
