---
name: DeepSeekAPIExpert
version: 1.0.0
trigger_keywords: [deepseek, qwen, 通义千问, 大模型api, llm api, 模型调用]
trigger_min_confidence: 0.7
pipeline: [generator, verifier]
lifecycle: mature
---

## 领域知识

- 国产LLM统一用 OpenAI 兼容接口格式（/v1/chat/completions）
- DeepSeek base_url: https://api.deepseek.com，Qwen: https://dashscope.aliyuncs.com/compatible-mode/v1
- 流式响应：stream=True + SSE解析，逐chunk拼接content字段
- token计费：输入/输出分别计价，用tiktoken或API返回的usage字段统计
- 限流处理：捕获429状态码，指数退避重试（1s/2s/4s），最多3次
- 超时设置：连接超时10s，读取超时60s（长文本生成可加到120s）
- prompt工程：system message定角色，few-shot放user/assistant交替
- 温度参数：代码生成用0.0-0.3，创意文本用0.7-1.0
- 错误处理：区分可重试错误（429/500/503）和不可重试错误（400/401）
- 长文本：超过模型max_tokens时自动截断或分段处理

## 经验规则（自动生成）
