#!/bin/sh
# KwCode 安装程序 - Mac/Linux
# 用法: curl -sSL https://raw.githubusercontent.com/offgrid-agent/offgrid/main/install.sh | sh
#   或: chmod +x install.sh && ./install.sh

set -e

# ── 颜色 ─────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m'

step()  { printf "  ${GREEN}[*]${NC} %s\n" "$1"; }
warn()  { printf "  ${YELLOW}[!]${NC} %s\n" "$1"; }
err()   { printf "  ${RED}[x]${NC} %s\n" "$1"; }
info()  { printf "      ${GRAY}%s${NC}\n" "$1"; }

# ── Banner ───────────────────────────────────────────────────
printf "\n"
printf "  ${CYAN}╔══════════════════════════════════════╗${NC}\n"
printf "  ${CYAN}║       KwCode 安装程序 v0.4            ║${NC}\n"
printf "  ${CYAN}║   本地模型 Coding Agent               ║${NC}\n"
printf "  ${CYAN}╚══════════════════════════════════════╝${NC}\n"
printf "\n"

# ── Step 1: Python 版本检查 ──────────────────────────────────
step "检查 Python 版本..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            info "找到 Python $ver ($cmd)"
            break
        else
            warn "Python $ver 版本过低，需要 >= 3.10"
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    err "未找到 Python >= 3.10"
    info "macOS:  brew install python@3.12"
    info "Ubuntu: sudo apt install python3.12"
    info "其他:   https://www.python.org/downloads/"
    exit 1
fi

# ── Step 2: GPU 检查 ─────────────────────────────────────────
step "检查 GPU..."

VRAM_MB=0
OS_TYPE=$(uname -s)

if [ "$OS_TYPE" = "Darwin" ]; then
    # macOS - 检查 Apple Silicon 统一内存
    chip=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "")
    if echo "$chip" | grep -qi "apple"; then
        mem_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
        VRAM_MB=$((mem_bytes / 1024 / 1024))
        info "Apple Silicon: $chip  统一内存: ${VRAM_MB}MB"
        info "（统一内存可共享给 GPU，实际可用约 75%）"
    else
        # Intel Mac
        gpu_info=$(system_profiler SPDisplaysDataType 2>/dev/null | grep -i "vram\|chipset" | head -2 || echo "")
        if [ -n "$gpu_info" ]; then
            info "GPU: $gpu_info"
        else
            warn "未检测到独立 GPU，将使用 CPU 模式"
        fi
    fi
else
    # Linux - 检查 NVIDIA GPU
    if command -v nvidia-smi >/dev/null 2>&1; then
        smi_output=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "")
        if [ -n "$smi_output" ]; then
            gpu_name=$(echo "$smi_output" | cut -d, -f1 | xargs)
            vram_str=$(echo "$smi_output" | grep -oE '[0-9]+' | tail -1)
            if [ -n "$vram_str" ]; then
                VRAM_MB=$vram_str
            fi
            info "GPU: $gpu_name  VRAM: ${VRAM_MB}MB"
        fi
    else
        warn "未检测到 NVIDIA GPU (nvidia-smi 不可用)"
        info "如有 AMD GPU，Ollama 也支持 ROCm"
    fi
fi

# ── Step 3: pip install offgrid ────────────────────────────────
step "安装 KwCode..."

INSTALLED=0

# 尝试默认源
info "尝试默认 pip 源..."
if "$PYTHON_CMD" -m pip install offgrid --quiet 2>/dev/null; then
    INSTALLED=1
    info "安装成功（默认源）"
fi

# 降级到清华镜像
if [ "$INSTALLED" -eq 0 ]; then
    warn "默认源安装失败，切换到清华镜像..."
    if "$PYTHON_CMD" -m pip install offgrid \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --trusted-host pypi.tuna.tsinghua.edu.cn \
        --quiet 2>/dev/null; then
        INSTALLED=1
        info "安装成功（清华镜像）"
    fi
fi

if [ "$INSTALLED" -eq 0 ]; then
    err "KwCode 安装失败"
    info "请手动执行: $PYTHON_CMD -m pip install offgrid"
    info "如果网络慢，加上: -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
fi

# ── Step 4: Ollama 检查 ──────────────────────────────────────
step "检查 Ollama..."

OLLAMA_OK=0
if command -v ollama >/dev/null 2>&1; then
    ollama_ver=$(ollama --version 2>&1 || echo "unknown")
    info "Ollama 已安装: $ollama_ver"
    OLLAMA_OK=1
