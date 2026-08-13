from __future__ import annotations

import json

from api_identity import prepare_v1_provider_messages
from chat_agent import complete_model_round, stream_model_round
from openai_compat import (
    api_tool_calls_list,
    build_chat_completion,
    sse_chat_chunk,
    sse_chat_done,
    sse_tool_call_chunk,
)
from token_usage import empty_usage, merge_usage


def v1_disable_reasoning(*, tools, provider_id, thinking=None, reasoning_effort=None):
    """API リクエストで推論を無効化するか判定。

    - tools あり: 推論無効（ツールと併用不可のため）
    - thinking=false: 推論無効（最速）
    - reasoning_effort=off/none/minimal: 推論無効
    - それ以外はプロバイダー能力に依存
    """
    if tools:
        return True
    if thinking is False:
        return True
    if reasoning_effort in ("off", "none", "minimal"):
        return True
    from model_registry import provider_supports_thinking

    return not provider_supports_thinking(provider_id)


def _provider_messages(parsed):
    return prepare_v1_provider_messages(parsed.get("messages") or [])


def run_v1_chat_sync(*, client, api_model, parsed, provider_id):
    tools = parsed.get("tools")
    tool_choice = parsed.get("tool_choice")
    sampling = parsed.get("sampling") or {}
    disable_reasoning = v1_disable_reasoning(
        tools=tools,
        provider_id=provider_id,
        thinking=sampling.get("thinking"),
        reasoning_effort=sampling.get("reasoning_effort"),
    )
    round_data = complete_model_round(
        client,
        api_model,
        _provider_messages(parsed),
        tools=tools,
        tool_choice=tool_choice,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        sampling=sampling,
    )
    tool_calls = api_tool_calls_list(round_data.get("tool_calls_map") or {})
    content = round_data.get("content") or ""
    finish_reason = "tool_calls" if tool_calls else "stop"
    return build_chat_completion(
        parsed.get("response_model") or api_model,
        content,
        usage=round_data.get("usage"),
        tool_calls=tool_calls or None,
        finish_reason=finish_reason,
    )


def iter_v1_chat_stream(*, client, api_model, parsed, provider_id):
    from openai_compat import completion_id as new_completion_id

    tools = parsed.get("tools")
    tool_choice = parsed.get("tool_choice")
    sampling = parsed.get("sampling") or {}
    disable_reasoning = v1_disable_reasoning(
        tools=tools,
        provider_id=provider_id,
        thinking=sampling.get("thinking"),
        reasoning_effort=sampling.get("reasoning_effort"),
    )
    response_model = parsed.get("response_model") or api_model
    completion_id_value = new_completion_id()
    turn_usage = empty_usage()
    round_data = None

    for kind, payload in stream_model_round(
        client,
        api_model,
        _provider_messages(parsed),
        tools=tools,
        tool_choice=tool_choice,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        sampling=sampling,
    ):
        if kind == "content" and payload:
            yield sse_chat_chunk(
                response_model,
                content_delta=payload,
                completion_id_value=completion_id_value,
            )
        elif kind == "tool_call_delta" and payload:
            yield sse_tool_call_chunk(
                response_model,
                tool_call_delta=payload,
                completion_id_value=completion_id_value,
            )
        elif kind == "end":
            round_data = payload
            merge_usage(turn_usage, (payload or {}).get("usage") or {})

    tool_calls = api_tool_calls_list((round_data or {}).get("tool_calls_map") or {})
    finish_reason = "tool_calls" if tool_calls else "stop"
    yield sse_chat_chunk(
        response_model,
        finish_reason=finish_reason,
        completion_id_value=completion_id_value,
        usage=turn_usage if int(turn_usage.get("total_tokens") or 0) else None,
    )
    yield sse_chat_done()


def format_v1_provider_error(exc, *, provider_id):
    text = str(exc).strip().lower()
    if not text:
        return "The model failed to complete the request. Please retry."
    if "invalid api key" in text or "authentication" in text or "401" in text or "403" in text:
        return "Service configuration error."
    if "rate limit" in text or "429" in text or "too many requests" in text:
        return "Rate limit exceeded. Please retry later."
    if (
        "context length" in text
        or "maximum context" in text
        or "too many tokens" in text
        or "token limit" in text
        or "prompt is too long" in text
    ):
        return "Request context is too long."
    return "The model failed to complete the request. Please retry."
