#!/usr/bin/env python3
"""MultiManager v2 — Unified AI account manager with macOS menu bar."""
import json, os, shutil, socket, sys, threading, time, webbrowser, hashlib, uuid, base64, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime

APP_NAME = "MultiManager"
HOME = Path.home()
CONFIG_DIR = HOME / ".multimanager"
CONFIG_FILE = CONFIG_DIR / "config.json"
BACKUP_DIR = CONFIG_DIR / "backups"
MASTER_DIR = CONFIG_DIR / "master"
MASTER_SKILLS = MASTER_DIR / "skills"
MASTER_MCP = MASTER_DIR / "mcp.json"

CLAUDE_DESKTOP_DIR = HOME / "Library" / "Application Support"
CC_SETTINGS = HOME / ".claude" / "settings.json"
CX_CONFIG = HOME / ".codex" / "config.toml"
CX_AUTH = HOME / ".codex" / "auth.json"
ANTHROPIC_CRED_DIR = HOME / ".config" / "anthropic" / "credentials"
OPENCODE_CFG = HOME / ".config" / "opencode" / "opencode.json"
CLINE_CFG = HOME / ".cline" / "mcp_settings.json"
ROO_CFG = HOME / ".roo" / "mcp_settings.json"

CD_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CD_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"

PROGRAMS = [
    {"id": "claude-code", "name": "Claude Code", "letter": "C",
     "config_path": str(CC_SETTINGS), "type": "json",
     "skills_dir": str(HOME / ".claude" / "skills"),
     "mcp_key": "mcpServers"},
    {"id": "codex", "name": "Codex", "letter": "X",
     "config_path": str(CX_CONFIG), "type": "toml",
     "skills_dir": str(HOME / ".codex" / "skills"),
     "mcp_key": "mcp_servers"},
    {"id": "opencode", "name": "OpenCode", "letter": "O",
     "config_path": str(OPENCODE_CFG), "type": "json",
     "skills_dir": str(HOME / ".config" / "opencode" / "skills"),
     "mcp_key": "mcpServers"},
    {"id": "cline", "name": "Cline", "letter": "L",
     "config_path": str(CLINE_CFG), "type": "json",
     "skills_dir": str(HOME / ".cline" / "skills"),
     "mcp_key": "mcpServers"},
    {"id": "roo-code", "name": "Roo Code", "letter": "R",
     "config_path": str(ROO_CFG), "type": "json",
     "skills_dir": str(HOME / ".roo" / "skills"),
     "mcp_key": "mcpServers"},
]

DEFAULT_CONFIG = {
    "accounts": [],
    "auto_backup": True,
    "custom_skill_roots": [],
}

# ============================================================
# UTILS
# ============================================================
def expand_path(p):
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()

def load_config():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text())
        except: return {}
    return {}

def save_config(cfg):
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

def ensure_defaults():
    cfg = load_config()
    changed = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg: cfg[k] = v; changed = True
    if changed: save_config(cfg)
    return cfg

def file_hash(path):
    try: return hashlib.sha256(open(path, "rb").read(65536)).hexdigest()
    except: return ""

def read_file(path):
    try: return Path(path).read_text()
    except: return ""

def write_file(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)

def format_size(n):
    if n < 1024: return f"{n} B"
    if n < 1048576: return f"{n/1024:.1f} KB"
    return f"{n/1048576:.1f} MB"

def decode_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) < 2: return {}
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except: return {}

def do_backup(cfg):
    if not cfg.get("auto_backup"): return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bk = {"created_at": stamp, "files": {}}
    for cat, f in [("cc", CC_SETTINGS), ("cx_cfg", CX_CONFIG), ("cx_auth", CX_AUTH), ("opencode", OPENCODE_CFG)]:
        if f.exists():
            try: bk["files"][cat] = {"path": str(f), "content": f.read_text()}
            except: pass
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / f"auto-{stamp}.json").write_text(json.dumps(bk, ensure_ascii=False, indent=2))

def provider_color(provider):
    return {"anthropic": "#d97757", "openai": "#10a37f", "gemini": "#4285f4",
            "mistral": "#ff7000", "ollama": "#000", "deepseek": "#4d6bfe",
            "openrouter": "#6c63ff", "xai": "#1d1d1f", "groq": "#f55036"}.get(provider, "#6b7280")

def detect_provider(url):
    if not url: return "openai"
    u = url.lower()
    for kw, p in [("z.ai","anthropic"),("anthropic","anthropic"),("bigmodel","anthropic"),
                  ("openrouter","openrouter"),("deepseek","deepseek"),("mistral","mistral"),
                  ("groq","groq"),("xai","xai"),("gemini","gemini"),("ollama","ollama"),
                  ("localhost:11434","ollama")]:
        if kw in u: return p
    return "openai"

# ============================================================
# TOML HELPERS (simple, no dependency)
# ============================================================
def parse_toml_simple(text):
    result = {}; current_section = None; current_sub = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        if s.startswith("[[") and s.endswith("]]"):
            key = s[2:-2].strip()
            current_section = key; current_sub = None
            result.setdefault(key, [])
            result[key].append({})
            continue
        if s.startswith("[") and s.endswith("]"):
            key = s[1:-1].strip()
            current_section = key; current_sub = None
            if key not in result: result[key] = {}
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            k = k.strip(); v = v.strip()
            if v.startswith('"') and v.endswith('"'): v = v[1:-1]
            elif v == "true": v = True
            elif v == "false": v = False
            else:
                try: v = int(v)
                except:
                    try: v = float(v)
                    except: pass
            if current_section:
                if isinstance(result.get(current_section), list):
                    result[current_section][-1][k] = v
                else:
                    result[current_section][k] = v
            else:
                result[k] = v
    return result

