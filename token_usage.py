"""Token counting and OpenAI usage normalization."""

from __future__ import annotations

import json

try:
    import tiktoken
except ImportError:
    tiktoken = None

_ENCODING_CACHE = {}


def empty_usage():
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        # キャッシュ概念: input をキャッシュヒット/ミスに分割
        "input_cache_hit_tokens": 0,
        "input_cache_miss_tokens": 0,
    }


def merge_usage(target, part):
    if not part or part is target:
        return target
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_tokens",
        "input_cache_hit_tokens",
        "input_cache_miss_tokens",
    ):
        target[key] = int(target.get(key, 0)) + int(part.get(key, 0))
    if not target.get("total_tokens"):
        target["total_tokens"] = (
            target["prompt_tokens"]
            + target["completion_tokens"]
            + target["reasoning_tokens"]
        )
    return target


def usage_from_openai(usage):
    if not usage:
        return empty_usage()
    if hasattr(usage, "model_dump"):
        raw = usage.model_dump()
    elif isinstance(usage, dict):
        raw = usage
    else:
        raw = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }
        details = getattr(usage, "completion_tokens_details", None)
        if details is not None:
            raw["completion_tokens_details"] = (
                details.model_dump()
                if hasattr(details, "model_dump")
                else details
            )
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        if prompt_details is not None:
            raw["prompt_tokens_details"] = (
                prompt_details.model_dump()
                if hasattr(prompt_details, "model_dump")
                else prompt_details
            )

    prompt = int(raw.get("prompt_tokens") or 0)
    completion = int(raw.get("completion_tokens") or 0)
    total = int(raw.get("total_tokens") or 0)
    reasoning = 0
    details = raw.get("completion_tokens_details") or {}
    if isinstance(details, dict):
        reasoning = int(details.get("reasoning_tokens") or 0)

    # キャッシュヒット/ミストークン（OpenAI形式: prompt_tokens_details.cached_tokens）
    cache_hit = 0
    prompt_details = raw.get("prompt_tokens_details") or {}
    if isinstance(prompt_details, dict):
        cache_hit = int(prompt_details.get("cached_tokens") or 0)
    # DeepSeek等: トップレベルに prompt_cache_hit_tokens / prompt_cache_miss_tokens
    if not cache_hit:
        cache_hit = int(raw.get("prompt_cache_hit_tokens") or 0)
    cache_miss = int(raw.get("prompt_cache_miss_tokens") or 0)
    if not cache_miss and prompt:
        cache_miss = max(0, prompt - cache_hit)

    if not total:
        total = prompt + completion + reasoning

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "total_tokens": total,
        "input_cache_hit_tokens": cache_hit,
        "input_cache_miss_tokens": cache_miss,
    }


def _encoding_for_model(model):
    if not tiktoken:
        return None
    name = (model or "").strip()
    if name in _ENCODING_CACHE:
        return _ENCODING_CACHE[name]
    try:
        enc = tiktoken.encoding_for_model(name)
    except (KeyError, ValueError):
        try:
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = None
    _ENCODING_CACHE[name] = enc
    return enc


def _message_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append(part.get("text") or "")
            elif part.get("type") == "image_url":
                parts.append("[image]")
            elif part.get("type") == "pdf_url":
                parts.append("[pdf]")
        return "\n".join(parts)
    return str(content)


def _count_text_tokens(text, model):
    text = text or ""
    if not text:
        return 0
    enc = _encoding_for_model(model)
    if enc:
        return len(enc.encode(text))
    return max(len(text) // 3, 1 if text else 0)


def count_messages_tokens(messages, model=None):
    """Estimate input tokens for a chat messages list (OpenAI-style overhead)."""
    total = 0
    per_message = 4
    for msg in messages or []:
        role = msg.get("role") or "user"
        content = _message_text(msg.get("content"))
        extra = ""
        if msg.get("tool_calls"):
            try:
                extra += json.dumps(msg["tool_calls"], ensure_ascii=False)
            except (TypeError, ValueError):
                extra += str(msg.get("tool_calls"))
        if msg.get("reasoning_content"):
            extra += str(msg.get("reasoning_content"))
        total += per_message
        total += _count_text_tokens(role, model)
        total += _count_text_tokens(content + extra, model)
        if msg.get("name"):
            total += _count_text_tokens(str(msg.get("name")), model)
    total += 2
    return total


def estimate_output_tokens(text, reasoning_text="", model=None):
    return _count_text_tokens(text, model) + _count_text_tokens(reasoning_text, model)


def estimate_turn_tokens(input_messages, output_text="", reasoning_text="", model=None):
    prompt = count_messages_tokens(input_messages, model)
    completion = estimate_output_tokens(output_text, reasoning_text, model)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": _count_text_tokens(reasoning_text, model),
        "total_tokens": prompt + completion,
    }


def resolve_turn_token_usage(
    recorded,
    input_messages,
    output_text="",
    reasoning_text="",
    model=None,
):
    usage = {
        "prompt_tokens": int(recorded.get("prompt_tokens") or 0),
        "completion_tokens": int(recorded.get("completion_tokens") or 0),
        "reasoning_tokens": int(recorded.get("reasoning_tokens") or 0),
        "total_tokens": int(recorded.get("total_tokens") or 0),
    }
    if usage["total_tokens"] > 0:
        return usage
    if not input_messages:
        return usage
    return estimate_turn_tokens(
        input_messages, output_text, reasoning_text, model
    )
