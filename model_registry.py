"""Model catalog, providers (DeepSeek, Cerebras, Moonshot), and API client resolution."""

from __future__ import annotations

import os
import re
import uuid

PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "default_base_url": "https://api.deepseek.com",
        "supports_thinking": True,
    },
    "cerebras": {
        "label": "Cerebras",
        "api_key_env": "CEREBRAS_API_KEY",
        "base_url_env": "CEREBRAS_BASE_URL",
        "default_base_url": "https://api.cerebras.ai/v1",
        "supports_thinking": False,
    },
    "moonshot": {
        "label": "Moonshot / Kimi",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url_env": "MOONSHOT_BASE_URL",
        "default_base_url": "https://api.moonshot.ai/v1",
        "supports_thinking": False,
        "base_url_hint": "国際: https://api.moonshot.ai/v1 / 中国: https://api.moonshot.cn/v1",
    },
    "anthropic": {
        "label": "Anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "default_base_url": "https://api.anthropic.com",
        "supports_thinking": False,
    },
}


def provider_supports_thinking(provider_id):
    meta = PROVIDERS.get(provider_id) or {}
    return bool(meta.get("supports_thinking"))


def provider_supports_reasoning_content(provider_id):
    return provider_supports_thinking(provider_id)


def provider_supports_stream_usage(provider_id):
    return (provider_id or "").strip().lower() in ("deepseek", "moonshot")

AGENT_PROFILE_DEEPSEEK = "deepseek"
AGENT_PROFILE_STANDARD = "standard"
AGENT_PROFILE_ALIASES = {"cerebras": AGENT_PROFILE_STANDARD, "moonshot": AGENT_PROFILE_STANDARD}
AGENT_PROFILE_OPTIONS = (AGENT_PROFILE_DEEPSEEK, AGENT_PROFILE_STANDARD)


def default_agent_profile(model_id, provider):
    mid = (model_id or "").strip().lower()
    prov = (provider or "deepseek").strip().lower()
    if mid == "deepseek-v4-flash":
        return AGENT_PROFILE_DEEPSEEK
    if prov in ("cerebras", "moonshot"):
        return AGENT_PROFILE_STANDARD
    if prov == "deepseek":
        return AGENT_PROFILE_DEEPSEEK
    return AGENT_PROFILE_STANDARD


def normalize_agent_profile(value, model_id=None, provider=None):
    raw = (value or "").strip().lower()
    if raw in AGENT_PROFILE_ALIASES:
        raw = AGENT_PROFILE_ALIASES[raw]
    if raw in AGENT_PROFILE_OPTIONS:
        return raw
    return default_agent_profile(model_id, provider)


def is_deepseek_agent_profile(agent_profile):
    return normalize_agent_profile(agent_profile) == AGENT_PROFILE_DEEPSEEK


DEFAULT_MODELS = {
    "deepseek-v4-flash": {
        "display_name": "NEXGATE BASE",
        "api_id": "nexgate-base",
        "provider": "deepseek",
        "api_model": "deepseek-v4-flash",
        "agent_profile": AGENT_PROFILE_DEEPSEEK,
        "enabled": True,
        "tier": "frontier model",
        "cost_input_usd_per_1m": 0.14,
        "cost_output_usd_per_1m": 0.28,
        "price_input_usd_per_1m": 0.14,
        "price_output_usd_per_1m": 0.28,
        # キャッシュヒットは input の約2割（管理者が調整可能）
        "cost_input_cache_hit_usd_per_1m": 0.028,
        "price_input_cache_hit_usd_per_1m": 0.028,
    },
    "kimi-k2.6": {
        "display_name": "Kimi K2.6",
        "api_id": "kimi-k2-6",
        "provider": "moonshot",
        "api_model": "kimi-k2.6",
        "agent_profile": AGENT_PROFILE_STANDARD,
        "enabled": False,
        "tier": "1M context",
        "cost_input_usd_per_1m": 0.16,
        "cost_output_usd_per_1m": 0.95,
        "price_input_usd_per_1m": 4.0,
        "price_output_usd_per_1m": 4.0,
        "cost_input_cache_hit_usd_per_1m": 0.16,
        "price_input_cache_hit_usd_per_1m": 4.0,
    },
}

