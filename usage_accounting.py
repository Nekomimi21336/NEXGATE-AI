"""Entitlement-ordered usage allocation and request reservations."""

from __future__ import annotations

import threading
from datetime import datetime

_users_billing_lock = threading.RLock()
_pending_reserves = {}

DEFAULT_RESERVE_USD = 0.05
MIN_ON_DEMAND_START_JPY = 10


def billing_lock():
    return _users_billing_lock


def estimate_chat_reserve_usd(model_entry=None):
    if not model_entry:
        return DEFAULT_RESERVE_USD
    try:
        out_price = float(model_entry.get("price_output_usd_per_1m") or 0)
        if out_price > 0:
            return max(DEFAULT_RESERVE_USD, min(0.5, out_price / 1_000_000 * 800))
    except (TypeError, ValueError):
        pass
    return DEFAULT_RESERVE_USD


def entitlements_consumption_order(ents):
    def sort_key(ent):
        from billing_entitlements import _parse_dt

        exp = _parse_dt(ent.get("expires_at"))
        if not exp:
            return (1, datetime.max, ent.get("id") or "")
        return (0, exp, ent.get("id") or "")

    return sorted(ents or [], key=sort_key)


def get_entitlement_usage_map(usage):
    raw = (usage or {}).get("entitlement_usage")
    if not isinstance(raw, dict):
        return {}
    return {str(k): round(float(v or 0), 6) for k, v in raw.items()}


def entitlement_pool_used_usd(usage, active_ents):
    ent_usage = get_entitlement_usage_map(usage)
    total = 0.0
    for ent in active_ents or []:
        total += float(ent_usage.get(ent.get("id") or "", 0) or 0)
    return round(total, 6)


def entitlement_available_usd(usage, active_ents, total_budget):
    if total_budget is None:
        return None
    budget = float(total_budget or 0)
    used = entitlement_pool_used_usd(usage, active_ents)
    reserved = float((usage or {}).get("reserved_usd") or 0)
    return round(max(0.0, budget - used - reserved), 6)


def allocate_usd_across_entitlements(amount_usd, usage, active_ents):
    remaining = max(0.0, float(amount_usd or 0))
    ent_usage = get_entitlement_usage_map(usage)
    plan_portion = 0.0
    for ent in entitlements_consumption_order(active_ents):
        if remaining <= 1e-9:
            break
        eid = str(ent.get("id") or "")
        if not eid:
            continue
        cap = float(ent.get("budget_usd") or 0)
        used = float(ent_usage.get(eid, 0) or 0)
        room = max(0.0, cap - used)
        take = min(remaining, room)
        if take > 0:
            ent_usage[eid] = round(used + take, 6)
            plan_portion += take
            remaining -= take
    return round(plan_portion, 6), round(remaining, 6), ent_usage


def try_reserve_usage(username, request_id, amount_usd, record, active_ents, total_budget):
    request_id = (request_id or "").strip()
    if not request_id:
        return False, "invalid request"
    amount = max(0.0, float(amount_usd or DEFAULT_RESERVE_USD))
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    if total_budget is None:
        _pending_reserves[request_id] = 0.0
        return True, None
    available = entitlement_available_usd(usage, active_ents, total_budget)
    if available is not None and available > 1e-9:
        reserve_amount = min(amount, available)
        usage["reserved_usd"] = round(
            float(usage.get("reserved_usd") or 0) + reserve_amount, 6
        )
        record["usage"] = usage
        _pending_reserves[request_id] = reserve_amount
        return True, None
    return False, None


def release_usage_reserve(record, request_id):
    request_id = (request_id or "").strip()
    amount = _pending_reserves.pop(request_id, None)
    if amount is None:
        return
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    usage["reserved_usd"] = round(max(0.0, float(usage.get("reserved_usd") or 0) - float(amount)), 6)
    record["usage"] = usage


def commit_usage_reserve(record, request_id):
    request_id = (request_id or "").strip()
    amount = _pending_reserves.pop(request_id, None)
    if amount is None:
        return
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    usage["reserved_usd"] = round(max(0.0, float(usage.get("reserved_usd") or 0) - float(amount)), 6)
    record["usage"] = usage
