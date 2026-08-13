"""Plan entitlements (stackable usage pools) and per-request billing event logs."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from token_usage import empty_usage
from user_usage import usage_percent, usage_status
from usage_accounting import (
    entitlement_available_usd,
    entitlement_pool_used_usd,
    get_entitlement_usage_map,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
BILLING_EVENTS_FILE = DATA_DIR / "billing_events.json"
_billing_lock = threading.Lock()

BILLING_EVENT_STATUSES = frozenset(
    {"running", "completed", "cancelled", "failed", "blocked"}
)
BILLING_PAYMENT_TYPES = frozenset({"subscription", "metered", "included"})


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(
            microsecond=0, tzinfo=None
        )
    except ValueError:
        return None


def _format_dt(dt):
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.replace(microsecond=0).isoformat(timespec="minutes")


def _load_billing_events_store():
    if not BILLING_EVENTS_FILE.exists():
        return {"events": []}
    try:
        with open(BILLING_EVENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"events": []}
    if not isinstance(data, dict):
        return {"events": []}
    events = data.get("events")
    return {"events": events if isinstance(events, list) else []}


def _save_billing_events_store(store):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BILLING_EVENTS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    tmp.replace(BILLING_EVENTS_FILE)


def normalize_entitlement(raw, plan_budget_fn):
    if not isinstance(raw, dict):
        return None
    plan_id = (raw.get("plan_id") or "free").strip().lower()
    try:
        quantity = max(1, int(raw.get("quantity") or 1))
    except (TypeError, ValueError):
        quantity = 1
    ent_id = (raw.get("id") or "").strip() or str(uuid.uuid4())
    starts_at = _format_dt(_parse_dt(raw.get("starts_at")) or datetime.now())
    expires_at = _format_dt(_parse_dt(raw.get("expires_at")))
    source = (raw.get("source") or "admin").strip()[:32] or "admin"
    budget_each = plan_budget_fn(plan_id)
    if budget_each is None:
        line_budget = None
    else:
        line_budget = round(float(budget_each) * quantity, 6)
    return {
        "id": ent_id,
        "plan_id": plan_id,
        "quantity": quantity,
        "starts_at": starts_at,
        "expires_at": expires_at,
        "source": source,
        "budget_usd": line_budget,
    }


def normalize_entitlements(raw_list, plan_budget_fn):
    if not isinstance(raw_list, list):
        return []
    out = []
    for item in raw_list:
        ent = normalize_entitlement(item, plan_budget_fn)
        if ent:
            out.append(ent)
    return out


def entitlement_is_active(ent, now=None):
    now = now or datetime.now()
    starts = _parse_dt(ent.get("starts_at"))
    if starts and starts > now:
        return False
    expires = _parse_dt(ent.get("expires_at"))
    if expires and expires <= now:
        return False
    return True


def active_entitlements(record, now=None, plan_budget_fn=None):
    now = now or datetime.now()
    plan_budget_fn = plan_budget_fn or (lambda _p: 0.0)
    ents = normalize_entitlements(record.get("entitlements"), plan_budget_fn)
    return [e for e in ents if entitlement_is_active(e, now)]


def sum_entitlement_budget_usd(ents):
    if not ents:
        return 0.0
    if any(e.get("budget_usd") is None for e in ents):
        return None
    return round(sum(float(e.get("budget_usd") or 0) for e in ents), 6)


def usage_pool_id_for_record(record, active_ents):
    if active_ents:
        expires_list = [
            _parse_dt(e.get("expires_at")) for e in active_ents if e.get("expires_at")
        ]
        expires_list = [e for e in expires_list if e]
        if expires_list:
            latest = max(expires_list)
            ent_ids = sorted(e.get("id", "") for e in active_ents)
            return f"ent:{latest.date().isoformat()}:{':'.join(ent_ids[:8])}"
        return "ent:ongoing:" + ":".join(sorted(e.get("id", "")[:8] for e in active_ents))
    override = record.get("usage_quota_override_usd")
    if override is not None:
        return f"override:{current_usage_period()}"
    return current_usage_period()


def current_usage_period():
    return datetime.now().strftime("%Y-%m")


def normalize_user_usage_for_pool(record, pool_id, plan_budget_fn, active_ents=None):
    raw = record.get("usage")
    if not isinstance(raw, dict):
        raw = {}
    period_key = (raw.get("period") or "").strip()
    reset = period_key != pool_id
    ent_usage = {} if reset else get_entitlement_usage_map(raw)
    active_ents = active_ents or []
    if active_ents:
        cost = entitlement_pool_used_usd({"entitlement_usage": ent_usage}, active_ents)
    else:
        cost = 0.0 if reset else round(float(raw.get("usage_cost_usd") or 0), 6)
    reserved = 0.0 if reset else round(float(raw.get("reserved_usd") or 0), 6)
    tool_cost = 0.0 if reset else round(float(raw.get("tool_usage_cost_usd") or 0), 6)
    on_demand = 0.0 if reset else round(float(raw.get("on_demand_cost_usd") or 0), 6)
    return {
        "period": pool_id,
        "usage_cost_usd": round(cost, 6),
        "entitlement_usage": ent_usage,
        "reserved_usd": reserved,
        "tool_usage_cost_usd": tool_cost,
        "on_demand_cost_usd": on_demand,
    }


def effective_usage_budget(record, plan_budget_fn, normalize_plan_fn):
    override = record.get("usage_quota_override_usd")
    if override is not None:
        try:
            val = float(override)
            return round(val, 6) if val >= 0 else 0.0
        except (TypeError, ValueError):
            pass
    ents = active_entitlements(record, plan_budget_fn=plan_budget_fn)
    if ents:
        return sum_entitlement_budget_usd(ents)
    return 0.0


def sync_record_plan_state(record, plan_budget_fn, normalize_plan_fn, plan_tier_rank_fn=None):
    ents = normalize_entitlements(record.get("entitlements"), plan_budget_fn)
    active = [e for e in ents if entitlement_is_active(e)]
    record["entitlements"] = ents
    record["plan"] = highest_plan_from_entitlements(
        ents,
        normalize_plan_fn,
        plan_tier_rank_fn=plan_tier_rank_fn,
    )
    if active:
        exp_list = [_parse_dt(e.get("expires_at")) for e in active if e.get("expires_at")]
        exp_list = [e for e in exp_list if e]
        record["plan_expires_at"] = _format_dt(max(exp_list)) if exp_list else ""
    elif (record.get("paypal_subscription_status") or "").upper() != "ACTIVE":
        record["plan_expires_at"] = ""


def usage_pool_summary(record, plan_budget_fn, normalize_plan_fn, plan_tier_rank_fn=None):
    sync_record_plan_state(
        record,
        plan_budget_fn,
        normalize_plan_fn,
        plan_tier_rank_fn=plan_tier_rank_fn,
    )
    ents = active_entitlements(record, plan_budget_fn=plan_budget_fn)
    pool_id = usage_pool_id_for_record(record, ents)
    budget = effective_usage_budget(record, plan_budget_fn, normalize_plan_fn)
    usage = normalize_user_usage_for_pool(record, pool_id, plan_budget_fn, active_ents=ents)
    cost = float(usage.get("usage_cost_usd") or 0)
    percent = usage_percent(cost, budget)
    expires_at = ""
    if ents:
        exp_list = [_parse_dt(e.get("expires_at")) for e in ents if e.get("expires_at")]
        exp_list = [e for e in exp_list if e]
        if exp_list:
            expires_at = _format_dt(max(exp_list))
    available = entitlement_available_usd(usage, ents, budget)
    return {
        "pool_id": pool_id,
        "usage": usage,
        "ai_budget_usd": budget,
        "ai_available_usd": available,
        "usage_percent": percent,
        "usage_status": usage_status(percent),
        "usage_unlimited": budget is None,
        "active_entitlements": ents,
        "pool_expires_at": expires_at,
    }


def add_plan_entitlement(
    record,
    plan_id,
    *,
    months=1,
    hours=None,
    quantity=1,
    source="balance",
    plan_budget_fn=None,
    normalize_plan_fn=None,
    add_one_month_fn=None,
    plan_tier_rank_fn=None,
):
    plan_budget_fn = plan_budget_fn or (lambda _p: 0.0)
    normalize_plan_fn = normalize_plan_fn or (lambda p: (p or "free").strip().lower())
    plan_id = normalize_plan_fn(plan_id)
    try:
        quantity = max(1, int(quantity))
    except (TypeError, ValueError):
        quantity = 1
    try:
        months = max(1, int(months))
    except (TypeError, ValueError):
        months = 1

    now = datetime.now().replace(microsecond=0)
    ents = normalize_entitlements(record.get("entitlements"), plan_budget_fn)

    base_expires = now
    for ent in ents:
        if ent.get("plan_id") == plan_id and entitlement_is_active(ent, now):
            exp = _parse_dt(ent.get("expires_at"))
            if exp and exp > base_expires:
                base_expires = exp

    if hours is not None:
        try:
            hours = max(1, int(hours))
        except (TypeError, ValueError):
            hours = 1
        from datetime import timedelta

        expires_at = _format_dt(base_expires + timedelta(hours=hours))
    elif add_one_month_fn:
        cursor = base_expires
        for _ in range(months):
            cursor = add_one_month_fn(cursor)
        expires_at = _format_dt(cursor)
    else:
        from datetime import timedelta

        expires_at = _format_dt(now + timedelta(days=30 * months))

    new_ent = normalize_entitlement(
        {
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "quantity": quantity,
            "starts_at": _format_dt(now),
            "expires_at": expires_at,
            "source": source,
        },
        plan_budget_fn,
    )
    ents.append(new_ent)
    record["entitlements"] = ents
    record["plan"] = highest_plan_from_entitlements(
        ents,
        normalize_plan_fn,
        plan_tier_rank_fn=plan_tier_rank_fn,
    )
    record["plan_expires_at"] = expires_at
    return new_ent


def highest_plan_from_entitlements(ents, normalize_plan_fn, plan_tier_rank_fn=None):
    active = [e for e in ents if entitlement_is_active(e)]
    if not active:
        return "free"
    if plan_tier_rank_fn:
        return max(
            (normalize_plan_fn(e.get("plan_id")) for e in active),
            key=lambda p: plan_tier_rank_fn(p),
        )
    return normalize_plan_fn(active[-1].get("plan_id"))


def ensure_legacy_entitlements(record, plan_budget_fn, normalize_plan_fn):
    if record.get("entitlements"):
        return
    plan = normalize_plan_fn(record.get("plan"))
    if plan == "free":
        return
    now = datetime.now()
    expires = _parse_dt(record.get("plan_expires_at"))
    if not expires and not record.get("paypal_subscription_id"):
        return
    ent = normalize_entitlement(
        {
            "id": str(uuid.uuid4()),
            "plan_id": plan,
            "quantity": 1,
            "starts_at": _format_dt(now),
            "expires_at": _format_dt(expires) if expires else "",
            "source": "legacy",
        },
        plan_budget_fn,
    )
    record["entitlements"] = [ent]


def create_billing_event(
    username,
    *,
    session_id="",
    model_id="",
    payment_type="subscription",
    status="running",
):
    now = _format_dt(datetime.now())
    event = {
        "id": str(uuid.uuid4()),
        "user": (username or "").strip().lower(),
        "session_id": (session_id or "").strip()[:128],
        "status": status if status in BILLING_EVENT_STATUSES else "running",
        "payment_type": payment_type
        if payment_type in BILLING_PAYMENT_TYPES
        else "subscription",
        "created_at": now,
        "updated_at": now,
        "model_id": (model_id or "").strip()[:128],
        "tool_call_count": 0,
        "cost_usd": 0.0,
        "token_usage": empty_usage(),
    }
    with _billing_lock:
        store = _load_billing_events_store()
        store["events"].append(event)
        if len(store["events"]) > 50000:
            store["events"] = store["events"][-40000:]
        _save_billing_events_store(store)
    return event


def update_billing_event(event_id, **fields):
    event_id = (event_id or "").strip()
    if not event_id:
        return None
    with _billing_lock:
        store = _load_billing_events_store()
        for event in store["events"]:
            if event.get("id") != event_id:
                continue
            for key, value in fields.items():
                if key == "status" and value not in BILLING_EVENT_STATUSES:
                    continue
                if key == "payment_type" and value not in BILLING_PAYMENT_TYPES:
                    continue
                event[key] = value
            event["updated_at"] = _format_dt(datetime.now())
            _save_billing_events_store(store)
            return dict(event)
    return None


def list_billing_events_for_user(username, *, limit=100, offset=0):
    username = (username or "").strip().lower()
    with _billing_lock:
        store = _load_billing_events_store()
        rows = [
            e
            for e in store.get("events", [])
            if (e.get("user") or "").strip().lower() == username
        ]
    rows.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    total = len(rows)
    start = max(0, int(offset))
    end = start + max(1, min(500, int(limit)))
    return rows[start:end], total


def billing_plan_label(plan_key, lang="ja"):
    key = (plan_key or "").strip()
    if not key:
        return "—"
    if key == "on-demand":
        if lang == "en":
            return "on-demand"
        if lang == "ko":
            return "on-demand"
        return "on-demand"
    return key


def serialize_billing_event(event, lang="ja"):
    status = event.get("status") or "completed"
    payment_type = event.get("payment_type") or "subscription"
    request_id = event.get("id") or ""
    billing_plan = (event.get("billing_plan") or "").strip()
    return {
        "id": request_id,
        "request_id": request_id,
        "session_id": event.get("session_id") or "",
        "status": status,
        "status_label": billing_status_label(status, lang),
        "payment_type": payment_type,
        "payment_type_label": billing_payment_type_label(payment_type, lang),
        "billing_plan": billing_plan,
        "billing_plan_label": billing_plan_label(billing_plan, lang),
        "created_at": event.get("created_at") or "",
        "updated_at": event.get("updated_at") or "",
        "model_id": event.get("model_id") or "",
        "tool_call_count": int(event.get("tool_call_count") or 0),
        "cost_usd": round(float(event.get("cost_usd") or 0), 6),
        "token_usage": event.get("token_usage") or {},
    }


def billing_status_label(status, lang="ja"):
    labels = {
        "running": ("生成中", "In progress", "생성 중"),
        "completed": ("完了", "Completed", "완료"),
        "cancelled": ("キャンセル", "Cancelled", "취소"),
        "failed": ("失敗", "Failed", "실패"),
        "blocked": ("上限到達", "Blocked", "한도 도달"),
    }
    row = labels.get(status, labels["completed"])
    if lang == "en":
        return row[1]
    if lang == "ko":
        return row[2]
    return row[0]


def billing_payment_type_label(payment_type, lang="ja"):
    labels = {
        "subscription": ("サブスク枠", "Subscription pool", "구독 할당"),
        "metered": ("従量課金", "Pay as you go", "종량제"),
        "included": ("込み", "Included", "포함"),
    }
    row = labels.get(payment_type, labels["subscription"])
    if lang == "en":
        return row[1]
    if lang == "ko":
        return row[2]
    return row[0]


def billing_model_note(lang="ja"):
    if lang == "en":
        return (
            "Each chat request is assigned a request ID (click to copy). Usage cost is "
            "estimated from model list prices (input/output per 1M tokens) and counts "
            "toward your active plan entitlement pool. Stacked plans add their AI budgets "
            "for the entitlement period."
        )
    if lang == "ko":
        return (
            "각 채팅 요청에는 리クエ스트 ID가 부여됩니다(ID를 클릭하면 복사). 이용 비용은 "
            "모델 표시 단가(100만 토큰당)로 추정되며, 유효한 플랜 할당 풀에서 차감됩니다. "
            "플랜은 기간 중 예산을 합산합니다."
        )
    return (
        "チャットの各リクエストにはリクエストIDが付与されます（クリックでコピー）。"
        "コストはモデルの提供単価（100万トークンあたりの入出力）に基づく見積もりです。"
        "プラン枠から消費される場合はプラン名、残高から差し引かれる場合は on-demand と表示されます。"
        "オンデマンド課金は設定のアカウント → API で有効化できます。"
    )