def write_toml_simple(data, top_level_order=None):
    lines = []; top_done = set()
    order = top_level_order or ["model", "model_provider", "model_reasoning_effort", "personality", "approval_policy", "sandbox_mode", "notify"]

    for k in order:
        if k in data and not isinstance(data[k], dict) and not isinstance(data[k], list):
            lines.append(f'{k} = {_toml_val(data[k])}')
            top_done.add(k)

    for k, v in data.items():
        if k in top_done: continue
        if isinstance(v, dict) and not k.startswith("["):
            lines.append(f"\n[{k}]")
            for sk, sv in v.items():
                if isinstance(sv, dict):
                    lines.append(f"\n[{k}.{sk}]")
                    for ssk, ssv in sv.items():
                        lines.append(f'{ssk} = {_toml_val(ssv)}')
                elif isinstance(sv, list):
                    for item in sv:
                        lines.append(f"\n[[{k}.{sk}]]")
                        if isinstance(item, dict):
                            for ik, iv in item.items(): lines.append(f'{ik} = {_toml_val(iv)}')
                else:
                    lines.append(f'{sk} = {_toml_val(sv)}')
        elif isinstance(v, list):
            for item in v:
                lines.append(f"\n[[{k}]]")
                if isinstance(item, dict):
                    for ik, iv in item.items(): lines.append(f'{ik} = {_toml_val(iv)}')
        elif not isinstance(v, (dict, list)):
            lines.append(f'{k} = {_toml_val(v)}')

    return "\n".join(lines)

def _toml_val(v):
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, str): return f'"{v}"'
    if isinstance(v, (int, float)): return str(v)
    if isinstance(v, list): return json.dumps(v)
    return str(v)

# ============================================================
# ACCOUNT OPERATIONS
# ============================================================
def _read_cc_config():
    if not CC_SETTINGS.exists(): return {}
    try: return json.loads(CC_SETTINGS.read_text())
    except: return {}

def _write_cc_config(data):
    write_file(str(CC_SETTINGS), json.dumps(data, ensure_ascii=False, indent=2))

def _read_cx_config():
    if not CX_CONFIG.exists(): return {}
    return parse_toml_simple(read_file(CX_CONFIG))

def _write_cx_config(data):
    order = ["model", "model_provider", "model_reasoning_effort", "personality",
             "approval_policy", "sandbox_mode", "notify", "openai_base_url"]
    write_file(str(CX_CONFIG), write_toml_simple(data, order))

def _read_json_config(path):
    if not Path(path).exists(): return {}
    try: return json.loads(Path(path).read_text())
    except: return {}

def _write_json_config(path, data):
    write_file(path, json.dumps(data, ensure_ascii=False, indent=2))


def detect_active_accounts():
    result = {}
    accounts = ensure_defaults().get("accounts", [])

    # Claude Code
    cc = _read_cc_config()
    env = cc.get("env", {})
    cc_url = env.get("ANTHROPIC_BASE_URL", "")
    cc_key = env.get("ANTHROPIC_AUTH_TOKEN", "") or env.get("ANTHROPIC_API_KEY", "")
    cc_model = cc.get("model", "")
    best = None; best_score = 0
    for acc in accounts:
        score = 0
        a_url = acc.get("base_url", "")
        a_key = acc.get("api_key", "")
        a_model = acc.get("model", "")
        if a_url and cc_url and a_url.rstrip("/") == cc_url.rstrip("/"): score += 3
        if a_key and cc_key and (a_key == cc_key or a_key[:20] == cc_key[:20]): score += 3
        if a_model and cc_model and a_model == cc_model: score += 1
        if score > best_score: best_score = score; best = acc
    result["claude-code"] = best["id"] if best and best_score >= 2 else None

    # Codex
    cx = _read_cx_config()
    cx_model = cx.get("model", "")
    cx_provider = cx.get("model_provider", "")
    cx_base_url = ""
    mps = cx.get("model_providers", {})
    if cx_provider and isinstance(mps, dict):
        mp_data = mps.get(cx_provider, {})
        if isinstance(mp_data, dict):
            cx_base_url = mp_data.get("base_url", "")
    best = None; best_score = 0
    for acc in accounts:
        score = 0
        a_model = acc.get("model", "")
        a_url = acc.get("base_url", "")
        if a_url and cx_base_url and a_url.rstrip("/") == cx_base_url.rstrip("/"): score += 3
        if a_model and cx_model and a_model == cx_model: score += 1
        if acc.get("codex_provider") and acc["codex_provider"] == cx_provider: score += 3
        if score > best_score: best_score = score; best = acc
    result["codex"] = best["id"] if best and best_score >= 1 else None

    # OpenCode
    oc = _read_json_config(OPENCODE_CFG)
    for pname, pdata in (oc.get("provider") or {}).items():
        if isinstance(pdata, dict):
            opts = pdata.get("options", {})
            oc_key = opts.get("apiKey", "")
            oc_url = opts.get("baseUrl", "")
            best = None; best_score = 0
            for acc in accounts:
                score = 0
                if acc.get("api_key") and oc_key and acc["api_key"][:20] == oc_key[:20]: score += 3
                if acc.get("base_url") and oc_url and acc["base_url"] in oc_url: score += 2
                if score > best_score: best_score = score; best = acc
            result["opencode"] = best["id"] if best and best_score >= 2 else None

    return result


