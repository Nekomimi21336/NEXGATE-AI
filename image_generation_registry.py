"""Image generation (FLUX 2.0 / Black Forest Labs) catalog and provider resolution."""

from __future__ import annotations

import os
import re

IMAGE_MODEL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]{1,63}$")
API_MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]{1,127}$")
PLAN_IDS = ("free", "plus", "pro", "pro_plus", "max", "enterprise")

IMAGE_PROVIDERS = {
    "flux_bfl": {
        "label": "FLUX 2.0 (Black Forest Labs)",
        "api_key_env": "BFL_API_KEY",
        "base_url_env": "BFL_BASE_URL",
        "default_base_url": "https://api.bfl.ai",
    },
}

DEFAULT_IMAGE_MODELS = {
    "flux-2-pro": {
        "display_name": "FLUX.2 Pro",
        "provider": "flux_bfl",
        "api_model": "flux-2-pro",
        "enabled": True,
        "plan_ids": ["pro", "pro_plus", "max", "enterprise"],
        "cost_usd_per_image": 0.04,
        "price_usd_per_image": 0.08,
    },
    "flux-2-max": {
        "display_name": "FLUX.2 Max",
        "provider": "flux_bfl",
        "api_model": "flux-2-max",
        "enabled": True,
        "plan_ids": ["pro_plus", "max", "enterprise"],
        "cost_usd_per_image": 0.07,
        "price_usd_per_image": 0.14,
    },
    "flux-2-flex": {
        "display_name": "FLUX.2 Flex",
        "provider": "flux_bfl",
        "api_model": "flux-2-flex",
        "enabled": True,
        "plan_ids": ["plus", "pro", "pro_plus", "max", "enterprise"],
        "cost_usd_per_image": 0.05,
        "price_usd_per_image": 0.1,
    },
}

DEFAULT_IMAGE_GENERATION = {
    "enabled": True,
    "default_model_id": "flux-2-pro",
    "models": DEFAULT_IMAGE_MODELS,
}


def _float_field(entry, *keys, default=0.0):
    for key in keys:
        if key in entry:
            try:
                return max(0.0, float(entry[key]))
            except (TypeError, ValueError):
                return None
    return default


