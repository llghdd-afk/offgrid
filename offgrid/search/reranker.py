"""
Cross-Encoder搜索结果重排。
用CPU推理的轻量reranker，不需要GPU。
FLEX-2：CPU性能低时跳过，只用BM25。
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 使用sentence-transformers的cross-encoder
# 模型：cross-encoder/ms-marco-MiniLM-L-6-v2（82MB，CPU可跑）
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker = None
_reranker_disabled = False  # 如果加载失败或太慢，后续跳过


def get_reranker():
    """懒加载，首次使用时下载模型。"""
    global _reranker, _reranker_disabled
    if _reranker_disabled:
        return None
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(RERANKER_MODEL)
            logger.info("[reranker] 模型加载完成: %s", RERANKER_MODEL)
        except ImportError:
            logger.info("[reranker] sentence-transformers未安装，跳过重排")
            _reranker_disabled = True
        except Exception as e:
            logger.warning("[reranker] 模型加载失败: %s，跳过重排", e)
            _reranker_disabled = True
    return _reranker


def rerank(
    query: str,
    results: list[dict],
    top_k: int = 3,
) -> list[dict]:
    """
    用Cross-Encoder对搜索结果重排。
    失败时降级返回原始顺序（FLEX-2）。

    results: [{"title": str, "url": str, "snippet": str}, ...]
    """
    global _reranker_disabled

    reranker = get_reranker()
    if not reranker or not results:
        return results[:top_k]

    # 构建(query, document)对
    pairs = [
        (query, f"{r.get('title', '')} {r.get('snippet', '')}")
        for r in results
    ]

    try:
        t0 = time.perf_counter()
        scores = reranker.predict(pairs)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # 按分数排序
        ranked = sorted(
            zip(scores, results),
            key=lambda x: x[0],
            reverse=True,
        )

        logger.info(
            "[reranker] 重排完成：%d→%d结果，耗时%.0fms",
            len(results), top_k, elapsed_ms,
        )

        # FLEX-2：耗时超过2秒说明CPU太慢，后续跳过
        if elapsed_ms > 2000:
            logger.warning("[reranker] 耗时%.0fms超过2s，后续跳过重排", elapsed_ms)
            _reranker_disabled = True

        return [r for _, r in ranked[:top_k]]

    except Exception as e:
        logger.warning("[reranker] 重排失败: %s，返回原始顺序", e)
        return results[:top_k]
