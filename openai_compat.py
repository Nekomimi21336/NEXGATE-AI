import json
import time
import uuid


def openai_error(message, *, error_type="invalid_request_error", code=None, status=400):
    body = {
        "error": {
            "message": message,
            "type": error_type,
            "code": code or error_type,
        }
    }
    return body, status


def _normalize_message_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts)
    return str(content)


def _normalize_tool_calls(raw_calls):
    if not isinstance(raw_calls, list):
        return None
    calls = []
    for item in raw_calls:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = (fn.get("name") or item.get("name") or "").strip()
        if not name:
            continue
        call_id = (item.get("id") or "").strip() or None
        arguments = fn.get("arguments")
        if arguments is None:
            arguments = item.get("arguments", "{}")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        entry = {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }
        calls.append(entry)
    return calls or None


def _normalize_tools(raw_tools):
    if raw_tools is None:
        return None, None
    if not isinstance(raw_tools, list):
        return None, openai_error("tools must be an array")
    tools = []
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        if (item.get("type") or "function").strip().lower() != "function":
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = (fn.get("name") or "").strip()
        if not name:
            continue
        tool = {"type": "function", "function": {"name": name}}
        if "description" in fn:
            tool["function"]["description"] = str(fn.get("description") or "")
        if "parameters" in fn:
            tool["function"]["parameters"] = fn.get("parameters")
        tools.append(tool)
    return tools, None


def _normalize_tool_choice(raw_choice, tools):
    if raw_choice is None:
        return None
    if isinstance(raw_choice, str):
        choice = raw_choice.strip().lower()
        if choice in ("none", "auto", "required"):
            return choice
        return None, openai_error("tool_choice is invalid")
    if isinstance(raw_choice, dict):
        if (raw_choice.get("type") or "").strip().lower() != "function":
            return None, openai_error("tool_choice is invalid")
        fn = raw_choice.get("function") if isinstance(raw_choice.get("function"), dict) else {}
        name = (fn.get("name") or "").strip()
        if not name:
            return None, openai_error("tool_choice.function.name is required")
        return {"type": "function", "function": {"name": name}}
    return None, openai_error("tool_choice is invalid")


def parse_chat_completions_request(data):
    if not isinstance(data, dict):
        return None, openai_error("Invalid JSON body")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return None, openai_error("messages is required")
    normalized = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        if role == "system":
            normalized.append(
                {"role": "system", "content": _normalize_message_content(item.get("content"))}
            )
        elif role == "user":
            normalized.append(
                {"role": "user", "content": _normalize_message_content(item.get("content"))}
            )
        elif role == "assistant":
            msg = {
                "role": "assistant",
                "content": _normalize_message_content(item.get("content")) or None,
            }
            tool_calls = _normalize_tool_calls(item.get("tool_calls"))
            if tool_calls:
                msg["tool_calls"] = tool_calls
            normalized.append(msg)
        elif role == "tool":
            tool_call_id = (item.get("tool_call_id") or "").strip()
            if not tool_call_id:
                continue
            normalized.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": _normalize_message_content(item.get("content")),
                }
            )
    if not normalized:
        return None, openai_error("messages is required")

    tools, tools_err = _normalize_tools(data.get("tools"))
    if tools_err:
        return None, tools_err

    tool_choice = None
    if "tool_choice" in data:
        tool_choice, choice_err = _normalize_tool_choice(data.get("tool_choice"), tools)
        if choice_err:
            return None, choice_err

    model = (data.get("model") or "").strip()
    stream = bool(data.get("stream"))

    # ---- 標準OpenAIパラメータの解析 ----
    def _opt_float(name, default=None):
        val = data.get(name)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _opt_int(name, default=None):
        val = data.get(name)
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    # n > 1 は非対応（1のみ）。それ以外の値はエラー
    n_value = _opt_int("n", 1)
    if n_value is not None and n_value != 1:
        return None, openai_error(
            "n must be 1 for this API",
            error_type="invalid_request_error",
            code="n_not_supported",
            status=400,
        )

    stop = data.get("stop")
    if isinstance(stop, str):
        stop = [stop]
    elif not isinstance(stop, list):
        stop = None

    # 推論制御（TTFB 短縮のため）
    #   thinking: false -> 推論無効（最速）
    #   thinking: true / 未指定 -> 推論有効（既定）
    thinking = data.get("thinking")
    if isinstance(thinking, str):
        thinking = thinking.strip().lower() in (
            "1", "true", "yes", "on", "enable", "enabled",
        )
    reasoning_effort = (data.get("reasoning_effort") or "").strip().lower()

    sampling = {
        "temperature": _opt_float("temperature"),
        "top_p": _opt_float("top_p"),
        "max_tokens": _opt_int("max_tokens"),
        "max_completion_tokens": _opt_int("max_completion_tokens"),
        "presence_penalty": _opt_float("presence_penalty"),
        "frequency_penalty": _opt_float("frequency_penalty"),
        "seed": _opt_int("seed"),
        "stop": stop,
        "response_format": data.get("response_format"),
        "user": data.get("user"),
        "stream_options": data.get("stream_options"),
        "thinking": thinking,
        "reasoning_effort": reasoning_effort,
    }

    return {
        "messages": normalized,
        "model": model,
        "stream": stream,
        "tools": tools,
        "tool_choice": tool_choice,
        "sampling": sampling,
    }, None


