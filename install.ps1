# KwCode 安装程序 - Windows PowerShell
# 用法: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ── Banner ───────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║       KwCode 安装程序 v0.4            ║" -ForegroundColor Cyan
Write-Host "  ║   本地模型 Coding Agent               ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Helper ───────────────────────────────────────────────────
function Write-Step($msg) { Write-Host "  [*] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [x] $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "      $msg" -ForegroundColor Gray }

# ── Step 1: Python 版本检查 ──────────────────────────────────
Write-Step "检查 Python 版本..."

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonCmd = $cmd
                Write-Info "找到 $ver ($cmd)"
                break
            } else {
                Write-Warn "$ver 版本过低，需要 >= 3.10"
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Err "未找到 Python >= 3.10"
    Write-Info "请从 https://www.python.org/downloads/ 下载安装"
    Write-Info "安装时请勾选 'Add Python to PATH'"
    exit 1
}

# ── Step 2: GPU 检查 ─────────────────────────────────────────
Write-Step "检查 GPU..."

$vramMB = 0
try {
    $smiOutput = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0 -and $smiOutput -match "(\d+)\s*MiB") {
        $vramMB = [int]$Matches[1]
        $gpuName = ($smiOutput -split ",")[0].Trim()
        Write-Info "GPU: $gpuName  VRAM: $($vramMB)MB"
    } else {
        Write-Warn "未检测到 NVIDIA GPU，将使用 CPU 模式（速度较慢）"
    }
} catch {
    Write-Warn "nvidia-smi 不可用，将使用 CPU 模式"
}

# ── Step 3: pip install offgrid ────────────────────────────────
Write-Step "安装 KwCode..."

$installed = $false

# 尝试默认源
Write-Info "尝试默认 pip 源..."
& $pythonCmd -m pip install offgrid --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    $installed = $true
    Write-Info "安装成功（默认源）"
}

# 降级到清华镜像
if (-not $installed) {
    Write-Warn "默认源安装失败，切换到清华镜像..."
    & $pythonCmd -m pip install offgrid -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $installed = $true
        Write-Info "安装成功（清华镜像）"
    }
}

if (-not $installed) {
    Write-Err "KwCode 安装失败"
    Write-Info "请手动执行: $pythonCmd -m pip install offgrid"
    Write-Info "如果网络慢，加上: -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
}

# ── Step 4: Ollama 检查 ──────────────────────────────────────
Write-Step "检查 Ollama..."

$ollamaOk = $false
try {
    $ollamaVer = & ollama --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Info "Ollama 已安装: $ollamaVer"
        $ollamaOk = $true
    }
} catch {}

if (-not $ollamaOk) {
    Write-Warn "未检测到 Ollama"
    Write-Info ""
    Write-Info "Ollama 是运行本地模型的推理引擎，请手动安装："
    Write-Info "  下载地址: https://ollama.com/download"
    Write-Info "  安装后重新运行本脚本即可自动拉取模型"
    Write-Info ""
}

# ── Step 5: 拉取推荐模型 ─────────────────────────────────────
if ($ollamaOk) {
    Write-Step "拉取推荐模型..."

    # 根据 VRAM 选择模型
    if ($vramMB -ge 16000) {
        $model = "qwen3:14b"
        Write-Info "VRAM >= 16GB，推荐模型: $model"
    } elseif ($vramMB -ge 8000) {
        $model = "qwen3:8b"
        Write-Info "VRAM >= 8GB，推荐模型: $model"
    } else {
        $model = "gemma3:4b"
        if ($vramMB -gt 0) {
            Write-Info "VRAM < 8GB，推荐模型: $model"
        } else {
            Write-Info "未检测到 GPU，使用轻量模型: $model"
        }
    }

    # 检查 ModelScope 镜像（国内加速）
    Write-Step "检测模型下载源..."
    $hfOk = $false
    try {
        $r = Invoke-WebRequest -Uri "https://huggingface.co" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        $hfOk = $true
        Write-Info "HuggingFace 可达，使用默认源"
    } catch {
        Write-Warn "HuggingFace 不可达，自动切换到 ModelScope"
        $env:OLLAMA_MODELS = "https://modelscope.cn/models"
    }

    Write-Info "正在拉取 $model（首次下载可能需要几分钟）..."
    & ollama pull $model
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "模型拉取失败，请稍后手动执行: ollama pull $model"
    } else {
        Write-Info "模型 $model 已就绪"
    }
}

# ── Step 5.5: SearXNG 搜索服务 ──────────────────────────────
Write-Step "启动搜索服务（SearXNG）..."

if (Get-Command docker -ErrorAction SilentlyContinue) {
    $running = docker ps --format '{{.Names}}' | Where-Object { $_ -eq "offgrid-searxng" }
    if ($running) {
        Write-Info "SearXNG 已在运行，跳过"
    } else {
        $exists = docker ps -a --format '{{.Names}}' | Where-Object { $_ -eq "offgrid-searxng" }
        if ($exists) {
            docker start offgrid-searxng
            Write-Info "SearXNG 已重新启动"
        } else {
            Write-Info "拉取 SearXNG 镜像（约150MB）..."
            docker pull searxng/searxng
            docker run -d --name offgrid-searxng --restart always -p 8080:8080 searxng/searxng
            Write-Info "等待 SearXNG 启动..."
            for ($i = 1; $i -le 15; $i++) {
                try {
                    $null = Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 2 -UseBasicParsing
                    Write-Info "SearXNG 已就绪：http://localhost:8080"
                    break
                } catch { Start-Sleep -Seconds 1 }
            }
        }
    }
} else {
    Write-Warn "未检测到 Docker，搜索增强将使用 DuckDuckGo 降级方案"
    Write-Info "安装 Docker 可获得更好的搜索体验：https://docs.docker.com/get-docker/"
}

# ── Step 6: offgrid init ──────────────────────────────────────
Write-Step "初始化 KwCode..."

try {
    & offgrid init 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Info "KAIWU.md 已初始化"
    }
} catch {
    Write-Info "跳过初始化（可稍后在项目目录执行 offgrid init）"
}

# ── Step 7: offgrid status ────────────────────────────────────
Write-Step "验证安装..."

try {
    & offgrid status
} catch {
    Write-Warn "状态检查失败，但安装可能已成功"
    Write-Info "请手动执行: offgrid status"
}

# ── 完成 ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║         安装完成!                     ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  下一步:" -ForegroundColor Cyan
Write-Host "    1. cd 到你的项目目录" -ForegroundColor White
Write-Host "    2. offgrid init          # 初始化项目记忆" -ForegroundColor White
Write-Host "    3. offgrid               # 进入交互模式" -ForegroundColor White
Write-Host '    4. offgrid "修复登录bug"  # 直接执行任务' -ForegroundColor White
Write-Host ""
Write-Host "  文档: https://github.com/offgrid-agent/offgrid" -ForegroundColor Gray
Write-Host ""
