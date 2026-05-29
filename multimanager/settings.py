"""Paths, constants, program definitions, provider helpers."""
from pathlib import Path

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
OPENCODE_CFG = HOME / ".config" / "opencode" / "opencode.json"
CLINE_CFG = HOME / ".cline" / "mcp_settings.json"
ROO_CFG = HOME / ".roo" / "mcp_settings.json"

ANTHROPIC_DIR = HOME / ".config" / "anthropic"
ANTHROPIC_CREDENTIALS_DIR = ANTHROPIC_DIR / "credentials"
ANTHROPIC_CONFIGS_DIR = ANTHROPIC_DIR / "configs"
ANTHROPIC_ACTIVE_CONFIG = ANTHROPIC_DIR / "config"

APP_NAME = "MultiManager"
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


def provider_color(provider):
    return {"anthropic": "#d97757", "openai": "#10a37f", "gemini": "#4285f4",
            "mistral": "#ff7000", "ollama": "#000", "deepseek": "#4d6bfe",
            "openrouter": "#6c63ff", "xai": "#1d1d1f", "groq": "#f55036"}.get(provider, "#6b7280")


def detect_provider(url):
    if not url: return "openai"
    u = url.lower()
    for kw, p in [("z.ai", "anthropic"), ("anthropic", "anthropic"), ("bigmodel", "anthropic"),
                  ("openrouter", "openrouter"), ("deepseek", "deepseek"), ("mistral", "mistral"),
                  ("groq", "groq"), ("xai", "xai"), ("gemini", "gemini"), ("ollama", "ollama"),
                  ("localhost:11434", "ollama")]:
        if kw in u: return p
    return "openai"


def decode_jwt(token):
    import json, base64
    try:
        parts = token.split(".")
        if len(parts) < 2: return {}
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except: return {}


def expand_path(p):
    import os
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()