MODEL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]{1,63}$")
PUBLIC_API_OWNER = "nexgate"
PUBLIC_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _ensure_public_id(entry):
    pid = (entry.get("public_id") or "").strip()
    if pid and PUBLIC_ID_RE.match(pid):
        return pid
    return str(uuid.uuid4())


def _display_to_api_id(display_name):
    slug = re.sub(r"[^a-z0-9]+", "-", (display_name or "").strip().lower()).strip("-")
    if len(slug) >= 2 and MODEL_ID_RE.match(slug):
        return slug
    return None


def _ensure_api_id(model_id, entry):
    raw = (entry.get("api_id") or "").strip()
    validated = validate_model_id(raw)
    if validated:
        return validated
    default_api = (DEFAULT_MODELS.get(model_id) or {}).get("api_id") or ""
    validated = validate_model_id(str(default_api).strip())
    if validated:
        return validated
    slug = _display_to_api_id(entry.get("display_name"))
    if slug:
        return slug
    legacy = (entry.get("public_id") or "").strip()
    if legacy and validate_model_id(legacy) and not PUBLIC_ID_RE.match(legacy):
        return legacy
    digest = uuid.uuid5(uuid.NAMESPACE_OID, f"nexgate-api-id:{model_id}").hex[:12]
    return f"nexgate-{digest}"


def get_model_api_id(entry, catalog_id=""):
    if not isinstance(entry, dict):
        return (catalog_id or "").strip()
    return _ensure_api_id(catalog_id, entry)


def validate_unique_api_ids(models, *, pending=None):
    pending = pending if isinstance(pending, dict) else {}
    seen = {}
    for catalog_id, entry in (models or {}).items():
        api_id = pending.get(catalog_id, get_model_api_id(entry, catalog_id))
        if api_id in seen and seen[api_id] != catalog_id:
            return f"APIモデルID「{api_id}」が重複しています（{seen[api_id]} と {catalog_id}）"
        seen[api_id] = catalog_id
    return None


def _float_field(entry, *keys, default=0.0):
    for key in keys:
        if key in entry:
            try:
                return float(entry[key])
            except (TypeError, ValueError):
                return None
    return default


def normalize_model_entry(model_id, entry):
    if not isinstance(entry, dict):
        entry = {}
    provider = (entry.get("provider") or "deepseek").strip().lower()
    if provider not in PROVIDERS:
        provider = "deepseek"

    legacy_in = _float_field(entry, "input_usd_per_1m")
    legacy_out = _float_field(entry, "output_usd_per_1m")
    cost_in = _float_field(entry, "cost_input_usd_per_1m", default=legacy_in if legacy_in is not None else 0.14)
    cost_out = _float_field(entry, "cost_output_usd_per_1m", default=legacy_out if legacy_out is not None else 0.28)
    if cost_in is None:
        cost_in = 0.14
    if cost_out is None:
        cost_out = 0.28

    price_in = _float_field(
        entry,
        "price_input_usd_per_1m",
        default=legacy_in if legacy_in is not None else cost_in,
    )
    price_out = _float_field(
        entry,
        "price_output_usd_per_1m",
        default=legacy_out if legacy_out is not None else cost_out,
    )
    if price_in is None:
        price_in = cost_in
    if price_out is None:
        price_out = cost_out

    # キャッシュヒット単価（未設定時は通常 input 単価 = 割引なし）
    cost_cache_hit = _float_field(
        entry, "cost_input_cache_hit_usd_per_1m", default=cost_in
    )
    if cost_cache_hit is None:
        cost_cache_hit = cost_in
    price_cache_hit = _float_field(
        entry, "price_input_cache_hit_usd_per_1m", default=price_in
    )
    if price_cache_hit is None:
        price_cache_hit = price_in

    api_model = (entry.get("api_model") or model_id).strip() or model_id
    display_name = (entry.get("display_name") or model_id).strip() or model_id
    if "tier" in entry:
        tier = (entry.get("tier") or "").strip()
    else:
        tier = (PROVIDERS[provider]["label"] or "").strip()
    if not tier:
        tier = PROVIDERS[provider]["label"]

    agent_profile = normalize_agent_profile(
        entry.get("agent_profile"), model_id=model_id, provider=provider
    )
    description = (entry.get("description") or "").strip()

    api_id = _ensure_api_id(model_id, entry)

    return {
        "display_name": display_name,
        "description": description,
        "provider": provider,
        "api_model": api_model,
        "api_id": api_id,
        "public_id": _ensure_public_id(entry),
        "enabled": bool(entry.get("enabled", True)),
        "tier": tier,
        "agent_profile": agent_profile,
        "cost_input_usd_per_1m": max(0.0, cost_in),
        "cost_output_usd_per_1m": max(0.0, cost_out),
        "price_input_usd_per_1m": max(0.0, price_in),
        "price_output_usd_per_1m": max(0.0, price_out),
        "cost_input_cache_hit_usd_per_1m": max(0.0, cost_cache_hit),
        "price_input_cache_hit_usd_per_1m": max(0.0, price_cache_hit),
    }


