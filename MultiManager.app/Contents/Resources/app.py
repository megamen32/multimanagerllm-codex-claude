#!/usr/bin/env python3
"""MultiManager v2 — Unified AI account manager with macOS menu bar."""
import json, os, shutil, socket, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from http.client import HTTPConnection, HTTPSConnection

APP_NAME = "MultiManager"
HOME = Path.home()
CONFIG_DIR = HOME / ".multimanager"
CONFIG_FILE = CONFIG_DIR / "config.json"
BACKUP_DIR = CONFIG_DIR / "backups"

CLAUDE_DESKTOP_DIR = HOME / "Library" / "Application Support"
CLAUDE_CODE_SETTINGS = HOME / ".claude" / "settings.json"
CODEX_CONFIG = HOME / ".codex" / "config.toml"
CODEX_AUTH = HOME / ".codex" / "auth.json"
ANTHROPIC_CONFIG_DIR = HOME / ".config" / "anthropic"
ANTHROPIC_CONFIGS_DIR = ANTHROPIC_CONFIG_DIR / "configs"
ANTHROPIC_CREDENTIALS_DIR = ANTHROPIC_CONFIG_DIR / "credentials"
ANTHROPIC_ACTIVE_CONFIG = ANTHROPIC_CONFIG_DIR / "active_config"

OPENCODE_CONFIG = HOME / ".config" / "opencode" / "opencode.json"
CLINE_MCP_CONFIG = HOME / ".cline" / "mcp_settings.json"
ROO_MCP_CONFIG = HOME / ".roo" / "mcp_settings.json"

SKILL_ROOTS_DEFAULT = [
    HOME / ".claude" / "skills",
    HOME / ".codex" / "skills",
    HOME / ".agents" / "skills",
    HOME / ".opencode" / "skills",
]

CD_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CD_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"

DEFAULT_CONFIG = {
    "accounts": [],
    "auto_backup": True,
    "custom_skill_roots": [],
}

PROGRAMS = [
    {"id": "claude-code", "name": "Claude Code", "icon": "claude", "config_path": str(CLAUDE_CODE_SETTINGS), "config_type": "json"},
    {"id": "codex", "name": "Codex", "icon": "codex", "config_path": str(CODEX_CONFIG), "config_type": "toml"},
    {"id": "claude-desktop", "name": "Claude Desktop", "icon": "claude-desktop", "config_path": None, "config_type": "json"},
    {"id": "opencode", "name": "OpenCode", "icon": "opencode", "config_path": str(OPENCODE_CONFIG), "config_type": "json"},
    {"id": "cline", "name": "Cline", "icon": "cline", "config_path": str(CLINE_MCP_CONFIG), "config_type": "json"},
    {"id": "roo-code", "name": "Roo Code", "icon": "roo", "config_path": str(ROO_MCP_CONFIG), "config_type": "json"},
]


def expand_path(p):
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            return {}
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
    if changed:
        save_config(cfg)
    return cfg


def file_hash(path):
    import hashlib
    try:
        return hashlib.sha256(open(path, "rb").read(65536)).hexdigest()
    except Exception:
        return ""


def read_file_text(path):
    try:
        return Path(path).read_text()
    except Exception:
        return ""


def write_file_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)


def format_size(n):
    if n < 1024:
        return f"{n} B"
    elif n < 1048576:
        return f"{n / 1024:.1f} KB"
    else:
        return f"{n / 1048576:.1f} MB"


def do_auto_backup(cfg):
    if not cfg.get("auto_backup", True):
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = {"created_at": stamp, "files": {}}
    paths = {
        "claude_code": [CLAUDE_CODE_SETTINGS] if CLAUDE_CODE_SETTINGS.exists() else [],
        "codex_config": [CODEX_CONFIG] if CODEX_CONFIG.exists() else [],
        "codex_auth": [CODEX_AUTH] if CODEX_AUTH.exists() else [],
    }
    for cat, files in paths.items():
        for f in files:
            try:
                backup["files"][f"{cat}:{f.name}"] = {"path": str(f), "content": f.read_text()}
            except Exception:
                pass
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / f"auto-{stamp}.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2))


def _decode_jwt_payload(token):
    import base64
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    pad = 4 - len(payload) % 4
    if pad != 4:
        payload += "=" * pad
    return json.loads(base64.urlsafe_b64decode(payload))


def _detect_provider_by_url(url):
    u = url.lower()
    if "anthropic" in u or "z.ai" in u or "bigmodel" in u:
        return "anthropic"
    if "openai" in u:
        return "openai"
    if "gemini" in u or "generativelanguage" in u:
        return "gemini"
    if "mistral" in u:
        return "mistral"
    if "ollama" in u or "localhost:11434" in u:
        return "ollama"
    if "deepseek" in u:
        return "deepseek"
    if "openrouter" in u:
        return "openrouter"
    if "xai" in u or "grok" in u:
        return "xai"
    if "groq" in u:
        return "groq"
    return "openai-compat"


def _provider_color(provider):
    colors = {
        "anthropic": "#d97757", "openai": "#10a37f", "gemini": "#4285f4",
        "mistral": "#ff7000", "ollama": "#000000", "deepseek": "#4d6bfe",
        "openrouter": "#6c63ff", "xai": "#1d1d1f", "groq": "#f55036",
        "openai-compat": "#6b7280",
    }
    return colors.get(provider, "#6b7280")


# ============================================================
# ACCOUNT MANAGEMENT
# ============================================================

def _get_account_provider_display(account):
    provider = account.get("provider", "openai")
    base_url = account.get("base_url", "")
    if base_url:
        detected = _detect_provider_by_url(base_url)
        if detected != "openai-compat":
            return detected, _provider_color(detected)
    return provider, _provider_color(provider)


def _detect_account_limits(account):
    limits = {"has_limits": False, "usage": 0, "limit": 0, "resets_at": "", "plan": ""}
    provider = account.get("provider", "")
    base_url = account.get("base_url", "")
    if "openai" == provider and "openrouter" not in (base_url or "").lower():
        limits["has_limits"] = True
    elif "anthropic" == provider:
        limits["has_limits"] = True
    return limits


def _get_active_accounts_for_programs(cfg):
    result = {}
    for prog in PROGRAMS:
        pid = prog["id"]
        active = _detect_active_account(cfg, pid)
        result[pid] = active
    return result


