"""Per-request audit detail for admin session inspection."""

from __future__ import annotations

import copy
import json
import threading
from datetime import datetime
from pathlib import Path

from session_title import extract_plain_user_text

DATA_DIR = Path(__file__).resolve().parent / "data"
DETAILS_DIR = DATA_DIR / "request_details"
_lock = threading.Lock()
_buffers: dict[str, dict] = {}

MAX_TEXT_FIELD = 120_000
MAX_TOOL_JSON = 24_000
MAX_TOOL_EVENTS = 200

_TOOL_FLAG_KEYS = {
    "tasks_tool_used": "tasks",
    "memory_tool_used": "memory",
    "memory_updated": "memory_update",
    "computelab_tool_used": "computelab",
}


def _now_iso():
    return datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def _truncate_text(value, limit=MAX_TEXT_FIELD):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（残り {len(text) - limit} 文字を省略）"


def _json_safe(value, *, limit=MAX_TOOL_JSON):
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"_raw": _truncate_text(str(value), limit)}
    if len(text) <= limit:
        return json.loads(text)
    return {"_truncated": True, "preview": text[:limit]}


def _compact_tool_payload(key, value):
    if not isinstance(value, dict):
        if value is True:
            return {"invoked": True}
        return value
    payload = copy.deepcopy(value)
    if key == "search" and payload.get("type") == "done":
        results = payload.get("results") or []
        compact = []
        for row in results[:10]:
            if not isinstance(row, dict):
                continue
            compact.append(
                {
                    "title": _truncate_text(row.get("title") or "", 300),
                    "url": row.get("url") or "",
                    "snippet": _truncate_text(
                        row.get("snippet") or row.get("content") or "", 800
                    ),
                }
            )
        payload["results"] = compact
        payload["results_count"] = len(results)
    if key == "fetch" and payload.get("type") == "done":
        text = payload.get("text") or payload.get("content") or ""
        if text:
            payload["text"] = _truncate_text(text, 4000)
    if key == "image_generation" and isinstance(payload, dict):
        for img_key in ("url", "image_url", "path"):
            if payload.get(img_key):
                payload[img_key] = str(payload.get(img_key))[:500]
    return _json_safe(payload)


def summarize_messages_for_audit(messages, *, max_messages=40):
    rows = []
    for msg in (messages or [])[-max_messages:]:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").strip()
        content = msg.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type") or "text"
                if ptype == "text":
                    parts.append(_truncate_text(part.get("text") or "", 4000))
                elif ptype == "image_url":
                    parts.append("[画像]")
                elif ptype == "file":
                    parts.append("[ファイル]")
                else:
                    parts.append(f"[{ptype}]")
            text = "\n".join(p for p in parts if p).strip()
        else:
            text = _truncate_text(extract_plain_user_text(content), 8000)
        rows.append({"role": role, "content": text})
    return rows


def last_user_message_text(messages):
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        text = extract_plain_user_text(msg.get("content"))
        if text:
            return _truncate_text(text, MAX_TEXT_FIELD)
    return ""


def begin_request_detail(
    request_id,
    *,
    username="",
    display_name="",
    session_id="",
    model_id="",
    client_ip="",
    user_agent="",
    messages_summary=None,
    user_message="",
):
    request_id = (request_id or "").strip()
    if not request_id:
        return
    row = {
        "request_id": request_id,
        "username": (username or "").strip().lower(),
        "display_name": (display_name or "").strip(),
        "session_id": (session_id or "").strip()[:128],
        "model_id": (model_id or "").strip()[:128],
        "status": "running",
        "started_at": _now_iso(),
        "ended_at": "",
        "duration_seconds": 0.0,
        "client_ip": (client_ip or "").strip()[:64],
        "user_agent": (user_agent or "").strip()[:512],
        "user_message": _truncate_text(user_message),
        "messages_sent": messages_summary or [],
        "assistant_response": "",
        "reasoning_text": "",
        "tool_events": [],
        "error_message": "",
        "token_usage": {},
        "cost_usd": 0.0,
        "tool_call_count": 0,
    }
    with _lock:
        _buffers[request_id] = row


