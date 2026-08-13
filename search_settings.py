import json
import os
from pathlib import Path

from plan_features import extract_search_plan_flags

SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"

DEFAULT_SEARCH_ENGINES = {
    "tavily_api_key": "",
    "serper_api_key": "",
    "tavily_enabled": True,
    "serper_enabled": True,
    "ddg_enabled": True,
}

def _read_config_file():
    if not SYSTEM_CONFIG_FILE.exists():
        return {}
    try:
        with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_search_engines_config():
    raw = _read_config_file().get("search_engines") or {}
    merged = {**DEFAULT_SEARCH_ENGINES}
    if isinstance(raw, dict):
        if "tavily_api_key" in raw:
            merged["tavily_api_key"] = str(raw.get("tavily_api_key") or "").strip()
        if "serper_api_key" in raw:
            merged["serper_api_key"] = str(raw.get("serper_api_key") or "").strip()
        for key in ("tavily_enabled", "serper_enabled", "ddg_enabled"):
            if key in raw:
                merged[key] = bool(raw[key])
    return merged


def get_resolved_api_keys():
    from config_secrets import resolve_secret

    cfg = get_search_engines_config()
    tavily = resolve_secret(
        ("TAVILY_API_KEY",),
        cfg.get("tavily_api_key") or "",
    )
    serper = resolve_secret(
        ("SERPER_API_KEY",),
        cfg.get("serper_api_key") or "",
    )
    return {"tavily": tavily, "serper": serper}


def resolve_engines_for_plan(plan_key, plan_features):
    cfg = get_search_engines_config()
    keys = get_resolved_api_keys()
    feat = plan_features if isinstance(plan_features, dict) else {}

    web_on = bool(feat.get("web_search_enabled", True))
    global_ddg = bool(cfg.get("ddg_enabled", True))
    plan_ddg = web_on and global_ddg and bool(feat.get("search_ddg_enabled", True))
    return {
        "tavily": web_on
        and bool(cfg.get("tavily_enabled", True))
        and bool(feat.get("search_tavily_enabled", True))
        and bool(keys["tavily"]),
        "serper": web_on
        and bool(cfg.get("serper_enabled", True))
        and bool(feat.get("search_serper_enabled", True))
        and bool(keys["serper"]),
        "ddg": plan_ddg,
        "ddg_fallback": web_on and global_ddg and not plan_ddg,
    }


def merge_search_engines_config(incoming, current=None):
    current = current or get_search_engines_config()
    merged = dict(current)
    if not isinstance(incoming, dict):
        return merged
    if "tavily_api_key" in incoming:
        val = str(incoming.get("tavily_api_key") or "").strip()
        if val and not (os.getenv("TAVILY_API_KEY") or "").strip():
            merged["tavily_api_key"] = val
    if "serper_api_key" in incoming:
        val = str(incoming.get("serper_api_key") or "").strip()
        if val and not (os.getenv("SERPER_API_KEY") or "").strip():
            merged["serper_api_key"] = val
    for key in ("tavily_enabled", "serper_enabled", "ddg_enabled"):
        if key in incoming:
            merged[key] = bool(incoming[key])
    return merged


def serialize_search_engines_admin():
    cfg = get_search_engines_config()
    keys = get_resolved_api_keys()
    stored_tavily = (cfg.get("tavily_api_key") or "").strip()
    stored_serper = (cfg.get("serper_api_key") or "").strip()
    env_tavily = os.getenv("TAVILY_API_KEY", "").strip()
    env_serper = os.getenv("SERPER_API_KEY", "").strip()
    return {
        "tavily_enabled": bool(cfg.get("tavily_enabled", True)),
        "serper_enabled": bool(cfg.get("serper_enabled", True)),
        "ddg_enabled": bool(cfg.get("ddg_enabled", True)),
        "tavily_key_set": bool(stored_tavily),
        "serper_key_set": bool(stored_serper),
        "tavily_configured": bool(keys["tavily"]),
        "serper_configured": bool(keys["serper"]),
        "env_fallback_tavily": bool(not stored_tavily and env_tavily),
        "env_fallback_serper": bool(not stored_serper and env_serper),
        "tavily_key_hint": _mask_key(keys["tavily"]),
        "serper_key_hint": _mask_key(keys["serper"]),
    }


def _mask_key(key):
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}…{key[-4:]}"


