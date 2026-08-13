from contextvars import ContextVar

_COST_PERFORMANCE_ACTIVE = ContextVar("cost_performance_maximized", default=False)

COST_PERFORMANCE_THINKING_BUDGET = 1024
COST_PERFORMANCE_MAX_OUTPUT_TOKENS = 2048

COST_PERFORMANCE_SYSTEM_APPEND = (
    "\n\n【コストパフォーマンス最大化】\n"
    "推論と出力のトークンを極力抑えつつ、事実の正確性とユーザーの要求への適合は維持する。\n"
    "- 内部推論は必要最小限。冗長な思考・迷いの言い換えを避ける\n"
    "- 回答は要点のみ。前置き・お世辞・同内容の繰り返し・過剰な見出しや箇条書きを省く\n"
    "- ユーザーが詳細を求めた場合のみ十分に書く\n"
)


def cost_performance_system_prompt_append():
    return COST_PERFORMANCE_SYSTEM_APPEND


def cost_performance_token(enabled):
    return _COST_PERFORMANCE_ACTIVE.set(bool(enabled))


def reset_cost_performance_token(token):
    _COST_PERFORMANCE_ACTIVE.reset(token)


def is_cost_performance_active():
    return bool(_COST_PERFORMANCE_ACTIVE.get())


def apply_cost_performance_kwargs(kwargs, disable_reasoning=False, provider_id=None):
    if not is_cost_performance_active():
        return kwargs
    if disable_reasoning:
        kwargs["max_tokens"] = COST_PERFORMANCE_MAX_OUTPUT_TOKENS
        return kwargs
    from model_registry import provider_supports_thinking

    if provider_supports_thinking(provider_id):
        extra = dict(kwargs.get("extra_body") or {})
        extra["thinking"] = {
            "type": "enabled",
            "budget_tokens": COST_PERFORMANCE_THINKING_BUDGET,
        }
        kwargs["extra_body"] = extra
    kwargs["max_tokens"] = COST_PERFORMANCE_MAX_OUTPUT_TOKENS
    return kwargs
