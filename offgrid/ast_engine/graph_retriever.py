"""
Two-stage retriever: BM25 keyword recall + call graph expansion.
LOC-RED-3: BM25+graph is the primary path, LLM is fallback.
LOC-RED-5: Total retrieval time must be under 3 seconds.
"""

import logging
import sqlite3
import time
from pathlib import Path

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".offgrid" / "graph.db"

SKIP_NAMES = {
    "__init__", "__repr__", "__str__", "__eq__", "__hash__",
    "setUp", "tearDown",
}


class GraphRetriever:
    """BM25 recall + call graph expansion retriever."""

    def __init__(self, project_root: str):
        self.project_root = str(Path(project_root).resolve())
        self._nodes_cache: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._bm25_built_at: float = 0.0

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def has_graph(self) -> bool:
        """Check if graph data exists for this project."""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT node_count FROM graph_meta WHERE project_root=?",
                    (self.project_root,)
                ).fetchone()
            return row is not None and (row["node_count"] or 0) > 0
        except Exception:
            return False

    def _ensure_bm25(self):
        """Build BM25 index from SQLite nodes (cached for 5 min)."""
        if self._bm25 and (time.time() - self._bm25_built_at) < 300:
            return

        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """SELECT id, name, qualified, file_path,
                              start_line, end_line, node_type, search_text
                       FROM nodes
                       WHERE project_root=?""",
                    (self.project_root,)
                ).fetchall()
        except Exception:
            return

        if not rows:
            return

        self._nodes_cache = [dict(row) for row in rows]
        corpus = [
            (node["search_text"] or node["name"]).lower().split()
            for node in self._nodes_cache
        ]
        self._bm25 = BM25Okapi(corpus)
        self._bm25_built_at = time.time()
        logger.info("[retriever] BM25 index built: %d nodes", len(self._nodes_cache))

    def retrieve(
        self,
        query: str,
        top_k_bm25: int = 20,
        graph_hops: int = 2,
        max_results: int = 10,
    ) -> list[dict]:
        """
        Two-stage retrieval:
        Stage 1: BM25 keyword recall -> top_k_bm25 candidates
        Stage 2: Call graph expansion -> graph_hops hops
        Returns: deduplicated nodes sorted by relevance.
        """
        t0 = time.perf_counter()

        self._ensure_bm25()
        if not self._bm25 or not self._nodes_cache:
            logger.warning("[retriever] BM25 index empty, graph may not be built")
            return []

        # Stage 1: BM25 recall
        query_tokens = query.lower().split()
        scores = self._bm25.get_scores(query_tokens)
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k_bm25]

        candidates = [
            {**self._nodes_cache[i], "bm25_score": scores[i]}
            for i in top_indices
            if scores[i] > 0
        ]
        logger.info("[retriever] BM25 recalled %d candidates (query=%s)",
                    len(candidates), query[:50])

        # FLEX-2: if BM25 returns nothing, use first few nodes as entry
        if not candidates:
            logger.info("[retriever] BM25 empty, triggering graph traversal from entries")
            candidates = [{**n, "bm25_score": 0.0} for n in self._nodes_cache[:5]]

        # Stage 2: call graph expansion
        candidate_ids = {c["id"] for c in candidates}
        graph_nodes = self._expand_graph(candidate_ids, hops=graph_hops)

        # Merge BM25 candidates + graph-discovered nodes
        all_node_ids = candidate_ids | graph_nodes
        result_nodes = self._fetch_nodes(all_node_ids)

        # Sort: BM25 candidates first (by score), graph-discovered after
        bm25_id_score = {c["id"]: c["bm25_score"] for c in candidates}
        result_nodes.sort(
            key=lambda n: bm25_id_score.get(n["id"], 0),
            reverse=True
        )

        # Filter noise
        result_nodes = [
            n for n in result_nodes
            if n["name"] not in SKIP_NAMES
            and not n["name"].startswith("test_")
        ]

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info("[retriever] retrieval done: %d results %dms",
                    len(result_nodes[:max_results]), elapsed_ms)

        if elapsed_ms > 3000:
            logger.warning("[retriever] %dms exceeds 3s red line!", elapsed_ms)

        return result_nodes[:max_results]

    def _expand_graph(self, seed_ids: set[int], hops: int = 2) -> set[int]:
        """Expand from seed nodes along call graph (both directions)."""
        if not seed_ids:
            return set()

        discovered = set(seed_ids)
        frontier = set(seed_ids)

        try:
            with self._get_conn() as conn:
                for _ in range(hops):
                    if not frontier:
                        break

                    ph = ",".join("?" * len(frontier))
                    frontier_list = list(frontier)

                    # Downstream: who does frontier call
                    to_nodes = {
                        row[0] for row in conn.execute(
                            f"SELECT to_id FROM edges WHERE from_id IN ({ph}) AND project_root=?",
                            frontier_list + [self.project_root]
                        ).fetchall()
                    }
                    # Upstream: who calls frontier
                    from_nodes = {
                        row[0] for row in conn.execute(
                            f"SELECT from_id FROM edges WHERE to_id IN ({ph}) AND project_root=?",
                            frontier_list + [self.project_root]
                        ).fetchall()
                    }

                    new_nodes = (to_nodes | from_nodes) - discovered
                    discovered |= new_nodes
                    frontier = new_nodes
        except Exception as e:
            logger.warning("[retriever] graph expansion error: %s", e)

        return discovered - seed_ids

    def _fetch_nodes(self, node_ids: set[int]) -> list[dict]:
        if not node_ids:
            return []
        ph = ",".join("?" * len(node_ids))
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    f"""SELECT id, name, qualified, file_path,
                               start_line, end_line, node_type
                        FROM nodes
                        WHERE id IN ({ph}) AND project_root=?""",
                    list(node_ids) + [self.project_root]
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def update_task_stats(self, node_ids: list[int], success: bool):
        """Update node task statistics (flywheel data)."""
        if not node_ids:
            return
        ph = ",".join("?" * len(node_ids))
        try:
            with self._get_conn() as conn:
                if success:
                    conn.execute(
                        f"""UPDATE nodes
                            SET task_count = task_count + 1,
                                success_count = success_count + 1
                            WHERE id IN ({ph})""",
                        node_ids
                    )
                else:
                    conn.execute(
                        f"""UPDATE nodes
                            SET task_count = task_count + 1
                            WHERE id IN ({ph})""",
                        node_ids
                    )
        except Exception as e:
            logger.warning("[retriever] update_task_stats error: %s", e)
