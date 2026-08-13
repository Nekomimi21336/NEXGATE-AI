"""Server-side chat session history per user."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

CHAT_SESSIONS_DIR = Path(__file__).resolve().parent / "data" / "chat_sessions"
SESSION_ID_RE = re.compile(r"^[0-9a-f-]{36}$", re.I)
MAX_SESSIONS = 2000
MAX_MESSAGES = 500
MAX_MESSAGE_CONTENT_LEN = 120_000
MAX_IMAGE_DATA_URL_LEN = 12_000_000
MAX_TITLE_LEN = 200
DEFAULT_SESSION_TITLE = "新しいチャット"

_lock = threading.RLock()


def _merge_session_title(existing_title, incoming_title):
    """Avoid overwriting a meaningful title with the default placeholder."""
    incoming = _truncate_text((incoming_title or "").strip(), MAX_TITLE_LEN)
    existing = _truncate_text((existing_title or "").strip(), MAX_TITLE_LEN)
    if not incoming:
        return existing or DEFAULT_SESSION_TITLE
    if not existing or existing == DEFAULT_SESSION_TITLE:
        return incoming
    if incoming == DEFAULT_SESSION_TITLE:
        return existing
    return incoming


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user_dir(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return CHAT_SESSIONS_DIR / safe


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


def _truncate_text(value, limit=MAX_MESSAGE_CONTENT_LEN):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _try_parse_multipart_json(text: str):
    stripped = (text or "").strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _sanitize_content_part(part):
    if not isinstance(part, dict):
        return None
    ptype = (part.get("type") or "").strip().lower()
    if ptype == "text":
        text = _truncate_text(part.get("text") or "")
        return {"type": "text", "text": text} if text else None
    if ptype == "image_url":
        block = part.get("image_url") if isinstance(part.get("image_url"), dict) else {}
        url = str(block.get("url") or "").strip()
        if url.startswith("data:image/"):
            if len(url) > MAX_IMAGE_DATA_URL_LEN:
                return None
            return {"type": "image_url", "image_url": {"url": url}}
        if url.startswith(("http://", "https://")):
            return {"type": "image_url", "image_url": {"url": _truncate_text(url, 4000)}}
        return None
    if ptype == "pdf_url":
        block = part.get("pdf_url") if isinstance(part.get("pdf_url"), dict) else {}
        url = str(block.get("url") or "").strip()
        if url.startswith("data:application/pdf"):
            if len(url) > MAX_IMAGE_DATA_URL_LEN:
                return None
            return {"type": "pdf_url", "pdf_url": {"url": url}}
        if url.startswith(("http://", "https://")):
            return {"type": "pdf_url", "pdf_url": {"url": _truncate_text(url, 4000)}}
        return None
    return None


def _sanitize_user_content(content):
    if isinstance(content, list):
        parts = []
        for part in content:
            sanitized = _sanitize_content_part(part)
            if sanitized:
                parts.append(sanitized)
        if not parts:
            return None
        if len(parts) == 1 and parts[0].get("type") == "text":
            return parts[0]["text"]
        return parts
    if isinstance(content, str):
        parsed = _try_parse_multipart_json(content)
        if parsed is not None:
            return _sanitize_user_content(parsed)
        text = _truncate_text(content)
        return text if text else None
    return None


def _sanitize_message(item):
    if not isinstance(item, dict):
        return None
    role = (item.get("role") or "").strip().lower()
    if role not in ("user", "assistant", "search", "reasoning"):
        return None

    created_at = item.get("created_at")
    created = created_at.strip()[:40] if isinstance(created_at, str) and created_at.strip() else None

    if role == "search":
        content = item.get("content")
        if not isinstance(content, dict):
            return None
        out = {
            "role": "search",
            "content": {
                "queries": content.get("queries") if isinstance(content.get("queries"), list) else [],
                "sites": content.get("sites") if isinstance(content.get("sites"), list) else [],
                "urls": content.get("urls") if isinstance(content.get("urls"), list) else [],
                "collapsed": bool(content.get("collapsed")),
                "complete": bool(content.get("complete")),
            },
        }
    elif role == "reasoning":
        content = item.get("content")
        if not isinstance(content, dict):
            return None
        out = {
            "role": "reasoning",
            "content": {
                "text": _truncate_text(content.get("text") or "", 32000),
                "collapsed": bool(content.get("collapsed")),
                "complete": bool(content.get("complete")),
            },
        }
    elif role == "assistant":
        content = item.get("content")
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        else:
            content = _truncate_text(content)
        if not content and not item.get("tasksToolUsed"):
            return None
        out = {"role": "assistant", "content": content}
        if item.get("showActions") is True:
            out["showActions"] = True
        if item.get("tasksToolUsed") is True:
            out["tasksToolUsed"] = True
    else:
        content = _sanitize_user_content(item.get("content"))
        if not content:
            return None
        out = {"role": "user", "content": content}

    if created:
        out["created_at"] = created
    return out


def sanitize_messages(raw_messages):
    cleaned = []
    if not isinstance(raw_messages, list):
        return cleaned
    for item in raw_messages[:MAX_MESSAGES]:
        msg = _sanitize_message(item)
        if msg:
            cleaned.append(msg)
    return cleaned


def _normalize_index_entry(raw, *, fallback_updated_at=None):
    if not isinstance(raw, dict):
        return None
    sid = (raw.get("id") or "").strip()
    if not SESSION_ID_RE.match(sid):
        return None
    title = _truncate_text(raw.get("title") or "新しいチャット", MAX_TITLE_LEN)
    updated_at = (raw.get("updated_at") or "").strip() or fallback_updated_at or _now_iso()
    entry = {"id": sid, "title": title, "updated_at": updated_at[:40]}
    if raw.get("favorite"):
        entry["favorite"] = True
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


def list_chat_sessions(username):
    with _lock:
        return list(_load_index(username))


def _session_in_index(sessions, session_id):
    return any(s["id"] == session_id for s in sessions)


def get_chat_session_messages(username, session_id):
    session_id = _validate_session_id(session_id)
    with _lock:
        sessions = _load_index(username)
        if not _session_in_index(sessions, session_id):
            return None
        data = _read_json(_messages_path(username, session_id), {"messages": []})
    messages = data.get("messages") if isinstance(data, dict) else []
    return sanitize_messages(messages)


def get_chat_session_meta(username, session_id):
    session_id = _validate_session_id(session_id)
    with _lock:
        for row in _load_index(username):
            if row["id"] == session_id:
                return dict(row)
    return None


def upsert_chat_session(
    username,
    session_id,
    *,
    title=None,
    messages=None,
    favorite=None,
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
                    "title": _merge_session_title(None, title or DEFAULT_SESSION_TITLE),
                    "updated_at": now,
                    "created_at": now,
                }
                if favorite:
                    entry["favorite"] = True
                sessions.insert(0, entry)
            else:
                entry = sessions[idx]
                if title is not None:
                    entry["title"] = _merge_session_title(entry.get("title"), title)
                entry["updated_at"] = now
                if favorite is not None:
                    if favorite:
                        entry["favorite"] = True
                    else:
                        entry.pop("favorite", None)
                sessions[idx] = entry
            _save_index(username, sessions)
            saved = next(s for s in sessions if s["id"] == session_id)
            result = {
                "id": session_id,
                "title": saved["title"],
                "updated_at": saved["updated_at"],
                "favorite": bool(saved.get("favorite")),
                "message_count": len(cleaned),
            }
            if saved.get("created_at"):
                result["created_at"] = saved["created_at"]
            return result

        if idx < 0:
            raise ValueError("session not found")

        entry = sessions[idx]
        if title is not None:
            entry["title"] = _merge_session_title(entry.get("title"), title)
        entry["updated_at"] = now
        if favorite is not None:
            if favorite:
                entry["favorite"] = True
            else:
                entry.pop("favorite", None)
        sessions[idx] = entry
        _save_index(username, sessions)
        return dict(entry)


def delete_chat_session(username, session_id):
    session_id = _validate_session_id(session_id)
    with _lock:
        sessions = _load_index(username)
        sessions = [s for s in sessions if s["id"] != session_id]
        _save_index(username, sessions)
        path = _messages_path(username, session_id)
        if path.is_file():
            path.unlink(missing_ok=True)
    return True


def sync_chat_sessions_from_client(username, payload):
    """Merge client-exported sessions into server store (migration)."""
    username = (username or "").strip().lower()
    if not isinstance(payload, dict):
        raise ValueError("invalid payload")

    incoming_sessions = payload.get("sessions") or []
    messages_by_id = payload.get("messages_by_id") or {}
    if not isinstance(incoming_sessions, list):
        incoming_sessions = []
    if not isinstance(messages_by_id, dict):
        messages_by_id = {}

    with _lock:
        existing = {s["id"]: s for s in _load_index(username)}
        merged = dict(existing)

        for raw in incoming_sessions:
            entry = _normalize_index_entry(raw)
            if not entry:
                continue
            sid = entry["id"]
            msgs = messages_by_id.get(sid)
            if msgs is None:
                if sid in merged:
                    continue
                file_msgs = _read_json(_messages_path(username, sid), {"messages": []}).get(
                    "messages"
                )
                msgs = file_msgs
            cleaned = sanitize_messages(msgs or [])
            if not cleaned:
                continue
            _write_json(_messages_path(username, sid), {"messages": cleaned})
            prev = merged.get(sid)
            if prev and (prev.get("updated_at") or "") > (entry.get("updated_at") or ""):
                merged_title = _merge_session_title(prev.get("title"), entry.get("title"))
                entry = {**prev, "title": merged_title}
            elif prev:
                entry = {**entry, "title": _merge_session_title(prev.get("title"), entry.get("title"))}
            merged[sid] = entry

        ordered = sorted(
            merged.values(),
            key=lambda r: r.get("updated_at") or "",
            reverse=True,
        )[:MAX_SESSIONS]
        _save_index(username, ordered)
        return {"sessions": ordered, "count": len(ordered)}


def new_session_id():
    return str(uuid.uuid4())