def _detect_active_account(cfg, program_id):
    accounts = cfg.get("accounts", [])
    if not accounts:
        return None

    if program_id == "claude-code":
        if not CLAUDE_CODE_SETTINGS.exists():
            return None
        try:
            settings = json.loads(CLAUDE_CODE_SETTINGS.read_text())
            env = settings.get("env", {})
            base_url = env.get("ANTHROPIC_BASE_URL", env.get("ANTHROPIC_AUTH_TOKEN", ""))
            api_key = env.get("ANTHROPIC_API_KEY", env.get("ANTHROPIC_AUTH_TOKEN", ""))
            model = settings.get("model", "")
            for acc in accounts:
                acc_url = acc.get("base_url", "")
                acc_key = acc.get("api_key", "")
                if acc_url and base_url and acc_url in base_url:
                    return acc["id"]
                if acc_key and api_key and acc_key[:20] == api_key[:20]:
                    return acc["id"]
                if acc.get("model") and model and acc["model"] == model:
                    return acc["id"]
        except Exception:
            pass

    elif program_id == "codex":
        if not CODEX_CONFIG.exists():
            return None
        try:
            config_text = CODEX_CONFIG.read_text()
            model = ""
            provider_id = ""
            for line in config_text.splitlines():
                stripped = line.strip()
                if stripped.startswith("model ") and "=" in stripped:
                    model = stripped.split("=", 1)[1].strip().strip('" ')
                if stripped.startswith("model_provider ") and "=" in stripped:
                    provider_id = stripped.split("=", 1)[1].strip().strip('" ')
            mp_section = None
            in_mp = False
            for line in config_text.splitlines():
                if line.strip().startswith("[model_providers.") and "]" in line:
                    mp_section = line.strip().split(".")[1].split("]")[0]
                    in_mp = True
                    continue
                if line.strip().startswith("["):
                    in_mp = False
                if in_mp and mp_section == provider_id:
                    if "base_url" in stripped:
                        base_url = stripped.split("=", 1)[1].strip().strip('" ')
                        for acc in accounts:
                            if acc.get("base_url") == base_url:
                                return acc["id"]
            for acc in accounts:
                if acc.get("model") == model and not provider_id:
                    return acc["id"]
                if acc.get("codex_profile") == provider_id:
                    return acc["id"]
        except Exception:
            pass

    elif program_id == "claude-desktop":
        instances = _find_claude_instances()
        if instances:
            for acc in accounts:
                if acc.get("claude_desktop_instance"):
                    return acc["id"]

    elif program_id == "opencode":
        if OPENCODE_CONFIG.exists():
            try:
                oc = json.loads(OPENCODE_CONFIG.read_text())
                prov = oc.get("provider", {})
                for prov_name, prov_data in prov.items():
                    if isinstance(prov_data, dict):
                        opts = prov_data.get("options", {})
                        key = opts.get("apiKey", "")
                        base_url = opts.get("baseUrl", "")
                        for acc in accounts:
                            if key and acc.get("api_key") and acc["api_key"][:20] == key[:20]:
                                return acc["id"]
                            if base_url and acc.get("base_url") and acc["base_url"] in base_url:
                                return acc["id"]
            except Exception:
                pass

    return accounts[0]["id"] if accounts else None


def _find_claude_instances():
    if not CLAUDE_DESKTOP_DIR.exists():
        return []
    instances = []
    for p in sorted(CLAUDE_DESKTOP_DIR.glob("Claude*")):
        if not p.is_dir():
            continue
        config_file = p / "claude_desktop_config.json"
        instances.append({"name": p.name, "path": str(p), "config_path": str(config_file) if config_file.exists() else None})
    return instances


def _apply_account_to_program(cfg, account_id, program_id):
    accounts = cfg.get("accounts", [])
    account = next((a for a in accounts if a["id"] == account_id), None)
    if not account:
        return False, f"Account {account_id} not found"

    do_auto_backup(cfg)
    provider = account.get("provider", "openai")
    base_url = account.get("base_url", "")
    api_key = account.get("api_key", "")
    model = account.get("model", "")

    if program_id == "claude-code":
        settings = {}
        if CLAUDE_CODE_SETTINGS.exists():
            try:
                settings = json.loads(CLAUDE_CODE_SETTINGS.read_text())
            except Exception:
                pass
        env = settings.setdefault("env", {})
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        elif api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if model:
            settings["model"] = model
        if account.get("claude_model_overrides"):
            mo = account["claude_model_overrides"]
            if mo.get("sonnet"):
                env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = mo["sonnet"]
            if mo.get("opus"):
                env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = mo["opus"]
            if mo.get("haiku"):
                env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = mo["haiku"]
        write_file_text(str(CLAUDE_CODE_SETTINGS), json.dumps(settings, ensure_ascii=False, indent=2))
        return True, f"Applied to Claude Code"

    elif program_id == "codex":
        if not CODEX_CONFIG.exists():
            return False, "codex config.toml not found"
        config_text = CODEX_CONFIG.read_text()
        lines = config_text.split("\n")
        new_lines = []
        has_mp_section = False
        mp_name = None
        in_model_providers = False
        current_mp = None

        if account.get("codex_profile"):
            mp_name = account["codex_profile"]

        if account.get("model"):
            found_model = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("model ") and "=" in stripped and not found_model:
                    new_lines.append(f'model = "{account["model"]}"')
                    found_model = True
                    continue
                new_lines.append(line)
            if not found_model:
                new_lines.append(f'model = "{account["model"]}"')

        if base_url and account.get("codex_provider"):
            mp_name = account["codex_provider"]
            lines = new_lines
            new_lines = []
            found_provider = False
            has_mp = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("[model_providers."):
                    has_mp = True
                if stripped == f'[model_providers.{mp_name}]':
                    found_provider = True
                new_lines.append(line)
            if not found_provider:
                if has_mp:
                    new_lines.append("")
                new_lines.append(f'\n[model_providers.{mp_name}]')
                new_lines.append(f'name = "{account.get("provider_name", mp_name)}"')
                new_lines.append(f'base_url = "{base_url}"')
                env_key = account.get("codex_env_key", f'{mp_name.upper()}_API_KEY')
                new_lines.append(f'env_key = "{env_key}"')
            new_lines = new_lines
            lines = new_lines
            new_lines = []
            found_mp_line = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("model_provider ") and "=" in stripped and not found_mp_line:
                    new_lines.append(f'model_provider = "{mp_name}"')
                    found_mp_line = True
                    continue
                new_lines.append(line)
            if not found_mp_line:
                new_lines.append(f'model_provider = "{mp_name}"')

        write_file_text(str(CODEX_CONFIG), "\n".join(new_lines))
        return True, f"Applied to Codex"

    elif program_id == "opencode":
        if not OPENCODE_CONFIG.exists():
            return False, "OpenCode config not found"
        try:
            oc = json.loads(OPENCODE_CONFIG.read_text())
        except Exception:
            oc = {}
        prov = oc.setdefault("provider", {})
        if base_url and "z.ai" in base_url.lower():
            zai = prov.setdefault("zai-coding-plan", {})
            opts = zai.setdefault("options", {})
            if api_key:
                opts["apiKey"] = api_key
            if base_url:
                opts["baseUrl"] = base_url
        return True, "Applied to OpenCode"

    return False, f"Program {program_id} not yet supported"


