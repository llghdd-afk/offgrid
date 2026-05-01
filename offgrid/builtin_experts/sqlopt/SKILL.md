---
name: SQLOptExpert
version: 1.0.0
trigger_keywords: [sql优化, 慢查询, explain, 索引, sql性能]
trigger_min_confidence: 0.7
pipeline: [locator, generator, verifier]
lifecycle: mature
---

## 领域知识

- EXPLAIN分析：关注type列（ALL全表扫描→需优化，ref/range/const为佳）、rows估算、Extra中的Using filesort/temporary
- 索引设计：WHERE条件列建索引，联合索引遵循最左前缀原则，区分度高的列放前面
- 覆盖索引：SELECT的列都在索引中，避免回表（Extra显示Using index）
- 避免索引失效：不在索引列上用函数/运算、不用前导%LIKE、注意隐式类型转换
- 子查询改JOIN：IN子查询改为INNER JOIN，EXISTS改为LEFT JOIN + IS NOT NULL判断
- 分页优化：深分页用WHERE id > last_id LIMIT n代替OFFSET，或延迟关联
- 批量操作：INSERT用批量VALUES（每批500-1000条），UPDATE用CASE WHEN批量
- COUNT优化：COUNT(*)让引擎选最小索引，不要COUNT(列名)除非需排除NULL
- 大表JOIN：确保JOIN字段有索引且类型一致，小表驱动大表
- 锁优化：长事务拆短、避免SELECT...FOR UPDATE范围过大

## 经验规则（自动生成）
