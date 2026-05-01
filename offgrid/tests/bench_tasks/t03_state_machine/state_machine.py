# 状态机系统 — 多步骤实现任务
#
# 任务分三步，每步依赖前一步的实现：
#
# 第一步：实现 StateMachine 核心
#   - add_state(name, on_enter=None, on_exit=None)
#   - add_transition(trigger, source, dest, guard=None, action=None)
#   - start(initial_state) — 设置初始状态并调用 on_enter
#   - fire(trigger, **kwargs) — 执行转换
#   - state — 当前状态名
#
# 第二步：实现 EventLog（依赖 StateMachine 的事件回调）
#   - EventLog 记录所有状态变化和动作执行
#   - log 格式: list[dict]，每项有 type("enter"/"exit"/"action"/"guard"), state, trigger, timestamp
#
# 第三步：实现 replay(log, machine) — 从日志回放到最终状态
#   - 根据 EventLog 的记录，重新 fire 所有 trigger 让 machine 到达同一最终状态

import time


class StateMachine:
    def __init__(self):
        self._states = {}        # name -> {"on_enter": fn, "on_exit": fn}
        self._transitions = {}   # (trigger, source) -> {"dest": str, "guard": fn, "action": fn}
        self._current = None

    @property
    def state(self):
        return self._current

    def add_state(self, name, on_enter=None, on_exit=None):
        pass

    def add_transition(self, trigger, source, dest, guard=None, action=None):
        pass

    def start(self, initial_state):
        pass

    def fire(self, trigger, **kwargs):
        """触发转换。如果 guard 返回 False 则不转换，返回 False。否则执行转换返回 True。"""
        pass


class EventLog:
    def __init__(self):
        self.entries = []

    def attach(self, machine: StateMachine):
        """把自己挂到 machine 上，记录所有事件"""
        pass

    def clear(self):
        self.entries.clear()


def replay(log_entries: list, machine: StateMachine) -> str:
    """从日志回放，返回最终状态名"""
    pass
