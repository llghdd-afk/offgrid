---
name: UniAppExpert
version: 1.0.0
trigger_keywords: [uniapp, uni-app, 小程序, 跨端, vue3小程序]
trigger_min_confidence: 0.5
pipeline: [locator, generator, verifier]
lifecycle: mature
---

## 领域知识

- 基于Vue3组合式API（setup语法糖），ref/reactive管理状态，computed派生数据
- 条件编译：#ifdef MP-WEIXIN 微信专属代码 #endif，支持H5/MP-WEIXIN/MP-ALIPAY/APP
- 生命周期：页面用onLoad(接收参数)/onShow/onHide，组件用onMounted/onUnmounted
- 路由：uni.navigateTo跳转保留当前页，uni.redirectTo关闭当前页，uni.switchTab切Tab
- 网络请求：封装uni.request为Promise，统一拦截添加token、处理401跳登录
- 存储：uni.setStorageSync/getStorageSync同步操作，大数据用异步版本
- 样式：rpx自适应单位（750rpx=屏幕宽），不用px；scoped样式避免污染
- 组件通信：props向下传、emit向上传、provide/inject跨层级、Pinia全局状态
- 分包：subPackages配置分包加载，主包控制在2MB内
- 兼容性：避免直接操作DOM，不用window/document，用uni API替代Web API

## 经验规则（自动生成）
