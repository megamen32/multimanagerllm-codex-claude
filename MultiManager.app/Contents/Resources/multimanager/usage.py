"""Usage/limit cache with per-provider fetchers."""
import json, time, urllib.request
from .settings import CX_AUTH
from .settings import decode_jwt
from .config import ensure_defaults

_USAGE_CACHE = {}
_USAGE_CACHE_TTL = 120


def _get_codex_plan():
    try:
        if CX_AUTH.exists():
            auth = json.loads(CX_AUTH.read_text())
            tokens = auth.get("tokens", {})
            access_token = tokens.get("access_token", "")
            token_exp = 0
            email = ""
            plan = ""
            if access_token:
                claims = decode_jwt(access_token)
                token_exp = claims.get("exp", 0)
                profile = claims.get("https://api.openai.com/profile", {})
                oa = claims.get("https://api.openai.com/auth", {})
                email = profile.get("email", "")
                plan = oa.get("chatgpt_plan_type", "")
            now = time.time()
            return {
                "email": email,
                "plan": plan,
                "token_expires_in": max(0, token_exp - now) if token_exp else None,
                "has_api_key": bool(auth.get("OPENAI_API_KEY")),
            }
    except: pass
    return {}


def fetch_account_usage(account):
    key = account.get("id", "")
    now = time.time()
    cached = _USAGE_CACHE.get(key)
    if cached and now - cached["ts"] < _USAGE_CACHE_TTL:
        return cached["data"]

    api_key = account.get("api_key", "")
    base_url = account.get("base_url", "")
    prov = account.get("provider", "openai")
    from .settings import detect_provider
    if base_url: prov = detect_provider(base_url)
    result = {}

    # Codex accounts — read plan info from auth.json
    all_accs = ensure_defaults().get("accounts", [])
    no_key_ids = {a["id"] for a in all_accs if not a.get("api_key")}
    if account.get("id") in no_key_ids:
        plan = _get_codex_plan()
        if plan:
            result = {"type": "codex", "plan": plan.get("plan", ""), "email": plan.get("email", ""),
                      "token_expires_in": plan.get("token_expires_in"), "has_api_key": plan.get("has_api_key")}
            if plan.get("token_expires_in") is not None:
                hours = plan["token_expires_in"] / 3600
                if hours < 24:
                    result["used_pct"] = round((1 - hours / 24) * 100, 1)
                    result["remaining"] = f"{hours:.1f}h"

    # OpenAI accounts with real API key (not "any-key" dummy)
    elif prov == "openai" and api_key and api_key.startswith("sk-"):
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/dashboard/rate_limits",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                limits = data if isinstance(data, list) else data.get("data", [])
                rem = sum(l.get("remaining", 0) for l in limits if isinstance(l, dict))
                total = sum(l.get("max_requests", 0) for l in limits if isinstance(l, dict))
                pct = round((total - rem) / total * 100, 1) if total > 0 else None
                result = {"type": "openai", "remaining": rem, "total": total, "used_pct": pct}
        except urllib.error.HTTPError as e:
            result = {"type": "openai", "error": f"{e.code}"}
        except Exception as e:
            result = {"type": "openai", "error": str(e)[:80]}

    # Z.AI / GLM — try BigModel balance API
    elif ("z.ai" in base_url or "bigmodel" in base_url) and api_key:
        try:
            req = urllib.request.Request(
                "https://open.bigmodel.cn/api/llm/balance",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                result = {"type": "zai", "data": data}
        except Exception:
            result = {"type": "zai", "note": "quota via MCP"}

    _USAGE_CACHE[key] = {"ts": now, "data": result}
    return result
