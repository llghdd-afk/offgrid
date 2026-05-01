"""
状态栏数据容器 + 渲染器 + tok/s 估算器。

状态栏通过 prompt_toolkit 的 bottom_toolbar 常驻显示，
这里只负责数据和渲染文本，不做终端控制。
"""

import psutil


class StatusBar:
    """状态栏数据容器 + 渲染器。"""

    def __init__(self):
        self.model: str = ""
        self.ctx_used: int = 0
        self.ctx_max: int = 8192
        self.compress_count: int = 0
        self.tok_per_sec: float = 0.0
        self.vram_used: float = 0.0
        self.vram_total: float = 0.0
        self.ram_used: float = 0.0
        self.ram_total: float = 0.0

    def refresh_ram(self):
        """刷新RAM数据（开销极低）。"""
        try:
            vm = psutil.virtual_memory()
            self.ram_used = vm.used / 1024**3
            self.ram_total = vm.total / 1024**3
        except Exception:
            pass

    def render(self, width: int) -> str:
        """根据终端宽度渲染状态栏纯文本。"""
        pct = self.ctx_used / max(self.ctx_max, 1)
        ctx_k = self.ctx_used / 1000
        max_k = self.ctx_max / 1000

        bar_w = 6
        filled = int(pct * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)

        compress = f"压缩×{self.compress_count}" if self.compress_count > 0 else ""

        if width >= 100:
            p = [f"⚡ {self.model}"]
            p.append(f"ctx {ctx_k:.1f}K/{max_k:.0f}K {bar} {pct*100:.0f}%")
            if compress:
                p.append(compress)
            p.append(f"{self.tok_per_sec:.1f} tok/s")
            if self.vram_total > 0:
                p.append(f"VRAM {self.vram_used:.1f}G/{self.vram_total:.0f}G")
            p.append(f"RAM {self.ram_used:.1f}G/{self.ram_total:.0f}G")
            return " │ ".join(p)

        elif width >= 80:
            p = [f"⚡ {self.model}"]
            p.append(f"ctx {ctx_k:.1f}K/{max_k:.0f}K {pct*100:.0f}%")
            if compress:
                p.append(compress)
            p.append(f"{self.tok_per_sec:.0f}t/s")
            if self.vram_total > 0:
                p.append(f"VRAM {self.vram_used:.1f}G")
            return " │ ".join(p)

        elif width >= 60:
            p = [f"ctx {ctx_k:.1f}K/{max_k:.0f}K"]
            if compress:
                p.append(compress)
            p.append(f"{self.tok_per_sec:.0f}t/s")
            return " │ ".join(p)

        else:
            return f"{ctx_k:.1f}K/{max_k:.0f}K tokens"


class TokPerSecEstimator:
    """模糊计算 tok/s，EMA平滑，不依赖Ollama eval_rate。"""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self._ema_tps: float = 0.0

    def record(self, output_text: str, elapsed_sec: float):
        if elapsed_sec <= 0:
            return
        tokens = _estimate_tokens(output_text)
        tps = tokens / elapsed_sec
        if self._ema_tps == 0:
            self._ema_tps = tps
        else:
            self._ema_tps = self.alpha * tps + (1 - self.alpha) * self._ema_tps

    @property
    def value(self) -> float:
        return round(self._ema_tps, 1)


def _estimate_tokens(text: str) -> int:
    """粗估 token 数。中文 ~1.5 字/token，英文 ~4 字符/token。"""
    cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    en = len(text) - cn
    return int(cn * 1.5 + en / 4)
