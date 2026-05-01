"""V8: 状态栏渲染验证"""

import sys
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from offgrid.cli.status_bar import StatusBar


def test_status_bar():
    bar = StatusBar()
    bar.model = "qwen3:8b"
    bar.ctx_used = 4200
    bar.ctx_max = 8192
    bar.compress_count = 3
    bar.tok_per_sec = 18.4
    bar.vram_used = 5.8
    bar.vram_total = 8.0
    bar.ram_used = 11.2
    bar.ram_total = 32.0

    for width in [55, 70, 85, 110]:
        rendered = bar.render(width)
        print(f"width={width}: {rendered}")
        assert len(rendered) <= width + 5, f"FAIL width={width}渲染超长: {len(rendered)}"

    print("V8 PASS")


if __name__ == "__main__":
    test_status_bar()
