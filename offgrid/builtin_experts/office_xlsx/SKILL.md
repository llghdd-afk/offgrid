---
name: OfficeXlsxExpert
version: 1.0.0
trigger_keywords: [excel, xlsx, 表格, 报表, 数据表]
trigger_min_confidence: 0.7
pipeline: [office]
lifecycle: mature
---

## 领域知识

- 使用openpyxl库，Workbook()创建，ws = wb.active获取活动sheet
- 表头样式：深色背景（#003366）+白色加粗字体+居中对齐
- 斑马纹：奇偶行交替浅灰（#F2F2F2）和白色背景
- 冻结首行：ws.freeze_panes = 'A2'，冻结首行+首列用'B2'
- 列宽自适应：遍历列取max(len(str(cell.value)))设置column_dimensions
- 数据验证：DataValidation(type="list", formula1='"选项1,选项2"')
- 条件格式：ColorScaleRule/CellIsRule高亮异常值
- 公式：直接写Excel公式字符串如'=SUM(B2:B100)'，不用Python计算
- 数字格式：金额'#,##0.00'，百分比'0.00%'，日期'YYYY-MM-DD'
- 合并单元格：ws.merge_cells('A1:D1') 用于标题行
- 边框：thin边框包围数据区域，表头用medium底边框

## 经验规则（自动生成）