def _normalize_plan_ids(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        pid = str(item).strip().lower()
        if pid in PLAN_IDS and pid not in out:
            out.append(pid)
    return out


def _normalize_provider(provider):
    raw = (provider or "flux_bfl").strip().lower()
    if raw in ("openai_images", "openai"):
        return "flux_bfl"
    if raw not in IMAGE_PROVIDERS:
        return "flux_bfl"
    return raw


def normalize_image_model_entry(model_id, entry):
    if not isinstance(entry, dict):
        entry = {}
    provider = _normalize_provider(entry.get("provider"))
    api_model = (entry.get("api_model") or model_id).strip() or model_id
    if not API_MODEL_RE.match(api_model):
        api_model = model_id
    display_name = (entry.get("display_name") or model_id).strip() or model_id
    defaults = DEFAULT_IMAGE_MODELS.get(model_id) or {}
    cost = _float_field(entry, "cost_usd_per_image")
    if cost is None:
        cost = _float_field(defaults, "cost_usd_per_image", default=0.04)
    price = _float_field(entry, "price_usd_per_image")
    if price is None:
        price = _float_field(defaults, "price_usd_per_image", default=cost)
    if price is None:
        price = cost
    return {
        "display_name": display_name,
        "provider": provider,
        "api_model": api_model,
        "enabled": bool(entry.get("enabled", True)),
        "plan_ids": _normalize_plan_ids(entry.get("plan_ids")),
        "cost_usd_per_image": cost if cost is not None else 0.04,
        "price_usd_per_image": price if price is not None else cost,
    }


def normalize_image_generation_config(raw):
    base = {
        "enabled": bool(DEFAULT_IMAGE_GENERATION["enabled"]),
        "default_model_id": DEFAULT_IMAGE_GENERATION["default_model_id"],
        "models": {
            mid: normalize_image_model_entry(mid, dict(cfg))
            for mid, cfg in DEFAULT_IMAGE_MODELS.items()
        },
    }
    if not isinstance(raw, dict):
        return base
    if "enabled" in raw:
        base["enabled"] = bool(raw["enabled"])
    default_id = (raw.get("default_model_id") or "").strip()
    models_raw = raw.get("models")
    if isinstance(models_raw, dict):
        merged = dict(base["models"])
        for model_id, entry in models_raw.items():
            mid = str(model_id).strip()
            if not mid:
                continue
            if isinstance(entry, dict):
                legacy_provider = (entry.get("provider") or "").strip().lower()
                if legacy_provider in ("openai_images", "openai"):
                    continue
            prev = merged.get(mid) or {}
            merged[mid] = normalize_image_model_entry(
                mid, {**prev, **(entry if isinstance(entry, dict) else {})}
            )
        base["models"] = merged
    if default_id and default_id in base["models"]:
        base["default_model_id"] = default_id
    elif base["default_model_id"] not in base["models"]:
        for mid, ent in base["models"].items():
            if ent.get("enabled", True):
                base["default_model_id"] = mid
                break
    return base


def validate_image_model_id(model_id):
    mid = (model_id or "").strip()
    if not mid or not IMAGE_MODEL_ID_RE.match(mid):
        return None
    return mid


def get_image_provider_credentials(provider_id, providers_config):
    pid = _normalize_provider(provider_id)
    meta = IMAGE_PROVIDERS[pid]
    cfg = (providers_config or {}).get(pid) or {}
    legacy = (providers_config or {}).get("openai_images") or {}
    if not (cfg.get("api_key") or "").strip() and (legacy.get("api_key") or "").strip():
        cfg = {**legacy, **cfg}
    api_key = os.getenv(meta["api_key_env"], "").strip() or (cfg.get("api_key") or "").strip()
    base_url = (
        (cfg.get("base_url") or "").strip()
        or os.getenv(meta["base_url_env"], "").strip()
        or meta["default_base_url"]
    )
    return api_key, base_url.rstrip("/")


def flux_generation_url(base_url, api_model):
    slug = (api_model or "").strip().lstrip("/")
    if slug.startswith("v1/"):
        return f"{base_url.rstrip('/')}/{slug}"
    return f"{base_url.rstrip('/')}/v1/{slug}"


def image_generation_globally_enabled(image_generation):
    cfg = image_generation or {}
    return bool(cfg.get("enabled", True))


def resolve_image_model_for_plan(plan_key, image_generation):
    cfg = image_generation or {}
    models = cfg.get("models") or {}
    plan = (plan_key or "free").strip().lower()
    default_id = (cfg.get("default_model_id") or "").strip()

    def allowed(entry):
        if not entry.get("enabled", True):
            return False
        plan_ids = entry.get("plan_ids") or []
        if not plan_ids:
            return False
        return plan in plan_ids

    if default_id and default_id in models and allowed(models[default_id]):
        catalog_id = default_id
    else:
        catalog_id = None
        for mid in sorted(models.keys()):
            if allowed(models[mid]):
                catalog_id = mid
                break
    if not catalog_id:
        return None
    entry = models[catalog_id]
    provider = _normalize_provider(entry.get("provider"))
    return {
        "model_id": catalog_id,
        "api_model": entry.get("api_model") or catalog_id,
        "provider": provider,
        "display_name": entry.get("display_name") or catalog_id,
        "cost_usd_per_image": entry.get("cost_usd_per_image", 0.0),
        "price_usd_per_image": entry.get("price_usd_per_image", 0.0),
        "entry": entry,
    }


def plan_has_image_generation(plan_key, image_generation):
    if not image_generation_globally_enabled(image_generation):
        return False
    return resolve_image_model_for_plan(plan_key, image_generation) is not None


def serialize_image_generation_admin(image_generation, providers_config):
    cfg = normalize_image_generation_config(image_generation)
    models = cfg.get("models") or {}
    rows = []
    for model_id in sorted(models.keys()):
        ent = models[model_id]
        rows.append(
            {
                "id": model_id,
                "display_name": ent.get("display_name") or model_id,
                "provider": ent.get("provider") or "flux_bfl",
                "api_model": ent.get("api_model") or model_id,
                "enabled": bool(ent.get("enabled", True)),
                "plan_ids": list(ent.get("plan_ids") or []),
                "cost_usd_per_image": ent.get("cost_usd_per_image", 0.0),
                "price_usd_per_image": ent.get("price_usd_per_image", 0.0),
            }
        )
    stored = (providers_config or {}).get("flux_bfl") or {}
    env_key = os.getenv(IMAGE_PROVIDERS["flux_bfl"]["api_key_env"], "").strip()
    stored_key = (stored.get("api_key") or "").strip()
    base_url = (
        (stored.get("base_url") or "").strip()
        or os.getenv(IMAGE_PROVIDERS["flux_bfl"]["base_url_env"], "").strip()
        or IMAGE_PROVIDERS["flux_bfl"]["default_base_url"]
    )
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "default_model_id": (cfg.get("default_model_id") or "").strip(),
        "models": rows,
        "provider": {
            "id": "flux_bfl",
            "label": IMAGE_PROVIDERS["flux_bfl"]["label"],
            "has_api_key": bool(stored_key or env_key),
            "api_key_env": IMAGE_PROVIDERS["flux_bfl"]["api_key_env"],
            "base_url": base_url,
        },
        "plan_options": [{"id": p, "label": p} for p in PLAN_IDS],
        "api_model_hints": [
            "flux-2-pro",
            "flux-2-max",
            "flux-2-flex",
            "flux-2-klein-9b",
            "flux-2-klein-4b",
        ],
    }
