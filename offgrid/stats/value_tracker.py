"""
Value tracking dashboard.
P2-RED-3: All data stored locally in SQLite, no network requests.
P2-RED-4: Numbers are real and conservative, never inflated.
"""

import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".offgrid" / "stats.db"


class ValueTracker:

    def __init__(self):
        self._init_db()

    def _get_conn(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_conn() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS task_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        project_root TEXT,
                        expert_type TEXT,
                        expert_name TEXT,
                        success INTEGER,
                        elapsed_s REAL,
                        retry_count INTEGER,
                        model TEXT
                    );
                """)
        except Exception as e:
            logger.debug("[value_tracker] init_db failed: %s", e)

    def record(self, project_root: str, expert_type: str,
               expert_name: str, success: bool,
               elapsed_s: float, retry_count: int, model: str):
        """Record task completion (P2-RED-3: local only)."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO task_stats
                    (timestamp, project_root, expert_type, expert_name,
                     success, elapsed_s, retry_count, model)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    project_root, expert_type, expert_name or "",
                    1 if success else 0,
                    elapsed_s, retry_count, model,
                ))
        except Exception as e:
            logger.debug("[value_tracker] record failed: %s", e)

    def get_summary(self, days: int = 30) -> dict:
        """Get stats summary for the given period."""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        try:
            with self._get_conn() as conn:
                row = conn.execute("""
                    SELECT COUNT(*) as total,
                           SUM(success) as succeeded
                    FROM task_stats
                    WHERE timestamp > ?
                """, (since,)).fetchone()

                total = row["total"] or 0
                succeeded = int(row["succeeded"] or 0)

                top_expert = conn.execute("""
                    SELECT expert_name,
                           COUNT(*) as cnt,
                           AVG(success) as rate
                    FROM task_stats
                    WHERE timestamp > ?
                      AND expert_name != ''
                      AND expert_name IS NOT NULL
                    GROUP BY expert_name
                    ORDER BY cnt DESC
                    LIMIT 1
                """, (since,)).fetchone()

                # Total task count (all time, for milestones)
                total_all = conn.execute(
                    "SELECT COUNT(*) as c FROM task_stats"
                ).fetchone()["c"] or 0

        except Exception as e:
            logger.debug("[value_tracker] get_summary failed: %s", e)
            return {
                "days": days, "total_tasks": 0, "succeeded_tasks": 0,
                "time_saved_hours": 0, "top_expert_name": "",
                "top_expert_count": 0, "top_expert_rate": 0,
                "total_all_time": 0,
            }

        # Conservative time estimate: 5 min per successful task (P2-RED-4)
        MINUTES_PER_TASK = 5
        time_saved_h = succeeded * MINUTES_PER_TASK / 60

        return {
            "days": days,
            "total_tasks": total,
            "succeeded_tasks": succeeded,
            "time_saved_hours": round(time_saved_h, 1),
            "top_expert_name": top_expert["expert_name"] if top_expert else "",
            "top_expert_count": top_expert["cnt"] if top_expert else 0,
            "top_expert_rate": top_expert["rate"] if top_expert else 0,
            "total_all_time": total_all,
        }

    def get_total_task_count(self) -> int:
        """Get total task count across all time (for milestone detection)."""
        try:
            with self._get_conn() as conn:
                row = conn.execute("SELECT COUNT(*) as c FROM task_stats").fetchone()
                return row["c"] or 0
        except Exception:
            return 0