# ============================================================
# MCP HELPERS
# ============================================================

def _read_cdx_mcp_servers(config_path):
    servers = []
    p = Path(config_path)
    if not p.exists():
        return []
    try:
        import tomllib
        data = tomllib.loads(p.read_text())
        return [(name, srv) for name, srv in data.get("mcp_servers", {}).items()]
    except Exception:
        pass
    return []


def _write_cdx_mcp_servers(config_path, servers):
    import tomllib
    p = Path(config_path)
    data = {}
    if p.exists():
        try:
            data = tomllib.loads(p.read_text())
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    data["mcp_servers"] = {name: srv for name, srv in servers}
    write_file_text(str(p), "" if not data else "")
    if not data:
        return
    lines = []
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"[{k}]")
            for sk, sv in v.items():
                if isinstance(sv, list):
                    lines.append(f'{sk} = {json.dumps(sv)}')
                elif isinstance(sv, bool):
                    lines.append(f'{sk} = {"true" if sv else "false"}')
                elif isinstance(sv, (int, float)):
                    lines.append(f'{sk} = {sv}')
                elif isinstance(sv, str):
                    lines.append(f'{sk} = "{sv}"')
                elif isinstance(sv, dict):
                    lines.append(f'\n[{k}.{sk}]')
                    for ssk, ssv in sv.items():
                        if isinstance(ssv, list):
                            lines.append(f'{ssk} = {json.dumps(ssv)}')
                        elif isinstance(ssv, bool):
                            lines.append(f'{ssk} = {"true" if ssv else "false"}')
                        elif isinstance(ssv, str):
                            lines.append(f'{ssk} = "{ssv}"')
                        else:
                            lines.append(f'{ssk} = {ssv}')
            lines.append("")
    write_file_text(str(p), "\n".join(lines))


def _read_cline_mcp(path):
    if not Path(path).exists():
        return []
    try:
        d = json.loads(Path(path).read_text())
        return list(d.get("mcpServers", {}).items())
    except Exception:
        return []


# ============================================================
# SKILLS HELPERS
# ============================================================

def skills_in(root):
    root = expand_path(root)
    if not root.exists():
        return []
    result = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        md = d / "SKILL.md"
        result.append({"name": d.name, "path": str(d), "has_skill_md": md.exists()})
    return result


def scan_skills_roots(cfg):
    roots = list(SKILL_ROOTS_DEFAULT) + [expand_path(p) for p in cfg.get("custom_skill_roots", [])]
    return [{"path": str(r), "exists": r.exists(), "label": r.name, "skills": skills_in(r)} for r in roots]


