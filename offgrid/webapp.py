from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from offgrid.core.network import detect_network
from offgrid.flywheel.trajectory_collector import TrajectoryCollector
from offgrid.llm.llama_backend import LLMBackend
from offgrid.registry.expert_registry import ExpertRegistry

app = FastAPI(title="OffGrid Web UI", version="0.7.0")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_COLLECTOR = TrajectoryCollector()
REGISTRY = ExpertRegistry()
try:
    REGISTRY.load_builtin()
    REGISTRY.load_user()
except Exception:
    pass

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class RunRequest(BaseModel):
    task: str = Field(..., min_length=1)
    model: str | None = None
    mode: str = "chat"


def _get_ollama_models() -> list[dict]:
    try:
        import requests
        return requests.get(f"{DEFAULT_OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
    except Exception:
        return []


def _pick_model(preferred: str | None = None) -> str:
    models = _get_ollama_models()
    names = [m.get("name", "") for m in models if m.get("name")]
    if preferred and preferred in names:
        return preferred
    if "huihui_ai/qwen3.5-abliterated:9b" in names:
        return "huihui_ai/qwen3.5-abliterated:9b"
    return names[0] if names else "huihui_ai/qwen3.5-abliterated:9b"


@app.get("/api/health")
def health() -> dict:
    net = detect_network()
    models = _get_ollama_models()
    names = [m.get("name", "") for m in models if m.get("name")]
    return {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "model": _pick_model(),
        "models": names,
        "base_url": DEFAULT_OLLAMA_URL,
        "china_network": net.get("china", False),
        "proxy": net.get("proxy"),
        "ddg_ok": net.get("ddg_ok", False),
        "hf_ok": net.get("hf_ok", False),
    }


@app.get("/api/models")
def get_models() -> dict:
    return {"models": _get_ollama_models()}


@app.get("/api/trajectories")
def get_trajectories(limit: int = 20) -> dict:
    items = TRAJECTORY_COLLECTOR.load_recent(limit=limit)
    return {"items": [asdict(x) for x in items]}


@app.post("/api/run")
def run_task(req: RunRequest) -> dict:
    model_name = _pick_model(req.model)
    llm = LLMBackend(ollama_url=DEFAULT_OLLAMA_URL, ollama_model=model_name)
    reply = llm.chat(
        [
            {"role": "system", "content": "你是OffGrid，一个简洁直接的本地 AI 助手。"},
            {"role": "user", "content": req.task},
        ],
        max_tokens=256,
        temperature=0.7,
    )
    return {"ok": True, "mode": req.mode, "task": req.task, "model": model_name, "reply": reply}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OffGrid</title>
  <style>
    :root { --bg:#0a1020; --panel:rgba(13,20,36,.76); --border:rgba(148,163,184,.16); --text:#e8f0ff; --muted:#8ea1c6; --accent:#7b9cff; --ok:#66e3a1; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; color:var(--text); font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background: radial-gradient(circle at top left, rgba(123,156,255,.16), transparent 28%), linear-gradient(180deg, #07101d, var(--bg)); }
    .shell { max-width: 1320px; margin:0 auto; padding:24px; }
    .topbar, .card { border:1px solid var(--border); background:var(--panel); backdrop-filter: blur(18px); box-shadow:0 18px 50px rgba(0,0,0,.32); }
    .topbar { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:18px 22px; border-radius:26px; }
    h1 { margin:0; font-size:32px; }
    .subtitle { color:var(--muted); margin-top:6px; }
    .chip { display:inline-flex; align-items:center; gap:10px; padding:12px 16px; border-radius:999px; background:rgba(102,227,161,.10); border:1px solid rgba(102,227,161,.18); font-weight:700; }
    .dot { width:10px; height:10px; border-radius:50%; background:var(--ok); box-shadow:0 0 0 6px rgba(102,227,161,.12); }
    .stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-top:16px; }
    .card { border-radius:22px; padding:18px; }
    .label { font-size:12px; text-transform:uppercase; letter-spacing:.14em; color:var(--muted); }
    .value { font-size:20px; font-weight:800; margin-top:10px; }
    .layout { display:grid; grid-template-columns: 1.45fr .75fr; gap:16px; margin-top:16px; align-items:start; }
    .chat { min-height:74vh; display:flex; flex-direction:column; overflow:hidden; }
    .chat-head { padding:18px 20px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); }
    .chat-title { font-size:17px; font-weight:800; }
    .chat-log { flex:1; overflow:auto; padding:18px; background:linear-gradient(180deg, rgba(10,16,32,.22), rgba(10,16,32,.06)); }
    .bubble { max-width:82%; padding:14px 16px; border-radius:18px; margin-bottom:14px; white-space:pre-wrap; line-height:1.55; }
    .user { margin-left:auto; background:linear-gradient(135deg, #3b82f6, #6f8cff); color:#fff; border-bottom-right-radius:6px; }
    .assistant { background:rgba(15,23,42,.92); border:1px solid var(--border); border-bottom-left-radius:6px; }
    .composer { padding:16px; border-top:1px solid var(--border); background:rgba(8,14,28,.70); }
    textarea { width:100%; min-height:88px; resize:vertical; border-radius:18px; border:1px solid rgba(148,163,184,.18); background:rgba(3,8,20,.6); color:var(--text); padding:14px 16px; font-size:15px; outline:none; }
    textarea:focus { border-color:rgba(123,156,255,.55); box-shadow:0 0 0 4px rgba(123,156,255,.12); }
    .actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
    .btn { border:0; border-radius:999px; padding:11px 16px; font-weight:800; cursor:pointer; color:#fff; background:linear-gradient(135deg, #5478ff, #7b9cff); }
    .btn.secondary { background:rgba(148,163,184,.12); border:1px solid rgba(148,163,184,.16); color:var(--text); }
    .side { display:flex; flex-direction:column; gap:16px; }
    .side h3 { margin:0 0 12px; font-size:16px; }
    .mini { color:var(--muted); font-size:13px; line-height:1.55; }
    pre { margin:0; white-space:pre-wrap; word-break:break-word; background:rgba(3,8,20,.56); border:1px solid var(--border); padding:14px; border-radius:16px; color:#d9e6ff; }
    .list { display:flex; flex-direction:column; gap:10px; }
    select { width:100%; background:rgba(3,8,20,.6); color:var(--text); border:1px solid rgba(148,163,184,.18); border-radius:14px; padding:10px; }
    @media (max-width: 1080px) { .stats, .layout { grid-template-columns:1fr; } .bubble { max-width:100%; } }
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div>
        <h1>OffGrid</h1>
        <div class="subtitle">Gemini-style chat workspace · 直接接 Ollama</div>
      </div>
      <div class="chip"><span class="dot"></span><span id="svc">Running</span></div>
    </div>

    <div class="stats">
      <div class="card"><div class="label">模型</div><div class="value" id="model">-</div></div>
      <div class="card"><div class="label">Base URL</div><div class="value" id="base-url">-</div></div>
      <div class="card"><div class="label">网络</div><div class="value" id="network">-</div></div>
      <div class="card"><div class="label">轨迹</div><div class="value" id="traj-count">-</div></div>
    </div>

    <div class="layout">
      <div class="card chat">
        <div class="chat-head">
          <div>
            <div class="chat-title">对话</div>
            <div class="mini">直接用 Ollama 里当前可用模型。</div>
          </div>
          <div class="chip" style="padding:8px 12px; font-size:13px;">Ollama 集成</div>
        </div>
        <div id="log" class="chat-log"></div>
        <div class="composer">
          <textarea id="task" placeholder="输入一句话，开始和 OffGrid 对话..."></textarea>
          <div class="actions">
            <button class="btn" onclick="send()">发送</button>
            <button class="btn secondary" onclick="refreshAll()">刷新状态</button>
            <button class="btn secondary" onclick="preset('你好，先自我介绍一下')">示例 1</button>
            <button class="btn secondary" onclick="preset('如果要清洗机械键盘，但是不想拆键帽，有什么办法')">示例 2</button>
          </div>
        </div>
      </div>

      <div class="side">
        <div class="card">
          <h3>当前状态</h3>
          <div class="list">
            <div class="mini">• 服务：<span id="svc2">-</span></div>
            <div class="mini">• 模型：<span id="model2">-</span></div>
            <div class="mini">• 运行模式：对话优先 / 复杂任务后置</div>
            <div class="mini">• 模型来自 Ollama /api/tags 自动读取</div>
          </div>
        </div>
        <div class="card">
          <h3>Ollama 模型</h3>
          <select id="modelSelect" onchange="chooseModel()"></select>
        </div>
        <div class="card">
          <h3>最近轨迹</h3>
          <pre id="traj">加载中...</pre>
        </div>
        <div class="card">
          <h3>执行回包</h3>
          <pre id="run-result">等待输入...</pre>
        </div>
      </div>
    </div>
  </div>

<script>
const log = document.getElementById('log');
let currentModel = '';
function bubble(text, cls) { const d = document.createElement('div'); d.className = 'bubble ' + cls; d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; }
function preset(t) { document.getElementById('task').value = t; }
async function refreshAll() {
  const h = await fetch('/api/health').then(r => r.json());
  currentModel = h.model || '-';
  document.getElementById('model').textContent = currentModel;
  document.getElementById('model2').textContent = currentModel;
  document.getElementById('base-url').textContent = h.base_url || '-';
  document.getElementById('network').textContent = `${h.china_network ? 'CN' : 'Global'} · DDG ${h.ddg_ok ? 'Y' : 'N'} · HF ${h.hf_ok ? 'Y' : 'N'}`;
  document.getElementById('svc').textContent = h.ok ? 'Running' : 'Down';
  document.getElementById('svc2').textContent = h.ok ? 'Running' : 'Down';
  const t = await fetch('/api/trajectories?limit=5').then(r => r.json());
  document.getElementById('traj').textContent = JSON.stringify(t, null, 2);
  document.getElementById('traj-count').textContent = String((t.items || []).length);
  const sel = document.getElementById('modelSelect');
  sel.innerHTML = '';
  const models = (h.models || []);
  models.forEach(m => { const o = document.createElement('option'); o.value = m; o.textContent = m; if (m === currentModel) o.selected = true; sel.appendChild(o); });
}
async function chooseModel() {
  currentModel = document.getElementById('modelSelect').value;
  document.getElementById('model').textContent = currentModel;
  document.getElementById('model2').textContent = currentModel;
}
async function send() {
  const task = document.getElementById('task').value.trim();
  if (!task) return;
  bubble(task, 'user');
  document.getElementById('task').value = '';
  const res = await fetch('/api/run', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({task, model: currentModel || null, mode:'chat'}) }).then(r => r.json());
  bubble(res.reply || JSON.stringify(res), 'assistant');
  document.getElementById('run-result').textContent = JSON.stringify(res, null, 2);
}
refreshAll();
</script>
</body>
</html>
"""
