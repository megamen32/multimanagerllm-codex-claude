"""Account CRUD, import from programs, detect active, apply."""
import json, uuid, shutil, os
from pathlib import Path
from .settings import (
    CC_SETTINGS, CX_CONFIG, CX_AUTH, OPENCODE_CFG, CONFIG_DIR, MASTER_DIR,
    PROGRAMS, decode_jwt, expand_path, detect_provider
)
from .config import ensure_defaults, save_config, do_backup
from .toml_utils import parse_toml_simple, write_toml_simple


def _read_json(path):
    if not Path(path).exists(): return {}
    try: return json.loads(Path(path).read_text())
    except: return {}

def _write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))

def _read_cc(): return _read_json(CC_SETTINGS)
def _write_cc(d): _write_json(CC_SETTINGS, d)

def _read_cx():
    if not CX_CONFIG.exists(): return {}
    return parse_toml_simple(CX_CONFIG.read_text())
def _write_cx(data):
    order = ["model", "model_provider", "model_reasoning_effort", "personality",
             "approval_policy", "sandbox_mode", "notify", "openai_base_url"]
    CX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CX_CONFIG.write_text(write_toml_simple(data, order))


def import_accounts():
    cfg = ensure_defaults()
    accounts = cfg.setdefault("accounts", [])
    imported = []
    existing_keys = {a.get("api_key", "")[:20] for a in accounts}
    existing_urls = {a.get("base_url", "").rstrip("/") for a in accounts}

    # Claude Code settings.json
    cc = _read_cc()
    env = cc.get("env", {})
    cc_url = env.get("ANTHROPIC_BASE_URL", "")
    cc_key = (env.get("ANTHROPIC_AUTH_TOKEN", "") or env.get("ANTHROPIC_API_KEY", ""))
    cc_model = cc.get("model", "")
    cc_overrides = {}
    for k in ("ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL"):
        if env.get(k): cc_overrides[k.replace("ANTHROPIC_DEFAULT_", "").replace("_MODEL", "").lower()] = env[k]
    if cc_key and cc_key[:20] not in existing_keys:
        name = "Z.AI (GLM)" if "z.ai" in (cc_url or "") else "Claude Code"
        accounts.append({
            "id": uuid.uuid4().hex[:8], "name": name, "provider": "anthropic",
            "api_key": cc_key, "base_url": cc_url, "model": cc_model or "sonnet",
            "claude_overrides": cc_overrides
        })
        imported.append(name)

    # Codex config.toml + auth.json
    cx = _read_cx()
    cx_model = cx.get("model", "")
    cx_auth_data = _read_json(CX_AUTH)
    tokens = cx_auth_data.get("tokens", {})
    cx_key = cx_auth_data.get("OPENAI_API_KEY", tokens.get("access_token", ""))
    email = ""
    plan = ""
    if tokens.get("access_token"):
        claims = decode_jwt(tokens["access_token"])
        profile = claims.get("https://api.openai.com/profile", {})
        oa = claims.get("https://api.openai.com/auth", {})
        email = profile.get("email", "")
        plan = oa.get("chatgpt_plan_type", "")
    if cx_key and cx_key[:20] not in existing_keys:
        # Check for model_providers definitions
        mps = cx.get("model_providers", {})
        base_url = ""
        codex_provider = cx.get("model_provider", "")
        if codex_provider and isinstance(mps, dict):
            mp = mps.get(codex_provider, {})
            if isinstance(mp, dict): base_url = mp.get("base_url", "")
        name = f"Codex ({cx_model or 'default'})"
        accounts.append({
            "id": uuid.uuid4().hex[:8], "name": name, "provider": "openai",
            "api_key": "", "base_url": base_url, "model": cx_model,
            "email": email, "plan": plan, "codex_provider": codex_provider
        })
        imported.append(name)

    # OpenCode config
    oc = _read_json(OPENCODE_CFG)
    for pname, pdata in (oc.get("provider") or {}).items():
        if isinstance(pdata, dict):
            opts = pdata.get("options", {})
            key = opts.get("apiKey", "")
            url = opts.get("baseUrl", "")
            if key and key[:20] not in existing_keys and url.rstrip("/") not in existing_urls:
                n = f"OpenCode ({pname})"
                accounts.append({
                    "id": uuid.uuid4().hex[:8], "name": n, "provider": "openai",
                    "api_key": key, "base_url": url, "model": ""
                })
                imported.append(n)

    save_config(cfg)
    return imported


def detect_active_accounts():
    result = {}
    accounts = ensure_defaults().get("accounts", [])

    # Claude Code
    cc = _read_cc()
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
    cx = _read_cx()
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
    oc = _read_json(OPENCODE_CFG)
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


def apply_account(acc_id, program_id):
    cfg = ensure_defaults()
    acc = next((a for a in cfg.get("accounts", []) if a["id"] == acc_id), None)
    if not acc: return False, "Account not found"
    do_backup(cfg)

    if program_id == "claude-code":
        cc = _read_cc()
        env = cc.setdefault("env", {})
        base_url = acc.get("base_url", "")
        api_key = acc.get("api_key", "")
        model = acc.get("model", "")
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
        _write_cc(cc)
        return True, f"Claude Code: {acc['name']}"

    elif program_id == "codex":
        cx = _read_cx()
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
        _write_cx(cx)
        return True, f"Codex: {acc['name']}"

    elif program_id == "opencode":
        oc = _read_json(OPENCODE_CFG)
        prov = oc.setdefault("provider", {})
        base_url = acc.get("base_url", "")
        api_key = acc.get("api_key", "")
        if "z.ai" in base_url or "zai" in acc.get("provider", ""):
            zai = prov.setdefault("zai-coding-plan", {})
            opts = zai.setdefault("options", {})
            if api_key: opts["apiKey"] = api_key
            if base_url: opts["baseUrl"] = base_url
        _write_json(OPENCODE_CFG, oc)
        return True, f"OpenCode: {acc['name']}"

    return False, f"{program_id}: not implemented"