def get_skill_diffs(master_root, target_roots):
    import difflib
    master = expand_path(master_root)
    if not master.exists():
        return []
    master_skills = {s["name"]: expand_path(s["path"]) for s in skills_in(master)}
    result = []
    for target_str in target_roots:
        target = expand_path(target_str)
        target_skills = {s["name"]: expand_path(s["path"]) for s in skills_in(target)}
        for name, tpath in target_skills.items():
            mpath = master_skills.get(name)
            if not mpath:
                continue
            t_md = tpath / "SKILL.md"
            m_md = mpath / "SKILL.md"
            if not t_md.exists() or not m_md.exists():
                continue
            try:
                diff_lines = list(difflib.unified_diff(
                    m_md.read_text().splitlines(), t_md.read_text().splitlines(),
                    fromfile=f"master/{name}/SKILL.md", tofile=f"target/{name}/SKILL.md",
                    lineterm="", n=3))
                result.append({"name": name, "has_diff": len(diff_lines) > 0, "diff_preview": "\n".join(diff_lines[:20])})
            except Exception:
                continue
    return result


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
        if n == 0:
            return {}
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._html()
            return
        cfg = ensure_defaults()

        if u.path == "/api/accounts":
            accounts = cfg.get("accounts", [])
            active_map = _get_active_accounts_for_programs(cfg)
            enriched = []
            for acc in accounts:
                prov_id, prov_color = _get_account_provider_display(acc)
                limits = _detect_account_limits(acc)
                enriched.append({**acc, "_provider_color": prov_color, "_provider_display": prov_id, "_limits": limits})
            self._json({"accounts": enriched, "active_map": active_map, "programs": PROGRAMS})
            return

        if u.path == "/api/programs":
            active_map = _get_active_accounts_for_programs(cfg)
            accounts = cfg.get("accounts", [])
            result = []
            for prog in PROGRAMS:
                active_id = active_map.get(prog["id"])
                active_name = ""
                if active_id:
                    acc = next((a for a in accounts if a["id"] == active_id), None)
                    if acc:
                        active_name = acc.get("name", active_id)
                result.append({**prog, "active_account_id": active_id, "active_account_name": active_name})
            self._json({"programs": result})
            return

        if u.path == "/api/mcp-list":
            servers = []
            for prog in PROGRAMS:
                pid = prog["id"]
                if pid in ("claude-code", "codex"):
                    cp = prog["config_path"]
                    if cp:
                        for name, srv in _read_cdx_mcp_servers(cp):
                            servers.append({"name": name, "tool": pid, "enabled": not srv.get("disabled", False), "command": srv.get("command", ""), "args": srv.get("args", []), "url": srv.get("url", "")})
                elif pid == "cline":
                    for name, srv in _read_cline_mcp(prog["config_path"]):
                        servers.append({"name": name, "tool": pid, "enabled": True, "command": srv.get("command", ""), "args": srv.get("args", []), "url": srv.get("url", "")})
            self._json({"servers": servers})
            return

        if u.path == "/api/skills":
            self._json({"roots": scan_skills_roots(cfg)})
            return

        if u.path == "/api/skills-diff":
            qs = parse_qs(u.query)
            master = qs.get("master", [""])[0]
            targets = qs.get("targets", [])
            if master and targets:
                self._json({"diffs": get_skill_diffs(master, targets)})
            else:
                self._json({"diffs": []})
            return

        if u.path == "/api/get-settings":
            self._json(cfg)
            return

        if u.path == "/api/backups":
            backups = []
            if BACKUP_DIR.exists():
                for f in sorted(BACKUP_DIR.iterdir(), reverse=True)[:20]:
                    if f.suffix == ".json":
                        backups.append({"name": f.stem, "size": format_size(f.stat().st_size), "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
            self._json({"backups": backups})
            return

        if u.path == "/api/shutdown":
            self._json({"message": "shutting down"})
            threading.Timer(0.1, lambda: os._exit(0)).start()
            return

        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        body = self._read_body()
        cfg = ensure_defaults()

        # ---- Accounts ----
        if u.path == "/api/accounts-save":
            accounts = body.get("accounts", [])
            cfg["accounts"] = accounts
            save_config(cfg)
            self._json({"message": f"Saved {len(accounts)} accounts"})
            return

        if u.path == "/api/account-create":
            name = body.get("name", "").strip()
            if not name:
                return self._error("name required")
            import uuid
            acc = {
                "id": str(uuid.uuid4())[:8],
                "name": name,
                "provider": body.get("provider", "anthropic"),
                "api_key": body.get("api_key", ""),
                "base_url": body.get("base_url", ""),
                "model": body.get("model", ""),
                "email": body.get("email", ""),
            }
            for key in ("claude_model_overrides", "codex_profile", "codex_provider", "codex_env_key", "provider_name"):
                if body.get(key):
                    acc[key] = body[key]
            accounts = cfg.setdefault("accounts", [])
            accounts.append(acc)
            save_config(cfg)
            self._json({"message": f"Created account: {name}", "account": acc})
            return

        if u.path == "/api/account-delete":
            acc_id = body.get("id", "")
            accounts = cfg.get("accounts", [])
            cfg["accounts"] = [a for a in accounts if a["id"] != acc_id]
            save_config(cfg)
            self._json({"message": "Account deleted"})
            return

        # ---- Apply account to programs ----
        if u.path == "/api/apply-account":
            acc_id = body.get("account_id", "")
            prog_ids = body.get("programs", [])
            if not acc_id:
                return self._error("account_id required")
            results = []
            for pid in prog_ids:
                ok, msg = _apply_account_to_program(cfg, acc_id, pid)
                results.append({"program": pid, "ok": ok, "message": msg})
            self._json({"results": results})
            return

        # ---- Import from current configs ----
        if u.path == "/api/import-current":
            imported = []
            accounts = cfg.setdefault("accounts", [])

            if CLAUDE_CODE_SETTINGS.exists():
                try:
                    s = json.loads(CLAUDE_CODE_SETTINGS.read_text())
                    env = s.get("env", {})
                    base_url = env.get("ANTHROPIC_BASE_URL", "")
                    auth_token = env.get("ANTHROPIC_AUTH_TOKEN", "")
                    api_key = env.get("ANTHROPIC_API_KEY", "")
                    model = s.get("model", "")
                    if base_url or api_key:
                        name = "Claude Code Current"
                        provider = "anthropic"
                        if "z.ai" in base_url:
                            name = "Z.AI (GLM)"
                        elif "anthropic" not in base_url and base_url:
                            name = f"Claude ({_detect_provider_by_url(base_url)})"
                        existing = next((a for a in accounts if a.get("name") == name), None)
                        if not existing:
                            acc = {"id": base_url[-8:] if base_url else str(hash(api_key))[:8], "name": name, "provider": provider, "api_key": auth_token or api_key, "base_url": base_url, "model": model}
                            if env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"):
                                acc["claude_model_overrides"] = {"sonnet": env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "opus": env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", ""), "haiku": env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")}
                            accounts.append(acc)
                            imported.append(name)
                except Exception:
                    pass

            if CODEX_CONFIG.exists():
                try:
                    ct = CODEX_CONFIG.read_text()
                    model = ""
                    mp_id = ""
                    for line in ct.splitlines():
                        s = line.strip()
                        if s.startswith("model ") and "=" in s and not s.startswith("model_"):
                            model = s.split("=", 1)[1].strip().strip('" ')
                        if s.startswith("model_provider ") and "=" in s:
                            mp_id = s.split("=", 1)[1].strip().strip('" ')
                    name = f"Codex ({mp_id or 'openai'})"
                    existing = next((a for a in accounts if a.get("name") == name), None)
                    if not existing:
                        import uuid
                        acc = {"id": str(uuid.uuid4())[:8], "name": name, "provider": "openai", "api_key": "", "base_url": "", "model": model, "codex_profile": mp_id}
                        if mp_id:
                            acc["codex_provider"] = mp_id
                        accounts.append(acc)
                        imported.append(name)
                except Exception:
                    pass

            save_config(cfg)
            self._json({"imported": imported, "total": len(cfg.get("accounts", []))})
            return

        # ---- MCP ----
        if u.path == "/api/mcp-add":
            name = body.get("name", "")
            tool = body.get("tool", "")
            command = body.get("command", "")
            args = body.get("args", [])
            url = body.get("url", "")
            if not name or not tool:
                return self._error("name and tool required")
            prog = next((p for p in PROGRAMS if p["id"] == tool), None)
            if not prog:
                return self._error(f"Unknown tool: {tool}")
            cp = prog["config_path"]
            if not cp:
                return self._error(f"No config path for {tool}")
            try:
                if tool in ("claude-code", "codex"):
                    servers = _read_cdx_mcp_servers(cp)
                    srv = {}
                    if url:
                        srv["url"] = url
                    else:
                        srv["command"] = command
                        srv["args"] = args
                    servers.append((name, srv))
                    _write_cdx_mcp_servers(cp, servers)
                elif tool == "cline":
                    if not Path(cp).exists():
                        Path(cp).parent.mkdir(parents=True, exist_ok=True)
                        Path(cp).write_text("{}")
                    d = json.loads(Path(cp).read_text())
                    mcp = d.setdefault("mcpServers", {})
                    if url:
                        mcp[name] = {"url": url}
                    else:
                        mcp[name] = {"command": command, "args": args}
                    Path(cp).write_text(json.dumps(d, ensure_ascii=False, indent=2))
                self._json({"ok": True, "message": f"Added {name} to {tool}"})
            except Exception as e:
                self._json({"ok": False, "message": str(e)})
            return

        if u.path == "/api/mcp-delete":
            name = body.get("name", "")
            tool = body.get("tool", "")
            prog = next((p for p in PROGRAMS if p["id"] == tool), None)
            if prog and prog["config_path"]:
                try:
                    if tool in ("claude-code", "codex"):
                        servers = [(n, s) for n, s in _read_cdx_mcp_servers(prog["config_path"]) if n != name]
                        _write_cdx_mcp_servers(prog["config_path"], servers)
                    elif tool == "cline":
                        d = json.loads(Path(prog["config_path"]).read_text())
                        d.get("mcpServers", {}).pop(name, None)
                        Path(prog["config_path"]).write_text(json.dumps(d, ensure_ascii=False, indent=2))
                    self._json({"ok": True})
                except Exception as e:
                    self._json({"ok": False, "message": str(e)})
            return

        # ---- Skills ----
        if u.path == "/api/skills-sync":
            source = body.get("source", "")
            targets = body.get("targets", [])
            ok_msgs = []
            for target in targets:
                src = expand_path(source)
                dst = expand_path(target)
                if src.exists() and src.is_dir():
                    try:
                        if dst.exists():
                            shutil.rmtree(str(dst))
                        shutil.copytree(str(src), str(dst))
                        ok_msgs.append(f"{src.name} -> {dst.parent.name}")
                    except Exception as e:
                        ok_msgs.append(f"Error: {e}")
            self._json({"ok": True, "log": ok_msgs})
            return

        if u.path == "/api/skills-add-root":
            p = str(expand_path(body.get("path", "")))
            if not p:
                return self._error("path required")
            custom = cfg.setdefault("custom_skill_roots", [])
            if p not in custom:
                custom.append(p)
                save_config(cfg)
            self._json({"roots": scan_skills_roots(cfg)})
            return

        # ---- Settings ----
        if u.path == "/api/backup-now":
            do_auto_backup(cfg)
            self._json({"message": "Backup created"})
            return

        if u.path == "/api/set-auto-backup":
            cfg["auto_backup"] = body.get("enabled", True)
            save_config(cfg)
            self._json({"message": "OK"})
            return

        self.send_error(404)

    def log_message(self, *args):
        pass


# ============================================================
# HTML FRONTEND
# ============================================================

html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MultiManager</title>
<style>
:root {
  --bg: #0a0a0a; --bg-sidebar: #111111; --bg-card: #1a1a1a; --bg-hover: #222222;
  --bg-selected: #2a2a2a; --text: #e5e5e5; --text-dim: #888888; --text-muted: #555555;
  --accent: #3b82f6; --accent-hover: #2563eb; --border: #2a2a2a; --border-light: #333333;
  --success: #22c55e; --warning: #f59e0b; --danger: #ef4444;
  --radius: 8px; --radius-lg: 12px; --sidebar-w: 220px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif; background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; font-size: 13px; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-light); border-radius: 3px; }

