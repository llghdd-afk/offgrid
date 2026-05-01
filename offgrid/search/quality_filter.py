"""
搜索结果质量过滤器：基于域名的优先级排序 + 黑名单过滤。
优先域名排前面，屏蔽域名直接移除，最多返回 max_fetch 条。
"""

from urllib.parse import urlparse

# 高质量域名（匹配顺序即优先级）
PRIORITY_DOMAINS = [
    "github.com",
    "stackoverflow.com",
    "docs.python.org",
    "pytorch.org",
    "huggingface.co",
    "arxiv.org",
    "pypi.org",
    "developer.mozilla.org",
    "learn.microsoft.com",
    "numpy.org",
    "pandas.pydata.org",
    "docs.rs",
]

# 屏蔽域名（低质量 / 社交媒体 / 内容农场）
BLOCKED_DOMAINS = [
    "csdn.net",
    "baidu.com",
    "zhihu.com",
    "weibo.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "reddit.com",
    "tiktok.com",
    "pinterest.com",
    "medium.com",
    "quora.com",
]


def _extract_domain(url: str) -> str:
    """提取 URL 的主域名（去掉 www. 前缀）。"""
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.")
    except Exception:
        return ""


def _is_blocked(domain: str) -> bool:
    """检查域名是否在黑名单中（支持子域名匹配）。"""
    return any(domain == bd or domain.endswith(f".{bd}") for bd in BLOCKED_DOMAINS)


def _priority_score(domain: str) -> int:
    """优先域名返回其索引（越小越优先），非优先域名返回一个大值。"""
    for i, pd in enumerate(PRIORITY_DOMAINS):
        if domain == pd or domain.endswith(f".{pd}"):
            return i
    return len(PRIORITY_DOMAINS)


def filter_results(results: list[dict], max_fetch: int = 3) -> list[dict]:
    """
    过滤并排序搜索结果。

    Args:
        results: [{"url": ..., "title": ..., "snippet": ...}, ...]
        max_fetch: 最多返回条数

    Returns:
        过滤 + 排序后的结果列表
    """
    filtered = []
    for r in results:
        url = r.get("url", "")
        domain = _extract_domain(url)
        if not domain or _is_blocked(domain):
            continue
        filtered.append((r, _priority_score(domain)))

    # 按优先级排序（分数相同保持原始顺序）
    filtered.sort(key=lambda x: x[1])
    return [r for r, _ in filtered[:max_fetch]]
