"""
网络环境探测 + 代理配置。
所有 httpx 调用统一从这里获取 client 配置。

探测逻辑：
  1. 读环境变量 KAIWU_PROXY > HTTPS_PROXY > HTTP_PROXY
  2. 读 ~/.offgrid/config.yaml 的 proxy 字段
  3. 探测 DDG 是否可达（3s timeout）→ 判断是否国内网络
  4. 缓存结果，整个 session 只探测一次
"""

import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Session-level cache
_network_cache: Optional[dict] = None


def get_proxy() -> Optional[str]:
    """
    从环境变量或 config 读取代理地址。
    优先级：KAIWU_PROXY > HTTPS_PROXY > HTTP_PROXY > ~/.offgrid/config.yaml
    """
    for var in ("KWCODE_PROXY", "KAIWU_PROXY", "HTTPS_PROXY", "HTTP_PROXY",
                "offgrid_proxy", "offgrid_proxy", "https_proxy", "http_proxy"):
        val = os.environ.get(var)
        if val:
            return val

    # Try ~/.offgrid/config.yaml first, then legacy ~/.offgrid/config.yaml
    for dirname in (".offgrid", ".offgrid"):
        config_path = os.path.join(Path.home(), dirname, "config.yaml")
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                proxy = cfg.get("proxy")
                if not proxy:
                    # Also check nested default.proxy
                    default = cfg.get("default", {})
                    if isinstance(default, dict):
                        proxy = default.get("proxy")
                if proxy:
                    return proxy
            except Exception:
                pass

    return None


def _probe_url(url: str, timeout: float = 3.0) -> bool:
    """测试 URL 是否可达（HEAD 请求，不下载内容）。"""
    try:
        proxy = get_proxy()
        kwargs = {"timeout": timeout, "follow_redirects": True}
        if proxy:
            kwargs["proxy"] = proxy
        resp = httpx.head(url, **kwargs)
        return resp.status_code < 500
    except Exception:
        return False


def detect_network(force: bool = False) -> dict:
    """
    探测网络环境，返回：
    {
        "china": bool,       # 是否国内网络（DDG不通）
        "proxy": str|None,   # 代理地址
        "ddg_ok": bool,      # DuckDuckGo 可达
        "hf_ok": bool,       # HuggingFace 可达
    }
    结果缓存，整个 session 只探测一次（除非 force=True）。
    """
    global _network_cache
    if _network_cache is not None and not force:
        return _network_cache

    proxy = get_proxy()
    ddg_ok = _probe_url("https://html.duckduckgo.com/html/")
    hf_ok = _probe_url("https://huggingface.co")
    china = not ddg_ok

    _network_cache = {
        "china": china,
        "proxy": proxy,
        "ddg_ok": ddg_ok,
        "hf_ok": hf_ok,
    }

    if china:
        logger.info("[network] 检测到国内网络 (DDG=%s, HF=%s, proxy=%s)",
                     ddg_ok, hf_ok, "yes" if proxy else "no")
    else:
        logger.debug("[network] 海外网络 (DDG=ok, HF=%s)", hf_ok)

    return _network_cache


def get_httpx_kwargs(timeout: float = 10.0) -> dict:
    """
    返回 httpx.Client / httpx.get / httpx.post 的通用 kwargs。
    包含 proxy、timeout、follow_redirects。
    """
    kwargs: dict = {
        "timeout": timeout,
        "follow_redirects": True,
    }
    proxy = get_proxy()
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def is_china_network() -> bool:
    """快速判断是否国内网络（使用缓存）。"""
    return detect_network().get("china", False)