/* SIDEBAR */
#sidebar { width: var(--sidebar-w); min-width: var(--sidebar-w); background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 12px 0; }
#sidebar .logo { padding: 8px 16px 20px; font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px; color: var(--accent); }
#sidebar .logo svg { width: 18px; height: 18px; }
.nav-items { flex: 1; display: flex; flex-direction: column; gap: 2px; padding: 0 8px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: var(--radius); cursor: pointer; color: var(--text-dim); transition: all 0.15s; font-size: 13px; user-select: none; }
.nav-item:hover { background: var(--bg-hover); color: var(--text); }
.nav-item.active { background: var(--bg-selected); color: var(--text); }
.nav-item.active svg { color: var(--accent); }
.nav-item svg { width: 18px; height: 18px; flex-shrink: 0; opacity: 0.7; }
.nav-item.active svg { opacity: 1; }
.nav-sep { height: 1px; background: var(--border); margin: 8px 12px; }

/* MAIN CONTENT */
#main { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.page { display: none; flex: 1; overflow: auto; padding: 20px 24px; }
.page.active { display: flex; flex-direction: column; }
.page-title { font-size: 20px; font-weight: 600; margin-bottom: 16px; }

/* PAGE 1: Accounts */
#page-accounts { flex-direction: row; padding: 0; }
#account-list { width: 300px; min-width: 300px; border-right: 1px solid var(--border); overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
#account-list .list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
#account-list .list-header h3 { font-size: 14px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.btn { padding: 6px 12px; border-radius: var(--radius); border: 1px solid var(--border-light); background: var(--bg-card); color: var(--text); cursor: pointer; font-size: 12px; transition: all 0.15s; display: inline-flex; align-items: center; gap: 4px; }
.btn:hover { background: var(--bg-hover); border-color: var(--text-muted); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: white; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-danger { color: var(--danger); border-color: var(--danger); }
.btn-danger:hover { background: rgba(239,68,68,0.1); }
.btn-sm { padding: 4px 8px; font-size: 11px; }
.btn-icon { padding: 6px; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; }

.account-card { padding: 12px; border-radius: var(--radius-lg); border: 1px solid var(--border); cursor: pointer; transition: all 0.15s; }
.account-card:hover { border-color: var(--border-light); background: var(--bg-hover); }
.account-card.selected { border-color: var(--accent); background: rgba(59,130,246,0.08); }
.account-card .acc-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.account-card .acc-color { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.account-card .acc-name { font-weight: 500; font-size: 13px; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.account-card .acc-provider { font-size: 11px; color: var(--text-dim); margin-left: auto; flex-shrink: 0; }
.account-card .acc-model { font-size: 11px; color: var(--text-muted); }
.account-card .acc-usage { margin-top: 6px; }
.usage-bar { height: 3px; background: var(--border); border-radius: 2px; overflow: hidden; }
.usage-bar-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }

#program-panel { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; }
#program-panel .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
#program-panel .panel-header h2 { font-size: 18px; font-weight: 600; }
.prog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 16px; }
.prog-card { padding: 14px; border-radius: var(--radius-lg); border: 1px solid var(--border); background: var(--bg-card); display: flex; flex-direction: column; gap: 8px; transition: all 0.15s; cursor: pointer; }
.prog-card:hover { border-color: var(--border-light); }
.prog-card.checked { border-color: var(--accent); background: rgba(59,130,246,0.06); }
.prog-card .prog-top { display: flex; align-items: center; gap: 10px; }
.prog-card .prog-icon { width: 32px; height: 32px; border-radius: var(--radius); background: var(--bg-hover); display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
.prog-card .prog-name { font-weight: 500; font-size: 14px; }
.prog-card .prog-active { font-size: 11px; color: var(--text-dim); margin-left: auto; }
.prog-card .prog-active .active-tag { color: var(--success); font-weight: 500; }
.prog-card .prog-check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-dim); }
.prog-card .prog-check input { accent-color: var(--accent); }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; color: var(--text-muted); gap: 8px; }
.empty-state svg { width: 48px; height: 48px; opacity: 0.3; }
.empty-state p { font-size: 14px; }

/* PAGE 2: Programs */
#page-programs { padding: 20px 24px; }
.prog-settings-layout { display: flex; gap: 20px; height: calc(100vh - 40px); }
.prog-sidebar { width: 200px; min-width: 200px; display: flex; flex-direction: column; gap: 4px; }
.prog-sidebar-item { padding: 10px 12px; border-radius: var(--radius); cursor: pointer; color: var(--text-dim); display: flex; align-items: center; gap: 8px; font-size: 13px; transition: all 0.15s; }
.prog-sidebar-item:hover { background: var(--bg-hover); color: var(--text); }
.prog-sidebar-item.active { background: var(--bg-selected); color: var(--text); }
.prog-detail { flex: 1; overflow-y: auto; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px solid var(--border); padding: 20px; }

