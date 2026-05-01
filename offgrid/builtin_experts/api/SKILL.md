---
name: APIExpert
version: 1.0.0
trigger_keywords: [api, endpoint, rest, restful, swagger, openapi]
trigger_min_confidence: 0.7
pipeline: [locator, generator, verifier]
lifecycle: mature
---

## 领域知识

- 资源命名用复数名词（/users, /orders），避免动词
- HTTP方法语义：GET查询、POST创建、PUT全量更新、PATCH部分更新、DELETE删除
- 状态码：200成功、201已创建、204无内容、400参数错误、401未认证、403无权限、404不存在、409冲突、422验证失败、500服务端错误
- 分页：支持 ?page=1&size=20，响应包含 total/pages/current 元数据
- 错误响应统一格式：{"code": int, "message": str, "details": [...]}
- 认证：Bearer Token 放 Authorization header，不放 URL 参数
- 版本控制：URL前缀 /api/v1/ 或 Accept header
- 自动检测框架（Flask/FastAPI/Express/Spring）并适配对应路由注册方式
- FastAPI 优先用 Pydantic model 做请求/响应校验
- Express 用 router.route() 链式注册同路径不同方法

## 经验规则（自动生成）
