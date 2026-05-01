"""
Four-level content extraction pipeline.
Inspired by local-deep-research's extraction architecture.

Pipeline:
  1. trafilatura (primary — best benchmarks, multilingual)
  2. newspaper3k (parallel — strong on news/forum pages)
  → pick higher quality_score winner
  3. readabilipy (fallback — Mozilla Readability DOM-level extraction)
  4. BeautifulSoup get_text (last resort)

Quality scoring: len(text) - boilerplate_count * 500
"""

import logging
import re
from typing import Optional

import httpx

from offgrid.core.network import get_httpx_kwargs

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Boilerplate keywords for quality scoring
_BOILERPLATE_KEYWORDS = [
    "cookie", "sign up", "newsletter", "subscribe",
    "accept all", "privacy policy", "terms of service",
    "登录", "注册", "隐私政策", "用户协议",
]

# Minimum content length to accept
MIN_CONTENT_LENGTH = 50
BOILERPLATE_PENALTY = 500


def _quality_score(text: Optional[str]) -> int:
    """Score extraction quality: length minus boilerplate penalty."""
    if not text:
        return 0
    lower = text.lower()
    boilerplate = sum(1 for kw in _BOILERPLATE_KEYWORDS if kw in lower)
    return len(text) - (boilerplate * BOILERPLATE_PENALTY)


def _extract_trafilatura(html: str) -> Optional[str]:
    """Level 1: trafilatura extraction."""
    try:
        import trafilatura
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        return result if result and result.strip() else None
    except ImportError:
        return None
    except Exception as e:
        logger.debug("[pipeline] trafilatura failed: %s", e)
        return None


def _extract_newspaper(html: str, url: str = "") -> Optional[str]:
    """Level 2: newspaper3k extraction (strong on news pages)."""
    try:
        from newspaper import Article
        article = Article(url or "http://example.com")
        article.set_html(html)
        article.parse()
        text = article.text
        return text if text and len(text.strip()) > MIN_CONTENT_LENGTH else None
    except ImportError:
        return None
    except Exception as e:
        logger.debug("[pipeline] newspaper failed: %s", e)
        return None


def _extract_readability(html: str) -> Optional[str]:
    """Level 3: readabilipy (Mozilla Readability) extraction."""
    try:
        from readabilipy import simple_json_from_html_string
        article = simple_json_from_html_string(html, use_readability=True)
        if not article:
            return None
        # Extract plain text from the HTML content
        content = article.get("content", "")
        if content:
            # Strip HTML tags from readability output
            text = re.sub(r"<[^>]+>", " ", content)
            text = re.sub(r"\s+", " ", text).strip()
            return text if len(text) > MIN_CONTENT_LENGTH else None
        # Try plain_text field
        plain = article.get("plain_text")
        if plain and isinstance(plain, list):
            text = "\n".join(p.get("text", "") for p in plain if p.get("text"))
            return text if len(text) > MIN_CONTENT_LENGTH else None
        return None
    except ImportError:
        return None
    except Exception as e:
        logger.debug("[pipeline] readability failed: %s", e)
        return None


def _extract_soup(html: str) -> Optional[str]:
    """Level 4: BeautifulSoup get_text (last resort)."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style/nav/footer
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text if len(text) > MIN_CONTENT_LENGTH else None
    except Exception as e:
        logger.debug("[pipeline] soup failed: %s", e)
        return None


def extract_content(html: str, url: str = "") -> Optional[str]:
    """
    Four-level extraction pipeline. Returns best quality content.

    Pipeline:
      1+2: trafilatura and newspaper run, pick higher score
      3: readabilipy fallback if both above fail
      4: soup.get_text() last resort
    """
    if not html or not html.strip():
        return None

    # Level 1+2: Run both, pick winner by quality score
    traf_result = _extract_trafilatura(html)
    news_result = _extract_newspaper(html, url)

    traf_score = _quality_score(traf_result)
    news_score = _quality_score(news_result)

    if traf_score >= news_score and traf_result:
        content = traf_result
    elif news_result:
        content = news_result
    else:
        content = traf_result

    if content and len(content.strip()) >= MIN_CONTENT_LENGTH:
        return content.strip()

    # Level 3: readabilipy fallback
    content = _extract_readability(html)
    if content and len(content.strip()) >= MIN_CONTENT_LENGTH:
        return content.strip()

    # Level 4: soup last resort
    content = _extract_soup(html)
    if content and len(content.strip()) >= MIN_CONTENT_LENGTH:
        return content.strip()

    return None


def fetch_and_extract(url: str, timeout: float = 8.0, max_chars: int = 800) -> str:
    """
    Fetch URL and extract content through the four-level pipeline.
    Returns compressed text ≤ max_chars. Empty string on failure.
    """
    try:
        kwargs = get_httpx_kwargs(min(timeout, 8.0))
        kwargs["headers"] = HEADERS
        kwargs["verify"] = False
        resp = httpx.get(url, **kwargs)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.debug("[pipeline] fetch failed %s: %s", url[:60], e)
        return ""

    content = extract_content(html, url)
    if not content:
        return ""

    # Compress to max_chars
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "..."
    return result