/* PAGE 3: MCP */
.mcp-table { width: 100%; border-collapse: collapse; }
.mcp-table th { text-align: left; padding: 8px 12px; color: var(--text-dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
.mcp-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.mcp-table tr:hover td { background: var(--bg-hover); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; background: var(--bg-hover); color: var(--text-dim); }
.tag-enabled { background: rgba(34,197,94,0.15); color: var(--success); }

/* PAGE 4: Skills */
.skill-root { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 12px; }
.skill-root-header { padding: 12px 16px; background: var(--bg-card); display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
.skill-root-header:hover { background: var(--bg-hover); }
.skill-root-body { padding: 0 16px 12px; display: none; }
.skill-root.expanded .skill-root-body { display: block; }
.skill-item { padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 12px; display: flex; justify-content: space-between; align-items: center; }
.skill-item:last-child { border-bottom: none; }
.skill-name { color: var(--text); }
.skill-status { font-size: 11px; }
.skill-status.has-md { color: var(--success); }

/* PAGE 5: Settings */
.setting-group { margin-bottom: 24px; }
.setting-group h3 { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-dim); }
.setting-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }
.setting-label { font-size: 13px; }
.setting-desc { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* MODAL */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; align-items: center; justify-content: center; }
.modal-overlay.open { display: flex; }
.modal { background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-lg); padding: 24px; width: 420px; max-width: 90vw; }
.modal h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 4px; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border-light); border-radius: var(--radius); color: var(--text); font-size: 13px; outline: none; }
.form-group input:focus, .form-group select:focus { border-color: var(--accent); }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }

/* Toast */
#toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 200; display: flex; flex-direction: column; gap: 8px; }
.toast { padding: 10px 16px; border-radius: var(--radius); background: var(--bg-card); border: 1px solid var(--border-light); font-size: 13px; animation: slideIn 0.2s ease; }
.toast.success { border-color: var(--success); }
.toast.error { border-color: var(--danger); }
@keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

/* Status dot for menu bar indication */
.status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.status-dot.online { background: var(--success); box-shadow: 0 0 4px var(--success); }
</style>
</head>
<body>

<!-- SIDEBAR -->
<div id="sidebar">
  <div class="logo">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    MultiManager
  </div>
  <div class="nav-items">
    <div class="nav-item active" data-page="accounts" onclick="switchPage('accounts')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      Accounts
    </div>
    <div class="nav-item" data-page="programs" onclick="switchPage('programs')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
      Programs
    </div>
    <div class="nav-item" data-page="mcp" onclick="switchPage('mcp')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4m-9.9-2.1l2.8-2.8m14.2-14.2l2.8-2.8M1 12h4m14 0h4m-2.1 9.9l-2.8-2.8M3.9 3.9L1.1 1.1"/></svg>
      MCP
    </div>
    <div class="nav-item" data-page="skills" onclick="switchPage('skills')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      Skills
    </div>
    <div class="nav-sep"></div>
    <div class="nav-item" data-page="settings" onclick="switchPage('settings')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      Settings
    </div>
  </div>
  <div style="padding: 8px 16px; margin-top: auto; font-size: 11px; color: var(--text-muted);">
    <span class="status-dot online"></span> Running
  </div>
</div>

<!-- MAIN -->
<div id="main">
  <!-- PAGE: Accounts & Programs -->
  <div id="page-accounts" class="page active">
    <div id="account-list">
      <div class="list-header">
        <h3>Accounts</h3>
        <div style="display:flex;gap:4px">
          <button class="btn btn-sm" onclick="importCurrent()">Import</button>
          <button class="btn btn-sm btn-primary" onclick="openCreateModal()">+</button>
        </div>
      </div>
      <div id="account-cards"></div>
    </div>
    <div id="program-panel">
      <div class="empty-state" id="no-selection">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <p>Select an account to configure programs</p>
      </div>
      <div id="program-content" style="display:none">
        <div class="panel-header">
          <h2 id="panel-title">Apply Account</h2>
          <div style="display:flex;gap:8px">
            <button class="btn" onclick="toggleAllChecks(true)">All</button>
            <button class="btn" onclick="toggleAllChecks(false)">None</button>
            <button class="btn btn-primary" onclick="applySelected()">Apply</button>
          </div>
        </div>
        <div class="prog-grid" id="prog-grid"></div>
      </div>
    </div>
  </div>

  <!-- PAGE: Programs -->
  <div id="page-programs" class="page">
    <div class="page-title">Program Settings</div>
    <div class="prog-settings-layout">
      <div class="prog-sidebar" id="prog-settings-sidebar"></div>
      <div class="prog-detail" id="prog-detail">
        <div class="empty-state"><p>Select a program</p></div>
      </div>
    </div>
  </div>

  <!-- PAGE: MCP -->
  <div id="page-mcp" class="page">
    <div class="page-title" style="display:flex;justify-content:space-between;align-items:center">
      MCP Servers
      <button class="btn btn-primary" onclick="openMcpAddModal()">Add Server</button>
    </div>
    <div id="mcp-content"></div>
  </div>

  <!-- PAGE: Skills -->
  <div id="page-skills" class="page">
    <div class="page-title" style="display:flex;justify-content:space-between;align-items:center">
      Skills
      <button class="btn" onclick="refreshSkills()">Refresh</button>
    </div>
    <div id="skills-content"></div>
  </div>

  <!-- PAGE: Settings -->
  <div id="page-settings" class="page">
    <div class="page-title">Settings</div>
    <div id="settings-content"></div>
  </div>
</div>

<!-- CREATE ACCOUNT MODAL -->
<div class="modal-overlay" id="modal-create">
  <div class="modal">
    <h2>New Account</h2>
    <div class="form-group"><label>Name</label><input id="acc-name" placeholder="e.g. My GLM"></div>
    <div class="form-group"><label>Provider</label>
      <select id="acc-provider">
        <option value="anthropic">Anthropic / Claude</option>
        <option value="openai">OpenAI</option>
        <option value="openrouter">OpenRouter</option>
        <option value="gemini">Gemini</option>
        <option value="mistral">Mistral</option>
        <option value="deepseek">DeepSeek</option>
        <option value="ollama">Ollama (local)</option>
        <option value="xai">xAI (Grok)</option>
        <option value="groq">Groq</option>
        <option value="openai-compat">OpenAI Compatible</option>
      </select>
    </div>
    <div class="form-group"><label>API Key</label><input id="acc-apikey" type="password" placeholder="sk-..."></div>
    <div class="form-group"><label>Base URL (optional)</label><input id="acc-baseurl" placeholder="https://api.example.com/v1"></div>
    <div class="form-group"><label>Model (optional)</label><input id="acc-model" placeholder="e.g. gpt-5.4"></div>
    <div class="form-actions">
      <button class="btn" onclick="closeCreateModal()">Cancel</button>
      <button class="btn btn-primary" onclick="createAccount()">Create</button>
    </div>
  </div>
