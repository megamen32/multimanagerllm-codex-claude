#!/usr/bin/env python3
import json, os, shutil, socket, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime

APP_NAME = "MultiManager"
HOME = Path.home()
CONFIG_DIR = HOME / ".multimanager"
CONFIG_FILE = CONFIG_DIR / "config.json"
BACKUP_DIR = CONFIG_DIR / "backups"

CLAUDE_DESKTOP_DIR = HOME / "Library" / "Application Support"
CLAUDE_CODE_SETTINGS = HOME / ".claude" / "settings.json"
CODEX_CONFIG = HOME / ".codex" / "config.toml"
CODEX_AUTH = HOME / ".codex" / "auth.json"

SKILL_ROOTS_DEFAULT = [
    HOME / ".claude" / "skills",
    HOME / ".codex" / "skills",
    HOME / ".agents" / "skills",
    HOME / ".opencode" / "skills",
]

DEFAULT_CONFIG = {
    "claude_desktop_profiles": {},
    "claude_code_presets": {"z.ai": {}, "standard": {}},
    "codex_profiles": {},
    "codex_endpoint": "",
    "skills_master": str(HOME / ".agents" / "skills"),
    "skills_targets": [],
    "custom_roots": [],
    "scenes": {},
    "auto_backup": True,
}

# ============================================================
# HTML
# ============================================================

html = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MultiManager</title>
<style>
*{box-sizing:border-box}
:root{--bg:#0b1020;--card:#131a30;--card2:#18213d;--text:#edf2ff;--muted:#9aa8c7;--accent:#8b5cf6;--accent2:#22c55e;--danger:#ef4444;--warning:#f59e0b;--border:#2a3558}
body{margin:0;background:radial-gradient(circle at top left,#26335d 0,#0b1020 45%,#080b14 100%);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Arial,sans-serif;min-height:100vh}
.wrap{max-width:1200px;margin:0 auto;padding:24px}
.hero{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:20px}
.title{font-size:36px;font-weight:800;letter-spacing:-.04em;background:linear-gradient(135deg,#c4b5fd,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:var(--muted);font-size:14px;margin-top:6px}
.pill{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border:1px solid var(--border);border-radius:999px;background:rgba(255,255,255,.04);color:#cbd5e1;font-size:13px}
.tabs{display:flex;gap:4px;margin-bottom:18px;flex-wrap:wrap}
.tab{padding:10px 20px;border:1px solid var(--border);border-radius:12px 12px 0 0;background:rgba(255,255,255,.04);color:var(--muted);cursor:pointer;font-size:14px;font-weight:600;transition:all .15s}
.tab:hover{background:rgba(139,92,246,.1);color:var(--text)}
.tab.active{background:var(--accent);color:white;border-color:var(--accent)}
.tab-content{display:none}
.tab-content.active{display:block}
.card{background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.025));border:1px solid var(--border);border-radius:18px;padding:20px;margin-bottom:16px;box-shadow:0 20px 60px rgba(0,0,0,.22);backdrop-filter:blur(12px)}
.card h2{margin:0 0 14px;font-size:18px;display:flex;align-items:center;gap:10px}
.card h3{margin:14px 0 8px;font-size:15px;color:#cbd5e1}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.btn{border:0;border-radius:10px;padding:9px 16px;background:var(--accent);color:white;font-weight:700;cursor:pointer;font-size:13px;transition:all .12s}
.btn:hover{filter:brightness(1.15)}
.btn.secondary{background:#24304f;color:#dbe7ff;border:1px solid var(--border)}
.btn.green{background:var(--accent2);color:#052e16}
.btn.red{background:var(--danger)}
.btn.warning{background:var(--warning);color:#1a1a1a}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-sm{padding:5px 10px;font-size:12px}
input[type=text],input[type=url],input[type=password],select,textarea{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:#0d1325;color:var(--text);outline:none;font-size:13px}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
label{display:block;color:#cbd5e1;font-size:13px;margin:10px 0 4px}
.list{display:flex;flex-direction:column;gap:6px;max-height:350px;overflow:auto;padding-right:4px}
.item{border:1px solid var(--border);background:rgba(10,16,32,.74);border-radius:12px;padding:10px 14px;display:flex;gap:10px;align-items:center;justify-content:space-between}
.item .info{flex:1}
.item .name{font-weight:700;font-size:14px}
.item .path{font-size:11px;color:var(--muted);word-break:break-all;margin-top:2px}
.item .tag{font-size:11px;background:var(--accent);color:white;border-radius:999px;padding:2px 8px;margin-left:6px}
.item .tag.green{background:var(--accent2);color:#052e16}
.item .tag.warning{background:var(--warning);color:#1a1a1a}
.item .tag.danger{background:var(--danger)}
.item .actions{display:flex;gap:6px;flex-shrink:0}
.dual{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.triple{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.log{background:#080c16;border:1px solid var(--border);border-radius:12px;padding:14px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:300px;overflow:auto;color:#a8b8d8;margin-top:10px;line-height:1.5}
.footer{text-align:center;color:var(--muted);font-size:12px;margin-top:30px;padding:16px;border-top:1px solid var(--border)}
code{background:rgba(139,92,246,.15);padding:1px 5px;border-radius:4px;font-size:12px}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.green{background:var(--accent2)}
.status-dot.yellow{background:var(--warning)}
.status-dot.red{background:var(--danger)}
.empty-state{color:var(--muted);text-align:center;padding:24px;font-size:14px}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:100;align-items:center;justify-content:center}
.modal-overlay.show{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:24px;max-width:550px;width:90%;max-height:80vh;overflow:auto}
.modal h2{margin:0 0 14px}
.env-row{display:flex;gap:8px;margin-bottom:6px;align-items:center}
.env-row input{flex:1}
@media(max-width:700px){.dual,.triple{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div><div class="title">MultiManager</div><div class="subtitle">Управление профилями Claude Desktop, Claude Code, Codex + синхронизация skills</div></div>
    <div class="pill" id="statusBar">готов</div>
  </div>

  <div class="tabs" id="tabs">
    <div class="tab active" data-tab="profiles">Профили</div>
    <div class="tab" data-tab="scenes">Сцены</div>
    <div class="tab" data-tab="skills">Skills</div>
    <div class="tab" data-tab="codex-endpoint">Codex endpoint</div>
    <div class="tab" data-tab="mcp">MCP</div>
    <div class="tab" data-tab="plugins">Плагины</div>
    <div class="tab" data-tab="settings">Настройки</div>
  </div>

  <!-- ========== TAB: PROFILES ========== -->
  <div class="tab-content active" id="tab-profiles">
    <div class="dual">
      <div class="card">
        <h2><span class="status-dot green"></span>Claude Desktop</h2>
        <div class="row" style="margin-bottom:10px">
          <button class="btn btn-sm" onclick="cdSave()">Сохранить текущий</button>
          <button class="btn btn-sm secondary" onclick="cdRefresh()">Обновить</button>
        </div>
        <div id="cdProfiles" class="list"><div class="empty-state">Загрузка...</div></div>
      </div>

      <div class="card">
        <h2><span class="status-dot green"></span>Claude Code (CLI)</h2>
        <div class="row" style="margin-bottom:10px">
          <button class="btn btn-sm" onclick="ccSave()">Сохранить текущий как</button>
          <input id="ccNewName" type="text" placeholder="имя пресета" style="width:140px;display:inline-block;padding:6px 10px">
          <button class="btn btn-sm secondary" onclick="ccRefresh()">Обновить</button>
        </div>
        <div id="ccPresets" class="list"><div class="empty-state">Загрузка...</div></div>
      </div>
    </div>

    <div class="card">
      <h2><span class="status-dot yellow"></span>Codex</h2>
      <div class="row" style="margin-bottom:10px">
        <button class="btn btn-sm" onclick="cxSave()">Сохранить текущий как</button>
        <input id="cxNewName" type="text" placeholder="имя профиля" style="width:140px;display:inline-block;padding:6px 10px">
        <button class="btn btn-sm secondary" onclick="cxRefresh()">Обновить</button>
      </div>
      <div id="cxProfiles" class="list"><div class="empty-state">Загрузка...</div></div>
    </div>
  </div>

  <!-- ========== TAB: SCENES ========== -->
  <div class="tab-content" id="tab-scenes">
    <div class="dual">
      <div class="card">
        <h2><span class="status-dot green"></span>Сцены</h2>
        <p style="color:var(--muted);font-size:13px;margin:0 0 12px">
          Сцена = комбинация профилей для всех инструментов сразу.<br>
          Один клик — переключить Claude Desktop + Claude Code + Codex.
        </p>
        <div class="row" style="margin-bottom:10px">
          <button class="btn" onclick="sceneSave()">Сохранить текущее как сцену</button>
          <input id="sceneNewName" type="text" placeholder="имя сцены" style="width:160px;display:inline-block;padding:6px 10px">
        </div>
        <div id="scenesList" class="list"><div class="empty-state">Загрузка...</div></div>
      </div>
      <div class="card">
        <h2>Quick Launch</h2>
        <p style="color:var(--muted);font-size:13px;margin:0 0 12px">
          Сгенерировать bash-команды для запуска инструментов<br>с текущими профилями прямо из терминала.
        </p>
        <button class="btn" onclick="qlGenerate()">Сгенерировать</button>
        <div id="qlOutput" class="log" style="margin-top:10px">Нажми «Сгенерировать».</div>
      </div>
    </div>
    <div class="card">
      <h2>Быстрое переключение</h2>
      <p style="color:var(--muted);font-size:13px;margin:0">
        <code>multimanager scene &lt;name&gt;</code> — CLI-команда для переключения сцены из терминала.<br>
        Сцена сохраняется в <code>~/.multimanager/config.json</code>.
      </p>
    </div>
  </div>

  <!-- ========== TAB: SKILLS ========== -->
  <div class="tab-content" id="tab-skills">
    <div class="dual">
      <div class="card">
        <h2>1. Папки со skills</h2>
        <div class="row">
          <button class="btn" onclick="skScan()">Сканировать</button>
          <button class="btn secondary" onclick="skSelectAll()">Выбрать все</button>
        </div>
        <label>Добавить папку вручную</label>
        <div class="row">
          <input id="skCustomRoot" type="text" placeholder="/path/to/skills" style="flex:1">
          <button class="btn secondary" onclick="skAddRoot()">Добавить</button>
        </div>
        <div id="skRoots" class="list"><div class="empty-state">Нажми «Сканировать»</div></div>
      </div>
      <div class="card">
        <h2>2. Источник (master)</h2>
        <label>Master skills folder</label>
        <select id="skSource" style="margin-bottom:12px"></select>
        <div id="skSkillsList" class="list"><div class="empty-state">Выбери источник</div></div>
      </div>
    </div>
    <div class="card">
      <h2>3. Синхронизация</h2>
      <div class="row">
        <button class="btn green" onclick="skSync(false)">Скопировать skills</button>
        <button class="btn secondary" onclick="skSync(true)">Dry run</button>
        <label style="display:inline-flex;align-items:center;gap:6px;margin:0;font-size:13px">
          <input id="skOverwrite" type="checkbox"> backup конфликтов
        </label>
        <label style="display:inline-flex;align-items:center;gap:6px;margin:0;font-size:13px">
          <input id="skSymlink" type="checkbox"> symlink (не copy)
        </label>
      </div>
      <p style="font-size:12px;color:var(--muted);margin:8px 0 0">
        Claude Desktop skills всегда копируются (symlink не работает).
      </p>
      <div id="skLog" class="log">Нажми «Сканировать» чтобы начать.</div>
    </div>
    <div class="card">
      <h2>4. Сравнение skills (diff)</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 10px">
        Сравнить <code>SKILL.md</code> в master и targets. Покажет какие файлы новее и diff.
      </p>
      <div class="row">
        <button class="btn warning" onclick="skDiff()">Сравнить все</button>
        <button class="btn secondary" onclick="skDiffClear()">Очистить</button>
      </div>
      <div id="skDiffResults" class="log" style="margin-top:10px">Нажми «Сравнить все».</div>
    </div>
  </div>

  <!-- ========== TAB: CODEX ENDPOINT ========== -->
  <div class="tab-content" id="tab-codex-endpoint">
    <div class="card">
      <h2>Codex Custom API Endpoint</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 12px">
        Укажи кастомный endpoint для Codex, например <code>https://llm.bezrabotnyi.com/v1</code>.
        Устанавливает <code>OPENAI_BASE_URL</code>.
      </p>
      <label>API Endpoint URL</label>
      <div class="row">
        <input id="cxEndpoint" type="url" placeholder="https://llm.bezrabotnyi.com/v1" style="flex:1">
        <button class="btn" onclick="cxSetEndpoint()">Установить</button>
        <button class="btn secondary" onclick="cxClearEndpoint()">Сбросить</button>
      </div>
      <div id="cxEndpointStatus" style="margin-top:10px;font-size:13px">Загрузка...</div>
    </div>
    <div class="card">
      <h2>Codex Wrapper Script</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 12px">
        Создаёт <code>~/.local/bin/codex-wrapper</code> с <code>OPENAI_BASE_URL</code>.
      </p>
      <button class="btn" onclick="cxCreateWrapper()">Создать wrapper</button>
      <div id="cxWrapperStatus" style="margin-top:10px;font-size:13px"></div>
    </div>
  </div>

  <!-- ========== TAB: MCP ========== -->
  <div class="tab-content" id="tab-mcp">
    <div class="card">
      <h2>MCP Серверы</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 10px">
        Все MCP серверы из Claude Desktop, Claude Code и Codex. Можно добавлять, отключать, удалять.
      </p>
      <div class="row" style="margin-bottom:10px">
        <button class="btn" onclick="mcpRefresh()">Обновить</button>
        <button class="btn secondary" onclick="mcpShowAdd()">+ Добавить MCP</button>
      </div>
      <div id="mcpAddForm" style="display:none;border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:12px">
        <div class="dual">
          <div><label>Инструмент</label><select id="mcpAddTool" style="margin-bottom:8px"></select></div>
          <div><label>Имя сервера</label><input id="mcpAddName" type="text" placeholder="my-server"></div>
        </div>
        <div class="dual">
          <div><label>Тип</label><select id="mcpAddType"><option value="stdio">stdio</option><option value="http">HTTP</option></select></div>
          <div id="mcpAddStdioFields"><label>Команда</label><input id="mcpAddCommand" type="text" placeholder="npx"></div>
          <div id="mcpAddUrlField" style="display:none"><label>URL</label><input id="mcpAddUrl" type="url" placeholder="https://..."></div>
        </div>
        <label>Аргументы (через запятую или каждый на новой строке)</label>
        <textarea id="mcpAddArgs" rows="2" placeholder="-y, package@latest"></textarea>
        <div class="row" style="margin-top:10px">
          <button class="btn green" onclick="mcpAdd()">Добавить</button>
          <button class="btn secondary" onclick="mcpHideAdd()">Отмена</button>
        </div>
      </div>
      <div id="mcpList" class="list"><div class="empty-state">Загрузка...</div></div>
    </div>
  </div>

  <!-- ========== TAB: PLUGINS ========== -->
  <div class="tab-content" id="tab-plugins">
    <div class="dual">
      <div class="card">
        <h2>Claude Code Плагины</h2>
        <p style="color:var(--muted);font-size:13px;margin:0 0 10px">Плагины из <code>~/.claude/settings.json</code></p>
        <div class="row" style="margin-bottom:10px">
          <button class="btn btn-sm" onclick="plCcRefresh()">Обновить</button>
        </div>
        <div id="plCcList" class="list"><div class="empty-state">Загрузка...</div></div>
      </div>
      <div class="card">
        <h2>Codex Плагины</h2>
        <p style="color:var(--muted);font-size:13px;margin:0 0 10px">Плагины из <code>~/.codex/config.toml</code></p>
        <div class="row" style="margin-bottom:10px">
          <button class="btn btn-sm" onclick="plCxRefresh()">Обновить</button>
        </div>
        <div id="plCxList" class="list"><div class="empty-state">Загрузка...</div></div>
      </div>
    </div>
    <div class="card">
      <h2>Plugin Marketplaces (Claude Code)</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 10px">Зарегистрированные marketplace-и для Claude Code плагинов.</p>
      <div id="plMarketplaces" class="list"><div class="empty-state">Загрузка...</div></div>
    </div>
  </div>

  <!-- ========== TAB: SETTINGS ========== -->
  <div class="tab-content" id="tab-settings">
    <div class="dual">
      <div class="card">
        <h2>Пути к конфигам</h2>
        <div style="font-size:12px">
          <div><label>Claude Desktop</label><code id="cfgCdPath" style="font-size:11px;word-break:break-all">...</code></div>
          <div><label>Claude Code (CLI)</label><code id="cfgCcPath" style="font-size:11px;word-break:break-all">...</code></div>
          <div><label>Codex</label><code id="cfgCxPath" style="font-size:11px;word-break:break-all">...</code></div>
        </div>
      </div>
      <div class="card">
        <h2>Auto-backup</h2>
        <p style="font-size:13px;color:var(--muted);margin:0 0 12px">
          При переключении профиля текущее состояние авто-бэкапится.
        </p>
        <label style="display:flex;align-items:center;gap:8px;margin:0;font-size:14px">
          <input id="cfgAutoBackup" type="checkbox" onchange="toggleAutoBackup()"> Авто-бэкап включён
        </label>
        <div style="margin-top:10px">
          <button class="btn btn-sm secondary" onclick="backupNow()">Создать бэкап сейчас</button>
        </div>
      </div>
    </div>
    <div class="card">
      <h2>Бэкапы</h2>
      <div class="row" style="margin-bottom:10px">
        <button class="btn btn-sm" onclick="listBackups()">Обновить список</button>
      </div>
      <div id="backupsList" class="list"><div class="empty-state">Загрузка...</div></div>
    </div>
    <div class="card">
      <h2>Claude Desktop — перенос данных</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 10px">
        Копировать IndexedDB (разговоры, проекты, память) и Local Storage между Claude Desktop instances.<br>
        <b>Важно:</b> Claude Desktop должен быть закрыт перед копированием.
      </p>
      <div class="row" style="margin-bottom:10px">
        <button class="btn btn-sm" onclick="cdDataRefresh()">Обновить</button>
      </div>
      <div id="cdDataInfo" class="list"><div class="empty-state">Загрузка...</div></div>
    </div>
    <div class="card">
      <h2>О приложении</h2>
      <p style="font-size:13px;color:var(--muted)">
        MultiManager v1.1 — локальное приложение. Ничего никуда не отправляет.<br>
        Конфиг: <code>~/.multimanager/config.json</code><br>
        Бэкапы: <code>~/.multimanager/backups/</code>
      </p>
    </div>
  </div>

  <div class="footer">MultiManager • локально • v1.1</div>
</div>

<!-- ===== ENV EDITOR MODAL ===== -->
<div id="envModal" class="modal-overlay">
  <div class="modal">
    <h2>Env vars: <span id="envModalTitle"></span></h2>
    <div id="envEditorContainer"></div>
    <div class="row" style="margin-top:14px;justify-content:flex-end">
      <button class="btn secondary" onclick="closeEnvModal()">Отмена</button>
      <button class="btn green" onclick="saveEnvVars()">Сохранить</button>
    </div>
  </div>
</div>

<script>
let envEditPreset = null;

function log(id,msg){const el=document.getElementById(id);if(el)el.textContent=msg}
function setStatus(t){document.getElementById('statusBar').textContent=t}

async function api(path,body=null){
  const opts={method:body?'POST':'GET',headers:{'Content-Type':'application/json'}}
  if(body)opts.body=JSON.stringify(body)
  const r=await fetch(path,opts);return await r.json()
}

// ===== TABS =====
document.querySelectorAll('.tab').forEach(tab=>{
  tab.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'))
    document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'))
    tab.classList.add('active')
    const t=tab.dataset.tab
    document.getElementById('tab-'+t).classList.add('active')
    if(t==='mcp')mcpRefresh()
    if(t==='plugins'){plCcRefresh();plCxRefresh()}
  })
})

// ===== CLAUDE DESKTOP PROFILES =====
async function cdRefresh(){
  setStatus('загрузка...');const data=await api('/api/cd-profiles');renderCdProfiles(data);setStatus('готов')
}
function renderCdProfiles(data){
  const el=document.getElementById('cdProfiles');el.innerHTML=''
  if(!data.instances||data.instances.length===0){el.innerHTML='<div class="empty-state">Нет профилей</div>';return}
  data.instances.forEach(inst=>{
    const div=document.createElement('div');div.className='item'
    const activeDot=inst.active?'<span class="status-dot green"></span>':'<span class="status-dot"></span>'
    let ph=''
    if(inst.profiles&&inst.profiles.length>0){
      inst.profiles.forEach(p=>{
        const act=p.active?'<span class="status-dot green"></span>':''
        ph+=`<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04)">
          <span>${act}${esc(p.name)}</span>
          <div class="actions">
            <button class="btn btn-sm ${p.active?'green':'secondary'}" onclick="cdUse('${esc(inst.name)}','${esc(p.name)}')">${p.active?'активен':'Switch'}</button>
            <button class="btn btn-sm red" onclick="cdDelete('${esc(inst.name)}','${esc(p.name)}')">×</button>
          </div>
        </div>`
      })
    }
    div.innerHTML=`<div class="info"><div class="name">${activeDot}${esc(inst.name)} <span class="tag">${inst.profiles?inst.profiles.length:0}</span></div>
      <div class="path">${esc(inst.path)}</div>${ph}</div>
      <div class="actions" style="flex-direction:column;gap:4px">
        <button class="btn btn-sm" onclick="cdSaveInstance('${esc(inst.name)}')">Save</button>
        <button class="btn btn-sm secondary" onclick="cdRefresh()">⟳</button>
      </div>`
    el.appendChild(div)
  })
}
async function cdSaveInstance(instanceName){
  const name=prompt('Имя профиля для '+instanceName+':');if(!name)return
  setStatus('сохранение...');await api('/api/cd-save-instance',{instance:instanceName,name});cdRefresh();setStatus('готов')
}
async function cdUse(instanceName,profileName){
  setStatus('переключение...');await api('/api/cd-use',{instance:instanceName,profile:profileName});cdRefresh();setStatus('готов')
}
async function cdDelete(instanceName,profileName){
  if(!confirm('Удалить профиль "'+profileName+'" из '+instanceName+'?'))return
  await api('/api/cd-delete',{instance:instanceName,profile:profileName});cdRefresh()
}

// ===== CLAUDE CODE PRESETS =====
async function ccRefresh(){
  setStatus('загрузка...');const data=await api('/api/cc-presets');renderCcPresets(data);setStatus('готов')
}
function renderCcPresets(data){
  const el=document.getElementById('ccPresets');el.innerHTML=''
  const presets=data.presets||[];const currentName=data.current||''
  if(presets.length===0&&!data.current){el.innerHTML='<div class="empty-state">Нет пресетов</div>';return}
  presets.sort((a,b)=>a.name.localeCompare(b.name))
  presets.forEach(p=>{
    const act=p.active||p.name===currentName;const dot=act?'<span class="status-dot green"></span>':''
    const envCount=p.env_count?`env: ${p.env_count} vars`:p.endpoint?p.endpoint:''
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<div class="info"><div class="name">${dot}${esc(p.name)}</div>
      <div class="path">${p.model?'model: '+esc(p.model):''} ${envCount?'| '+esc(envCount):''}</div></div>
      <div class="actions">
        <button class="btn btn-sm warning" onclick="openEnvEditor('${esc(p.name)}')" title="Edit env vars">⚙</button>
        ${act?'<span class="tag green">активен</span>':`<button class="btn btn-sm secondary" onclick="ccUse('${esc(p.name)}')">Switch</button>`}
        <button class="btn btn-sm red" onclick="ccDelete('${esc(p.name)}')">×</button>
      </div>`
    el.appendChild(div)
  })
}
async function ccSave(){
  const name=document.getElementById('ccNewName').value.trim()
  if(!name){alert('Введи имя пресета');return}
  setStatus('сохранение...');await api('/api/cc-save',{name});ccRefresh();setStatus('готов')
  document.getElementById('ccNewName').value=''
}
async function ccUse(name){setStatus('переключение...');await api('/api/cc-use',{name});ccRefresh();setStatus('готов')}
async function ccDelete(name){if(!confirm('Удалить пресет "'+name+'"?'))return;await api('/api/cc-delete',{name});ccRefresh()}

// ===== ENV VARS EDITOR =====
async function openEnvEditor(presetName){
  envEditPreset=presetName
  document.getElementById('envModalTitle').textContent=presetName
  const data=await api('/api/cc-preset-env?name='+encodeURIComponent(presetName))
  const env=data.env||{}
  const container=document.getElementById('envEditorContainer');container.innerHTML=''
  const keys=Object.keys(env)
  if(keys.length===0){
    container.innerHTML='<div class="empty-state" style="padding:12px">Нет env vars. Добавь ниже.</div>'
  }
  keys.forEach(k=>{
    const row=document.createElement('div');row.className='env-row'
    row.innerHTML=`<input class="env-key" value="${esc(k)}" placeholder="KEY"><input class="env-val" value="${esc(env[k])}" placeholder="value"><button class="btn btn-sm red" onclick="this.parentElement.remove()">×</button>`
    container.appendChild(row)
  })
  const addBtn=document.createElement('button');addBtn.className='btn btn-sm secondary';addBtn.textContent='+ Добавить var'
  addBtn.onclick=()=>{
    const row=document.createElement('div');row.className='env-row'
    row.innerHTML=`<input class="env-key" placeholder="KEY"><input class="env-val" placeholder="value"><button class="btn btn-sm red" onclick="this.parentElement.remove()">×</button>`
    container.appendChild(row)
  }
  container.appendChild(addBtn)
  document.getElementById('envModal').classList.add('show')
}
function closeEnvModal(){document.getElementById('envModal').classList.remove('show')}
async function saveEnvVars(){
  const rows=document.querySelectorAll('#envEditorContainer .env-row:not(:last-child)')
  const env={}
  rows.forEach(r=>{
    const k=r.querySelector('.env-key').value.trim()
    const v=r.querySelector('.env-val').value.trim()
    if(k)env[k]=v
  })
  if(!envEditPreset)return
  await api('/api/cc-preset-env',{name:envEditPreset,env})
  closeEnvModal();ccRefresh()
}

// ===== CODEX PROFILES =====
async function cxRefresh(){
  setStatus('загрузка...');const data=await api('/api/cx-profiles');renderCxProfiles(data);setStatus('готов')
}
function renderCxProfiles(data){
  const el=document.getElementById('cxProfiles');el.innerHTML=''
  const profiles=data.profiles||[];const currentName=data.current||''
  if(profiles.length===0&&!data.current){el.innerHTML='<div class="empty-state">Нет профилей</div>';return}
  profiles.sort((a,b)=>a.name.localeCompare(b.name))
  profiles.forEach(p=>{
    const act=p.active||p.name===currentName;const dot=act?'<span class="status-dot green"></span>':''
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<div class="info"><div class="name">${dot}${esc(p.name)}${p.model?' <span style="color:var(--muted)">— '+esc(p.model)+'</span>':''}</div>
      <div class="path">${p.endpoint?'endpoint: '+esc(p.endpoint):p.email?'email: '+esc(p.email):''}</div></div>
      <div class="actions">
        ${act?'<span class="tag green">активен</span>':`<button class="btn btn-sm secondary" onclick="cxUse('${esc(p.name)}')">Switch</button>`}
        <button class="btn btn-sm red" onclick="cxDelete('${esc(p.name)}')">×</button>
      </div>`
    el.appendChild(div)
  })
}
async function cxSave(){
  const name=document.getElementById('cxNewName').value.trim()
  if(!name){alert('Введи имя профиля');return}
  setStatus('сохранение...');await api('/api/cx-save',{name});cxRefresh();setStatus('готов')
  document.getElementById('cxNewName').value=''
}
async function cxUse(name){setStatus('переключение...');await api('/api/cx-use',{name});cxRefresh();setStatus('готов')}
async function cxDelete(name){if(!confirm('Удалить профиль Codex "'+name+'"?'))return;await api('/api/cx-delete',{name});cxRefresh()}

// ===== CODEX ENDPOINT =====
async function cxEndpointStatus(){
  const data=await api('/api/cx-endpoint-status')
  const el=document.getElementById('cxEndpointStatus')
  if(data.current){el.innerHTML='<span class="status-dot green"></span> Текущий: <code>'+esc(data.current)+'</code>';document.getElementById('cxEndpoint').value=data.current}
  else{el.innerHTML='<span class="status-dot"></span> Не установлен (стандартный OpenAI API)'}
}
async function cxSetEndpoint(){const url=document.getElementById('cxEndpoint').value.trim();if(!url){alert('Введи URL');return}
  setStatus('установка...');await api('/api/cx-set-endpoint',{url});cxEndpointStatus();setStatus('готов')}
async function cxClearEndpoint(){await api('/api/cx-clear-endpoint');cxEndpointStatus()}
async function cxCreateWrapper(){
  setStatus('создание...');const data=await api('/api/cx-create-wrapper')
  document.getElementById('cxWrapperStatus').innerHTML=data.error?'<span class="status-dot red"></span> '+esc(data.error):'<span class="status-dot green"></span> '+esc(data.message||'')
  setStatus('готов')
}

// ===== SKILLS =====
async function skScan(){setStatus('сканирование...');const data=await api('/api/sk-scan');renderSkRoots(data);setStatus('готов')}
function renderSkRoots(data){
  const el=document.getElementById('skRoots');el.innerHTML=''
  const sel=document.getElementById('skSource');const old=sel.value;sel.innerHTML=''
  ;(data.roots||[]).forEach(r=>{
    const opt=document.createElement('option');opt.value=r.path;opt.textContent=r.label+' — '+r.skill_count+' skills';sel.appendChild(opt)
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<input type="checkbox" class="sk-target" data-path="${esc(r.path)}" ${r.isTarget?'checked':''}>
      <div class="info"><div class="name">${esc(r.label)} <span class="tag">${r.skill_count}</span></div><div class="path">${esc(r.path)}</div></div>`
    el.appendChild(div)
  })
  if(old&&[...sel.options].some(o=>o.value===old))sel.value=old
  sel.onchange=skLoadSkills;skLoadSkills()
  if(data.roots)document.getElementById('skLog').textContent='Найдено папок: '+data.roots.length
}
async function skAddRoot(){const p=document.getElementById('skCustomRoot').value.trim();if(!p)return
  setStatus('добавление...');const data=await api('/api/sk-add-root',{path:p});renderSkRoots(data);setStatus('готов')}
async function skLoadSkills(){
  const src=document.getElementById('skSource').value;const el=document.getElementById('skSkillsList');el.innerHTML=''
  if(!src){el.innerHTML='<div class="empty-state">Выбери источник</div>';return}
  const data=await api('/api/sk-skills?root='+encodeURIComponent(src))
  ;(data.skills||[]).forEach(s=>{
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<input type="checkbox" class="sk-skill" data-name="${esc(s.name)}" checked><div class="info"><div class="name">${esc(s.name)}</div><div class="path">${esc(s.path)}</div></div>`
    el.appendChild(div)
  })
}
function skSelectAll(){document.querySelectorAll('.sk-target').forEach(x=>x.checked=true)}
async function skSync(dryRun){
  const source=document.getElementById('skSource').value
  if(!source||![...document.querySelectorAll('.sk-target:checked')].length){alert('Выбери источник и target');return}
  const targets=[...document.querySelectorAll('.sk-target:checked')].map(x=>x.dataset.path).filter(p=>p!==source)
  const skills=[...document.querySelectorAll('.sk-skill:checked')].map(x=>x.dataset.name)
  const overwrite=document.getElementById('skOverwrite').checked;const useSymlink=document.getElementById('skSymlink').checked
  setStatus(dryRun?'dry run...':'sync...');const data=await api('/api/sk-sync',{source,targets,skills,overwrite,dry_run:dryRun,use_symlink:useSymlink})
  document.getElementById('skLog').textContent=data.log||'Ошибка';setStatus(data.ok?'готово':'ошибка')
}

// ===== SCENES =====
async function scenesRefresh(){setStatus('загрузка...');const data=await api('/api/scenes');renderScenes(data);setStatus('готов')}
function renderScenes(data){
  const el=document.getElementById('scenesList');el.innerHTML=''
  const scenes=data.scenes||[]
  if(!scenes.length){el.innerHTML='<div class="empty-state">Нет сцен. Сохрани текущие профили как сцену.</div>';return}
  scenes.forEach(s=>{
    const div=document.createElement('div');div.className='item'
    let details=''
    if(s.cc_preset)details+='CC: '+esc(s.cc_preset)+' '
    if(s.cx_profile)details+='CX: '+esc(s.cx_profile)+' '
    if(s.cd_profiles){const names=Object.values(s.cd_profiles);if(names.length)details+='CD: '+esc(names.join(', '))}
    div.innerHTML=`<div class="info"><div class="name">🎬 ${esc(s.name)}</div><div class="path">${details||'нет профилей'}</div></div>
      <div class="actions">
        <button class="btn btn-sm green" onclick="sceneApply('${esc(s.name)}')">Apply</button>
        <button class="btn btn-sm red" onclick="sceneDelete('${esc(s.name)}')">×</button>
      </div>`
    el.appendChild(div)
  })
}
async function sceneSave(){
  const name=document.getElementById('sceneNewName').value.trim()
  if(!name){alert('Введи имя сцены');return}
  setStatus('сохранение...');await api('/api/scenes-save',{name});scenesRefresh();setStatus('готов')
  document.getElementById('sceneNewName').value=''
}
async function sceneApply(name){setStatus('применение...');const d=await api('/api/scenes-apply',{name});scenesRefresh();cdRefresh();ccRefresh();cxRefresh();setStatus(d.error||'готов')}
async function sceneDelete(name){if(!confirm('Удалить сцену "'+name+'"?'))return;await api('/api/scenes-delete',{name});scenesRefresh()}

// ===== QUICK LAUNCH =====
async function qlGenerate(){setStatus('генерация...');const data=await api('/api/quick-launch');document.getElementById('qlOutput').textContent=data.script||'Ошибка';setStatus('готов')}

// ===== BACKUPS =====
async function listBackups(){const data=await api('/api/backups');renderBackups(data)}
function renderBackups(data){
  const el=document.getElementById('backupsList');el.innerHTML=''
  const backups=data.backups||[]
  if(!backups.length){el.innerHTML='<div class="empty-state">Нет бэкапов</div>';return}
  backups.forEach(b=>{
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<div class="info"><div class="name">${esc(b.name)}</div><div class="path">${b.date} | ${b.size}</div></div>
      <div class="actions">
        <button class="btn btn-sm warning" onclick="backupRestore('${esc(b.name)}')">Restore</button>
        <button class="btn btn-sm red" onclick="backupDelete('${esc(b.name)}')">×</button>
      </div>`
    el.appendChild(div)
  })
}
async function backupNow(){const data=await api('/api/backup-now');listBackups();setStatus(data.error||'бэкап создан')}
async function backupRestore(name){if(!confirm('Восстановить бэкап "'+name+'"?'))return;await api('/api/backup-restore',{name});cdRefresh();ccRefresh();cxRefresh()}
async function backupDelete(name){if(!confirm('Удалить бэкап "'+name+'"?'))return;await api('/api/backup-delete',{name});listBackups()}
async function toggleAutoBackup(){const v=document.getElementById('cfgAutoBackup').checked;await api('/api/set-auto-backup',{enabled:v})}

// ===== SKILL DIFF =====
async function skDiff(){
  setStatus('сравнение...')
  const source=document.getElementById('skSource').value
  if(!source){document.getElementById('skDiffResults').textContent='Выбери источник мастер';setStatus('готов');return}
  const targets=[...document.querySelectorAll('.sk-target:checked')].map(x=>x.dataset.path).filter(p=>p!==source)
  if(!targets.length){document.getElementById('skDiffResults').textContent='Выбери target';setStatus('готов');return}
  const data=await api('/api/sk-diff',{master:source,targets})
  const el=document.getElementById('skDiffResults');el.innerHTML=''
  if(!data.diffs||!data.diffs.length){el.textContent='Все skills одинаковы.';setStatus('готов');return}
  data.diffs.forEach(d=>{
    const div=document.createElement('div');div.style.marginBottom='12px';div.style.border='1px solid var(--border)';div.style.borderRadius='8px';div.style.padding='10px'
    const header=document.createElement('div');header.style.display='flex';header.style.justifyContent='space-between';header.style.alignItems='center';header.style.marginBottom='6px'
    const newerIcon=d.newer==='target'?'🔄':'✓'
    const newerLabel=d.newer==='target'?'новее в target':'актуален'
    header.innerHTML=`<b>${esc(d.name)}</b> <span>${newerIcon} ${newerLabel} | ${esc(d.source_root)}</span>`
    div.appendChild(header)
    if(d.newer==='target'&&d.diff_lines&&d.diff_lines.length){
      const diffPre=document.createElement('pre');diffPre.style.fontSize='11px';diffPre.style.lineHeight='1.4';diffPre.style.margin='4px 0'
      diffPre.textContent=d.diff_lines.slice(0,60).join('\n')
      div.appendChild(diffPre)
      if(d.diff_lines.length>60)div.innerHTML+='<div style="color:var(--muted);font-size:11px">...и ещё '+(d.diff_lines.length-60)+' строк</div>'
      const btn=document.createElement('button');btn.className='btn btn-sm green';btn.textContent='Обновить master из target'
      btn.onclick=async()=>{
        setStatus('обновление...')
        await api('/api/sk-sync-one',{source:d.source_path,dest:d.master_path})
        el.innerHTML='<div style="color:var(--accent2)">✓ '+esc(d.name)+' обновлён в master</div>'
        setStatus('готов')
      }
      div.appendChild(btn)
    }
    el.appendChild(div)
  })
  setStatus('готов')
}
function skDiffClear(){document.getElementById('skDiffResults').innerHTML='Очищено.'}

// ===== CD DATA MANAGEMENT =====
async function cdDataRefresh(){
  setStatus('загрузка...');const data=await api('/api/cd-data-info');renderCdData(data);setStatus('готов')
}
function renderCdData(data){
  const el=document.getElementById('cdDataInfo');el.innerHTML=''
  if(!data.instances||!data.instances.length){el.innerHTML='<div class="empty-state">Нет instances</div>';return}
  data.instances.forEach(inst=>{
    const div=document.createElement('div');div.className='item'
    let dbsHtml=''
    if(inst.databases&&inst.databases.length){
      inst.databases.forEach(db=>{
        dbsHtml+=`<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;font-size:12px;border-bottom:1px solid rgba(255,255,255,.04)">
          <span>${esc(db.name)}</span>
          <span style="color:var(--muted)">${db.size}</span>
        </div>`
      })
    }
    div.innerHTML=`<div class="info"><div class="name">${esc(inst.name)}</div>
      <div class="path">${inst.size_total}</div>${dbsHtml}</div>
      <div class="actions" style="flex-direction:column;gap:4px">`
    const actionsDiv=div.querySelector('.actions')
    const allInstances=document.querySelectorAll('#cdDataInfo .item')
    data.instances.forEach(other=>{
      if(other.name===inst.name)return
      const copyBtn=document.createElement('button');copyBtn.className='btn btn-sm warning';copyBtn.textContent='← из '+esc(other.name)
      copyBtn.onclick=async()=>{
        if(!confirm('Копировать IndexedDB (разговоры/проекты/память) из "'+other.name+'" в "'+inst.name+'"? Claude Desktop должен быть закрыт.'))return
        setStatus('копирование...')
        const r=await api('/api/cd-copy-data',{from:other.name,to:inst.name,databases:['IndexedDB']})
        cdDataRefresh();setStatus(r.error||'готов')
      }
      actionsDiv.appendChild(copyBtn)
    })
    el.appendChild(div)
  })
}

// ===== MCP MANAGEMENT =====
async function mcpRefresh(){
  setStatus('загрузка...');const data=await api('/api/mcp-list');renderMcp(data);setStatus('готов')
}
function renderMcp(data){
  const el=document.getElementById('mcpList');el.innerHTML=''
  const servers=data.servers||[]
  if(!servers.length){el.innerHTML='<div class="empty-state">Нет MCP серверов</div>';return}
  const groups={}
  servers.forEach(s=>{
    const key=s.source+'|'+s.instance
    if(!groups[key])groups[key]=[]
    groups[key].push(s)
  })
  Object.entries(groups).forEach(([key,items])=>{
    const first=items[0]
    const groupDiv=document.createElement('div');groupDiv.style.marginBottom='8px';groupDiv.style.border='1px solid var(--border)';groupDiv.style.borderRadius='12px';groupDiv.style.padding='8px 12px'
    const header=document.createElement('div');header.style.display='flex';header.style.justifyContent='space-between';header.style.alignItems='center';header.style.marginBottom='6px'
    header.innerHTML=`<span style="font-weight:600;font-size:13px">${esc(first.sourceIcon)} ${esc(first.source)}${first.instance?' — '+esc(first.instance):''}</span><span style="font-size:11px;color:var(--muted)">${items.length} серверов</span>`
    groupDiv.appendChild(header)
    items.forEach(s=>{
      const cmd=s.type==='http'?s.url:(s.command+(s.args&&s.args.length?' '+esc(s.args.join(' ')):''))
      const item=document.createElement('div');item.style.display='flex';item.style.justifyContent='space-between';item.style.alignItems='center';item.style.padding='4px 0';item.style.borderBottom='1px solid rgba(255,255,255,.04)'
      item.innerHTML=`<div><span style="font-weight:600;font-size:13px">${esc(s.name)}</span><span style="font-size:11px;color:var(--muted);margin-left:8px">${s.type||'stdio'}</span>
        <div style="font-size:11px;color:var(--muted)">${esc(cmd.substr(0,80))}${cmd.length>80?'…':''}</div></div>
        <div class="actions" style="gap:4px">
          ${s.source==='Codex'?`<button class="btn btn-sm ${s.enabled?'green':'secondary'}" onclick="mcpToggle('${esc(s.name)}','${esc(s.source)}','${esc(s.instance||'')}')">${s.enabled?'ON':'OFF'}</button>`:''}
          <button class="btn btn-sm red" onclick="mcpDelete('${esc(s.name)}','${esc(s.source)}','${esc(s.instance||'')}')">×</button>
        </div>`
      groupDiv.appendChild(item)
    })
    el.appendChild(groupDiv)
  })
  // Populate add form tool selector
  const sel=document.getElementById('mcpAddTool');sel.innerHTML=''
  data.tools.forEach(t=>{
    const opt=document.createElement('option');opt.value=t.key;opt.textContent=t.label;sel.appendChild(opt)
  })
}
function mcpShowAdd(){document.getElementById('mcpAddForm').style.display='block'}
function mcpHideAdd(){document.getElementById('mcpAddForm').style.display='none'}
document.addEventListener('change',function(e){
  if(e.target.id==='mcpAddType'){
    const isHttp=e.target.value==='http'
    document.getElementById('mcpAddStdioFields').style.display=isHttp?'none':'block'
    document.getElementById('mcpAddUrlField').style.display=isHttp?'block':'none'
  }
})
async function mcpAdd(){
  const tool=document.getElementById('mcpAddTool').value
  const name=document.getElementById('mcpAddName').value.trim()
  const type=document.getElementById('mcpAddType').value
  const command=document.getElementById('mcpAddCommand').value.trim()
  const url=document.getElementById('mcpAddUrl').value.trim()
  const argsRaw=document.getElementById('mcpAddArgs').value
  if(!name||(type==='stdio'&&!command)||(type==='http'&&!url)){alert('Заполни обязательные поля');return}
  const args=argsRaw.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean)
  setStatus('добавление...')
  const data=await api('/api/mcp-add',{tool,name,type,command,args,url})
  mcpRefresh();setStatus(data.error||'готов')
  if(!data.error)mcpHideAdd()
}
async function mcpDelete(name,source,instance){
  if(!confirm('Удалить MCP "'+name+'" из '+source+(instance?' ('+instance+')':'')+'?'))return
  setStatus('удаление...');await api('/api/mcp-delete',{name,source,instance});mcpRefresh();setStatus('готов')
}
async function mcpToggle(name,source,instance){
  setStatus('переключение...');await api('/api/mcp-toggle',{name,source,instance});mcpRefresh();setStatus('готов')
}

// ===== PLUGINS =====
async function plCcRefresh(){
  setStatus('загрузка...');const data=await api('/api/plugins-cc');renderPlCc(data);setStatus('готов')
}
function renderPlCc(data){
  const el=document.getElementById('plCcList');el.innerHTML=''
  const plugins=data.plugins||[]
  if(!plugins.length){el.innerHTML='<div class="empty-state">Нет плагинов</div>';return}
  plugins.forEach(p=>{
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<div class="info"><div class="name">${p.enabled?'<span class="status-dot green"></span>':'<span class="status-dot"></span>'}${esc(p.name)}</div>
      <div class="path">${p.marketplace||''}</div></div>
      <div class="actions">
        <button class="btn btn-sm ${p.enabled?'green':'secondary'}" onclick="plCcToggle('${esc(p.name)}')">${p.enabled?'ON':'OFF'}</button>
      </div>`
    el.appendChild(div)
  })
  // Marketplaces
  const mel=document.getElementById('plMarketplaces');mel.innerHTML=''
  const mps=data.marketplaces||[]
  if(mps.length){
    mps.forEach(m=>{
      const d=document.createElement('div');d.className='item'
      d.innerHTML=`<div class="info"><div class="name">${esc(m.name)}</div><div class="path">${esc(m.source||'')}</div></div>`
      mel.appendChild(d)
    })
  }else{mel.innerHTML='<div class="empty-state">Нет marketplace-ов</div>'}
}
async function plCcToggle(name){
  setStatus('переключение...');await api('/api/plugins-cc-toggle',{name});plCcRefresh();setStatus('готов')
}
async function plCxRefresh(){setStatus('загрузка...')
  const data=await api('/api/plugins-cx');renderPlCx(data);setStatus('готов')
}
function renderPlCx(data){
  const el=document.getElementById('plCxList');el.innerHTML=''
  const plugins=data.plugins||[]
  if(!plugins.length){el.innerHTML='<div class="empty-state">Нет плагинов</div>';return}
  plugins.forEach(p=>{
    const div=document.createElement('div');div.className='item'
    div.innerHTML=`<div class="info"><div class="name">${p.enabled?'<span class="status-dot green"></span>':'<span class="status-dot"></span>'}${esc(p.name)}</div></div>
      <div class="actions">
        <button class="btn btn-sm green" onclick="plCxToggle('${esc(p.name)}')">Toggle</button>
      </div>`
    el.appendChild(div)
  })
}
async function plCxToggle(name){
  setStatus('переключение...');await api('/api/plugins-cx-toggle',{name});plCxRefresh();setStatus('готов')
}

// ===== UTILS =====
function esc(s){if(!s)return '';const d=document.createElement('div');d.textContent=s;return d.innerHTML}

// ===== INIT =====
async function init(){
  cdRefresh();ccRefresh();cxRefresh();cxEndpointStatus();scenesRefresh()
  const cfg=await api('/api/get-settings')
  document.getElementById('cfgAutoBackup').checked=cfg.auto_backup!==false
  document.getElementById('cfgCdPath').textContent=document.location.origin+'/api/cd-config-path'
  document.getElementById('cfgCcPath').textContent=document.location.origin+'/api/cc-config-path'
  document.getElementById('cfgCxPath').textContent=document.location.origin+'/api/cx-config-path'
}
init()
</script>
</body></html>"""

# ============================================================
# BACKEND
# ============================================================

def expand_path(p):
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()

def load_config():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text())
        except Exception: return {}
    return {}

def save_config(cfg):
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

def ensure_defaults():
    cfg = load_config()
    changed = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed: save_config(cfg)
    return cfg

def file_hash(path):
    import hashlib
    try: return hashlib.sha256(open(path, "rb").read(65536)).hexdigest()
    except Exception: return ""

def read_file_text(path):
    try: return Path(path).read_text()
    except Exception: return ""

def write_file_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)

def format_size(bytesize):
    if bytesize < 1024: return f"{bytesize} B"
    elif bytesize < 1048576: return f"{bytesize/1024:.1f} KB"
    else: return f"{bytesize/1048576:.1f} MB"

# ---- Skill Diff ----
def get_skill_diffs(master_root, target_roots):
    import difflib
    master = expand_path(master_root)
    if not master.exists(): return []
    master_skills = {s["name"]: expand_path(s["path"]) for s in skills_in(master)}
    result = []
    for target_str in target_roots:
        target = expand_path(target_str)
        target_skills = {s["name"]: expand_path(s["path"]) for s in skills_in(target)}
        for name, tpath in target_skills.items():
            t_md = tpath / "SKILL.md"
            mpath = master_skills.get(name)
            if not mpath: continue
            m_md = mpath / "SKILL.md"
            if not t_md.exists() or not m_md.exists(): continue
            try:
                t_mtime = os.path.getmtime(t_md)
                m_mtime = os.path.getmtime(m_md)
                newer = "target" if t_mtime > m_mtime else ("master" if m_mtime > t_mtime else "same")
                diff_lines = []
                if newer == "target":
                    t_text = t_md.read_text()
                    m_text = m_md.read_text()
                    if t_text != m_text:
                        diff_lines = list(difflib.unified_diff(
                            m_text.splitlines(), t_text.splitlines(),
                            fromfile=f"master/{name}/SKILL.md",
                            tofile=f"target/{name}/SKILL.md",
                            lineterm='', n=3
                        ))
                result.append({
                    "name": name,
                    "source_root": str(target),
                    "source_path": str(tpath),
                    "master_path": str(mpath),
                    "newer": newer,
                    "diff_lines": diff_lines[:80],
                    "has_diff": len(diff_lines) > 0
                })
            except Exception:
                continue
    result.sort(key=lambda x: (0 if x["newer"] == "target" else 1, x["name"]))
    return result

def sync_one_skill(source_path, dest_path):
    src = expand_path(source_path)
    dst = expand_path(dest_path)
    if not src.exists(): return False, f"Source not found: {src}"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if dst.exists():
        backup = dst.parent / f"{dst.name}.backup-{stamp}"
        shutil.move(str(dst), str(backup))
    shutil.copytree(str(src), str(dst), symlinks=True)
    return True, f"Copied {src} -> {dst}"

# ---- CD Data Management ----
def get_cd_data_info():
    instances = find_claude_instances()
    result = {"instances": []}
    for inst in instances:
        base = Path(inst["path"])
        size_total = 0
        databases = []
        # IndexedDB (conversations/projects/memory)
        indexeddb = base / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
        if indexeddb.exists():
            sz = sum(f.stat().st_size for f in indexeddb.glob("**/*") if f.is_file())
            size_total += sz
            databases.append({"name": "IndexedDB (разговоры/проекты/память)", "path": str(indexeddb), "size": format_size(sz), "key": "IndexedDB"})
        # Local Storage
        ls = base / "Local Storage" / "leveldb"
        if ls.exists():
            sz = sum(f.stat().st_size for f in ls.glob("**/*") if f.is_file())
            size_total += sz
            databases.append({"name": "Local Storage (настройки)", "path": str(ls), "size": format_size(sz), "key": "LocalStorage"})
        # Session Storage
        ss = base / "Session Storage" / "leveldb"
        if ss.exists():
            sz = sum(f.stat().st_size for f in ss.glob("**/*") if f.is_file())
            size_total += sz
            databases.append({"name": "Session Storage", "path": str(ss), "size": format_size(sz), "key": "SessionStorage"})
        result["instances"].append({
            "name": inst["name"],
            "path": inst["path"],
            "size_total": format_size(size_total),
            "databases": databases
        })
    return result

def copy_cd_data(from_name, to_name, db_keys):
    from_path = CLAUDE_DESKTOP_DIR / from_name
    to_path = CLAUDE_DESKTOP_DIR / to_name
    if not from_path.exists(): return False, f"Source {from_name} not found"
    if not to_path.exists(): return False, f"Target {to_name} not found"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_map = {
        "IndexedDB": ("IndexedDB", "https_claude.ai_0.indexeddb.leveldb"),
        "LocalStorage": ("Local Storage", "leveldb"),
        "SessionStorage": ("Session Storage", "leveldb"),
    }
    copied = []
    for key in db_keys:
        if key not in db_map: continue
        subdir, name = db_map[key]
        src = from_path / subdir / name
        if not src.exists(): continue
        dst = to_path / subdir
        dst_db = dst / name
        if dst_db.exists():
            backup = dst / f"{name}.bak-{stamp}"
            shutil.move(str(dst_db), str(backup))
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(src), str(dst_db))
        copied.append(key)
    return True, f"Copied {', '.join(copied)} from {from_name} to {to_name}"

# ---- Auto-backup ----
def do_auto_backup(cfg):
    if not cfg.get("auto_backup", True):
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = {"created_at": stamp, "files": {}}
    paths = {
        "claude_desktop": list(CLAUDE_DESKTOP_DIR.glob("Claude*/claude_desktop_config.json")),
        "claude_code": [CLAUDE_CODE_SETTINGS] if CLAUDE_CODE_SETTINGS.exists() else [],
        "codex_config": [CODEX_CONFIG] if CODEX_CONFIG.exists() else [],
        "codex_auth": [CODEX_AUTH] if CODEX_AUTH.exists() else [],
    }
    for category, files in paths.items():
        for f in files:
            try:
                backup["files"][f"{category}:{f.name}"] = {"path": str(f), "content": f.read_text()}
            except Exception:
                pass
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_file = BACKUP_DIR / f"auto-{stamp}.json"
    backup_file.write_text(json.dumps(backup, ensure_ascii=False, indent=2))

# ---- Claude Desktop instances ----
def find_claude_instances():
    if not CLAUDE_DESKTOP_DIR.exists(): return []
    instances = []
    for p in sorted(CLAUDE_DESKTOP_DIR.glob("Claude*")):
        if not p.is_dir(): continue
        config_file = p / "claude_desktop_config.json"
        instances.append({"name": p.name, "path": str(p), "config_path": str(config_file) if config_file.exists() else None, "profiles": []})
    return instances

def get_cd_profiles_data(cfg):
    instances = find_claude_instances()
    saved = cfg.get("claude_desktop_profiles", {})
    for inst in instances:
        inst_profiles = saved.get(inst["name"], {})
        profile_list = []
        current_hash = file_hash(inst["config_path"]) if inst["config_path"] and os.path.exists(inst["config_path"]) else None
        for pname, pdata in inst_profiles.items():
            profile_list.append({"name": pname, "active": current_hash and pdata.get("hash") == current_hash, "hash": pdata.get("hash", "")})
        inst["profiles"] = profile_list
    return {"instances": instances}

# ---- Claude Code presets ----
def get_current_cc_preset_name(cfg):
    if not CLAUDE_CODE_SETTINGS.exists(): return None
    ch = file_hash(CLAUDE_CODE_SETTINGS)
    for name, pdata in cfg.get("claude_code_presets", {}).items():
        if pdata.get("hash") == ch: return name
    return None

def get_cc_presets_data(cfg):
    presets = cfg.get("claude_code_presets", {})
    current_name = get_current_cc_preset_name(cfg)
    current_hash = file_hash(CLAUDE_CODE_SETTINGS) if CLAUDE_CODE_SETTINGS.exists() else None
    result = {"presets": [], "current": current_name}
    for name in sorted(presets.keys()):
        pdata = presets[name]
        active = bool(current_hash and pdata.get("hash") == current_hash)
        model = endpoint = ""
        env_count = 0
        if "settings" in pdata and isinstance(pdata["settings"], dict):
            st = pdata["settings"]
            model = st.get("model", "")
            env = st.get("env", {})
            endpoint = env.get("ANTHROPIC_BASE_URL", "")
            env_count = len(env)
        result["presets"].append({"name": name, "active": active, "model": model, "endpoint": endpoint, "env_count": env_count})
    return result

# ---- Codex profiles ----
def get_current_cx_profile_name(cfg):
    ch = file_hash(CODEX_CONFIG) if CODEX_CONFIG.exists() else None
    ah = file_hash(CODEX_AUTH) if CODEX_AUTH.exists() else None
    for name, pdata in cfg.get("codex_profiles", {}).items():
        if pdata.get("config_hash") == ch and pdata.get("auth_hash") == ah: return name
    return None

def get_cx_profiles_data(cfg):
    profiles = cfg.get("codex_profiles", {})
    current_name = get_current_cx_profile_name(cfg)
    ch, ah = (file_hash(CODEX_CONFIG) if CODEX_CONFIG.exists() else None), (file_hash(CODEX_AUTH) if CODEX_AUTH.exists() else None)
    result = {"profiles": [], "current": current_name}
    for name in sorted(profiles.keys()):
        pdata = profiles[name]
        active = bool(ch and ah and pdata.get("config_hash") == ch and pdata.get("auth_hash") == ah)
        result["profiles"].append({"name": name, "active": active, "email": pdata.get("email", ""), "endpoint": pdata.get("endpoint", ""), "model": pdata.get("model", "")})
    return result

# ---- Skills ----
def has_skill(root):
    try: return (root / "SKILL.md").is_file()
    except (PermissionError, OSError): return False

def skills_in(root):
    if not root.exists() or not root.is_dir(): return []
    try: children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except (PermissionError, OSError): return []
    out = []
    for child in children:
        try:
            if child.is_dir() and has_skill(child):
                out.append({"name": child.name, "path": str(child)})
        except (PermissionError, OSError): continue
    return out

def label_for(p):
    s = str(p)
    if s.endswith("/.claude/skills"): return "Claude Code"
    if s.endswith("/.codex/skills"): return "Codex"
    if s.endswith("/.agents/skills"): return "Agents shared"
    if "/Library/Application Support/Claude" in s and "/skills-plugin/" in s: return "Claude Desktop session"
    if s.endswith("/.opencode/skills"): return "OpenCode"
    if s.endswith("/.gemini/skills"): return "Gemini"
    return p.name or s

def is_claude_desktop_skills(path_str):
    return "/Library/Application Support/Claude" in path_str and "/skills-plugin/" in path_str

def claude_desktop_skills_roots():
    base = HOME / "Library" / "Application Support"; roots = []
    for claude in base.glob("Claude*"):
        try: roots += list(claude.glob("local-agent-mode-sessions/skills-plugin/*/*/skills"))
        except (PermissionError, OSError): continue
    return roots

def scan_skills_roots(cfg):
    custom = [expand_path(x) for x in cfg.get("custom_roots", [])]
    targets_set = set(cfg.get("skills_targets", []))
    candidates = [*SKILL_ROOTS_DEFAULT, *claude_desktop_skills_roots(), *custom]
    seen, roots = set(), []
    for p in candidates:
        try: rp = p.resolve()
        except Exception: rp = p
        if str(rp) in seen: continue
        seen.add(str(rp))
        try: exists = rp.exists()
        except (PermissionError, OSError): exists = False
        count = len(skills_in(rp)) if exists else 0
        if exists or count > 0 or str(rp) in custom:
            roots.append({"path": str(rp), "label": label_for(rp), "exists": exists, "skill_count": count, "isTarget": str(rp) in targets_set})
    roots.sort(key=lambda r: (not r["exists"], r["label"], r["path"]))
    return roots

def do_sync(source, targets, skill_names, overwrite=False, dry_run=False, use_symlink=False):
    lines = []; ok = True
    src = expand_path(source)
    if not src.exists(): return False, f"Источник не найден: {src}"
    all_skills = {s["name"]: Path(s["path"]) for s in skills_in(src)}
    names = skill_names or list(all_skills)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for target in targets:
        t = expand_path(target)
        if dry_run: lines.append(f"[dry] mkdir -p {t}")
        else: t.mkdir(parents=True, exist_ok=True)
        for name in names:
            source_skill = all_skills.get(name)
            if not source_skill: lines.append(f"[skip] skill не найден: {name}"); continue
            dest = t / name; is_cd = is_claude_desktop_skills(str(t))
            if dest.exists() or dest.is_symlink():
                if dest.is_symlink():
                    if not dry_run: dest.unlink()
                    lines.append(f"[remove-symlink] {dest}")
                elif overwrite:
                    backup = t / f"{name}.backup-{stamp}"
                    if dry_run: lines.append(f"[dry] mv {dest} {backup}")
                    else: shutil.move(str(dest), str(backup))
                    lines.append(f"[backup] {dest} -> {backup}")
                else: lines.append(f"[conflict] существует: {dest}"); ok = False; continue
            do_sym = use_symlink and not is_cd
            if do_sym:
                if dry_run: lines.append(f"[dry] ln -s {source_skill} {dest}")
                else:
                    try:
                        os.symlink(str(source_skill), str(dest))
                        lines.append(f"[link] {dest} -> {source_skill}")
                    except Exception as e: lines.append(f"[error] symlink {dest}: {e}"); ok = False
            else:
                if dry_run: lines.append(f"[dry] cp -r {source_skill} {dest}")
                else:
                    try:
                        if dest.exists(): shutil.rmtree(dest)
                        shutil.copytree(str(source_skill), str(dest), symlinks=True)
                        lines.append(f"[copy] {dest} ({name})")
                    except Exception as e: lines.append(f"[error] copy {dest}: {e}"); ok = False
    return ok, "\n".join(lines) if lines else "Ничего не сделано."

# ---- Scenes ----
def get_scenes_data(cfg):
    scenes = cfg.get("scenes", {})
    cc_current = get_current_cc_preset_name(cfg)
    cx_current = get_current_cx_profile_name(cfg)
    cd_instances = find_claude_instances()
    cd_current = {}
    for inst in cd_instances:
        inst_profiles = cfg.get("claude_desktop_profiles", {}).get(inst["name"], {})
        ch = file_hash(inst["config_path"]) if inst["config_path"] and os.path.exists(inst["config_path"]) else None
        for pname, pdata in inst_profiles.items():
            if ch and pdata.get("hash") == ch:
                cd_current[inst["name"]] = pname
    result = {"scenes": [], "current": {"cc_preset": cc_current, "cx_profile": cx_current, "cd_profiles": cd_current}}
    for name, sdata in sorted(scenes.items()):
        result["scenes"].append({"name": name, **sdata})
    return result

# ---- Backups ----
def list_backups():
    if not BACKUP_DIR.exists(): return []
    backups = []
    for f in sorted(BACKUP_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            size = f.stat().st_size
            backups.append({
                "name": f.stem, "date": data.get("created_at", ""),
                "size": f"{size/1024:.1f} KB" if size < 1048576 else f"{size/1048576:.1f} MB",
                "file_count": len(data.get("files", {}))
            })
        except Exception: continue
    return backups

def restore_backup(name):
    backup_file = BACKUP_DIR / f"{name}.json"
    if not backup_file.exists(): return False, "Бэкап не найден"
    data = json.loads(backup_file.read_text())
    restored = []
    for key, finfo in data.get("files", {}).items():
        try:
            write_file_text(finfo["path"], finfo["content"])
            restored.append(key)
        except Exception as e: restored.append(f"{key}: ERROR {e}")
    return True, "\n".join(restored)

# ---- MCP Helpers ----
CODEX_MCP_INI = CODEX_CONFIG

def _mcp_source_label(key, tool_label=None):
    parts = key.split("|", 1)
    if tool_label:
        return tool_label
    return parts[0]

def _read_cdx_mcp_servers():
    """Read MCP servers from Codex config.toml (mcp_servers section)."""
    if not CODEX_CONFIG.exists():
        return {}
    raw = CODEX_CONFIG.read_text()
    try:
        import tomllib
        data = tomllib.loads(raw)
    except Exception:
        return {}
    servers = {}
    sec = data.get("mcp_servers", {})
    for name, val in sec.items():
        if isinstance(val, dict):
            servers[name] = {
                "command": val.get("command", ""),
                "args": val.get("args", []),
                "type": "http" if "url" in val else "stdio",
                "url": val.get("url", ""),
                "enabled": val.get("enabled", True),
                "headers": val.get("headers", {}),
            }
    return servers

def _write_cdx_mcp_servers(servers):
    """Write MCP servers back into Codex config.toml."""
    if not CODEX_CONFIG.exists():
        return False, "Codex config not found"
    raw = CODEX_CONFIG.read_text()
    lines = raw.split("\n")
    new_lines = []
    in_servers = False
    server_keys = set(servers.keys())
    wrote = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Detect start of mcp_servers section
        if stripped.startswith("[mcp_servers."):
            in_servers = True
            key = stripped[len("[mcp_servers."):].rstrip("]")
            # Skip this server section entirely; we'll rewrite all
            while i < len(lines) and not (lines[i].strip().startswith("[") and lines[i].strip() != stripped and not lines[i].strip().startswith("[mcp_servers.")):
                i += 1
            i -= 1  # will be incremented
        elif in_servers and stripped.startswith("[") and not stripped.startswith("[mcp_servers."):
            in_servers = False
            if not wrote:
                # Write all servers before leaving section
                for srv_name, srv in sorted(servers.items()):
                    new_lines.append(f"\n[mcp_servers.{srv_name}]")
                    if srv.get("type") == "http":
                        new_lines.append(f'url = "{srv["url"]}"')
                    else:
                        new_lines.append(f'command = "{srv["command"]}"')
                        if srv.get("args"):
                            if len(srv["args"]) == 1:
                                new_lines.append(f'args = ["{srv["args"][0]}"]')
                            else:
                                new_lines.append(f"args = [")
                                for a in srv["args"]:
                                    new_lines.append(f'  "{a}",')
                                new_lines.append(f"]")
                    if "enabled" in srv and not srv["enabled"]:
                        new_lines.append("enabled = false")
                    if srv.get("headers"):
                        new_lines.append("[mcp_servers." + srv_name + ".headers]")
                        for k, v in srv.get("headers", {}).items():
                            new_lines.append(f'{k} = "{v}"')
                wrote = True
        if not in_servers or i >= len(lines):
            new_lines.append(line)
        elif in_servers and i >= len(lines):
            pass
        i += 1
    if not wrote:
        new_lines.append("\n")
        for srv_name, srv in sorted(servers.items()):
            new_lines.append(f"\n[mcp_servers.{srv_name}]")
            if srv.get("type") == "http":
                new_lines.append(f'url = "{srv["url"]}"')
            else:
                new_lines.append(f'command = "{srv["command"]}"')
                if srv.get("args"):
                    if len(srv["args"]) == 1:
                        new_lines.append(f'args = ["{srv["args"][0]}"]')
                    else:
                        new_lines.append(f"args = [")
                        for a in srv["args"]:
                            new_lines.append(f'  "{a}",')
                        new_lines.append(f"]")
            if "enabled" in srv and not srv["enabled"]:
                new_lines.append("enabled = false")
    CODEX_CONFIG.write_text("\n".join(new_lines))
    return True, "OK"

def mcp_list_servers(cfg):
    servers = []
    tools = []
    tool_keys = set()
    def add_source(label, key, icon="🖥"):
        if key not in tool_keys:
            tools.append({"key": key, "label": f"{icon} {label}"})
            tool_keys.add(key)

    # Claude Desktop instances
    for inst in get_cd_profiles_data(cfg)["instances"]:
        name = inst["name"]
        config_path = CLAUDE_DESKTOP_DIR / name / "claude_desktop_config.json"
        add_source(f"Claude Desktop — {name}", f"cd|{name}", "💬")
        if config_path.exists():
            try:
                d = json.loads(config_path.read_text())
                mcp = d.get("mcpServers", {})
                for srv_name, srv in mcp.items():
                    servers.append({
                        "name": srv_name,
                        "source": "Claude Desktop",
                        "sourceIcon": "💬",
                        "instance": name,
                        "key": f"cd|{name}",
                        "type": "http" if "url" in srv else "stdio",
                        "command": srv.get("command", ""),
                        "args": srv.get("args", []),
                        "url": srv.get("url", ""),
                        "enabled": True,
                    })
            except Exception:
                pass

    # Claude Code
    add_source("Claude Code", "cc", "⌨️")
    if CLAUDE_CODE_SETTINGS.exists():
        try:
            d = json.loads(CLAUDE_CODE_SETTINGS.read_text())
            mcp = d.get("mcpServers", {})
            for srv_name, srv in mcp.items():
                servers.append({
                    "name": srv_name,
                    "source": "Claude Code",
                    "sourceIcon": "⌨️",
                    "instance": "",
                    "key": "cc",
                    "type": srv.get("type", "stdio"),
                    "command": srv.get("command", ""),
                    "args": srv.get("args", []),
                    "url": srv.get("url", ""),
                    "enabled": True,
                    "headers": srv.get("headers", {}),
                })
        except Exception:
            pass

    # Codex
    add_source("Codex", "cx", "🤖")
    cdx = _read_cdx_mcp_servers()
    for srv_name, srv in cdx.items():
        servers.append({
            "name": srv_name,
            "source": "Codex",
            "sourceIcon": "🤖",
            "instance": "",
            "key": "cx",
            "type": srv.get("type", "stdio"),
            "command": srv.get("command", ""),
            "args": srv.get("args", []),
            "url": srv.get("url", ""),
            "enabled": srv.get("enabled", True),
        })

    return {"servers": servers, "tools": tools}

def mcp_add_server(tool_key, name, srv_type, command, args, url):
    if tool_key.startswith("cd|"):
        inst = tool_key.split("|", 1)[1]
        config_path = CLAUDE_DESKTOP_DIR / inst / "claude_desktop_config.json"
        if not config_path.exists():
            return False, f"Config not found for {inst}"
        d = json.loads(config_path.read_text())
        if "mcpServers" not in d:
            d["mcpServers"] = {}
        if srv_type == "http":
            d["mcpServers"][name] = {"url": url, "type": "http"}
        else:
            d["mcpServers"][name] = {"command": command, "args": args}
        config_path.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        return True, "OK"
    elif tool_key == "cc":
        if not CLAUDE_CODE_SETTINGS.exists():
            return False, "Claude Code settings not found"
        d = json.loads(CLAUDE_CODE_SETTINGS.read_text())
        if "mcpServers" not in d:
            d["mcpServers"] = {}
        if srv_type == "http":
            d["mcpServers"][name] = {"url": url, "type": "http"}
        else:
            d["mcpServers"][name] = {"command": command, "args": args}
        CLAUDE_CODE_SETTINGS.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        return True, "OK"
    elif tool_key == "cx":
        servers = _read_cdx_mcp_servers()
        if srv_type == "http":
            servers[name] = {"command": "", "args": [], "type": "http", "url": url, "enabled": True}
        else:
            servers[name] = {"command": command, "args": args, "type": "stdio", "url": "", "enabled": True}
        ok, msg = _write_cdx_mcp_servers(servers)
        return ok, msg
    return False, "Unknown tool"

def mcp_delete_server(name, source, instance):
    if source == "Claude Desktop":
        config_path = CLAUDE_DESKTOP_DIR / instance / "claude_desktop_config.json"
        if not config_path.exists():
            return False, "Config not found"
        d = json.loads(config_path.read_text())
        d.get("mcpServers", {}).pop(name, None)
        config_path.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        return True, "OK"
    elif source == "Claude Code":
        if not CLAUDE_CODE_SETTINGS.exists():
            return False, "Settings not found"
        d = json.loads(CLAUDE_CODE_SETTINGS.read_text())
        d.get("mcpServers", {}).pop(name, None)
        CLAUDE_CODE_SETTINGS.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        return True, "OK"
    elif source == "Codex":
        servers = _read_cdx_mcp_servers()
        servers.pop(name, None)
        ok, msg = _write_cdx_mcp_servers(servers)
        return ok, msg
    return False, "Unknown source"

def mcp_toggle_server(name, source, instance):
    if source == "Codex":
        servers = _read_cdx_mcp_servers()
        if name in servers:
            servers[name]["enabled"] = not servers[name].get("enabled", True)
            ok, msg = _write_cdx_mcp_servers(servers)
            return ok, msg
        return False, "Not found"
    return False, "Toggle only supported for Codex"

# ---- Plugins Helpers ----
def plugins_cc_list():
    if not CLAUDE_CODE_SETTINGS.exists():
        return {"plugins": [], "marketplaces": []}
    d = json.loads(CLAUDE_CODE_SETTINGS.read_text())
    plugins = []
    eps = d.get("enabledPlugins", {})
    for name, enabled in eps.items():
        plugins.append({"name": name, "enabled": enabled, "source": "claude_code"})
    marketplaces = []
    ekm = d.get("extraKnownMarketplaces", {})
    for name, val in ekm.items():
        src = val.get("source", {})
        if isinstance(src, dict):
            marketplaces.append({"name": name, "source": src.get("path", str(src))})
        else:
            marketplaces.append({"name": name, "source": str(src)})
    return {"plugins": plugins, "marketplaces": marketplaces}

def plugins_cc_toggle(name):
    if not CLAUDE_CODE_SETTINGS.exists():
        return False, "Settings not found"
    d = json.loads(CLAUDE_CODE_SETTINGS.read_text())
    eps = d.setdefault("enabledPlugins", {})
    if name in eps:
        eps[name] = not eps[name]
    else:
        eps[name] = True
    CLAUDE_CODE_SETTINGS.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    return True, "OK"

def plugins_cx_list():
    if not CODEX_CONFIG.exists():
        return {"plugins": []}
    raw = CODEX_CONFIG.read_text()
    try:
        import tomllib
        data = tomllib.loads(raw)
    except Exception:
        return {"plugins": []}
    plugins = []
    sec = data.get("plugins", {})
    for name, val in sec.items():
        if isinstance(val, dict):
            plugins.append({"name": name, "enabled": val.get("enabled", True), "source": "codex"})
    return {"plugins": plugins}

def plugins_cx_toggle(name):
    # Read full config and toggle plugin
    if not CODEX_CONFIG.exists():
        return False, "Config not found"
    raw = CODEX_CONFIG.read_text()
    import tomllib
    data = tomllib.loads(raw)
    plugins = data.get("plugins", {})
    if name not in plugins:
        return False, "Plugin not found"
    current = plugins[name].get("enabled", True)
    # Toggle via raw text manipulation
    target = f"[plugins.{name}]"
    lines = raw.split("\n")
    new_lines = []
    in_plugin = False
    for line in lines:
        stripped = line.strip()
        if stripped == target:
            in_plugin = True
            new_lines.append(line)
        elif in_plugin and stripped.startswith("["):
            # Write the toggled enabled line before leaving
            new_lines.append(f"enabled = {'false' if current else 'true'}")
            new_lines.append(line)
            in_plugin = False
        elif in_plugin and stripped.startswith("enabled"):
            continue  # skip old enabled line
        else:
            if in_plugin:
                new_lines.append(line)
            else:
                new_lines.append(line)
    if in_plugin:
        new_lines.append(f"enabled = {'false' if current else 'true'}")
    CODEX_CONFIG.write_text("\n".join(new_lines))
    return True, "OK"

# ============================================================
# HTTP HANDLER
# ============================================================

class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self):
        d = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _error(self, msg, status=400):
        self._json({"error": msg}, status)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        if n == 0: return {}
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/": self._html(); return
        cfg = ensure_defaults()

        if u.path == "/api/cd-profiles": self._json(get_cd_profiles_data(cfg)); return
        if u.path == "/api/cc-presets": self._json(get_cc_presets_data(cfg)); return
        if u.path == "/api/cx-profiles": self._json(get_cx_profiles_data(cfg)); return
        if u.path == "/api/cx-endpoint-status": self._json({"current": cfg.get("codex_endpoint", "")}); return
        if u.path == "/api/sk-scan": self._json({"roots": scan_skills_roots(cfg)}); return
        if u.path == "/api/scenes": self._json(get_scenes_data(cfg)); return
        if u.path == "/api/backups": self._json({"backups": list_backups()}); return
        if u.path == "/api/get-settings": self._json(cfg); return

        if u.path == "/api/sk-skills":
            qs = parse_qs(u.query)
            self._json({"skills": skills_in(expand_path(qs.get("root", [""])[0]))}); return

        if u.path == "/api/cc-preset-env":
            qs = parse_qs(u.query); name = qs.get("name", [""])[0]
            pdata = cfg.get("claude_code_presets", {}).get(name, {})
            env = {}
            if isinstance(pdata.get("settings"), dict):
                env = pdata["settings"].get("env", {})
            self._json({"env": env, "name": name}); return

        if u.path == "/api/cd-data-info":
            self._json(get_cd_data_info()); return

        if u.path in ("/api/cd-config-path",): self._json({"path": str(CLAUDE_DESKTOP_DIR)}); return
        if u.path in ("/api/cc-config-path",): self._json({"path": str(CLAUDE_CODE_SETTINGS)}); return
        if u.path in ("/api/cx-config-path",): self._json({"path": str(CODEX_CONFIG)}); return

        # MCP & Plugins GET endpoints
        if u.path == "/api/mcp-list": self._json(mcp_list_servers(cfg)); return
        if u.path == "/api/plugins-cc": self._json(plugins_cc_list()); return
        if u.path == "/api/plugins-cx": self._json(plugins_cx_list()); return

        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path); body = self._read_body(); cfg = ensure_defaults()

        # CD profiles
        if u.path == "/api/cd-save-instance":
            inst_name = body.get("instance", "").strip(); name = body.get("name", "").strip()
            if not inst_name or not name: return self._error("instance and name required")
            instances = find_claude_instances()
            target = next((i for i in instances if i["name"] == inst_name), None)
            if not target or not target["config_path"] or not os.path.exists(target["config_path"]):
                return self._error(f"Instance {inst_name} config not found")
            do_auto_backup(cfg)
            profiles = cfg.setdefault("claude_desktop_profiles", {})
            inst_profiles = profiles.setdefault(inst_name, {})
            inst_profiles[name] = {"hash": file_hash(target["config_path"]), "content": read_file_text(target["config_path"])}
            save_config(cfg); self._json({"message": f"Сохранено: {inst_name}/{name}"}); return

        if u.path == "/api/cd-use":
            inst = body.get("instance", "").strip(); profile = body.get("profile", "").strip()
            if not inst or not profile: return self._error("instance and profile required")
            pdata = cfg.get("claude_desktop_profiles", {}).get(inst, {}).get(profile)
            if not pdata: return self._error(f"Profile {profile} not found for {inst}")
            do_auto_backup(cfg)
            write_file_text(str(CLAUDE_DESKTOP_DIR / inst / "claude_desktop_config.json"), pdata["content"])
            self._json({"message": f"Активирован: {inst}/{profile}"}); return

        if u.path == "/api/cd-delete":
            inst = body.get("instance", "").strip(); profile = body.get("profile", "").strip()
            dp = cfg.get("claude_desktop_profiles", {}).get(inst, {})
            if profile in dp: del dp[profile]
            save_config(cfg); self._json({"message": f"Удалён: {inst}/{profile}"}); return

        # CC presets
        if u.path == "/api/cc-save":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            if not CLAUDE_CODE_SETTINGS.exists(): return self._error("settings.json не найден")
            content = read_file_text(CLAUDE_CODE_SETTINGS)
            try: settings_json = json.loads(content)
            except Exception: settings_json = content
            cfg.setdefault("claude_code_presets", {})[name] = {"hash": file_hash(CLAUDE_CODE_SETTINGS), "settings": settings_json, "raw": content}
            save_config(cfg); self._json({"message": f"Пресет '{name}' сохранён"}); return

        if u.path == "/api/cc-use":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            pdata = cfg.get("claude_code_presets", {}).get(name)
            if not pdata: return self._error(f"Пресет '{name}' не найден")
            do_auto_backup(cfg)
            raw = pdata.get("raw", "")
            if not raw:
                if isinstance(pdata.get("settings"), dict): raw = json.dumps(pdata["settings"], ensure_ascii=False, indent=2)
                else: raw = str(pdata.get("settings", ""))
            write_file_text(str(CLAUDE_CODE_SETTINGS), raw)
            self._json({"message": f"Активирован пресет '{name}'"}); return

        if u.path == "/api/cc-delete":
            name = body.get("name", "").strip()
            cfg.get("claude_code_presets", {}).pop(name, None)
            save_config(cfg); self._json({"message": f"Пресет '{name}' удалён"}); return

        # CC env vars
        if u.path == "/api/cc-preset-env":
            name = body.get("name", "").strip(); new_env = body.get("env", {})
            if not name: return self._error("name required")
            presets = cfg.get("claude_code_presets", {})
            pdata = presets.get(name)
            if pdata is None: return self._error(f"Пресет '{name}' не найден")
            if not isinstance(pdata.get("settings"), dict):
                pdata["settings"] = {}
            pdata["settings"]["env"] = new_env
            pdata["raw"] = json.dumps(pdata["settings"], ensure_ascii=False, indent=2)
            save_config(cfg); self._json({"message": f"Env vars обновлены для '{name}'"}); return

        # CX profiles
        if u.path == "/api/cx-save":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            if not CODEX_CONFIG.exists(): return self._error("config.toml не найден")
            config_text = read_file_text(CODEX_CONFIG); auth_text = read_file_text(CODEX_AUTH)
            ch = file_hash(CODEX_CONFIG); ah = file_hash(CODEX_AUTH)
            email = ""; model = ""
            for line in config_text.splitlines():
                if line.startswith("model"):
                    model = line.split("=")[-1].strip().strip('" ')
            try:
                import base64
                auth_json = json.loads(auth_text) if auth_text else {}
                id_token = auth_json.get("tokens", {}).get("id_token", "")
                if id_token:
                    parts = id_token.split(".")
                    if len(parts) > 1:
                        payload = parts[1]
                        pad = 4 - len(payload) % 4
                        if pad != 4: payload += "=" * pad
                        claims = json.loads(base64.urlsafe_b64decode(payload))
                        email = claims.get("email", "")
            except Exception: pass
            cfg.setdefault("codex_profiles", {})[name] = {"config_hash": ch, "auth_hash": ah, "config": config_text, "auth": auth_text, "email": email, "model": model, "endpoint": cfg.get("codex_endpoint", "")}
            save_config(cfg); self._json({"message": f"Профиль '{name}' сохранён"}); return

        if u.path == "/api/cx-use":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            pdata = cfg.get("codex_profiles", {}).get(name)
            if not pdata: return self._error(f"Профиль '{name}' не найден")
            do_auto_backup(cfg)
            if pdata.get("config"): write_file_text(str(CODEX_CONFIG), pdata["config"])
            if pdata.get("auth"): write_file_text(str(CODEX_AUTH), pdata["auth"])
            if pdata.get("endpoint"): cfg["codex_endpoint"] = pdata["endpoint"]
            save_config(cfg); self._json({"message": f"Активирован профиль '{name}'"}); return

        if u.path == "/api/cx-delete":
            name = body.get("name", "").strip()
            cfg.get("codex_profiles", {}).pop(name, None)
            save_config(cfg); self._json({"message": f"Профиль '{name}' удалён"}); return

        # CX endpoint
        if u.path == "/api/cx-set-endpoint":
            url = body.get("url", "").strip()
            if not url: return self._error("url required")
            cfg["codex_endpoint"] = url; save_config(cfg)
            self._json({"message": f"Endpoint: {url}"}); return

        if u.path == "/api/cx-clear-endpoint":
            cfg["codex_endpoint"] = ""; save_config(cfg)
            self._json({"message": "Endpoint сброшен"}); return

        if u.path == "/api/cx-create-wrapper":
            endpoint = cfg.get("codex_endpoint", "")
            wrapper_path = HOME / ".local" / "bin" / "codex-wrapper"
            codex_bin = "/Applications/Codex.app/Contents/Resources/codex"
            if not os.path.exists(codex_bin): codex_bin = shutil.which("codex") or ""
            script = "#!/bin/bash\n"
            if endpoint: script += f'export OPENAI_BASE_URL="{endpoint}"\n'
            script += f'exec "{codex_bin}" "$@"\n' if codex_bin else 'exec codex "$@"\n'
            write_file_text(str(wrapper_path), script); os.chmod(str(wrapper_path), 0o755)
            msg = f"Wrapper: {wrapper_path}" + (f"\nOPENAI_BASE_URL={endpoint}" if endpoint else "")
            self._json({"message": msg}); return

        # Skills
        if u.path == "/api/sk-add-root":
            p = str(expand_path(body.get("path", "")))
            if not p: return self._error("path required")
            custom = cfg.setdefault("custom_roots", [])
            if p not in custom: custom.append(p)
            save_config(cfg)
            self._json({"roots": scan_skills_roots(cfg), "message": f"Добавлено: {p}"}); return

        if u.path == "/api/sk-sync":
            ok, out = do_sync(body.get("source", ""), body.get("targets", []), body.get("skills", []), body.get("overwrite", False), body.get("dry_run", False), body.get("use_symlink", False))
            self._json({"ok": ok, "log": out}); return

        # Scenes
        if u.path == "/api/scenes-save":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            cc_current = get_current_cc_preset_name(cfg)
            cx_current = get_current_cx_profile_name(cfg)
            cd_instances = find_claude_instances()
            cd_profiles = {}
            for inst in cd_instances:
                inst_profiles = cfg.get("claude_desktop_profiles", {}).get(inst["name"], {})
                ch = file_hash(inst["config_path"]) if inst["config_path"] and os.path.exists(inst["config_path"]) else None
                for pname, pdata in inst_profiles.items():
                    if ch and pdata.get("hash") == ch:
                        cd_profiles[inst["name"]] = pname
            cfg.setdefault("scenes", {})[name] = {"cd_profiles": cd_profiles, "cc_preset": cc_current, "cx_profile": cx_current}
            save_config(cfg); self._json({"message": f"Сцена '{name}' сохранена"}); return

        if u.path == "/api/scenes-apply":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            scene = cfg.get("scenes", {}).get(name)
            if not scene: return self._error(f"Сцена '{name}' не найдена")
            do_auto_backup(cfg)
            errors = []
            # Apply CD profiles
            for inst_name, profile_name in scene.get("cd_profiles", {}).items():
                pdata = cfg.get("claude_desktop_profiles", {}).get(inst_name, {}).get(profile_name)
                if pdata:
                    write_file_text(str(CLAUDE_DESKTOP_DIR / inst_name / "claude_desktop_config.json"), pdata["content"])
            # Apply CC preset
            cc_name = scene.get("cc_preset")
            if cc_name:
                pdata = cfg.get("claude_code_presets", {}).get(cc_name)
                if pdata:
                    raw = pdata.get("raw", "")
                    if not raw and isinstance(pdata.get("settings"), dict): raw = json.dumps(pdata["settings"], ensure_ascii=False, indent=2)
                    write_file_text(str(CLAUDE_CODE_SETTINGS), raw)
            # Apply CX profile
            cx_name = scene.get("cx_profile")
            if cx_name:
                pdata = cfg.get("codex_profiles", {}).get(cx_name)
                if pdata:
                    if pdata.get("config"): write_file_text(str(CODEX_CONFIG), pdata["config"])
                    if pdata.get("auth"): write_file_text(str(CODEX_AUTH), pdata["auth"])
            self._json({"message": f"Сцена '{name}' применена" + (f" ({len(errors)} errors)" if errors else "")}); return

        if u.path == "/api/scenes-delete":
            name = body.get("name", "").strip()
            cfg.get("scenes", {}).pop(name, None)
            save_config(cfg); self._json({"message": f"Сцена '{name}' удалена"}); return

        # Quick launch
        if u.path == "/api/quick-launch":
            cc_name = get_current_cc_preset_name(cfg)
            cx_name = get_current_cx_profile_name(cfg)
            endpoint = cfg.get("codex_endpoint", "")
            lines = ["#!/bin/bash", "# MultiManager Quick Launch", f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
            if cc_name:
                lines.append(f"# Claude Code preset: {cc_name}")
                lines.append(f"# claude code (uses ~/.claude/settings.json)")
                lines.append("alias cc='claude code'")
                lines.append("")
            if cx_name:
                lines.append(f"# Codex profile: {cx_name}")
                if endpoint:
                    lines.append(f'export OPENAI_BASE_URL="{endpoint}"')
                lines.append("alias cx='codex-wrapper' 2>/dev/null || alias cx='OPENAI_BASE_URL=\"'$OPENAI_BASE_URL'\" codex'")
                lines.append("")
            lines.append("# Copy these aliases to ~/.zshrc or ~/.bashrc")
            self._json({"script": "\n".join(lines)}); return

        # Backups
        if u.path == "/api/backup-now":
            do_auto_backup(cfg)
            self._json({"message": "Бэкап создан"}); return

        if u.path == "/api/backup-restore":
            name = body.get("name", "").strip()
            if not name: return self._error("name required")
            ok, msg = restore_backup(name)
            self._json({"ok": ok, "message": msg}); return

        if u.path == "/api/backup-delete":
            name = body.get("name", "").strip()
            f = BACKUP_DIR / f"{name}.json"
            if f.exists(): f.unlink()
            self._json({"message": f"Бэкап '{name}' удалён"}); return

        if u.path == "/api/set-auto-backup":
            cfg["auto_backup"] = body.get("enabled", True)
            save_config(cfg); self._json({"message": "OK"}); return

        # Skill diff
        if u.path == "/api/sk-diff":
            master = body.get("master", ""); targets = body.get("targets", [])
            if not master or not targets: return self._error("master and targets required")
            self._json({"diffs": get_skill_diffs(master, targets)}); return

        if u.path == "/api/sk-sync-one":
            source = body.get("source", ""); dest = body.get("dest", "")
            if not source or not dest: return self._error("source and dest required")
            ok, msg = sync_one_skill(source, dest)
            self._json({"ok": ok, "message": msg}); return

        # CD data copy
        if u.path == "/api/cd-copy-data":
            from_name = body.get("from", ""); to_name = body.get("to", ""); databases = body.get("databases", ["IndexedDB"])
            if not from_name or not to_name: return self._error("from and to required")
            ok, msg = copy_cd_data(from_name, to_name, databases)
            self._json({"ok": ok, "message": msg}); return

        # MCP add
        if u.path == "/api/mcp-add":
            name = body.get("name", ""); tool = body.get("tool", "")
            srv_type = body.get("type", "stdio"); command = body.get("command", "")
            args = body.get("args", []); url = body.get("url", "")
            if not name or not tool: return self._error("name and tool required")
            ok, msg = mcp_add_server(tool, name, srv_type, command, args, url)
            self._json({"ok": ok, "error": None if ok else msg}); return

        # MCP delete
        if u.path == "/api/mcp-delete":
            name = body.get("name", ""); source = body.get("source", ""); instance = body.get("instance", "")
            ok, msg = mcp_delete_server(name, source, instance)
            self._json({"ok": ok, "error": None if ok else msg}); return

        # MCP toggle
        if u.path == "/api/mcp-toggle":
            name = body.get("name", ""); source = body.get("source", ""); instance = body.get("instance", "")
            ok, msg = mcp_toggle_server(name, source, instance)
            self._json({"ok": ok, "error": None if ok else msg}); return

        # Plugins CC toggle
        if u.path == "/api/plugins-cc-toggle":
            name = body.get("name", "")
            ok, msg = plugins_cc_toggle(name)
            self._json({"ok": ok, "error": None if ok else msg}); return

        # Plugins CX toggle
        if u.path == "/api/plugins-cx-toggle":
            name = body.get("name", "")
            ok, msg = plugins_cx_toggle(name)
            self._json({"ok": ok, "error": None if ok else msg}); return

        self.send_error(404)

    def log_message(self, *args): pass


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close(); return port


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    print(f"{APP_NAME} running: {url}")
    server.serve_forever()


if __name__ == "__main__":
    main()
