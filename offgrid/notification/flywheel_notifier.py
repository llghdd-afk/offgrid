"""
Flywheel visibility notification system.
P2-RED-2: Notifications never interrupt current task, queued and shown at next REPL loop.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

NOTIFY_PATH = Path.home() / ".offgrid" / "pending_notifications.json"


@dataclass
class FlywheelNotification:
    type: str  # "expert_born" / "progress" / "milestone"
    expert_name: str = ""
    trigger_keywords: list[str] = field(default_factory=list)
    task_count: int = 0
    success_rate_new: float = 0.0
    success_rate_baseline: float = 0.0
    avg_latency_new: float = 0.0
    avg_latency_baseline: float = 0.0
    progress_current: int = 0
    progress_total: int = 5
    milestone_tasks: int = 0
    speedup: float = 0.0


class FlywheelNotifier:

    def queue_expert_born(self, expert_def: dict, metrics: dict):
        """Queue expert graduation notification (P2-RED-2: not shown immediately)."""
        notif = FlywheelNotification(
            type="expert_born",
            expert_name=expert_def.get("name", ""),
            trigger_keywords=expert_def.get("trigger_keywords", [])[:4],
            task_count=metrics.get("task_count", 0),
            success_rate_new=metrics.get("success_rate_new", 0),
            success_rate_baseline=metrics.get("success_rate_baseline", 0),
            avg_latency_new=metrics.get("avg_latency_new", 0),
            avg_latency_baseline=metrics.get("avg_latency_baseline", 0),
        )
        self._save(notif)

    def queue_progress(self, expert_type: str, current: int, total: int = 5):
        """Queue accumulation progress notification (3/5, 4/5)."""
        notif = FlywheelNotification(
            type="progress",
            expert_name=expert_type,
            progress_current=current,
            progress_total=total,
        )
        self._save(notif)

    def queue_milestone(self, total_tasks: int, expert_count: int, avg_speedup: float):
        """Queue milestone notification (50/100/200/500 tasks)."""
        notif = FlywheelNotification(
            type="milestone",
            milestone_tasks=total_tasks,
            task_count=expert_count,
            speedup=avg_speedup,
        )
        self._save(notif)

    def flush(self, console) -> int:
        """
        Show all pending notifications and clear queue.
        Called at REPL loop start (P2-RED-2: after previous task completes).
        Returns number of notifications displayed.
        """
        notifications = self._load()
        if not notifications:
            return 0

        for notif_data in notifications:
            notif = FlywheelNotification(**notif_data)
            self._display(notif, console)

        # Clear queue
        try:
            NOTIFY_PATH.write_text("[]", encoding="utf-8")
        except Exception:
            pass
        return len(notifications)

    def _display(self, notif: FlywheelNotification, console):
        if notif.type == "expert_born":
            self._display_expert_born(notif, console)
        elif notif.type == "progress":
            self._display_progress(notif, console)
        elif notif.type == "milestone":
            self._display_milestone(notif, console)

    def _display_expert_born(self, n: FlywheelNotification, console):
        from rich.panel import Panel

        speedup = ""
        if n.avg_latency_baseline > 0 and n.avg_latency_new > 0:
            ratio = n.avg_latency_baseline / n.avg_latency_new
            speedup = f"  速度：平均 {n.avg_latency_new:.0f}s（快了 {ratio:.1f}x）\n"

        rate_str = ""
        rate_diff = n.success_rate_new - n.success_rate_baseline
        if rate_diff > 0:
            rate_str = (
                f"  成功率：{n.success_rate_new*100:.0f}%"
                f"（↑{rate_diff*100:.0f}% vs 通用流水线）\n"
            )

        keywords_str = "、".join(n.trigger_keywords) if n.trigger_keywords else "N/A"

        content = (
            f"[bold cyan]{n.expert_name}[/bold cyan]\n"
            f"  触发词：{keywords_str}\n\n"
            f"  基于你过去 [bold]{n.task_count}[/bold] 次成功任务\n"
            f"{rate_str}"
            f"{speedup}"
            f"\n  [dim]输入 /experts 查看全部专家"
            f" · offgrid expert export {n.expert_name} 导出分享[/dim]"
        )

        console.print()
        console.print(Panel(
            content,
            title="[green]OffGrid 为你生成了一个新专家[/green]",
            border_style="green",
            padding=(0, 2),
        ))
        console.print()

    def _display_progress(self, n: FlywheelNotification, console):
        remaining = n.progress_total - n.progress_current
        console.print(
            f"  [dim][飞轮] {n.expert_name} · "
            f"已积累 {n.progress_current}/{n.progress_total} 次成功 · "
            f"再 {remaining} 次可生成专属专家[/dim]"
        )

    def _display_milestone(self, n: FlywheelNotification, console):
        console.print()
        console.print(
            f"  [bold yellow]里程碑[/bold yellow]  "
            f"已完成 {n.milestone_tasks} 个任务 · "
            f"积累了 {n.task_count} 个专属专家 · "
            f"同类任务平均快了 {n.speedup:.1f}x"
        )
        console.print()

    def _save(self, notif: FlywheelNotification):
        existing = self._load()
        existing.append({
            k: v for k, v in vars(notif).items()
        })
        try:
            NOTIFY_PATH.parent.mkdir(parents=True, exist_ok=True)
            NOTIFY_PATH.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug("[notifier] save failed: %s", e)

    def _load(self) -> list[dict]:
        if not NOTIFY_PATH.exists():
            return []
        try:
            data = json.loads(NOTIFY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