</div>

<!-- MCP ADD MODAL -->
<div class="modal-overlay" id="modal-mcp-add">
  <div class="modal">
    <h2>Add MCP Server</h2>
    <div class="form-group"><label>Name</label><input id="mcp-name" placeholder="server-name"></div>
    <div class="form-group"><label>Program</label>
      <select id="mcp-tool">
        <option value="claude-code">Claude Code</option>
        <option value="codex">Codex</option>
        <option value="cline">Cline</option>
      </select>
    </div>
    <div class="form-group"><label>Command (stdio)</label><input id="mcp-command" placeholder="npx"></div>
    <div class="form-group"><label>Args (comma-separated)</label><input id="mcp-args" placeholder="mcp-server,--flag"></div>
    <div class="form-group"><label>URL (SSE, optional)</label><input id="mcp-url" placeholder="https://..."></div>
    <div class="form-actions">
      <button class="btn" onclick="closeMcpAddModal()">Cancel</button>
      <button class="btn btn-primary" onclick="addMcpServer()">Add</button>
    </div>
  </div>
</div>

<div id="toast-container"></div>

<script>
let state = { accounts: [], programs: [], activeMap: {}, selectedAccountId: null };
const PROG_ICONS = { 'claude-code': 'C', 'codex': 'X', 'claude-desktop': 'D', 'opencode': 'O', 'cline': 'L', 'roo-code': 'R' };

function switchPage(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  if (page === 'mcp') loadMcp();
  if (page === 'skills') loadSkills();
  if (page === 'settings') loadSettings();
  if (page === 'programs') loadProgramSettings();
}

function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

async function api(path, body = null) {
  const opts = body ? { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) } : {};
  const res = await fetch(path, opts);
  return res.json();
}

async function loadAccounts() {
  const data = await api('/api/accounts');
  state = { ...state, ...data };
  renderAccountList();
}

function renderAccountList() {
  const { accounts } = state;
  const container = document.getElementById('account-cards');
  if (!accounts.length) {
    container.innerHTML = '<div class="empty-state"><p>No accounts yet</p></div>';
    return;
  }
  const sorted = [...accounts].sort((a, b) => {
    const aLim = a._limits?.has_limits ? 0 : 1;
    const bLim = b._limits?.has_limits ? 0 : 1;
    if (aLim !== bLim) return aLim - bLim;
    return a.name.localeCompare(b.name);
  });
  container.innerHTML = sorted.map(acc => `
    <div class="account-card ${state.selectedAccountId === acc.id ? 'selected' : ''}" onclick="selectAccount('${acc.id}')">
      <div class="acc-header">
        <span class="acc-color" style="background:${acc._provider_color}"></span>
        <span class="acc-name">${acc.name}</span>
        <span class="acc-provider">${acc._provider_display}</span>
      </div>
      <div class="acc-model">${acc.model || 'default model'}</div>
      ${acc.email ? `<div class="acc-model">${acc.email}</div>` : ''}
      ${acc._limits?.has_limits ? '<div class="acc-usage"><div class="usage-bar"><div class="usage-bar-fill" style="width:0%;background:var(--accent)"></div></div></div>' : ''}
    </div>
  `).join('');
}

function selectAccount(id) {
  state.selectedAccountId = id;
  renderAccountList();
  renderProgramPanel();
}

function renderProgramPanel() {
  const acc = state.accounts.find(a => a.id === state.selectedAccountId);
  if (!acc) return;
  document.getElementById('no-selection').style.display = 'none';
  document.getElementById('program-content').style.display = 'block';
  document.getElementById('panel-title').textContent = `Apply "${acc.name}" to:`;

  const grid = document.getElementById('prog-grid');
  grid.innerHTML = state.programs.map(prog => {
    const activeId = state.activeMap[prog.id];
    const isActive = activeId === acc.id;
    return `
      <div class="prog-card ${isActive ? 'checked' : ''}" onclick="toggleCheck(this)">
        <div class="prog-top">
          <div class="prog-icon">${PROG_ICONS[prog.id] || '?'}</div>
          <div>
            <div class="prog-name">${prog.name}</div>
          </div>
          <div class="prog-active">
            ${isActive ? '<span class="active-tag">Active</span>' : (activeId ? `← ${state.accounts.find(a=>a.id===activeId)?.name || activeId}` : '')}
          </div>
        </div>
        <div class="prog-check">
          <input type="checkbox" class="prog-check-input" value="${prog.id}" ${isActive ? 'checked' : ''}>
          <span>Select to apply</span>
        </div>
      </div>
    `;
  }).join('');
}

function toggleCheck(card) {
  const cb = card.querySelector('.prog-check-input');
  cb.checked = !cb.checked;
  card.classList.toggle('checked', cb.checked);
}

function toggleAllChecks(checked) {
  document.querySelectorAll('.prog-check-input').forEach(cb => {
    cb.checked = checked;
    cb.closest('.prog-card').classList.toggle('checked', checked);
  });
}

async function applySelected() {
  if (!state.selectedAccountId) return;
  const programs = [...document.querySelectorAll('.prog-check-input:checked')].map(cb => cb.value);
  if (!programs.length) { toast('No programs selected'); return; }
  const res = await api('/api/apply-account', { account_id: state.selectedAccountId, programs });
  const msgs = res.results?.map(r => r.ok ? `${r.program}: OK` : `${r.program}: ${r.message}`) || [];
  toast(msgs.join('; '), msgs.every(m => m.includes('OK')) ? 'success' : 'error');
  loadAccounts();
}

function openCreateModal() { document.getElementById('modal-create').classList.add('open'); }
function closeCreateModal() { document.getElementById('modal-create').classList.remove('open'); }

async function createAccount() {
  const name = document.getElementById('acc-name').value.trim();
  if (!name) { toast('Name required', 'error'); return; }
  const acc = {
    name,
    provider: document.getElementById('acc-provider').value,
    api_key: document.getElementById('acc-apikey').value,
    base_url: document.getElementById('acc-baseurl').value,
    model: document.getElementById('acc-model').value,
  };
  const res = await api('/api/account-create', acc);
  toast(res.message, 'success');
  closeCreateModal();
  ['acc-name','acc-apikey','acc-baseurl','acc-model'].forEach(id => document.getElementById(id).value = '');
  loadAccounts();
}

async function importCurrent() {
  const res = await api('/api/import-current');
  toast(`Imported: ${res.imported?.join(', ') || 'none'}`, res.imported?.length ? 'success' : '');
  loadAccounts();
}

