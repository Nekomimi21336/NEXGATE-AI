"""Live chat session monitoring for admins (WebSocket + session logs)."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from request_session_detail import format_duration_label

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
SESSION_LOGS_FILE = DATA_DIR / "session_logs.json"
USD_JPY_RATE = 160
SESSION_END_GRACE_SECONDS = 5
WS_UPDATE_MIN_INTERVAL = 0.2
_lock = threading.Lock()
_admin_connections: set = set()
_active_sessions: dict[str, dict] = {}
_abort_events: dict[str, threading.Event] = {}
_end_timers: dict[str, threading.Timer] = {}
_last_ws_broadcast: dict[str, float] = {}


def _now_iso():
    return datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def _load_logs_store():
    if not SESSION_LOGS_FILE.exists():
        return {"sessions": []}
    try:
        with open(SESSION_LOGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"sessions": []}
    if not isinstance(data, dict):
        return {"sessions": []}
    sessions = data.get("sessions")
    return {"sessions": sessions if isinstance(sessions, list) else []}


def _save_logs_store(store):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SESSION_LOGS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    tmp.replace(SESSION_LOGS_FILE)


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _session_elapsed_seconds(row):
    start = _parse_iso(row.get("started_at"))
    if not start:
        return 0.001
    status = (row.get("status") or "running").strip().lower()
    if status == "running" and not row.get("ended_at"):
        end = datetime.now().replace(microsecond=0)
    else:
        end = _parse_iso(row.get("ended_at") or row.get("updated_at")) or datetime.now()
    return max(0.001, (end - start).total_seconds())


def _session_tps(row):
    completion = int(row.get("completion_tokens") or 0)
    if completion <= 0:
        return 0.0
    return round(completion / _session_elapsed_seconds(row), 1)


def _cost_jpy(usd):
    return int(round(float(usd or 0) * USD_JPY_RATE))


def _session_duration_seconds(row):
    if row.get("duration_seconds") is not None:
        try:
            return round(float(row["duration_seconds"]), 2)
        except (TypeError, ValueError):
            pass
    return round(_session_elapsed_seconds(row), 2)


def _session_public(row):
    if not row:
        return None
    cost_usd = round(float(row.get("cost_usd") or 0), 6)
    status = row.get("status") or "running"
    duration_seconds = _session_duration_seconds(row)
    return {
        "request_id": row.get("request_id") or "",
        "username": row.get("username") or "",
        "display_name": row.get("display_name") or "",
        "session_id": row.get("session_id") or "",
        "model_id": row.get("model_id") or "",
        "status": status,
        "settling": bool(row.get("settling")),
        "prompt_tokens": int(row.get("prompt_tokens") or 0),
        "completion_tokens": int(row.get("completion_tokens") or 0),
        "total_tokens": int(row.get("total_tokens") or 0),
        "cost_usd": cost_usd,
        "cost_jpy": _cost_jpy(cost_usd),
        "tps": _session_tps(row),
        "duration_seconds": duration_seconds,
        "duration_label": format_duration_label(duration_seconds),
        "tool_call_count": int(row.get("tool_call_count") or 0),
        "started_at": row.get("started_at") or "",
        "updated_at": row.get("updated_at") or "",
        "ended_at": row.get("ended_at") or "",
    }


def _broadcast(payload):
    with _lock:
        targets = list(_admin_connections)
    text = json.dumps(payload, ensure_ascii=False)
    dead = []
    for ws in targets:
        try:
            ws.send(text)
        except Exception as exc:
            logger.debug("admin session ws send failed: %s", exc)
            dead.append(ws)
    if dead:
        with _lock:
            for ws in dead:
                _admin_connections.discard(ws)


def register_admin_ws(ws):
    with _lock:
        _admin_connections.add(ws)
        active = [_session_public(v) for v in _active_sessions.values()]
    return active


def unregister_admin_ws(ws):
    with _lock:
        _admin_connections.discard(ws)


def get_abort_event(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return None
    with _lock:
        ev = _abort_events.get(request_id)
        if ev is None:
            ev = threading.Event()
            _abort_events[request_id] = ev
        return ev


def request_chat_abort(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return False
    with _lock:
        ev = _abort_events.get(request_id)
    if ev:
        ev.set()
        return True
    return False


def is_chat_aborted(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return False
    with _lock:
        ev = _abort_events.get(request_id)
    return bool(ev and ev.is_set())


def begin_monitored_chat(
    *,
    request_id,
    username,
    display_name="",
    session_id="",
    model_id="",
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
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "tool_call_count": 0,
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "ended_at": "",
    }
    with _lock:
        _active_sessions[request_id] = row
        _abort_events[request_id] = threading.Event()
    _broadcast({"type": "session.updated", "session": _session_public(row)})


def update_monitored_chat(
    request_id,
    *,
    model_id=None,
    token_usage=None,
    cost_usd=None,
    tool_call_count=None,
    force=False,
):
    request_id = (request_id or "").strip()
    if not request_id:
        return
    with _lock:
        row = _active_sessions.get(request_id)
        if not row:
            return
        if model_id is not None:
            row["model_id"] = str(model_id).strip()[:128]
        if token_usage:
            row["prompt_tokens"] = int(token_usage.get("prompt_tokens") or 0)
            row["completion_tokens"] = int(token_usage.get("completion_tokens") or 0)
            row["total_tokens"] = int(token_usage.get("total_tokens") or 0)
        if cost_usd is not None:
            row["cost_usd"] = round(float(cost_usd), 6)
        if tool_call_count is not None:
            row["tool_call_count"] = int(tool_call_count)
        row["updated_at"] = _now_iso()
        snapshot = dict(row)
    if not force:
        now = time.monotonic()
        last = _last_ws_broadcast.get(request_id, 0.0)
        if now - last < WS_UPDATE_MIN_INTERVAL:
            return
        _last_ws_broadcast[request_id] = now
    _broadcast({"type": "session.updated", "session": _session_public(snapshot)})


def _cancel_end_timer(request_id):
    with _lock:
        timer = _end_timers.pop(request_id, None)
    if timer:
        timer.cancel()


def _apply_final_session_fields(
    row,
    *,
    status,
    token_usage=None,
    cost_usd=0.0,
    tool_call_count=0,
    model_id=None,
    duration_seconds=None,
):
    if model_id is not None:
        row["model_id"] = str(model_id).strip()[:128]
    if token_usage:
        row["prompt_tokens"] = int(token_usage.get("prompt_tokens") or 0)
        row["completion_tokens"] = int(token_usage.get("completion_tokens") or 0)
        row["total_tokens"] = int(token_usage.get("total_tokens") or 0)
    row["cost_usd"] = round(float(cost_usd or 0), 6)
    row["tool_call_count"] = int(tool_call_count or 0)
    row["pending_final_status"] = (status or "completed").strip()[:32]
    row["updated_at"] = _now_iso()
    if duration_seconds is not None:
        row["duration_seconds"] = round(float(duration_seconds), 2)
    else:
        row["duration_seconds"] = round(_session_elapsed_seconds(row), 2)


def _finalize_monitored_chat(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return
    _cancel_end_timer(request_id)
    ended_at = _now_iso()
    with _lock:
        row = _active_sessions.pop(request_id, None)
        _abort_events.pop(request_id, None)
        _last_ws_broadcast.pop(request_id, None)
    if not row:
        return
    final_status = (row.pop("pending_final_status", None) or row.get("status") or "completed")
    row.pop("settling", None)
    row["status"] = final_status.strip()[:32]
    row["ended_at"] = ended_at
    row["updated_at"] = ended_at
    if row.get("duration_seconds") is None:
        row["duration_seconds"] = round(_session_elapsed_seconds(row), 2)

    store = _load_logs_store()
    sessions = store.get("sessions") or []
    sessions.append(row)
    if len(sessions) > 50000:
        sessions = sessions[-40000:]
    store["sessions"] = sessions
    _save_logs_store(store)

    public = _session_public(row)
    _broadcast({"type": "session.ended", "session": public})


def end_monitored_chat(
    request_id,
    *,
    status="completed",
    token_usage=None,
    cost_usd=0.0,
    tool_call_count=0,
    model_id=None,
    duration_seconds=None,
    grace_seconds=SESSION_END_GRACE_SECONDS,
):
    request_id = (request_id or "").strip()
    if not request_id:
        return
    try:
        grace_seconds = max(0, float(grace_seconds))
    except (TypeError, ValueError):
        grace_seconds = SESSION_END_GRACE_SECONDS

    with _lock:
        row = _active_sessions.get(request_id)
        if not row:
            return
        _apply_final_session_fields(
            row,
            status=status,
            token_usage=token_usage,
            cost_usd=cost_usd,
            tool_call_count=tool_call_count,
            model_id=model_id,
            duration_seconds=duration_seconds,
        )
        row["status"] = "running"
        row["settling"] = True
        snapshot = dict(row)

    _last_ws_broadcast[request_id] = time.monotonic()
    _broadcast({"type": "session.updated", "session": _session_public(snapshot)})

    if grace_seconds <= 0:
        _finalize_monitored_chat(request_id)
        return

    _cancel_end_timer(request_id)

    def _on_grace_done():
        _finalize_monitored_chat(request_id)

    timer = threading.Timer(grace_seconds, _on_grace_done)
    timer.daemon = True
    with _lock:
        _end_timers[request_id] = timer
    timer.start()


def list_active_sessions():
    with _lock:
        rows = [_session_public(dict(v)) for v in _active_sessions.values()]
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return rows


def list_session_logs(*, limit=100, offset=0):
    with _lock:
        rows = list(_load_logs_store().get("sessions") or [])
    rows.sort(key=lambda r: r.get("ended_at") or r.get("started_at") or "", reverse=True)
    total = len(rows)
    start = max(0, int(offset))
    end = start + max(1, min(500, int(limit)))
    return [_session_public(r) for r in rows[start:end]], total


def stream_with_abort(generator, request_id):
    abort_ev = get_abort_event(request_id)
    while True:
        if abort_ev and abort_ev.is_set():
            try:
                generator.close()
            except Exception:
                pass
            return
        try:
            item = next(generator)
        except StopIteration:
            return
        yield item


def init_admin_session_monitor(app):
    from flask_sock import Sock

    sock = Sock(app)

    @sock.route("/ws/admin/sessions")
    def admin_sessions_ws(ws):
        from flask import session

        user = session.get("user") or {}
        if user.get("role") != "admin":
            ws.close(4403, "Forbidden")
            return

        active = register_admin_ws(ws)
        try:
            ws.send(
                json.dumps(
                    {"type": "snapshot", "active": active},
                    ensure_ascii=False,
                )
            )
        except Exception:
            unregister_admin_ws(ws)
            return

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                action = (message.get("action") or "").strip().lower()
                if action == "ping":
                    ws.send(json.dumps({"type": "pong"}))
                elif action == "stop":
                    rid = (message.get("request_id") or "").strip()
                    if rid:
                        request_chat_abort(rid)
                        ws.send(
                            json.dumps(
                                {"type": "stop.ack", "request_id": rid, "ok": True},
                                ensure_ascii=False,
                            )
                        )
        finally:
            unregister_admin_ws(ws)

    return sock
