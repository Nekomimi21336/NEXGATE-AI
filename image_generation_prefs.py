"""Per-user image generation preferences (model and dimensions)."""

from __future__ import annotations

from image_generation_registry import (
    image_generation_globally_enabled,
    normalize_image_generation_config,
    resolve_image_model_for_plan,
)

IMAGE_SIZE_PRESETS = (
    {"id": "square_1024", "label": "1024 × 1024（正方形）", "width": 1024, "height": 1024},
    {"id": "landscape_1344", "label": "1344 × 768（横長）", "width": 1344, "height": 768},
    {"id": "portrait_1344", "label": "768 × 1344（縦長）", "width": 768, "height": 1344},
    {"id": "wide_1536", "label": "1536 × 1024（ワイド）", "width": 1536, "height": 1024},
    {"id": "tall_1536", "label": "1024 × 1536（タテ）", "width": 1024, "height": 1536},
)

_PRESET_BY_ID = {p["id"]: p for p in IMAGE_SIZE_PRESETS}


def _clamp_dim(value, default=1024):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(256, min(2048, n))


def normalize_user_image_generation_prefs(raw, *, plan_key, image_generation):
    cfg = normalize_image_generation_config(image_generation)
    plan = (plan_key or "free").strip().lower()
    default_model = resolve_image_model_for_plan(plan, cfg)
    default_model_id = (default_model or {}).get("model_id") or cfg.get("default_model_id") or "flux-2-pro"
    default_w, default_h = 1024, 1024

    prefs_raw = raw if isinstance(raw, dict) else {}
    model_id = (prefs_raw.get("model_id") or "").strip() or default_model_id
    width = _clamp_dim(prefs_raw.get("width"), default_w)
    height = _clamp_dim(prefs_raw.get("height"), default_h)

    preset_id = (prefs_raw.get("size_preset") or "").strip()
    preset = _PRESET_BY_ID.get(preset_id)
    if preset:
        width = preset["width"]
        height = preset["height"]
    else:
        preset_id = _match_preset_id(width, height)

    resolved = resolve_image_model_by_id(plan, cfg, model_id)
    if not resolved:
        resolved = default_model
    if not resolved:
        model_id = default_model_id
        resolved = resolve_image_model_by_id(plan, cfg, model_id)
    else:
        model_id = resolved["model_id"]

    return {
        "model_id": model_id,
        "width": width,
        "height": height,
        "size_preset": preset_id or _match_preset_id(width, height),
        "model_display_name": (resolved or {}).get("display_name") or model_id,
        "api_model": (resolved or {}).get("api_model") or model_id,
    }


def _match_preset_id(width, height):
    for preset in IMAGE_SIZE_PRESETS:
        if preset["width"] == width and preset["height"] == height:
            return preset["id"]
    return "custom"


def resolve_image_model_by_id(plan_key, image_generation, model_id):
    cfg = normalize_image_generation_config(image_generation)
    plan = (plan_key or "free").strip().lower()
    mid = (model_id or "").strip()
    models = cfg.get("models") or {}
    if not mid or mid not in models:
        return resolve_image_model_for_plan(plan, cfg)

    entry = models[mid]

    def allowed(entry_obj):
        if not entry_obj.get("enabled", True):
            return False
        plan_ids = entry_obj.get("plan_ids") or []
        if not plan_ids:
            return False
        return plan in plan_ids

    if not allowed(entry):
        return resolve_image_model_for_plan(plan, cfg)

    return {
        "model_id": mid,
        "api_model": entry.get("api_model") or mid,
        "provider": entry.get("provider") or "flux_bfl",
        "display_name": entry.get("display_name") or mid,
        "entry": entry,
    }


def list_image_models_for_plan(plan_key, image_generation):
    if not image_generation_globally_enabled(image_generation):
        return []
    cfg = normalize_image_generation_config(image_generation)
    plan = (plan_key or "free").strip().lower()
    models = cfg.get("models") or {}
    rows = []
    for model_id in sorted(models.keys()):
        ent = models[model_id]
        if not ent.get("enabled", True):
            continue
        plan_ids = ent.get("plan_ids") or []
        if plan_ids and plan not in plan_ids:
            continue
        rows.append(
            {
                "id": model_id,
                "display_name": ent.get("display_name") or model_id,
                "api_model": ent.get("api_model") or model_id,
            }
        )
    return rows


def serialize_image_generation_options(plan_key, image_generation, user_prefs_raw):
    prefs = normalize_user_image_generation_prefs(
        user_prefs_raw, plan_key=plan_key, image_generation=image_generation
    )
    return {
        "models": list_image_models_for_plan(plan_key, image_generation),
        "size_presets": [
            {
                "id": p["id"],
                "label": p["label"],
                "width": p["width"],
                "height": p["height"],
            }
            for p in IMAGE_SIZE_PRESETS
        ],
        "prefs": prefs,
    }