// MCP
async function loadMcp() {
  const data = await api('/api/mcp-list');
  const container = document.getElementById('mcp-content');
  if (!data.servers?.length) {
    container.innerHTML = '<div class="empty-state"><p>No MCP servers configured</p></div>';
    return;
  }
  container.innerHTML = `<table class="mcp-table"><thead><tr>
    <th>Name</th><th>Program</th><th>Type</th><th>Command / URL</th><th></th>
  </tr></thead><tbody>${data.servers.map(s => `
    <tr>
      <td><strong>${s.name}</strong></td>
      <td><span class="tag">${s.tool}</span></td>
      <td>${s.url ? 'SSE' : 'stdio'}</td>
      <td style="color:var(--text-dim);font-size:11px">${s.url || (s.command + ' ' + (s.args||[]).join(' '))}</td>
      <td><button class="btn btn-sm btn-danger" onclick="deleteMcp('${s.name}','${s.tool}')">Del</button></td>
    </tr>
  `).join('')}</tbody></table>`;
}

function openMcpAddModal() { document.getElementById('modal-mcp-add').classList.add('open'); }
function closeMcpAddModal() { document.getElementById('modal-mcp-add').classList.remove('open'); }

async function addMcpServer() {
  const name = document.getElementById('mcp-name').value.trim();
  if (!name) return;
  const args = document.getElementById('mcp-args').value.split(',').map(s=>s.trim()).filter(Boolean);
  const res = await api('/api/mcp-add', {
    name, tool: document.getElementById('mcp-tool').value,
    command: document.getElementById('mcp-command').value,
    args, url: document.getElementById('mcp-url').value,
  });
  toast(res.message, res.ok ? 'success' : 'error');
  if (res.ok) { closeMcpAddModal(); loadMcp(); }
}

async function deleteMcp(name, tool) {
  const res = await api('/api/mcp-delete', { name, tool });
  if (res.ok) loadMcp();
  else toast(res.message, 'error');
}

// Skills
async function loadSkills() {
  const data = await api('/api/skills');
  const container = document.getElementById('skills-content');
  container.innerHTML = data.roots.map(root => `
    <div class="skill-root">
      <div class="skill-root-header" onclick="this.parentElement.classList.toggle('expanded')">
        <span>${root.label} <span style="color:var(--text-muted);font-size:11px">(${root.skills?.length || 0})</span></span>
        <span style="color:var(--text-muted)">${root.path}</span>
      </div>
      <div class="skill-root-body">
        ${root.skills?.map(s => `
          <div class="skill-item">
            <span class="skill-name">${s.name}</span>
            <span class="skill-status ${s.has_skill_md ? 'has-md' : ''}">${s.has_skill_md ? 'SKILL.md' : ''}</span>
          </div>
        `).join('') || '<p style="color:var(--text-muted);font-size:12px">Empty</p>'}
      </div>
    </div>
  `).join('');
}
function refreshSkills() { loadSkills(); }

// Programs Settings
async function loadProgramSettings() {
  const data = await api('/api/programs');
  const sidebar = document.getElementById('prog-settings-sidebar');
  sidebar.innerHTML = data.programs.map(p => `
    <div class="prog-sidebar-item" onclick="showProgDetail('${p.id}')">
      <span style="font-weight:600">${PROG_ICONS[p.id]||'?'}</span> ${p.name}
    </div>
  `).join('');
}

function showProgDetail(id) {
  document.querySelectorAll('.prog-sidebar-item').forEach(i => i.classList.remove('active'));
  event.currentTarget?.classList.add('active');
  const prog = state.programs.find(p => p.id === id) || PROGRAMS.find(p => p.id === id);
  const detail = document.getElementById('prog-detail');
  if (!prog) return;
  const active = prog.active_account_name || 'None';
  detail.innerHTML = `
    <h2 style="margin-bottom:12px">${prog.name}</h2>
    <div class="setting-group">
      <div class="setting-row"><div><div class="setting-label">Active Account</div><div class="setting-desc">${active}</div></div></div>
      <div class="setting-row"><div><div class="setting-label">Config Path</div><div class="setting-desc">${prog.config_path || 'N/A'}</div></div></div>
    </div>
  `;
}

// Settings
async function loadSettings() {
  const cfg = await api('/api/get-settings');
  const container = document.getElementById('settings-content');
  container.innerHTML = `
    <div class="setting-group">
      <h3>General</h3>
      <div class="setting-row">
        <div><div class="setting-label">Auto Backup</div><div class="setting-desc">Create backups before applying changes</div></div>
        <label style="cursor:pointer"><input type="checkbox" ${cfg.auto_backup !== false ? 'checked' : ''} onchange="api('/api/set-auto-backup',{enabled:this.checked}).then(()=>toast('Saved','success'))"></label>
      </div>
    </div>
    <div class="setting-group">
      <h3>Actions</h3>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" onclick="api('/api/backup-now').then(()=>toast('Backup created','success'))">Create Backup</button>
        <button class="btn btn-danger" onclick="api('/api/shutdown').then(()=>toast('Shutting down...'))">Shutdown</button>
      </div>
    </div>
    <div class="setting-group">
      <h3>Config</h3>
      <pre style="background:var(--bg);padding:12px;border-radius:var(--radius);font-size:11px;overflow:auto;max-height:300px;color:var(--text-dim)">${JSON.stringify(cfg, null, 2)}</pre>
    </div>
  `;
}

// Init
loadAccounts();
</script>
</body>
</html>"""


# ============================================================
# MENU BAR (macOS)
# ============================================================

def setup_menubar(port):
    try:
        import pystray
        from PIL import Image, ImageDraw

        def create_icon():
            size = 22
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=4, fill=(59, 130, 246, 255))
            draw.rounded_rectangle([6, 6, 10, 10], radius=1, fill=(255, 255, 255, 255))
            draw.rounded_rectangle([12, 6, 16, 10], radius=1, fill=(255, 255, 255, 255))
            draw.rounded_rectangle([6, 12, 10, 16], radius=1, fill=(255, 255, 255, 255))
            draw.rounded_rectangle([12, 12, 16, 16], radius=1, fill=(255, 255, 255, 255))
            return img

        def on_open(icon, item):
            webbrowser.open(f"http://127.0.0.1:{port}")

        def on_quit(icon, item):
            icon.stop()
            os._exit(0)

        icon = pystray.Icon(
            "MultiManager",
            icon=create_icon(),
            menu=pystray.Menu(
                pystray.MenuItem("Open MultiManager", on_open),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", on_quit),
            ),
        )
        icon.run_detached()
    except Exception as e:
        print(f"[menubar] Failed to start: {e}")
        print("[menubar] Continuing without menu bar icon")


# ============================================================
# SERVER
# ============================================================

def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[mm] MultiManager running at http://127.0.0.1:{port}")
    setup_menubar(port)
    threading.Timer(0.35, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