def import_accounts():
    cfg = ensure_defaults()
    accounts = cfg.setdefault("accounts", [])
    imported = []
    existing_keys = {a.get("api_key", "")[:20] for a in accounts}
    existing_urls = {a.get("base_url", "").rstrip("/") for a in accounts}

    # From Claude Code settings.json
    cc = _read_cc_config()
    env = cc.get("env", {})
    cc_url = env.get("ANTHROPIC_BASE_URL", "")
    cc_key = env.get("ANTHROPIC_AUTH_TOKEN", "") or env.get("ANTHROPIC_API_KEY", "")
    cc_model = cc.get("model", "")
    if cc_url or cc_key:
        prov = detect_provider(cc_url) if cc_url else "anthropic"
        if "z.ai" in cc_url:
            name = "Z.AI (GLM)"
        elif cc_url:
            name = f"Claude ({prov})"
        else:
            name = "Claude Code Default"
        if cc_url.rstrip("/") not in existing_urls and cc_key[:20] not in existing_keys:
            acc = {"id": uuid.uuid4().hex[:8], "name": name, "provider": prov,
                   "api_key": cc_key, "base_url": cc_url, "model": cc_model}
            # model overrides
            sonnet = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
            if sonnet:
                acc["claude_overrides"] = {
                    "sonnet": sonnet,
                    "opus": env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", ""),
                    "haiku": env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")}
            accounts.append(acc)
            imported.append(name)
            existing_urls.add(cc_url.rstrip("/"))
            existing_keys.add(cc_key[:20])

    # From Codex config.toml
    cx = _read_cx_config()
    cx_model = cx.get("model", "")
    cx_provider = cx.get("model_provider", "")
    mps = cx.get("model_providers", {})
    if cx_model:
        name = f"Codex ({cx_provider or 'openai'})"
        if name not in {a["name"] for a in accounts}:
            cx_base = ""
            if cx_provider and isinstance(mps, dict):
                mp = mps.get(cx_provider, {})
                if isinstance(mp, dict): cx_base = mp.get("base_url", "")
            acc = {"id": uuid.uuid4().hex[:8], "name": name, "provider": detect_provider(cx_base) if cx_base else "openai",
                   "api_key": "", "base_url": cx_base, "model": cx_model}
            if cx_provider: acc["codex_provider"] = cx_provider
            accounts.append(acc)
            imported.append(name)

    # From Codex auth.json (email/plan)
    if CX_AUTH.exists():
        try:
            ad = json.loads(CX_AUTH.read_text())
            id_token = ad.get("tokens", {}).get("id_token", "")
            claims = decode_jwt(id_token)
            email = claims.get("email", "")
            if email:
                auth_info = {}
                for k in claims:
                    if "auth" in k.lower() and isinstance(claims[k], dict):
                        auth_info = claims[k]; break
                plan = auth_info.get("chatgpt_plan_type", "")
                name = f"Codex ({email.split('@')[0]})"
                existing_emails = {a.get("email","") for a in accounts}
                if email not in existing_emails and name not in {a["name"] for a in accounts}:
                    acc = {"id": uuid.uuid4().hex[:8], "name": name, "provider": "openai",
                           "api_key": "", "base_url": "", "model": cx_model,
                           "email": email, "plan": plan}
                    accounts.append(acc)
                    imported.append(name)
        except: pass

    # From OpenCode
    oc = _read_json_config(OPENCODE_CFG)
    for pname, pdata in (oc.get("provider") or {}).items():
        if isinstance(pdata, dict):
            opts = pdata.get("options", {})
            ok = opts.get("apiKey", "")
            ou = opts.get("baseUrl", "")
            if ok or ou:
                name = f"OpenCode ({pname})"
                if ou.rstrip("/") not in existing_urls and ok[:20] not in existing_keys:
                    acc = {"id": uuid.uuid4().hex[:8], "name": name, "provider": detect_provider(ou),
                           "api_key": ok, "base_url": ou, "model": ""}
                    accounts.append(acc)
                    imported.append(name)
                    existing_urls.add(ou.rstrip("/"))
                    existing_keys.add(ok[:20])

    save_config(cfg)
    return imported


def apply_account(acc_id, program_id):
    cfg = ensure_defaults()
    acc = next((a for a in cfg.get("accounts", []) if a["id"] == acc_id), None)
    if not acc: return False, "Account not found"
    do_backup(cfg)

    if program_id == "claude-code":
        cc = _read_cc_config()
        env = cc.setdefault("env", {})
        base_url = acc.get("base_url", "")
        api_key = acc.get("api_key", "")
        model = acc.get("model", "")
        # Clear old auth keys
        for k in ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"]:
            env.pop(k, None)
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        elif api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if model: cc["model"] = model
        if acc.get("claude_overrides"):
            co = acc["claude_overrides"]
            if co.get("sonnet"): env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = co["sonnet"]
            if co.get("opus"): env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = co["opus"]
            if co.get("haiku"): env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = co["haiku"]
        _write_cc_config(cc)
        return True, f"Claude Code: {acc['name']}"

    elif program_id == "codex":
        cx = _read_cx_config()
        model = acc.get("model", "")
        base_url = acc.get("base_url", "")
        codex_prov = acc.get("codex_provider", "")
        if model: cx["model"] = model
        if base_url and codex_prov:
            cx["model_provider"] = codex_prov
            mps = cx.setdefault("model_providers", {})
            mps[codex_prov] = {"name": acc.get("name", codex_prov), "base_url": base_url}
            env_key_name = codex_prov.upper().replace("-", "_") + "_API_KEY"
            mps[codex_prov]["env_key"] = env_key_name
        elif base_url:
            cx["openai_base_url"] = base_url
        _write_cx_config(cx)
        return True, f"Codex: {acc['name']}"

    elif program_id == "opencode":
        oc = _read_json_config(OPENCODE_CFG)
        prov = oc.setdefault("provider", {})
        base_url = acc.get("base_url", "")
        api_key = acc.get("api_key", "")
        if "z.ai" in base_url or "zai" in acc.get("provider", ""):
            zai = prov.setdefault("zai-coding-plan", {})
            opts = zai.setdefault("options", {})
            if api_key: opts["apiKey"] = api_key
            if base_url: opts["baseUrl"] = base_url
        _write_json_config(OPENCODE_CFG, oc)
        return True, f"OpenCode: {acc['name']}"

    return False, f"{program_id}: not implemented"

# ============================================================
# SKILLS
# ============================================================
def scan_master_skills():
    MASTER_SKILLS.mkdir(parents=True, exist_ok=True)
    skills = []
    for d in sorted(MASTER_SKILLS.iterdir()):
        if d.is_dir():
            md = d / "SKILL.md"
            skills.append({"name": d.name, "path": str(d), "has_md": md.exists(),
                           "size": md.stat().st_size if md.exists() else 0})
    return skills

def scan_program_skills():
    result = {}
    for prog in PROGRAMS:
        sd = expand_path(prog["skills_dir"])
        if sd.exists():
            result[prog["id"]] = [d.name for d in sd.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
        else:
            result[prog["id"]] = []
    return result

def sync_skill_to_programs(skill_name, program_ids):
    src = MASTER_SKILLS / skill_name
    if not src.exists(): return False, f"Skill {skill_name} not in master"
    results = []
    for pid in program_ids:
        prog = next(p for p in PROGRAMS if p["id"] == pid)
        dst = expand_path(prog["skills_dir"]) / skill_name
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists(): shutil.rmtree(str(dst))
            shutil.copytree(str(src), str(dst))
            results.append(f"{prog['name']}: OK")
        except Exception as e:
            results.append(f"{prog['name']}: {e}")
    return True, "; ".join(results)

def sync_all_skills():
    skills = scan_master_skills()
    results = []
    for sk in skills:
        ok, msg = sync_skill_to_programs(sk["name"], [p["id"] for p in PROGRAMS])
        results.append(msg)
    return results

def collect_skill_to_master(skill_name, source_program_id):
    prog = next(p for p in PROGRAMS if p["id"] == source_program_id)
    src = expand_path(prog["skills_dir"]) / skill_name
    if not src.exists(): return False, f"Skill not found in {prog['name']}"
    dst = MASTER_SKILLS / skill_name
    MASTER_SKILLS.mkdir(parents=True, exist_ok=True)
    if dst.exists(): shutil.rmtree(str(dst))
    shutil.copytree(str(src), str(dst))
    return True, f"Collected {skill_name} from {prog['name']}"

def delete_skill_from_master(skill_name):
    dst = MASTER_SKILLS / skill_name
    if dst.exists(): shutil.rmtree(str(dst))
    return True

# ============================================================
# MCP
# ============================================================
def scan_master_mcp():
    if not MASTER_MCP.exists(): return {}
    try: return json.loads(MASTER_MCP.read_text())
    except: return {}

def save_master_mcp(data):
    MASTER_MCP.parent.mkdir(parents=True, exist_ok=True)
    MASTER_MCP.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def scan_program_mcp():
    result = {}
    for prog in PROGRAMS:
        cp = prog["config_path"]
        if not cp: result[prog["id"]] = {}; continue
        if prog["type"] == "json":
            d = _read_json_config(cp)
            result[prog["id"]] = d.get(prog["mcp_key"], {})
        elif prog["type"] == "toml":
            d = _read_cx_config()
            result[prog["id"]] = d.get("mcp_servers", {})
        else:
            result[prog["id"]] = {}
    return result

def sync_mcp_to_programs(server_name, server_config, program_ids):
    results = []
    for pid in program_ids:
        prog = next(p for p in PROGRAMS if p["id"] == pid)
        cp = prog["config_path"]
        if not cp: continue
        if prog["type"] == "json":
            d = _read_json_config(cp)
            mcp = d.setdefault(prog["mcp_key"], {})
            mcp[server_name] = server_config
            _write_json_config(cp, d)
            results.append(f"{prog['name']}: OK")
        elif prog["type"] == "toml":
            d = _read_cx_config()
            mcp = d.setdefault("mcp_servers", {})
            mcp[server_name] = server_config
            _write_cx_config(d)
            results.append(f"{prog['name']}: OK")
    return "; ".join(results)

def delete_mcp_from_program(server_name, program_id):
    prog = next(p for p in PROGRAMS if p["id"] == program_id)
    cp = prog["config_path"]
    if not cp: return
    if prog["type"] == "json":
        d = _read_json_config(cp)
        d.get(prog["mcp_key"], {}).pop(server_name, None)
        _write_json_config(cp, d)
    elif prog["type"] == "toml":
        d = _read_cx_config()
        d.get("mcp_servers", {}).pop(server_name, None)
        _write_cx_config(d)

# ============================================================
# HTTP HANDLER
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, s=200):
        d = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(s)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _html(self):
        d = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _err(self, msg, s=400):
        self._json({"error": msg}, s)

    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/": self._html(); return
        cfg = ensure_defaults()

        if u.path == "/api/accounts":
            accounts = cfg.get("accounts", [])
            active = detect_active_accounts()
            enriched = []
            for a in accounts:
                p = a.get("provider", "openai")
                if a.get("base_url"): p = detect_provider(a["base_url"])
                enriched.append({**a, "_color": provider_color(p), "_prov": p})
            self._json({"accounts": enriched, "active": active, "programs": PROGRAMS})
            return

        if u.path == "/api/skills":
            master = scan_master_skills()
            prog_skills = scan_program_skills()
            self._json({"master": master, "programs": prog_skills})
            return

        if u.path == "/api/mcp":
            master = scan_master_mcp()
            prog_mcp = scan_program_mcp()
            all_names = set(master.keys())
            for v in prog_mcp.values(): all_names.update(v.keys())
            servers = []
            for name in sorted(all_names):
                in_master = name in master
                config = master.get(name, next((v.get(name, {}) for v in prog_mcp.values() if name in v), {}))
                progs = {pid: name in pmcp for pid, pmcp in prog_mcp.items()}
                servers.append({"name": name, "in_master": in_master, "config": config, "programs": progs})
            self._json({"servers": servers, "program_names": {p["id"]: p["name"] for p in PROGRAMS}})
            return

        if u.path == "/api/get-settings":
            self._json(cfg); return
        if u.path == "/api/backups":
            bks = []
            if BACKUP_DIR.exists():
                for f in sorted(BACKUP_DIR.iterdir(), reverse=True)[:20]:
                    if f.suffix == ".json":
                        bks.append({"name": f.stem, "size": format_size(f.stat().st_size), "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
            self._json({"backups": bks}); return
        if u.path == "/api/shutdown":
            self._json({"ok": True}); threading.Timer(0.1, lambda: os._exit(0)).start(); return
        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path); b = self._body(); cfg = ensure_defaults()

        # ACCOUNTS
        if u.path == "/api/import":
            names = import_accounts()
            self._json({"imported": names, "total": len(ensure_defaults().get("accounts", []))})
            return
        if u.path == "/api/account-create":
            name = b.get("name", "").strip()
            if not name: return self._err("name required")
            acc = {"id": uuid.uuid4().hex[:8], "name": name,
                   "provider": b.get("provider", "anthropic"),
                   "api_key": b.get("api_key", ""), "base_url": b.get("base_url", ""),
                   "model": b.get("model", ""), "email": b.get("email", "")}
            for k in ("claude_overrides", "codex_provider"):
                if b.get(k): acc[k] = b[k]
            cfg.setdefault("accounts", []).append(acc)
            save_config(cfg)
            self._json({"ok": True, "account": acc}); return
        if u.path == "/api/account-delete":
            aid = b.get("id", "")
            cfg["accounts"] = [a for a in cfg.get("accounts", []) if a["id"] != aid]
            save_config(cfg); self._json({"ok": True}); return
        if u.path == "/api/account-update":
            aid = b.get("id", "")
            for a in cfg.get("accounts", []):
                if a["id"] == aid:
                    for k in ("name", "provider", "api_key", "base_url", "model", "email", "claude_overrides", "codex_provider"):
                        if k in b: a[k] = b[k]
                    break
            save_config(cfg); self._json({"ok": True}); return
        if u.path == "/api/apply":
            aid = b.get("account_id", ""); pids = b.get("programs", [])
            if not aid: return self._err("account_id required")
            results = []
            for pid in pids:
                ok, msg = apply_account(aid, pid)
                results.append({"program": pid, "ok": ok, "message": msg})
            self._json({"results": results}); return

        # SKILLS
        if u.path == "/api/skill-sync":
            sn = b.get("skill", ""); pids = b.get("programs", [])
            if not sn: return self._err("skill name required")
            ok, msg = sync_skill_to_programs(sn, pids)
            self._json({"ok": ok, "message": msg}); return
        if u.path == "/api/skill-sync-all":
            results = sync_all_skills()
            self._json({"ok": True, "results": results}); return
        if u.path == "/api/skill-collect":
            sn = b.get("skill", ""); pid = b.get("program", "")
            ok, msg = collect_skill_to_master(sn, pid)
            self._json({"ok": ok, "message": msg}); return
        if u.path == "/api/skill-delete":
            sn = b.get("skill", "")
            delete_skill_from_master(sn)
            self._json({"ok": True}); return
        if u.path == "/api/skill-upload":
            sn = b.get("name", "").strip(); content = b.get("content", "")
            if not sn: return self._err("name required")
            dst = MASTER_SKILLS / sn
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "SKILL.md").write_text(content)
            self._json({"ok": True}); return

        # MCP
        if u.path == "/api/mcp-add":
            name = b.get("name", "").strip()
            if not name: return self._err("name required")
            config = {}
            if b.get("url"): config["url"] = b["url"]
            else: config = {"command": b.get("command", ""), "args": b.get("args", [])}
            master = scan_master_mcp()
            master[name] = config
            save_master_mcp(master)
            pids = b.get("programs", [])
            if pids: msg = sync_mcp_to_programs(name, config, pids)
            self._json({"ok": True}); return
        if u.path == "/api/mcp-sync":
            name = b.get("name", ""); pids = b.get("programs", [])
            master = scan_master_mcp()
            if name not in master: return self._err("not in master")
            msg = sync_mcp_to_programs(name, master[name], pids)
            self._json({"ok": True, "message": msg}); return
        if u.path == "/api/mcp-sync-all":
            master = scan_master_mcp()
            results = []
            for name, config in master.items():
                msg = sync_mcp_to_programs(name, config, [p["id"] for p in PROGRAMS])
                results.append(f"{name}: {msg}")
            self._json({"ok": True, "results": results}); return
        if u.path == "/api/mcp-delete":
            name = b.get("name", ""); pid = b.get("program", "")
            if pid: delete_mcp_from_program(name, pid)
            else:
                master = scan_master_mcp()
                master.pop(name, None)
                save_master_mcp(master)
            self._json({"ok": True}); return

        # SETTINGS
        if u.path == "/api/backup-now":
            do_backup(cfg); self._json({"ok": True}); return
        if u.path == "/api/set-auto-backup":
            cfg["auto_backup"] = b.get("enabled", True); save_config(cfg); self._json({"ok": True}); return

        self.send_error(404)

    def log_message(self, *a): pass


# ============================================================
# HTML
# ============================================================
HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>MultiManager</title>
<style>
:root{--bg:#0a0a0a;--sbg:#111;--card:#1a1a1a;--hover:#222;--sel:#2a2a2a;
--tx:#e5e5e5;--tx2:#888;--tx3:#555;--acc:#3b82f6;--acc2:#2563eb;
--brd:#2a2a2a;--brd2:#333;--ok:#22c55e;--warn:#f59e0b;--err:#ef4444;--r:8px;--rl:12px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--tx);display:flex;height:100vh;overflow:hidden;font-size:13px}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--brd2);border-radius:3px}

#sb{width:200px;min-width:200px;background:var(--sbg);border-right:1px solid var(--brd);display:flex;flex-direction:column;padding:12px 0}
.logo{padding:8px 16px 20px;font-weight:700;font-size:14px;color:var(--acc);display:flex;align-items:center;gap:8px}
.logo svg{width:16px;height:16px}
.ni{display:flex;align-items:center;gap:10px;padding:7px 14px;border-radius:var(--r);cursor:pointer;color:var(--tx2);transition:.15s;font-size:13px}
.ni:hover{background:var(--hover);color:var(--tx)}.ni.on{background:var(--sel);color:var(--tx)}
.ni svg{width:16px;height:16px;opacity:.6}.ni.on svg{opacity:1;color:var(--acc)}
.sep{height:1px;background:var(--brd);margin:8px 12px}

#main{flex:1;overflow:hidden;display:flex;flex-direction:column}
.pg{display:none;flex:1;overflow:auto;padding:0}.pg.on{display:flex}
.pt{font-size:20px;font-weight:600;padding:20px 24px 12px}

/* BUTTONS */
.b{padding:6px 12px;border-radius:var(--r);border:1px solid var(--brd2);background:var(--card);color:var(--tx);cursor:pointer;font-size:12px;transition:.15s;display:inline-flex;align-items:center;gap:4px}
.b:hover{background:var(--hover);border-color:var(--tx3)}
.bp{background:var(--acc);border-color:var(--acc);color:#fff}.bp:hover{background:var(--acc2)}
.bd{color:var(--err);border-color:var(--err)}.bd:hover{background:rgba(239,68,68,.1)}
.bs{padding:4px 8px;font-size:11px}

/* ACCOUNTS PAGE */
#pg-acc{flex-direction:row}
#acc-list{width:300px;min-width:300px;border-right:1px solid var(--brd);overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:6px}
#acc-list .lh{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
#acc-list .lh h3{font-size:11px;font-weight:600;color:var(--tx2);text-transform:uppercase;letter-spacing:.5px}

.ac{padding:12px;border-radius:var(--rl);border:1px solid var(--brd);cursor:pointer;transition:.15s}
.ac:hover{border-color:var(--brd2);background:var(--hover)}
.ac.sel{border-color:var(--acc);background:rgba(59,130,246,.08)}
.ac .ah{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.ac .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.ac .an{font-weight:500;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ac .ap{font-size:11px;color:var(--tx2);margin-left:auto}
.ac .am{font-size:11px;color:var(--tx3)}
.ac .ae{font-size:11px;color:var(--tx3)}

#ppanel{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;margin-bottom:16px}
.pc{padding:12px;border-radius:var(--rl);border:1px solid var(--brd);background:var(--card);transition:.15s;cursor:pointer}
.pc:hover{border-color:var(--brd2)}.pc.chk{border-color:var(--acc);background:rgba(59,130,246,.06)}
.pc .pt2{display:flex;align-items:center;gap:10px}
.pc .pi{width:32px;height:32px;border-radius:var(--r);background:var(--hover);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;flex-shrink:0}
.pc .pn{font-weight:500;font-size:14px}
.pc .pa{font-size:11px;color:var(--tx2);margin-left:auto}
.pc .pa .at{color:var(--ok);font-weight:500}
.pc .pc2{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--tx2);margin-top:6px}
.pc .pc2 input{accent-color:var(--acc)}

.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;color:var(--tx3);gap:8px;font-size:14px}

/* TOGGLE MATRIX (Skills + MCP) */
.tmat{width:100%;border-collapse:collapse}
.tmat th{text-align:left;padding:8px 10px;color:var(--tx2);font-size:11px;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid var(--brd);position:sticky;top:0;background:var(--bg);z-index:1}
.tmat td{padding:8px 10px;border-bottom:1px solid var(--brd);font-size:13px}
.tmat tr:hover td{background:var(--hover)}
.tmat input[type=checkbox]{accent-color:var(--acc);width:16px;height:16px;cursor:pointer}
.tmat .sn{font-weight:500}.tmat .sd{font-size:11px;color:var(--tx3)}
.master-tag{display:inline-block;padding:1px 6px;border-radius:8px;font-size:10px;background:rgba(59,130,246,.15);color:var(--acc);margin-left:6px}

/* MODAL */
.mo{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}.mo.open{display:flex}
.md{background:var(--card);border:1px solid var(--brd2);border-radius:var(--rl);padding:24px;width:420px;max-width:90vw}
.md h2{font-size:16px;font-weight:600;margin-bottom:16px}
.fg{margin-bottom:12px}.fg label{display:block;font-size:12px;color:var(--tx2);margin-bottom:4px}
.fg input,.fg select,.fg textarea{width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--brd2);border-radius:var(--r);color:var(--tx);font-size:13px;outline:none}
.fg input:focus,.fg select:focus{border-color:var(--acc)}
.fa{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}

#tc{position:fixed;bottom:20px;right:20px;z-index:200;display:flex;flex-direction:column;gap:8px}
.toast{padding:10px 16px;border-radius:var(--r);background:var(--card);border:1px solid var(--brd2);font-size:13px;animation:si .2s ease;max-width:400px}
.toast.ok{border-color:var(--ok)}.toast.er{border-color:var(--err)}
@keyframes si{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
</style></head><body>

<div id="sb">
  <div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>MultiManager</div>
  <div style="padding:0 8px;flex:1;display:flex;flex-direction:column;gap:2px">
    <div class="ni on" data-p="acc" onclick="go('acc')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>Accounts</div>
    <div class="ni" data-p="skills" onclick="go('skills')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>Skills</div>
    <div class="ni" data-p="mcp" onclick="go('mcp')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M1 12h4m14 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg>MCP</div>
    <div class="sep"></div>
    <div class="ni" data-p="set" onclick="go('set')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>Settings</div>
  </div>
  <div style="padding:8px 16px;font-size:11px;color:var(--tx3)"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--ok);box-shadow:0 0 4px var(--ok)"></span> Running</div>
</div>

<div id="main">
<!-- ACCOUNTS -->
<div id="pg-acc" class="pg on">
  <div id="acc-list">
    <div class="lh"><h3>Accounts</h3><div style="display:flex;gap:4px"><button class="b bs" onclick="doImport()">Import</button><button class="b bs bp" onclick="openModal('m-create')">+</button></div></div>
    <div id="acc-cards"></div>
  </div>
  <div id="ppanel">
    <div class="empty" id="no-sel"><p>Select an account to apply to programs</p></div>
    <div id="pcon" style="display:none">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2 id="ptitle" style="font-size:16px;font-weight:600"></h2>
        <div style="display:flex;gap:6px"><button class="b bs" onclick="allChk(true)">All</button><button class="b bs" onclick="allChk(false)">None</button><button class="b bs bp" onclick="applySel()">Apply</button></div>
      </div>
      <div class="pgrid" id="pgrid"></div>
    </div>
  </div>
</div>

<!-- SKILLS -->
<div id="pg-skills" class="pg">
  <div style="display:flex;justify-content:space-between;align-items:center;padding:20px 24px 12px">
    <div class="pt" style="padding:0">Skills</div>
    <div style="display:flex;gap:6px"><button class="b bs bp" onclick="syncAllSkills()">Sync All to Programs</button><button class="b bs" onclick="loadSkills()">Refresh</button></div>
  </div>
  <div style="flex:1;overflow:auto;padding:0 24px 20px"><table class="tmat" id="sk-tbl"><thead id="sk-head"></thead><tbody id="sk-body"></tbody></table></div>
</div>

<!-- MCP -->
<div id="pg-mcp" class="pg">
  <div style="display:flex;justify-content:space-between;align-items:center;padding:20px 24px 12px">
    <div class="pt" style="padding:0">MCP Servers</div>
    <div style="display:flex;gap:6px"><button class="b bs bp" onclick="syncAllMcp()">Sync All</button><button class="b bs bp" onclick="openModal('m-mcp')">+ Add</button></div>
  </div>
  <div style="flex:1;overflow:auto;padding:0 24px 20px"><table class="tmat" id="mcp-tbl"><thead id="mcp-head"></thead><tbody id="mcp-body"></tbody></table></div>
</div>

<!-- SETTINGS -->
<div id="pg-set" class="pg" style="padding:20px 24px">
  <div class="pt" style="padding:0 0 16px">Settings</div>
  <div id="set-con"></div>
</div>
</div>

<!-- MODALS -->
<div class="mo" id="m-create"><div class="md">
  <h2>New Account</h2>
  <div class="fg"><label>Name</label><input id="f-name" placeholder="e.g. Z.AI GLM"></div>
  <div class="fg"><label>Provider</label><select id="f-prov"><option value="anthropic">Anthropic</option><option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option><option value="gemini">Gemini</option><option value="deepseek">DeepSeek</option><option value="mistral">Mistral</option><option value="ollama">Ollama</option><option value="groq">Groq</option><option value="xai">xAI</option></select></div>
  <div class="fg"><label>API Key</label><input id="f-key" type="password" placeholder="sk-..."></div>
  <div class="fg"><label>Base URL</label><input id="f-url" placeholder="https://api.z.ai/api/anthropic"></div>
  <div class="fg"><label>Model</label><input id="f-model" placeholder="glm-5.1"></div>
  <div class="fa"><button class="b" onclick="closeModal('m-create')">Cancel</button><button class="b bp" onclick="createAcc()">Create</button></div>
</div></div>

<div class="mo" id="m-mcp"><div class="md">
  <h2>Add MCP Server</h2>
  <div class="fg"><label>Name</label><input id="mf-name" placeholder="my-server"></div>
  <div class="fg"><label>Command</label><input id="mf-cmd" placeholder="npx"></div>
  <div class="fg"><label>Args (comma)</label><input id="mf-args" placeholder="mcp-server,--flag"></div>
  <div class="fg"><label>URL (SSE)</label><input id="mf-url" placeholder="https://..."></div>
  <div class="fa"><button class="b" onclick="closeModal('m-mcp')">Cancel</button><button class="b bp" onclick="addMcp()">Add</button></div>
</div></div>

<div id="tc"></div>

<script>
let S={accs:[],active:{},sel:null,progs:[]};
const PI={'claude-code':'C','codex':'X','opencode':'O','cline':'L','roo-code':'R'};

function go(p){document.querySelectorAll('.pg').forEach(e=>e.classList.remove('on'));document.getElementById('pg-'+p).classList.add('on');document.querySelectorAll('.ni').forEach(n=>n.classList.toggle('on',n.dataset.p===p));if(p==='skills')loadSkills();if(p==='mcp')loadMcp();if(p==='set')loadSet()}
function toast(m,t=''){const e=document.createElement('div');e.className='toast '+(t==='ok'?'ok':t==='er'?'er':'');e.textContent=m;document.getElementById('tc').appendChild(e);setTimeout(()=>e.remove(),4000)}
async function api(p,b=null){const o=b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{};const r=await fetch(p,o);return r.json()}
function openModal(id){document.getElementById(id).classList.add('open')}
function closeModal(id){document.getElementById(id).classList.remove('open')}

// ACCOUNTS
async function loadAccs(){const d=await api('/api/accounts');S.accs=d.accounts;S.active=d.active;S.progs=d.programs;renderAccs()}
function renderAccs(){const c=document.getElementById('acc-cards');if(!S.accs.length){c.innerHTML='<div class="empty"><p>No accounts. Click Import.</p></div>';return}
const sorted=[...S.accs].sort((a,b)=>a.name.localeCompare(b.name));
c.innerHTML=sorted.map(a=>`<div class="ac ${S.sel===a.id?'sel':''}" onclick="selAcc('${a.id}')"><div class="ah"><span class="dot" style="background:${a._color}"></span><span class="an">${a.name}</span><span class="ap">${a._prov}</span></div><div class="am">${a.model||'default'}${a.email?' · '+a.email:''}${a.plan?' · '+a.plan:''}</div></div>`).join('')}

function selAcc(id){S.sel=id;renderAccs();renderProgs()}
function renderProgs(){document.getElementById('no-sel').style.display='none';document.getElementById('pcon').style.display='block';
const acc=S.accs.find(a=>a.id===S.sel);if(!acc)return;
document.getElementById('ptitle').textContent=`Apply "${acc.name}"`;
document.getElementById('pgrid').innerHTML=S.progs.map(p=>{
const aid=S.active[p.id];const isMe=aid===acc.id;const who=isMe?'<span class="at">Active</span>':aid?S.accs.find(a=>a.id===aid)?.name||aid:'—';
return`<div class="pc ${isMe?'chk':''}" onclick="tglChk(this)"><div class="pt2"><div class="pi">${PI[p.id]||'?'}</div><div><div class="pn">${p.name}</div></div><div class="pa">${who}</div></div><div class="pc2"><input type="checkbox" value="${p.id}" ${isMe?'checked':''}><span>Select to apply</span></div></div>`}).join('')}

function tglChk(c){const cb=c.querySelector('input[type=checkbox]');cb.checked=!cb.checked;c.classList.toggle('chk',cb.checked)}
function allChk(v){document.querySelectorAll('#pgrid input[type=checkbox]').forEach(cb=>{cb.checked=v;cb.closest('.pc').classList.toggle('chk',v)})}

async function applySel(){if(!S.sel)return;const pids=[...document.querySelectorAll('#pgrid input:checked')].map(c=>c.value);if(!pids.length){toast('Select programs');return}
const r=await api('/api/apply',{account_id:S.sel,programs:pids});
r.results?.forEach(x=>toast(x.message,x.ok?'ok':'er'));loadAccs()}

async function doImport(){const r=await api('/api/import');toast(`Imported: ${r.imported?.join(', ')||'none'}`,r.imported?.length?'ok':'');loadAccs()}

async function createAcc(){const n=document.getElementById('f-name').value.trim();if(!n){toast('Name required','er');return}
const r=await api('/api/account-create',{name:n,provider:document.getElementById('f-prov').value,api_key:document.getElementById('f-key').value,base_url:document.getElementById('f-url').value,model:document.getElementById('f-model').value});
if(r.ok){toast('Created: '+n,'ok');closeModal('m-create');['f-name','f-key','f-url','f-model'].forEach(i=>document.getElementById(i).value='');loadAccs()}else toast(r.error,'er')}

// SKILLS
async function loadSkills(){const d=await api('/api/skills');
const head=document.getElementById('sk-head');const body=document.getElementById('sk-body');
const pids=S.progs.map(p=>p.id);const pnames={};S.progs.forEach(p=>pnames[p.id]=p.name);
head.innerHTML=`<tr><th>Skill</th>${pids.map(id=>`<th style="text-align:center">${pnames[id]}</th>`).join('')}<th></th></tr>`;
const rows=d.master.map(sk=>{const checks=pids.map(pid=>{const has=sk.name in Object.fromEntries((d.programs[pid]||[]).map(n=>[n,true]));return`<td style="text-align:center"><input type="checkbox" data-sk="${sk.name}" data-prog="${pid}" ${has?'checked':''}></td>`}).join('');
return`<tr><td class="sn">${sk.name}${sk.in_master?'<span class="master-tag">master</span>':''}<div class="sd">${sk.has_md?'SKILL.md':'—'}</div></td>${checks}<td><button class="b bs" onclick="syncSkill('${sk.name}')">Sync</button></td></tr>`}).join('');
if(!rows)body.innerHTML='<tr><td colspan="99" style="color:var(--tx3);padding:20px">No skills in master. Add skill folders to ~/.multimanager/master/skills/</td></tr>';else body.innerHTML=rows}

async function syncSkill(name){const pids=[...document.querySelectorAll(`input[data-sk="${name}"]:checked`)].map(c=>c.dataset.prog);if(!pids.length){toast('Select programs','er');return}
const r=await api('/api/skill-sync',{skill:name,programs:pids});toast(r.message,r.ok?'ok':'er')}
async function syncAllSkills(){const r=await api('/api/skill-sync-all');toast('All synced','ok')}

// MCP
async function loadMcp(){const d=await api('/api/mcp');
const head=document.getElementById('mcp-head');const body=document.getElementById('mcp-body');
const pids=Object.keys(d.program_names);const pnames=d.program_names;
head.innerHTML=`<tr><th>Server</th>${pids.map(id=>`<th style="text-align:center">${pnames[id]}</th>`).join('')}<th></th></tr>`;
body.innerHTML=d.servers.map(s=>{const checks=pids.map(pid=>`<td style="text-align:center"><input type="checkbox" data-srv="${s.name}" data-prog="${pid}" ${s.programs[pid]?'checked':''}></td>`).join('');
const info=s.config?.url||[s.config?.command||'',...(s.config?.args||[])].join(' ');
return`<tr><td class="sn">${s.name}${s.in_master?'<span class="master-tag">master</span>':''}<div class="sd">${info}</div></td>${checks}<td><button class="b bs" onclick="syncMcp('${s.name}')">Sync</button></td></tr>`}).join('')}

async function syncMcp(name){const pids=[...document.querySelectorAll(`input[data-srv="${name}"]:checked`)].map(c=>c.dataset.prog);
const r=await api('/api/mcp-sync',{name:name,programs:pids});toast(r.message||'Synced',r.ok?'ok':'er')}
async function syncAllMcp(){const r=await api('/api/mcp-sync-all');toast('All synced','ok')}
async function addMcp(){const name=document.getElementById('mf-name').value.trim();if(!name){toast('Name required','er');return}
const args=document.getElementById('mf-args').value.split(',').map(s=>s.trim()).filter(Boolean);
const pids=[...document.querySelectorAll(`input[data-srv="${name}"]:checked`)].map(c=>c.dataset.prog);
await api('/api/mcp-add',{name,command:document.getElementById('mf-cmd').value,args,url:document.getElementById('mf-url').value,programs:pids});
closeModal('m-mcp');toast('Added','ok');loadMcp()}

// SETTINGS
async function loadSet(){const c=document.getElementById('set-con');const cfg=await api('/api/get-settings');
c.innerHTML=`<div style="margin-bottom:16px"><div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--brd)"><div><div style="font-size:13px">Auto Backup</div><div style="font-size:11px;color:var(--tx3)">Before applying changes</div></div><input type="checkbox" ${cfg.auto_backup!==false?'checked':''} onchange="api('/api/set-auto-backup',{enabled:this.checked})"></div></div>
<div style="display:flex;gap:8px;margin-bottom:16px"><button class="b" onclick="api('/api/backup-now').then(()=>toast('Done','ok'))">Backup Now</button><button class="b bd" onclick="api('/api/shutdown').then(()=>toast('Shutting down'))">Shutdown</button></div>
<details><summary style="cursor:pointer;color:var(--tx2);font-size:12px;margin-bottom:8px">Raw config</summary><pre style="background:var(--card);padding:12px;border-radius:var(--r);font-size:11px;overflow:auto;max-height:300px;color:var(--tx2)">${JSON.stringify(cfg,null,2)}</pre></details>`}

loadAccs();
</script></body></html>"""


# ============================================================
# MENU BAR
# ============================================================
def setup_menubar(port):
    try:
        import pystray
        from PIL import Image, ImageDraw
        def make_icon():
            img = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([2, 2, 20, 20], radius=4, fill=(59, 130, 246, 255))
            for x, y in [(6, 6), (12, 6), (6, 12), (12, 12)]:
                d.rounded_rectangle([x, y, x + 4, y + 4], radius=1, fill=(255, 255, 255, 255))
            return img
        def on_open(icon, item): webbrowser.open(f"http://127.0.0.1:{port}")
        def on_quit(icon, item): icon.stop(); os._exit(0)
        pystray.Icon("MultiManager", icon=make_icon(),
            menu=pystray.Menu(pystray.MenuItem("Open", on_open), pystray.Menu.SEPARATOR, pystray.MenuItem("Quit", on_quit))
        ).run_detached()
    except Exception as e:
        print(f"[menubar] {e}")

# ============================================================
# SERVER
# ============================================================
def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def main():
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[mm] http://127.0.0.1:{port}")
    MASTER_SKILLS.mkdir(parents=True, exist_ok=True)
    setup_menubar(port)
    threading.Timer(0.35, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()

if __name__ == "__main__":
    main()
