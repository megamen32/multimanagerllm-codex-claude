"""HTTP request handler — all API routes."""
import json, os, threading, time, uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path

from .settings import PROGRAMS, provider_color, detect_provider, MASTER_SKILLS, MASTER_MCP
from .config import ensure_defaults, save_config, do_backup
from .accounts import import_accounts, detect_active_accounts, apply_account
from .skills import scan_master_skills, scan_all_skill_dirs, sync_skill_to_programs, sync_all_skills, collect_skill_to_master, delete_skill_from_master
from .mcp_ import scan_master_mcp, save_master_mcp, scan_program_mcp, sync_mcp_to_programs, delete_mcp_from_program
from .usage import fetch_account_usage, _USAGE_CACHE

_HERE = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, s=200):
        d = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(s)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _html(self):
        html_path = _HERE / "templates" / "index.html"
        if html_path.exists():
            d = html_path.read_bytes()
        else:
            d = b"<html><body><h1>MultiManager</h1><p>Template not found.</p></body></html>"
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
                usage = fetch_account_usage(a)
                enriched.append({**a, "_color": provider_color(p), "_prov": p, "_usage": usage})
            self._json({"accounts": enriched, "active": active, "programs": PROGRAMS})
            return

        if u.path == "/api/skills":
            master = scan_master_skills()
            prog_skills = scan_all_skill_dirs()
            self._json({"master": master, "programs": prog_skills})
            return

        if u.path == "/api/programs":
            active = detect_active_accounts()
            prog_mcp = scan_program_mcp()
            prog_skills = scan_all_skill_dirs()
            key_map = {a["id"]: a["name"] for a in cfg.get("accounts", [])}
            list_data = []
            for p in PROGRAMS:
                pid = p["id"]
                list_data.append({
                    "id": pid, "name": p["name"], "letter": p["letter"],
                    "config_path": p["config_path"],
                    "skills_count": len(prog_skills.get(pid, [])),
                    "mcp_count": len(prog_mcp.get(pid, {})),
                    "active_account": key_map.get(active.get(pid), None),
                    "type": p["type"],
                })
            self._json({"programs": list_data}); return

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
            import uuid
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
        if u.path == "/api/skills-import-from-program":
            pid = b.get("program", "")
            if not pid: return self._err("program required")
            prog = next(p for p in PROGRAMS if p["id"] == pid)
            from .settings import expand_path
            src = expand_path(prog["skills_dir"])
            if not src.exists(): return self._json({"imported": []})
            import shutil
            MASTER_SKILLS.mkdir(parents=True, exist_ok=True)
            names = []
            for d in sorted(src.iterdir()):
                if d.is_dir() and (d / "SKILL.md").exists():
                    dst = MASTER_SKILLS / d.name
                    if dst.exists(): continue
                    shutil.copytree(str(d), str(dst))
                    names.append(d.name)
            self._json({"imported": names})
            return
        if u.path == "/api/skills-import-from-folder":
            folder = b.get("folder", "").strip()
            if not folder: return self._err("folder path required")
            src = Path(os.path.expandvars(os.path.expanduser(folder)))
            if not src.exists(): return self._err("folder not found")
            import shutil
            MASTER_SKILLS.mkdir(parents=True, exist_ok=True)
            names = []
            for d in sorted(src.iterdir()):
                if d.is_dir() and (d / "SKILL.md").exists():
                    dst = MASTER_SKILLS / d.name
                    if dst.exists(): continue
                    shutil.copytree(str(d), str(dst))
                    names.append(d.name)
            self._json({"imported": names})
            return

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

        # USAGE
        if u.path == "/api/usage-refresh":
            aid = b.get("account_id", "")
            if aid: _USAGE_CACHE.pop(aid, None)
            else: _USAGE_CACHE.clear()
            self._json({"ok": True}); return

        # SETTINGS
        if u.path == "/api/backup-now":
            do_backup(cfg); self._json({"ok": True}); return
        if u.path == "/api/set-auto-backup":
            cfg["auto_backup"] = b.get("enabled", True); save_config(cfg); self._json({"ok": True}); return

        # UTILS
        if u.path == "/api/open-folder":
            path = b.get("path", "")
            if path:
                import subprocess, os
                p = Path(os.path.expanduser(path))
                if p.exists():
                    subprocess.Popen(["open", "-R", str(p.resolve())])
                    self._json({"ok": True}); return
            self._json({"ok": False, "error": "not found"}); return

        self.send_error(404)

    def log_message(self, *a): pass
