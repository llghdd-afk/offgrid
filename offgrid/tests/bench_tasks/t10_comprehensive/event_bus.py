# 事件总线系统 — 发布/订阅模式
#
# 这个系统有一些问题需要修复，同时需要重构：
# 1. 运行测试找出代码中的问题并修复
# 2. 将代码重构为 EventBus + EventStore + EventReplay 三个类
# 3. EventBus: 核心发布订阅，EventStore: 历史存储，EventReplay: 回放逻辑
# 4. 所有测试必须通过，不要修改测试文件

import time
import re
from collections import defaultdict


class EventBus:
    """
    事件总线：发布/订阅模式
    支持通配符订阅(user.*)、优先级、中间件链、事件存储和回放
    """

    def __init__(self):
        self._handlers = defaultdict(list)  # event_name -> [(priority, handler)]
        self._history = []  # 事件历史
        self._middleware = []  # 中间件链

    def subscribe(self, event_name: str, handler, priority: int = 0):
        """订阅事件。priority 越大越先执行。"""
        self._handlers[event_name].append((priority, handler))

    def unsubscribe(self, event_name: str, handler):
        """取消订阅"""
        if event_name in self._handlers:
            self._handlers[event_name] = [
                (p, h) for p, h in self._handlers[event_name] if h is not handler
            ]

    def publish(self, event_name: str, data=None):
        """发布事件，通知所有匹配的订阅者"""
        event = {
            "name": event_name,
            "data": data,
            "timestamp": time.time(),
            "cancelled": False,
        }

        # 执行中间件
        for mw in self._middleware:
            event = mw(event)
            if event is None or event.get("cancelled"):
                return event

        # 记录历史
        self._history.append(event)

        # 查找匹配的 handlers（精确匹配 + 通配符）
        matched = []
        for pattern, handlers in self._handlers.items():
            if self._match_pattern(pattern, event_name):
                matched.extend(handlers)

        # 按优先级排序执行
        matched.sort(key=lambda x: x[0], reverse=True)

        results = []
        for priority, handler in matched:
            try:
                result = handler(event)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e)})
                break

        event["results"] = results
        return event

    def add_middleware(self, middleware_fn):
        """添加中间件。中间件接收 event 返回修改后的 event，返回 None 则取消事件。"""
        self._middleware.append(middleware_fn)

    def get_history(self, event_name=None, limit=None):
        """获取事件历史"""
        history = self._history
        if event_name:
            history = [e for e in history if e["name"] == event_name]
        if limit:
            history = history[-limit:]
        return history

    def clear_history(self):
        """清空历史"""
        self._history = []

    def replay(self, events=None):
        """重放事件历史"""
        to_replay = events or self._history.copy()
        results = []
        for event in to_replay:
            result = self.publish(event["name"], event["data"])
            results.append(result)
        return results

    def handler_count(self, event_name=None):
        """返回 handler 数量"""
        if event_name:
            return len(self._handlers.get(event_name, []))
        return sum(len(hs) for hs in self._handlers.values())

    def _match_pattern(self, pattern: str, event_name: str) -> bool:
        """匹配事件名。支持 * 通配符。
        user.* 匹配 user.login, user.logout
        *.error 匹配 db.error, api.error
        """
        if pattern == event_name:
            return True
        if '*' not in pattern:
            return False
        regex = pattern.replace('.', r'\.').replace('*', '.*')
        return bool(re.match(f'^{regex}$', event_name))
