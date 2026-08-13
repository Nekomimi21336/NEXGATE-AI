"""Extended models (text-only OCR preprocessing) configuration."""

from __future__ import annotations

import os
import re

from model_registry import PROVIDERS, get_provider_credentials

OCR_MODEL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]{1,63}$")
PLAN_IDS = ("free", "plus", "pro", "pro_plus", "max", "enterprise")
OCR_ENGINES = ("ai", "local")
OCR_ENGINE_LABELS = {
    "ai": "AI OCR（Anthropic Vision）",
    "local": "OCR（ローカル・非AI）",
}

DEFAULT_OCR_MODELS = {
    "claude-haiku-4-5": {
        "display_name": "Haiku 4.5 文字OCR",
        "provider": "anthropic",
        "api_model": "claude-haiku-4-5-20251001",
        "enabled": True,
        "plan_ids": list(PLAN_IDS),
    },
    "claude-sonnet-4": {
        "display_name": "Sonnet 4 文字OCR",
        "provider": "anthropic",
        "api_model": "claude-sonnet-4-20250514",
        "enabled": True,
        "plan_ids": ["pro", "pro_plus", "max", "enterprise"],
    },
}

DEFAULT_EXTENDED_MODELS = {
    "ocr": {
        "enabled": True,
        "engine": "ai",
        "structure_model_id": "",
        "default_model_id": "claude-haiku-4-5",
        "models": DEFAULT_OCR_MODELS,
    }
}


def normalize_ocr_engine(raw) -> str:
    value = str(raw or "ai").strip().lower()
    return value if value in OCR_ENGINES else "ai"


def _normalize_plan_ids(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        pid = str(item).strip().lower()
        if pid in PLAN_IDS and pid not in out:
            out.append(pid)
    return out


def normalize_ocr_model_entry(model_id, entry):
    if not isinstance(entry, dict):
        entry = {}
    provider = (entry.get("provider") or "anthropic").strip().lower()
    if provider not in PROVIDERS:
        provider = "anthropic"
    api_model = (entry.get("api_model") or model_id).strip() or model_id
    display_name = (entry.get("display_name") or model_id).strip() or model_id
    return {
        "display_name": display_name,
        "provider": provider,
        "api_model": api_model,
        "enabled": bool(entry.get("enabled", True)),
        "plan_ids": _normalize_plan_ids(entry.get("plan_ids")),
    }


def normalize_extended_models_config(raw):
    base = {
        "ocr": {
            "enabled": bool(DEFAULT_EXTENDED_MODELS["ocr"]["enabled"]),
            "engine": normalize_ocr_engine(DEFAULT_EXTENDED_MODELS["ocr"]["engine"]),
            "structure_model_id": DEFAULT_EXTENDED_MODELS["ocr"]["structure_model_id"],
            "default_model_id": DEFAULT_EXTENDED_MODELS["ocr"]["default_model_id"],
            "models": {
                mid: normalize_ocr_model_entry(mid, dict(cfg))
                for mid, cfg in DEFAULT_OCR_MODELS.items()
            },
        }
    }
    if not isinstance(raw, dict):
        return base
    ocr_raw = raw.get("ocr")
    if not isinstance(ocr_raw, dict):
        return base
    ocr = base["ocr"]
    if "enabled" in ocr_raw:
        ocr["enabled"] = bool(ocr_raw["enabled"])
    if "engine" in ocr_raw:
        ocr["engine"] = normalize_ocr_engine(ocr_raw["engine"])
    structure_model_id = (ocr_raw.get("structure_model_id") or "").strip()
    if structure_model_id:
        ocr["structure_model_id"] = structure_model_id
    default_id = (ocr_raw.get("default_model_id") or "").strip()
    models_raw = ocr_raw.get("models")
    if isinstance(models_raw, dict):
        merged = dict(ocr["models"])
        for model_id, entry in models_raw.items():
            mid = str(model_id).strip()
            if not mid:
                continue
            prev = merged.get(mid) or {}
            merged[mid] = normalize_ocr_model_entry(
                mid, {**prev, **(entry if isinstance(entry, dict) else {})}
            )
        ocr["models"] = merged
    if default_id and default_id in ocr["models"]:
        ocr["default_model_id"] = default_id
    elif ocr["default_model_id"] not in ocr["models"]:
        for mid, ent in ocr["models"].items():
            if ent.get("enabled", True):
                ocr["default_model_id"] = mid
                break
    return base


def validate_ocr_model_id(model_id):
    mid = (model_id or "").strip()
    if not mid or not OCR_MODEL_ID_RE.match(mid):
        return None
    return mid


def get_anthropic_api_key(providers_config):
    api_key, _ = get_provider_credentials("anthropic", providers_config)
    return api_key


def ocr_globally_enabled(extended_models):
    ocr = (extended_models or {}).get("ocr") or {}
    return bool(ocr.get("enabled", True))


def resolve_ocr_engine(extended_models) -> str:
    ocr = (extended_models or {}).get("ocr") or {}
    return normalize_ocr_engine(ocr.get("engine"))


def resolve_ocr_model_for_plan(plan_key, extended_models):
    ocr = (extended_models or {}).get("ocr") or {}
    models = ocr.get("models") or {}
    plan = (plan_key or "free").strip().lower()
    default_id = (ocr.get("default_model_id") or "").strip()

    def allowed(entry):
        if not entry.get("enabled", True):
            return False
        plan_ids = entry.get("plan_ids") or []
        return not plan_ids or plan in plan_ids

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
    return {
        "model_id": catalog_id,
        "api_model": entry.get("api_model") or catalog_id,
        "provider": entry.get("provider") or "anthropic",
        "display_name": entry.get("display_name") or catalog_id,
        "entry": entry,
    }


def serialize_ocr_admin(extended_models, providers_config, system_config=None):
    ocr = (extended_models or {}).get("ocr") or {}
    models = ocr.get("models") or {}
    config = system_config or {}
    chat_models = config.get("models") or {}
    structure_options = []
    for model_id in sorted(chat_models.keys()):
        ent = chat_models[model_id] or {}
        if not ent.get("enabled", True):
            continue
        structure_options.append(
            {
                "id": model_id,
                "label": ent.get("display_name") or model_id,
            }
        )
    env_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    stored = (providers_config or {}).get("anthropic") or {}
    stored_key = (stored.get("api_key") or "").strip()
    rows = []
    for model_id in sorted(models.keys()):
        ent = models[model_id]
        rows.append(
            {
                "id": model_id,
                "display_name": ent.get("display_name") or model_id,
                "provider": ent.get("provider") or "anthropic",
                "api_model": ent.get("api_model") or model_id,
                "enabled": bool(ent.get("enabled", True)),
                "plan_ids": list(ent.get("plan_ids") or []),
            }
        )
    return {
        "enabled": bool(ocr.get("enabled", True)),
        "engine": normalize_ocr_engine(ocr.get("engine")),
        "engine_options": [
            {"id": key, "label": OCR_ENGINE_LABELS[key]} for key in OCR_ENGINES
        ],
        "structure_model_id": (ocr.get("structure_model_id") or "").strip(),
        "structure_model_options": structure_options,
        "default_model_id": (ocr.get("default_model_id") or "").strip(),
        "models": rows,
        "anthropic": {
            "has_api_key": bool(stored_key or env_key),
            "api_key_env": "ANTHROPIC_API_KEY",
        },
        "plan_options": [{"id": p, "label": p} for p in PLAN_IDS],
    }
