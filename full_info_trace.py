import json
import time

MAX_FIELD = 12000
MAX_MSG_FIELD = 8000


def _clip(text, limit=MAX_FIELD):
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n…[{len(s) - limit} chars omitted]"


def sanitize_message_for_full_info(message):
    role = message.get("role")
    out = {"role": role}
    if role in ("system", "user"):
        out["content"] = _clip(message.get("content"), MAX_MSG_FIELD)
    elif role == "assistant":
        out["content"] = _clip(message.get("content"), MAX_MSG_FIELD)
        if message.get("tool_calls"):
            out["tool_calls"] = message["tool_calls"]
        if message.get("reasoning_content"):
            out["reasoning_content"] = _clip(message.get("reasoning_content"), 4000)
    elif role == "tool":
        out["tool_call_id"] = message.get("tool_call_id")
        out["content"] = _clip(message.get("content"), MAX_MSG_FIELD)
    else:
        out["content"] = _clip(message.get("content"))
    return out


def sanitize_messages_for_full_info(messages):
    return [sanitize_message_for_full_info(m) for m in (messages or [])]


def tool_names_from_list(tools):
    names = []
    for tool in tools or []:
        fn = (tool or {}).get("function") or {}
        name = fn.get("name")
        if name:
            names.append(name)
    return names


def full_info_payload(kind, **data):
    return {
        "chat_full_info": {
            "kind": kind,
            "ts": time.time(),
            **data,
        }
    }


def model_request_payload(model, messages, tools=None, label=""):
    return full_info_payload(
        "model_request",
        label=label,
        model=model,
        messages=sanitize_messages_for_full_info(messages),
        tools=tool_names_from_list(tools),
    )


def mirror_sse_payload_to_full_info(payload):
    if not isinstance(payload, dict):
        return None
    if "chat_full_info" in payload:
        return None
    if "content" in payload:
        return full_info_payload("assistant_stream", text=payload.get("content") or "")
    if "tool_trace" in payload:
        trace = payload.get("tool_trace") or {}
        return full_info_payload(
            "tool_trace",
            name=trace.get("name"),
            duration_ms=trace.get("duration_ms"),
            ok=trace.get("ok"),
            error=trace.get("error"),
        )
    if "reasoning" in payload:
        return full_info_payload("reasoning", data=payload.get("reasoning"))
    if "expert_crawl" in payload:
        return full_info_payload("expert_crawl", data=payload.get("expert_crawl"))
    if "search" in payload:
        return full_info_payload(
            "search",
            data=_clip(json.dumps(payload.get("search"), ensure_ascii=False), 4000),
        )
    if "fetch" in payload:
        return full_info_payload(
            "fetch",
            data=_clip(json.dumps(payload.get("fetch"), ensure_ascii=False), 4000),
        )
    if payload.get("segment_start"):
        return full_info_payload(
            "segment",
            phase="start",
            discard_previous=bool(payload.get("discard_previous")),
        )
    if payload.get("segment_end"):
        return full_info_payload("segment", phase="end")
    if payload.get("done"):
        return full_info_payload("turn_done", usage=payload.get("usage"))
    if "error" in payload:
        return full_info_payload("error", message=_clip(payload.get("error")))
    if payload.get("expert_knowledge_updated"):
        return full_info_payload("expert_knowledge_updated", updated=True)
    return None


def traced_sse_event(sse_event, payload, enabled):
    if not enabled:
        return sse_event(payload)
    parts = []
    mirrored = mirror_sse_payload_to_full_info(payload)
    if mirrored:
        parts.append(sse_event(mirrored))
    parts.append(sse_event(payload))
    return "".join(parts)


def make_traced_sse_event(sse_event, enabled):
    def wrapped(payload):
        return traced_sse_event(sse_event, payload, enabled)

    return wrapped