def normalize_models_config(raw):
    models = {
        mid: normalize_model_entry(mid, dict(cfg))
        for mid, cfg in DEFAULT_MODELS.items()
    }
    if not isinstance(raw, dict):
        return models
    for model_id, entry in raw.items():
        mid = str(model_id).strip()
        if not mid:
            continue
        base = models.get(mid) or {}
        merged_raw = {**base, **(entry if isinstance(entry, dict) else {})}
        models[mid] = normalize_model_entry(mid, merged_raw)
    return models


def raw_models_missing_public_id(raw_models):
    if not isinstance(raw_models, dict):
        return False
    for entry in raw_models.values():
        if not isinstance(entry, dict):
            return True
        pid = (entry.get("public_id") or "").strip()
        if not pid or not PUBLIC_ID_RE.match(pid):
            return True
    return False


def find_model_by_api_id(models, requested):
    token = (requested or "").strip()
    if not token:
        return None, None
    for catalog_id, entry in models.items():
        if get_model_api_id(entry, catalog_id) == token:
            return catalog_id, entry
    return None, None


def find_model_catalog_entry(models, requested):
    token = (requested or "").strip()
    if not token:
        return None, None
    catalog_id, entry = find_model_by_api_id(models, token)
    if entry:
        return catalog_id, entry
    for catalog_id, entry in models.items():
        if (entry.get("public_id") or "").strip() == token:
            return catalog_id, entry
    if token in models:
        return token, models[token]
    return None, None


def normalize_providers_config(raw):
    stored = raw if isinstance(raw, dict) else {}
    out = {}
    for pid in PROVIDERS:
        entry = stored.get(pid) if isinstance(stored.get(pid), dict) else {}
        out[pid] = {
            "api_key": (entry.get("api_key") or "").strip(),
            "base_url": (entry.get("base_url") or "").strip(),
        }
    for pid, entry in stored.items():
        if pid in out or not isinstance(entry, dict):
            continue
        out[pid] = {
            "api_key": (entry.get("api_key") or "").strip(),
            "base_url": (entry.get("base_url") or "").strip(),
        }
    return out


def get_default_model_public_id(config):
    mid = get_default_model_id(config)
    entry = (config.get("models") or {}).get(mid) or {}
    return get_model_api_id(entry, mid)


def get_default_model_id(config):
    explicit = (config.get("default_model") or "").strip()
    models = config.get("models") or {}
    if explicit and explicit in models and models[explicit].get("enabled", True):
        return explicit
    env_default = os.getenv("OPENAI_MODEL", "").strip()
    if env_default and env_default in models and models[env_default].get("enabled", True):
        return env_default
    for mid, entry in models.items():
        if entry.get("enabled", True):
            return mid
    return next(iter(models.keys()), "deepseek-v4-flash")


def validate_model_id(model_id):
    mid = (model_id or "").strip()
    if not mid or not MODEL_ID_RE.match(mid):
        return None
    return mid


def models_for_chat_list(models_config):
    items = []
    for model_id in sorted(models_config.keys()):
        entry = models_config[model_id]
        if not entry.get("enabled", True):
            continue
        api_id = get_model_api_id(entry, model_id)
        if not api_id:
            continue
        provider = entry.get("provider", "deepseek")
        tier = entry.get("tier") or PROVIDERS.get(provider, {}).get("label", "")
        description = (entry.get("description") or "").strip() or tier
        items.append(
            {
                "id": api_id,
                "name": entry.get("display_name") or model_id,
                "tier": tier,
                "description": description,
                "agent_profile": entry.get("agent_profile") or AGENT_PROFILE_DEEPSEEK,
                "supports_thinking": provider_supports_thinking(provider),
            }
        )
    return items