def record_request_detail_sse(request_id, payload):
    request_id = (request_id or "").strip()
    if not request_id or not isinstance(payload, dict):
        return
    with _lock:
        row = _buffers.get(request_id)
    if not row:
        return

    piece = payload.get("content")
    if piece:
        row["assistant_response"] = _truncate_text(
            (row.get("assistant_response") or "") + piece
        )

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("type") == "delta":
        row["reasoning_text"] = _truncate_text(
            (row.get("reasoning_text") or "") + (reasoning.get("text") or "")
        )

    if payload.get("error"):
        row["error_message"] = _truncate_text(payload.get("error"))

    for key in ("search", "fetch", "image_generation"):
        if key not in payload:
            continue
        events = row.setdefault("tool_events", [])
        if len(events) >= MAX_TOOL_EVENTS:
            continue
        events.append(
            {
                "at": _now_iso(),
                "tool": key,
                "payload": _compact_tool_payload(key, payload.get(key)),
            }
        )

    for flag_key, tool_name in _TOOL_FLAG_KEYS.items():
        if not payload.get(flag_key):
            continue
        events = row.setdefault("tool_events", [])
        if len(events) >= MAX_TOOL_EVENTS:
            continue
        events.append({"at": _now_iso(), "tool": tool_name, "payload": {"invoked": True}})


def finish_request_detail(
    request_id,
    *,
    status="completed",
    assistant_response=None,
    reasoning_text=None,
    token_usage=None,
    cost_usd=0.0,
    tool_call_count=0,
    model_id=None,
    error_message="",
    duration_seconds=None,
):
    request_id = (request_id or "").strip()
    if not request_id:
        return
    ended_at = _now_iso()
    with _lock:
        row = _buffers.pop(request_id, None)
    if not row:
        path = DETAILS_DIR / f"{request_id}.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    row = json.load(f)
            except (json.JSONDecodeError, OSError):
                row = None
        if not row:
            row = {"request_id": request_id, "started_at": ended_at}
    if assistant_response is not None:
        row["assistant_response"] = _truncate_text(assistant_response)
    if reasoning_text is not None:
        row["reasoning_text"] = _truncate_text(reasoning_text)
    if model_id is not None:
        row["model_id"] = str(model_id).strip()[:128]
    row["status"] = (status or "completed").strip()[:32]
    row["ended_at"] = ended_at
    row["token_usage"] = dict(token_usage or {})
    row["cost_usd"] = round(float(cost_usd or 0), 6)
    row["tool_call_count"] = int(tool_call_count or 0)
    if error_message:
        row["error_message"] = _truncate_text(error_message)

    start = _parse_iso(row.get("started_at"))
    end = _parse_iso(ended_at)
    if duration_seconds is not None:
        row["duration_seconds"] = round(float(duration_seconds), 2)
    elif start and end:
        row["duration_seconds"] = round(max(0, (end - start).total_seconds()), 2)
    else:
        row["duration_seconds"] = 0.0

    _save_detail_file(request_id, row)
    return row


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _save_detail_file(request_id, row):
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    path = DETAILS_DIR / f"{request_id}.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(row, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_request_detail(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return None
    with _lock:
        buf = _buffers.get(request_id)
        if buf:
            return copy.deepcopy(buf)
    path = DETAILS_DIR / f"{request_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def serialize_request_detail_for_api(detail, *, usd_jpy=160):
    if not detail:
        return None
    cost_usd = round(float(detail.get("cost_usd") or 0), 6)
    usage = detail.get("token_usage") or {}
    duration = float(detail.get("duration_seconds") or 0)
    return {
        "request_id": detail.get("request_id") or "",
        "username": detail.get("username") or "",
        "display_name": detail.get("display_name") or "",
        "session_id": detail.get("session_id") or "",
        "model_id": detail.get("model_id") or "",
        "status": detail.get("status") or "",
        "started_at": detail.get("started_at") or "",
        "ended_at": detail.get("ended_at") or "",
        "duration_seconds": duration,
        "duration_label": format_duration_label(duration),
        "client_ip": detail.get("client_ip") or "",
        "user_agent": detail.get("user_agent") or "",
        "user_message": detail.get("user_message") or "",
        "messages_sent": detail.get("messages_sent") or [],
        "assistant_response": detail.get("assistant_response") or "",
        "reasoning_text": detail.get("reasoning_text") or "",
        "tool_events": detail.get("tool_events") or [],
        "error_message": detail.get("error_message") or "",
        "token_usage": usage,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "input_cache_hit_tokens": int(usage.get("input_cache_hit_tokens") or 0),
        "input_cache_miss_tokens": int(usage.get("input_cache_miss_tokens") or 0),
        "cost_usd": cost_usd,
        "cost_jpy": int(round(cost_usd * usd_jpy)),
        "tool_call_count": int(detail.get("tool_call_count") or 0),
    }


def format_duration_label(seconds):
    try:
        sec = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return "—"
    if sec < 1:
        return f"{int(sec * 1000)} ms"
    if sec < 60:
        return f"{sec:.1f} 秒"
    minutes = int(sec // 60)
    rem = sec % 60
    if minutes < 60:
        return f"{minutes} 分 {rem:.0f} 秒"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours} 時間 {minutes} 分"
