---
name: SpringBootExpert
version: 1.0.0
trigger_keywords: [springboot, spring, spring boot, 注解, autowired, bean]
trigger_min_confidence: 0.7
pipeline: [locator, generator, verifier]
lifecycle: mature
---

## 领域知识

- 分层架构：Controller→Service→Mapper/Repository，每层只依赖下一层
- 注解：@RestController处理请求、@Service业务逻辑、@Mapper数据访问、@Configuration配置类
- 依赖注入：优先构造器注入（不用@Autowired字段注入），便于测试
- 配置文件：application.yml分环境（dev/test/prod），敏感信息用环境变量${DB_PASSWORD}
- AOP切面：@Aspect+@Around做日志/权限/耗时统计，切点表达式精确匹配
- 异常处理：@ControllerAdvice+@ExceptionHandler全局捕获，返回统一错误格式
- Starter自动配置：@ConditionalOnClass/OnProperty控制Bean加载条件
- Mapper接口对应XML：接口在java目录，XML在resources/mapper/，namespace全限定名匹配
- 事务：@Transactional加在Service方法上，只读查询加readOnly=true
- 启动类：@SpringBootApplication放在根包下，确保组件扫描覆盖所有子包

## 经验规则（自动生成）
