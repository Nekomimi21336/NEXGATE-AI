"""Expert-mode chat sessions (separate from regular chat history)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from chat_sessions_storage import (
    DEFAULT_SESSION_TITLE,
    MAX_MESSAGE_CONTENT_LEN,
    MAX_MESSAGES,
    MAX_TITLE_LEN,
    SESSION_ID_RE,
    _merge_session_title,
    _truncate_text,
    sanitize_messages,
)

EXPERT_SESSIONS_DIR = Path(__file__).resolve().parent / "data" / "expert_sessions"
MAX_SESSIONS = 500
DEFAULT_EXPERT_SESSION_TITLE = "専門家を作成中"
CREATION_MODES = frozenset({"chat", "crawl"})

_lock = threading.RLock()


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user_dir(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return EXPERT_SESSIONS_DIR / safe


def _index_path(username):
    return _user_dir(username) / "index.json"


def _messages_path(username, session_id):
    return _user_dir(username) / f"{session_id}.json"


def _validate_session_id(session_id):
    sid = (session_id or "").strip()
    if not SESSION_ID_RE.match(sid):
        raise ValueError("invalid session_id")
    return sid


from json_store import read_json as _read_json_file
from json_store import write_json as _write_json_file


def _read_json(path, default):
    value = _read_json_file(path, default=default)
    return default if value is None else value


def _write_json(path, data):
    _write_json_file(path, data)


def _normalize_creation_mode(mode):
    m = (mode or "chat").strip().lower()
    return m if m in CREATION_MODES else "chat"


def _normalize_index_entry(raw, *, fallback_updated_at=None):
    if not isinstance(raw, dict):
        return None
    sid = (raw.get("id") or "").strip()
    if not SESSION_ID_RE.match(sid):
        return None
    title = _truncate_text(raw.get("title") or DEFAULT_EXPERT_SESSION_TITLE, MAX_TITLE_LEN)
    updated_at = (raw.get("updated_at") or "").strip() or fallback_updated_at or _now_iso()
    entry = {
        "id": sid,
        "title": title,
        "updated_at": updated_at[:40],
        "expert_id": (raw.get("expert_id") or "").strip(),
        "creation_mode": _normalize_creation_mode(raw.get("creation_mode")),
    }
    created_at = (raw.get("created_at") or "").strip()
    if created_at:
        entry["created_at"] = created_at[:40]
    return entry


def _load_index(username):
    data = _read_json(_index_path(username), {"sessions": []})
    sessions = data.get("sessions") if isinstance(data, dict) else []
    if not isinstance(sessions, list):
        sessions = []
    out = []
    for row in sessions:
        norm = _normalize_index_entry(row)
        if norm:
            out.append(norm)
    return out


def _save_index(username, sessions):
    sessions = sessions[:MAX_SESSIONS]
    _write_json(_index_path(username), {"sessions": sessions})


def serialize_expert_session(entry):
    if not entry:
        return None
    return {
        "id": entry.get("id") or "",
        "title": entry.get("title") or DEFAULT_EXPERT_SESSION_TITLE,
        "updated_at": entry.get("updated_at") or "",
        "created_at": entry.get("created_at") or "",
        "expert_id": entry.get("expert_id") or "",
        "creation_mode": _normalize_creation_mode(entry.get("creation_mode")),
    }


def list_expert_sessions(username):
    with _lock:
        return [serialize_expert_session(s) for s in _load_index(username)]


def get_expert_session_meta(username, session_id):
    session_id = _validate_session_id(session_id)
    with _lock:
        for row in _load_index(username):
            if row["id"] == session_id:
                return serialize_expert_session(row)
    return None


def get_expert_session_messages(username, session_id):
    session_id = _validate_session_id(session_id)
    with _lock:
        sessions = _load_index(username)
        if not any(s["id"] == session_id for s in sessions):
            return None
        data = _read_json(_messages_path(username, session_id), {"messages": []})
    messages = data.get("messages") if isinstance(data, dict) else []
    return sanitize_messages(messages)


def upsert_expert_session(
    username,
    session_id,
    *,
    title=None,
    messages=None,
    expert_id=None,
    creation_mode=None,
    updated_at=None,
):
    session_id = _validate_session_id(session_id)
    username = (username or "").strip().lower()

    with _lock:
        sessions = _load_index(username)
        idx = next((i for i, s in enumerate(sessions) if s["id"] == session_id), -1)
        now = (updated_at or "").strip()[:40] or _now_iso()

        if messages is not None:
            cleaned = sanitize_messages(messages)
            if not cleaned:
                if idx >= 0:
                    sessions.pop(idx)
                msg_path = _messages_path(username, session_id)
                if msg_path.is_file():
                    msg_path.unlink(missing_ok=True)
                _save_index(username, sessions)
                return None
            _write_json(_messages_path(username, session_id), {"messages": cleaned})
            if idx < 0:
                entry = {
                    "id": session_id,
                    "title": _merge_session_title(None, title or DEFAULT_EXPERT_SESSION_TITLE),
                    "updated_at": now,
                    "created_at": now,
                    "expert_id": (expert_id or "").strip(),
                    "creation_mode": _normalize_creation_mode(creation_mode),
                }
                sessions.insert(0, entry)
            else:
                entry = sessions[idx]
                if title is not None:
                    entry["title"] = _merge_session_title(entry.get("title"), title)
                if expert_id is not None:
                    entry["expert_id"] = (expert_id or "").strip()
                if creation_mode is not None:
                    entry["creation_mode"] = _normalize_creation_mode(creation_mode)
                entry["updated_at"] = now
                sessions[idx] = entry
            _save_index(username, sessions)
            saved = next(s for s in sessions if s["id"] == session_id)
            result = serialize_expert_session(saved)
            result["message_count"] = len(cleaned)
            return result

        if idx < 0:
            if not expert_id:
                raise ValueError("expert_id required for new session")
            entry = {
                "id": session_id,
                "title": _merge_session_title(None, title or DEFAULT_EXPERT_SESSION_TITLE),
                "updated_at": now,
                "created_at": now,
                "expert_id": (expert_id or "").strip(),
                "creation_mode": _normalize_creation_mode(creation_mode),
            }
            sessions.insert(0, entry)
            _save_index(username, sessions)
            return serialize_expert_session(entry)

        entry = sessions[idx]
        if title is not None:
            entry["title"] = _merge_session_title(entry.get("title"), title)
        if expert_id is not None:
            entry["expert_id"] = (expert_id or "").strip()
        if creation_mode is not None:
            entry["creation_mode"] = _normalize_creation_mode(creation_mode)
        entry["updated_at"] = now
        sessions[idx] = entry
        _save_index(username, sessions)
        return serialize_expert_session(entry)


def delete_expert_session(username, session_id):
    session_id = _validate_session_id(session_id)
    with _lock:
        sessions = _load_index(username)
        sessions = [s for s in sessions if s["id"] != session_id]
        _save_index(username, sessions)
        path = _messages_path(username, session_id)
        if path.is_file():
            path.unlink(missing_ok=True)
    return True


def delete_expert_sessions_for_expert(username, expert_id):
    expert_id = (expert_id or "").strip()
    if not expert_id:
        return 0
    with _lock:
        sessions = _load_index(username)
        to_delete = [s["id"] for s in sessions if s.get("expert_id") == expert_id]
        sessions = [s for s in sessions if s.get("expert_id") != expert_id]
        _save_index(username, sessions)
    for sid in to_delete:
        path = _messages_path(username, sid)
        if path.is_file():
            path.unlink(missing_ok=True)
    return len(to_delete)


def new_expert_session_id():
    return str(uuid.uuid4())
