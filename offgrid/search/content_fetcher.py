"""
页面正文提取。使用四级提取管道替代单一trafilatura。
主路径：extraction_pipeline（trafilatura→newspaper→readability→soup）。
"""

import logging

from offgrid.search.extraction_pipeline import fetch_and_extract

logger = logging.getLogger(__name__)


class ContentFetcher:
    """页面正文提取器。四级管道提取。"""

    def fetch(self, url: str, timeout: float = 8.0) -> str:
        """提取单个URL正文，≤800字。任何异常返回空字符串。"""
        return fetch_and_extract(url, timeout=timeout, max_chars=800)

    def fetch_many(self, urls: list[str], timeout: float = 8.0) -> list[str]:
        return [self.fetch(url, timeout) for url in urls]