else
    warn "未检测到 Ollama"
    info ""
    info "Ollama 是运行本地模型的推理引擎，请手动安装："
    if [ "$OS_TYPE" = "Darwin" ]; then
        info "  brew install ollama"
        info "  或: https://ollama.com/download"
    else
        info "  curl -fsSL https://ollama.com/install.sh | sh"
    fi
    info ""
    info "安装后重新运行本脚本即可自动拉取模型"
fi

# ── Step 5: 拉取推荐模型 ─────────────────────────────────────
if [ "$OLLAMA_OK" -eq 1 ]; then
    step "拉取推荐模型..."

    # 根据 VRAM 选择模型
    if [ "$VRAM_MB" -ge 16000 ]; then
        MODEL="qwen3:14b"
        info "VRAM >= 16GB，推荐模型: $MODEL"
    elif [ "$VRAM_MB" -ge 8000 ]; then
        MODEL="qwen3:8b"
        info "VRAM >= 8GB，推荐模型: $MODEL"
    else
        MODEL="gemma3:4b"
        if [ "$VRAM_MB" -gt 0 ]; then
            info "VRAM < 8GB，推荐模型: $MODEL"
        else
            info "未检测到 GPU，使用轻量模型: $MODEL"
        fi
    fi

    # 检测模型下载源
    step "检测模型下载源..."
    if curl -s --max-time 5 https://huggingface.co > /dev/null 2>&1; then
        info "HuggingFace 可达，使用默认源"
    else
        warn "HuggingFace 不可达，自动切换到 ModelScope"
        export OLLAMA_MODELS="https://modelscope.cn/models"
    fi

    info "正在拉取 $MODEL（首次下载可能需要几分钟）..."
    if ollama pull "$MODEL"; then
        info "模型 $MODEL 已就绪"
    else
        warn "模型拉取失败，请稍后手动执行: ollama pull $MODEL"
    fi
fi

# ── Step 5.5: SearXNG 搜索服务 ──────────────────────────────
step "启动搜索服务（SearXNG）..."

if command -v docker >/dev/null 2>&1; then
    # 已在运行则跳过
    if docker ps --format '{{.Names}}' | grep -q "^offgrid-searxng$"; then
        info "SearXNG 已在运行，跳过"
    elif docker ps -a --format '{{.Names}}' | grep -q "^offgrid-searxng$"; then
        docker start offgrid-searxng
        info "SearXNG 已重新启动"
    else
        info "拉取 SearXNG 镜像（约150MB）..."
        docker pull searxng/searxng
        docker run -d \
            --name offgrid-searxng \
            --restart always \
            -p 8080:8080 \
            searxng/searxng
        info "等待 SearXNG 启动..."
        for i in $(seq 1 15); do
            if curl -s http://localhost:8080 > /dev/null 2>&1; then
                info "SearXNG 已就绪：http://localhost:8080"
                break
            fi
            sleep 1
        done
    fi
else
    warn "未检测到 Docker，搜索增强将使用 DuckDuckGo 降级方案"
    info "安装 Docker 可获得更好的搜索体验：https://docs.docker.com/get-docker/"
fi

# ── Step 6: offgrid init ──────────────────────────────────────
step "初始化 KwCode..."

if command -v offgrid >/dev/null 2>&1; then
    offgrid init 2>/dev/null && info "KAIWU.md 已初始化" || info "跳过初始化（可稍后在项目目录执行 offgrid init）"
else
    info "offgrid 命令未在 PATH 中，跳过初始化"
    info "尝试: $PYTHON_CMD -m offgrid init"
fi

# ── Step 7: offgrid status ────────────────────────────────────
step "验证安装..."

if command -v offgrid >/dev/null 2>&1; then
    offgrid status || warn "状态检查失败，但安装可能已成功"
else
    "$PYTHON_CMD" -m offgrid status 2>/dev/null || warn "状态检查失败"
fi

# ── 完成 ─────────────────────────────────────────────────────
printf "\n"
printf "  ${GREEN}╔══════════════════════════════════════╗${NC}\n"
printf "  ${GREEN}║         安装完成!                     ║${NC}\n"
printf "  ${GREEN}╚══════════════════════════════════════╝${NC}\n"
printf "\n"
printf "  ${CYAN}下一步:${NC}\n"
printf "    1. cd 到你的项目目录\n"
printf "    2. offgrid init          # 初始化项目记忆\n"
printf "    3. offgrid               # 进入交互模式\n"
printf '    4. offgrid "修复登录bug"  # 直接执行任务\n'
printf "\n"
printf "  ${GRAY}文档: https://github.com/offgrid-agent/offgrid${NC}\n"
printf "\n"
