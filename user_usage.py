"""Per-user monthly usage accounting from model provided (price) rates."""

from __future__ import annotations

from model_usage import compute_usage_cost, current_usage_period

AI_BUDGET_RATIO = 0.60
TOOL_BUDGET_RATIO = 0.40
WARNING_PERCENT = 80
HARD_BLOCK_PERCENT = 100


def empty_user_usage():
    return {
        "period": current_usage_period(),
        "usage_cost_usd": 0.0,
        "tool_usage_cost_usd": 0.0,
        "on_demand_cost_usd": 0.0,
    }


def normalize_user_usage(raw):
    period = current_usage_period()
    if not isinstance(raw, dict):
        return empty_user_usage()
    if raw.get("period") != period:
        return empty_user_usage()
    return {
        "period": period,
        "usage_cost_usd": round(float(raw.get("usage_cost_usd") or 0), 6),
        "tool_usage_cost_usd": round(float(raw.get("tool_usage_cost_usd") or 0), 6),
        "on_demand_cost_usd": round(float(raw.get("on_demand_cost_usd") or 0), 6),
    }


def compute_turn_price_usd(token_usage, model_entry):
    if not token_usage or not model_entry:
        return 0.0
    return compute_usage_cost(
        token_usage.get("prompt_tokens"),
        token_usage.get("completion_tokens"),
        token_usage.get("reasoning_tokens"),
        model_entry.get("price_input_usd_per_1m", 0),
        model_entry.get("price_output_usd_per_1m", 0),
        input_cache_hit_per_1m=model_entry.get("price_input_cache_hit_usd_per_1m"),
        cache_hit_tokens=token_usage.get("input_cache_hit_tokens", 0),
    )


def plan_ai_budget_usd(price_usd):
    if price_usd is None:
        return None
    try:
        price = float(price_usd)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return 0.0
    return round(price * AI_BUDGET_RATIO, 4)


def plan_tool_budget_usd(price_usd):
    if price_usd is None:
        return None
    try:
        price = float(price_usd)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return 0.0
    return round(price * TOOL_BUDGET_RATIO, 4)


def usage_percent(usage_cost_usd, budget_usd):
    if budget_usd is None:
        return 0.0
    if not budget_usd or budget_usd <= 0:
        return 0.0
    return round(float(usage_cost_usd or 0) / float(budget_usd) * 100, 1)


def usage_status(percent):
    if percent >= HARD_BLOCK_PERCENT:
        return "blocked"
    if percent >= WARNING_PERCENT:
        return "warning"
    return "normal"


def usage_display_label(percent, budget_usd=None, lang="ja"):
    if budget_usd is None:
        if lang == "en":
            return "Unlimited"
        if lang == "ko":
            return "무제한"
        return "無制限"
    if percent >= HARD_BLOCK_PERCENT:
        if lang == "en":
            return "Limit reached"
        if lang == "ko":
            return "한도 도달"
        return "利用上限に達しました"
    if percent >= WARNING_PERCENT:
        if lang == "en":
            return "Running low"
        if lang == "ko":
            return "잔여 적음"
        return "残りわずか"
    if lang == "en":
        return "Normal"
    if lang == "ko":
        return "보통"
    return "通常利用"


def usage_warning_message(percent, lang="ja"):
    if percent < WARNING_PERCENT or percent >= HARD_BLOCK_PERCENT:
        return None
    if lang == "en":
        return "You are approaching this month's AI usage budget. Consider upgrading your plan."
    if lang == "ko":
        return "이번 달 AI 이용 예산이 거의 소진되었습니다. 플랜 업그레이드를 검토해 주세요."
    return "今月のAI利用枠が残りわずかです。プラン/課金ページでアップグレードをご検討ください。"


def usage_block_message(lang="ja"):
    if lang == "en":
        return "You have reached this month's usage limit. Please check Plans / Billing."
    if lang == "ko":
        return "이번 달 이용 한도에 도달했습니다. 플랜/결제 페이지를 확인해 주세요."
    return "今月の利用枠の上限に達しました。プラン/課金ページをご確認ください。"


def on_demand_balance_block_message(lang="ja"):
    if lang == "en":
        return "Your prepaid balance is insufficient. Top up on Plans / Billing."
    if lang == "ko":
        return "선불 잔액이 부족합니다. 플랜/결제 페이지에서 충전해 주세요."
    return "残高が不足しています。プラン/課金ページからチャージしてください。"


def split_turn_billing_usd(turn_cost_usd, current_usage_usd, budget_usd):
    turn_cost = max(0.0, float(turn_cost_usd or 0))
    if budget_usd is None:
        return turn_cost, 0.0
    budget = float(budget_usd or 0)
    current = max(0.0, float(current_usage_usd or 0))
    plan_remaining = max(0.0, budget - current)
    plan_portion = min(turn_cost, plan_remaining)
    on_demand_portion = round(turn_cost - plan_portion, 6)
    return round(plan_portion, 6), on_demand_portion