def models_for_openai_api(models_config):
    items = []
    for model_id in sorted(models_config.keys()):
        entry = models_config[model_id]
        if not entry.get("enabled", True):
            continue
        api_id = get_model_api_id(entry, model_id)
        if not api_id:
            continue
        items.append(
            {
                "id": api_id,
                "object": "model",
                "owned_by": PUBLIC_API_OWNER,
                "display_name": entry.get("display_name") or api_id,
            }
        )
    return items


def resolve_chat_model(model_id, config, *, public_api=False):
    models = config.get("models") or {}
    token = (model_id or "").strip()
    if public_api:
        catalog_id, entry = find_model_by_api_id(models, token)
        if not entry and not token:
            catalog_id = get_default_model_id(config)
            entry = models.get(catalog_id)
        if not entry:
            raise ValueError("The model does not exist or you do not have access to it")
    else:
        catalog_id, entry = find_model_catalog_entry(models, token)
        if not entry:
            catalog_id = get_default_model_id(config)
            entry = models.get(catalog_id)
        if not entry:
            raise ValueError("利用可能なモデルがありません")
    if not entry.get("enabled", True):
        if public_api:
            raise ValueError("The model does not exist or you do not have access to it")
        raise ValueError("このモデルは現在無効です")
    api_model = (entry.get("api_model") or catalog_id).strip() or catalog_id
    provider = entry.get("provider", "deepseek")
    if provider not in PROVIDERS:
        provider = "deepseek"
    return {
        "model_id": catalog_id,
        "api_model": api_model,
        "provider": provider,
        "agent_profile": entry.get("agent_profile") or default_agent_profile(catalog_id, provider),
        "entry": entry,
    }


def get_provider_credentials(provider_id, providers_config):
    meta = PROVIDERS.get(provider_id) or PROVIDERS["deepseek"]
    cfg = (providers_config or {}).get(provider_id) or {}
    api_key = os.getenv(meta["api_key_env"], "").strip() or (cfg.get("api_key") or "").strip()
    base_url = (
        (cfg.get("base_url") or "").strip()
        or os.getenv(meta["base_url_env"], "").strip()
        or meta["default_base_url"]
    )
    return api_key, base_url


def _provider_timeout():
    """プロバイダー接続のタイムアウト。

    遅延を抑え、プロバイダー障害時にスレッドを長時間専有しないようにする。
    - connect: 接続確立 10秒
    - read: ストリーム中の次のチャンク待ち 120秒（推論中もデータは流れる）
    - write: リクエスト送信 10秒
    - pool: コネクションプール取得 10秒
    """
    try:
        import httpx

        return httpx.Timeout(
            connect=10.0,
            read=120.0,
            write=10.0,
            pool=10.0,
        )
    except Exception:
        return 120.0


def make_openai_client_for_provider(provider_id, providers_config):
    from openai import OpenAI

    api_key, base_url = get_provider_credentials(provider_id, providers_config)
    kwargs = {"api_key": api_key or "no-key", "timeout": _provider_timeout()}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs), api_key


def provider_labels():
    return {pid: meta["label"] for pid, meta in PROVIDERS.items()}


def serialize_provider_admin(providers_config):
    rows = []
    for pid, meta in PROVIDERS.items():
        cfg = (providers_config or {}).get(pid) or {}
        env_key = os.getenv(meta["api_key_env"], "").strip()
        stored_key = (cfg.get("api_key") or "").strip()
        has_key = bool(stored_key or env_key)
        row = {
            "id": pid,
            "label": meta["label"],
            "base_url": (cfg.get("base_url") or "").strip()
            or os.getenv(meta["base_url_env"], "").strip()
            or meta["default_base_url"],
            "has_api_key": has_key,
            "api_key_env": meta["api_key_env"],
        }
        hint = (meta.get("base_url_hint") or "").strip()
        if hint:
            row["base_url_hint"] = hint
        rows.append(row)
    return rows
