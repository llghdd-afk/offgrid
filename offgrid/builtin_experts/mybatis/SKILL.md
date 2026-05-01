---
name: MybatisExpert
version: 1.0.0
trigger_keywords: [mybatis, mapper, xml映射, sql映射, dao]
trigger_min_confidence: 0.7
pipeline: [locator, generator, verifier]
lifecycle: mature
---

## 领域知识

- Mapper接口方法名与XML中id一一对应，namespace为接口全限定名
- 动态SQL标签：<if test=""> 条件拼接、<choose>/<when>/<otherwise> 多分支、<foreach> 集合遍历
- ResultMap：一对一用<association>，一对多用<collection>，嵌套查询用select属性
- 参数传递：单参数直接用#{param}，多参数用@Param注解或封装DTO
- #{} 预编译防注入，${} 字符串替换仅用于动态表名/列名
- 分页：配合PageHelper插件，Mapper方法前调用PageHelper.startPage()
- 批量操作：insert用<foreach>拼接VALUES，update用<foreach>+CASE WHEN
- 缓存：一级缓存SqlSession级别默认开启，二级缓存需在XML加<cache/>
- 通用字段（create_time/update_time）用拦截器自动填充
- XML文件放在 resources/mapper/ 目录，与接口包路径对应

## 经验规则（自动生成）