def api_tool_calls_list(tool_calls_map):
    calls = []
    for idx in sorted((tool_calls_map or {}).keys()):
        entry = tool_calls_map[idx] or {}
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        calls.append(
            {
                "id": (entry.get("id") or "").strip() or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": entry.get("arguments") or "{}",
                },
            }
        )
    return calls


def completion_id():
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def build_chat_completion(
    model,
    content,
    usage=None,
    *,
    tool_calls=None,
    finish_reason=None,
):
    now = int(time.time())
    usage = usage or {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    message = {"role": "assistant", "content": content if content else None}
    if tool_calls:
        message["tool_calls"] = tool_calls
        finish_reason = finish_reason or "tool_calls"
    else:
        finish_reason = finish_reason or "stop"
    return {
        "id": completion_id(),
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "prompt_tokens_details": {
                "cached_tokens": int(usage.get("input_cache_hit_tokens") or 0),
            },
        },
    }


def sse_chat_chunk(
    model,
    *,
    content_delta="",
    finish_reason=None,
    completion_id_value=None,
    usage=None,
):
    cid = completion_id_value or completion_id()
    choice = {
        "index": 0,
        "delta": {},
        "finish_reason": finish_reason,
    }
    if content_delta:
        choice["delta"] = {"content": content_delta}
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [choice],
    }
    if usage and int(usage.get("total_tokens") or 0):
        payload["usage"] = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "prompt_tokens_details": {
                "cached_tokens": int(usage.get("input_cache_hit_tokens") or 0),
            },
        }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_tool_call_chunk(model, *, tool_call_delta, completion_id_value=None):
    cid = completion_id_value or completion_id()
    idx = int(tool_call_delta.get("index") or 0)
    delta_tool = {"index": idx}
    if tool_call_delta.get("id"):
        delta_tool["id"] = tool_call_delta["id"]
    if tool_call_delta.get("type"):
        delta_tool["type"] = tool_call_delta["type"]
    fn = {}
    if tool_call_delta.get("name"):
        fn["name"] = tool_call_delta["name"]
    if tool_call_delta.get("arguments"):
        fn["arguments"] = tool_call_delta["arguments"]
    if fn:
        delta_tool["function"] = fn
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"tool_calls": [delta_tool]}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_chat_done():
    return "data: [DONE]\n\n"


def build_models_list(models):
    now = int(time.time())
    data = []
    for item in models or []:
        model_id = (item.get("id") or "").strip()
        if not model_id:
            continue
        data.append(
            {
                "id": model_id,
                "object": "model",
                "created": now,
                "owned_by": (item.get("owned_by") or "nexgate").strip() or "nexgate",
            }
        )
    return {"object": "list", "data": data}
