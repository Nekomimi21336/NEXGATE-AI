"""Model pricing, usage aggregates, and time-series charts for admin."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from model_registry import DEFAULT_MODELS, normalize_model_entry, normalize_models_config

SERIES_FILE = Path(__file__).parent / "data" / "model_usage_series.json"
SERIES_RETENTION_DAYS = 120

RANGE_PRESETS = {
    "24h": {
        "delta": timedelta(hours=24),
        "granularity": "hour",
        "label": "直近24時間",
    },
    "3d": {
        "delta": timedelta(days=3),
        "granularity": "hour",
        "label": "直近3日",
    },
    "7d": {
        "delta": timedelta(days=7),
        "granularity": "day",
        "label": "直近7日",
    },
    "30d": {
        "delta": timedelta(days=30),
        "granularity": "day",
        "label": "直近30日",
    },
    "12w": {
        "delta": timedelta(weeks=12),
        "granularity": "week",
        "label": "直近12週",
    },
}

DEFAULT_CHART_RANGE = "7d"


def current_usage_period():
    return datetime.now().strftime("%Y-%m")


def empty_model_stats():
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "input_cache_hit_tokens": 0,
        "input_cache_miss_tokens": 0,
        "requests": 0,
    }


def normalize_model_usage(raw):
    period = current_usage_period()
    if not isinstance(raw, dict):
        return {"period": period, "models": {}}
    if raw.get("period") != period:
        return {"period": period, "models": {}}
    models = raw.get("models") or {}
    if not isinstance(models, dict):
        models = {}
    return {"period": period, "models": dict(models)}


def load_usage_series():
    if not SERIES_FILE.exists():
        return {"models": {}}
    try:
        with open(SERIES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"models": {}}
    if not isinstance(data, dict):
        return {"models": {}}
    models = data.get("models") or {}
    if not isinstance(models, dict):
        models = {}
    return {"models": models}


def save_usage_series(data):
    SERIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SERIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hour_bucket_key(dt=None):
    dt = dt or datetime.now()
    return dt.strftime("%Y-%m-%dT%H")


def prune_series_buckets(model_buckets, cutoff):
    if not isinstance(model_buckets, dict):
        return {}
    kept = {}
    for key, stats in model_buckets.items():
        try:
            bucket_dt = datetime.strptime(key, "%Y-%m-%dT%H")
        except ValueError:
            continue
        if bucket_dt >= cutoff:
            kept[key] = stats
    return kept


def record_usage_series(model_id, token_usage):
    if not model_id or not token_usage:
        return
    series = load_usage_series()
    models = series.setdefault("models", {})
    model_buckets = models.setdefault(model_id, {})
    if not isinstance(model_buckets, dict):
        model_buckets = {}
        models[model_id] = model_buckets

    key = hour_bucket_key()
    current = model_buckets.get(key) or empty_model_stats()
    model_buckets[key] = merge_token_usage_into_stats(current, token_usage)
    models[model_id] = model_buckets

    cutoff = datetime.now() - timedelta(days=SERIES_RETENTION_DAYS)
    for mid in list(models.keys()):
        models[mid] = prune_series_buckets(models[mid], cutoff)

    save_usage_series(series)


def compute_usage_cost(
    prompt,
    completion,
    reasoning,
    input_per_1m,
    output_per_1m,
    input_cache_hit_per_1m=None,
    cache_hit_tokens=0,
):
    """3段階（input cache miss / input cache hit / output）でコスト計算

    input_cache_hit_per_1m が None の場合は input_per_1m と同じ扱い
    （キャッシュ割引なし）。cache_hit_tokens はトークン数のみ指定可能。
    """
    prompt = int(prompt or 0)
    completion = int(completion or 0)
    reasoning = int(reasoning or 0)
    cache_hit = int(cache_hit_tokens or 0)
    if cache_hit < 0:
        cache_hit = 0
    if cache_hit > prompt:
        cache_hit = prompt
    cache_miss = prompt - cache_hit

    input_rate = float(input_per_1m or 0)
    cache_rate = (
        float(input_cache_hit_per_1m)
        if input_cache_hit_per_1m is not None
        else input_rate
    )
    output_rate = float(output_per_1m or 0)
    output_tokens = completion + reasoning

    input_cost = (cache_miss / 1_000_000) * input_rate
    cache_cost = (cache_hit / 1_000_000) * cache_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    return input_cost + cache_cost + output_cost


def merge_token_usage_into_stats(stats, token_usage):
    stats = dict(stats or empty_model_stats())
    stats["prompt_tokens"] = int(stats.get("prompt_tokens", 0)) + int(
        token_usage.get("prompt_tokens") or 0
    )
    stats["completion_tokens"] = int(stats.get("completion_tokens", 0)) + int(
        token_usage.get("completion_tokens") or 0
    )
    stats["reasoning_tokens"] = int(stats.get("reasoning_tokens", 0)) + int(
        token_usage.get("reasoning_tokens") or 0
    )
    stats["input_cache_hit_tokens"] = int(stats.get("input_cache_hit_tokens", 0)) + int(
        token_usage.get("input_cache_hit_tokens") or 0
    )
    stats["input_cache_miss_tokens"] = int(stats.get("input_cache_miss_tokens", 0)) + int(
        token_usage.get("input_cache_miss_tokens") or 0
    )
    stats["requests"] = int(stats.get("requests", 0)) + 1
    return stats


def merge_stats(a, b):
    out = empty_model_stats()
    for src in (a, b):
        if not src:
            continue
        out["prompt_tokens"] += int(src.get("prompt_tokens", 0))
        out["completion_tokens"] += int(src.get("completion_tokens", 0))
        out["reasoning_tokens"] += int(src.get("reasoning_tokens", 0))
        out["input_cache_hit_tokens"] += int(src.get("input_cache_hit_tokens", 0))
        out["input_cache_miss_tokens"] += int(src.get("input_cache_miss_tokens", 0))
        out["requests"] += int(src.get("requests", 0))
    return out


def resolve_range(range_key):
    return RANGE_PRESETS.get(range_key, RANGE_PRESETS[DEFAULT_CHART_RANGE])


def week_start(dt):
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def iter_chart_slots(start, end, granularity):
    slots = []
    if granularity == "hour":
        cur = start.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
        while cur <= end:
            slots.append(
                {
                    "key": cur.strftime("%Y-%m-%dT%H"),
                    "start": cur,
                    "end": cur + step - timedelta(microseconds=1),
                }
            )
            cur += step
    elif granularity == "day":
        cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)
        while cur <= end:
            slots.append(
                {
                    "key": cur.strftime("%Y-%m-%d"),
                    "start": cur,
                    "end": cur + step - timedelta(microseconds=1),
                }
            )
            cur += step
    elif granularity == "week":
        cur = week_start(start)
        end_week = week_start(end)
        step = timedelta(weeks=1)
        while cur <= end_week:
            iso = cur.isocalendar()
            slots.append(
                {
                    "key": f"{iso.year}-W{iso.week:02d}",
                    "start": cur,
                    "end": cur + step - timedelta(microseconds=1),
                }
            )
            cur += step
    return slots


def format_slot_label(slot_start, granularity):
    if granularity == "hour":
        return slot_start.strftime("%m/%d %H時")
    if granularity == "day":
        return slot_start.strftime("%m/%d")
    if granularity == "week":
        iso = slot_start.isocalendar()
        return f"W{iso.week}"
    return slot_start.isoformat()


def aggregate_hourly_into_slot(hourly_buckets, slot_start, slot_end):
    total = empty_model_stats()
    if not isinstance(hourly_buckets, dict):
        return total
    for key, stats in hourly_buckets.items():
        try:
            bucket_dt = datetime.strptime(key, "%Y-%m-%dT%H")
        except ValueError:
            continue
        if slot_start <= bucket_dt <= slot_end:
            total = merge_stats(total, stats)
    return total


def _pricing_rates(pricing):
    return {
        "cost_in": float(pricing.get("cost_input_usd_per_1m", 0)),
        "cost_out": float(pricing.get("cost_output_usd_per_1m", 0)),
        "price_in": float(pricing.get("price_input_usd_per_1m", 0)),
        "price_out": float(pricing.get("price_output_usd_per_1m", 0)),
        "cost_cache_hit": float(pricing.get("cost_input_cache_hit_usd_per_1m") or pricing.get("cost_input_usd_per_1m", 0)),
        "price_cache_hit": float(pricing.get("price_input_cache_hit_usd_per_1m") or pricing.get("price_input_usd_per_1m", 0)),
    }


def build_model_row(model_id, pricing, stats):
    prompt = int(stats.get("prompt_tokens", 0))
    completion = int(stats.get("completion_tokens", 0))
    reasoning = int(stats.get("reasoning_tokens", 0))
    cache_hit = int(stats.get("input_cache_hit_tokens", 0))
    cache_miss = int(stats.get("input_cache_miss_tokens", 0))
    if not cache_miss and prompt:
        cache_miss = max(0, prompt - cache_hit)
    total_tokens = prompt + completion + reasoning
    rates = _pricing_rates(pricing)
    cost_usd = compute_usage_cost(
        prompt, completion, reasoning, rates["cost_in"], rates["cost_out"],
        input_cache_hit_per_1m=rates["cost_cache_hit"],
        cache_hit_tokens=cache_hit,
    )
    price_usd = compute_usage_cost(
        prompt, completion, reasoning, rates["price_in"], rates["price_out"],
        input_cache_hit_per_1m=rates["price_cache_hit"],
        cache_hit_tokens=cache_hit,
    )
    from model_registry import get_model_api_id

    return {
        "id": model_id,
        "api_id": get_model_api_id(pricing, model_id),
        "public_id": (pricing.get("public_id") or "").strip(),
        "display_name": pricing.get("display_name") or model_id,
        "provider": pricing.get("provider", "deepseek"),
        "api_model": pricing.get("api_model") or model_id,
        "enabled": bool(pricing.get("enabled", True)),
        "tier": pricing.get("tier") or "",
        "agent_profile": pricing.get("agent_profile") or "deepseek",
        "cost_input_usd_per_1m": rates["cost_in"],
        "cost_output_usd_per_1m": rates["cost_out"],
        "price_input_usd_per_1m": rates["price_in"],
        "price_output_usd_per_1m": rates["price_out"],
        "cost_input_cache_hit_usd_per_1m": rates["cost_cache_hit"],
        "price_input_cache_hit_usd_per_1m": rates["price_cache_hit"],
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "input_cache_hit_tokens": cache_hit,
        "input_cache_miss_tokens": cache_miss,
        "total_tokens": total_tokens,
        "requests": int(stats.get("requests", 0)),
        "cost_usd": round(cost_usd, 4),
        "cost_usd_label": f"${cost_usd:,.4f}",
        "price_usd": round(price_usd, 4),
        "price_usd_label": f"${price_usd:,.4f}",
    }


def build_usage_chart(models_config, series_data, range_key=None, model_filter=None):
    preset = resolve_range(range_key or DEFAULT_CHART_RANGE)
    end = datetime.now()
    start = end - preset["delta"]
    granularity = preset["granularity"]

    slots = iter_chart_slots(start, end, granularity)
    labels = [format_slot_label(s["start"], granularity) for s in slots]

    prompt_series = []
    completion_series = []
    reasoning_series = []
    total_series = []
    cost_series = []
    price_series = []
    request_series = []

    range_totals = empty_model_stats()
    range_cost = 0.0
    range_price = 0.0

    model_ids = []
    if model_filter and model_filter != "all":
        model_ids = [model_filter]
    else:
        model_ids = sorted(set(models_config.keys()) | set(series_data.get("models", {}).keys()))

    for slot in slots:
        slot_stats = empty_model_stats()
        slot_cost = 0.0
        slot_price = 0.0
        for model_id in model_ids:
            pricing = models_config.get(model_id) or normalize_model_entry(
                model_id, DEFAULT_MODELS.get("deepseek-v4-flash", {})
            )
            hourly = (series_data.get("models") or {}).get(model_id) or {}
            bucket_stats = aggregate_hourly_into_slot(
                hourly, slot["start"], slot["end"]
            )
            slot_stats = merge_stats(slot_stats, bucket_stats)
            rates = _pricing_rates(pricing)
            slot_cost += compute_usage_cost(
                bucket_stats["prompt_tokens"],
                bucket_stats["completion_tokens"],
                bucket_stats["reasoning_tokens"],
                rates["cost_in"],
                rates["cost_out"],
                input_cache_hit_per_1m=rates["cost_cache_hit"],
                cache_hit_tokens=bucket_stats.get("input_cache_hit_tokens", 0),
            )
            slot_price += compute_usage_cost(
                bucket_stats["prompt_tokens"],
                bucket_stats["completion_tokens"],
                bucket_stats["reasoning_tokens"],
                rates["price_in"],
                rates["price_out"],
                input_cache_hit_per_1m=rates["price_cache_hit"],
                cache_hit_tokens=bucket_stats.get("input_cache_hit_tokens", 0),
            )

        range_totals = merge_stats(range_totals, slot_stats)
        range_cost += slot_cost
        range_price += slot_price

        prompt_series.append(slot_stats["prompt_tokens"])
        completion_series.append(slot_stats["completion_tokens"])
        reasoning_series.append(slot_stats["reasoning_tokens"])
        total_series.append(
            slot_stats["prompt_tokens"]
            + slot_stats["completion_tokens"]
            + slot_stats["reasoning_tokens"]
        )
        cost_series.append(round(slot_cost, 4))
        price_series.append(round(slot_price, 4))
        request_series.append(slot_stats["requests"])

    granularity_label = {"hour": "時間", "day": "日", "week": "週"}.get(
        granularity, granularity
    )

    return {
        "range": range_key or DEFAULT_CHART_RANGE,
        "range_label": preset["label"],
        "granularity": granularity,
        "granularity_label": granularity_label,
        "model_filter": model_filter or "all",
        "labels": labels,
        "datasets": {
            "prompt_tokens": prompt_series,
            "completion_tokens": completion_series,
            "reasoning_tokens": reasoning_series,
            "total_tokens": total_series,
            "cost_usd": cost_series,
            "price_usd": price_series,
            "requests": request_series,
        },
        "totals": {
            "prompt_tokens": range_totals["prompt_tokens"],
            "completion_tokens": range_totals["completion_tokens"],
            "reasoning_tokens": range_totals["reasoning_tokens"],
            "total_tokens": (
                range_totals["prompt_tokens"]
                + range_totals["completion_tokens"]
                + range_totals["reasoning_tokens"]
            ),
            "requests": range_totals["requests"],
            "cost_usd": round(range_cost, 4),
            "cost_usd_label": f"${range_cost:,.4f}",
            "price_usd": round(range_price, 4),
            "price_usd_label": f"${range_price:,.4f}",
        },
        "updated_at": end.strftime("%Y-%m-%d %H:%M:%S"),
    }


def serialize_models_admin(
    models_config,
    model_usage,
    active_model_id=None,
    chart_range=None,
    providers_config=None,
    default_model_id=None,
):
    period = model_usage.get("period", current_usage_period())
    stats_map = model_usage.get("models") or {}
    series_data = load_usage_series()
    model_ids = list(models_config.keys())
    if active_model_id and active_model_id not in model_ids:
        model_ids.append(active_model_id)

    rows = []
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "cost_usd": 0.0,
        "price_usd": 0.0,
    }

    for model_id in sorted(model_ids):
        pricing = models_config.get(model_id)
        if not pricing:
            pricing = normalize_model_entry(model_id, {})
        stats = stats_map.get(model_id) or empty_model_stats()
        row = build_model_row(model_id, pricing, stats)
        rows.append(row)
        totals["prompt_tokens"] += row["prompt_tokens"]
        totals["completion_tokens"] += row["completion_tokens"]
        totals["reasoning_tokens"] += row["reasoning_tokens"]
        totals["total_tokens"] += row["total_tokens"]
        totals["requests"] += row["requests"]
        totals["cost_usd"] += row["cost_usd"]
        totals["price_usd"] += row["price_usd"]

    totals["cost_usd"] = round(totals["cost_usd"], 4)
    totals["cost_usd_label"] = f"${totals['cost_usd']:,.4f}"
    totals["price_usd"] = round(totals["price_usd"], 4)
    totals["price_usd_label"] = f"${totals['price_usd']:,.4f}"

    from model_registry import AGENT_PROFILE_OPTIONS, provider_labels, serialize_provider_admin

    chart = build_usage_chart(
        models_config,
        series_data,
        range_key=chart_range or DEFAULT_CHART_RANGE,
        model_filter="all",
    )

    active_display = ""
    if active_model_id:
        cfg = models_config.get(active_model_id) or {}
        active_display = (cfg.get("display_name") or "").strip() or active_model_id

    return {
        "period": period,
        "period_label": f"{period[:4]}年{period[5:]}月",
        "active_model": active_display,
        "default_model": default_model_id or "",
        "providers": serialize_provider_admin(providers_config),
        "provider_options": provider_labels(),
        "agent_profile_options": list(AGENT_PROFILE_OPTIONS),
        "models": rows,
        "totals": totals,
        "chart": chart,
        "chart_defaults": {
            "range": DEFAULT_CHART_RANGE,
            "refresh_seconds": 10,
        },
    }


def record_model_usage_in_config(config, model_id, token_usage):
    if not model_id or not token_usage:
        return config
    model_usage = normalize_model_usage(config.get("model_usage"))
    models = model_usage.setdefault("models", {})
    current = models.get(model_id) or empty_model_stats()
    models[model_id] = merge_token_usage_into_stats(current, token_usage)
    config["model_usage"] = model_usage
    record_usage_series(model_id, token_usage)
    return config
