import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

COLLAB_DIR = Path(__file__).parent / "data" / "chat_session_collab"
BY_ID_DIR = COLLAB_DIR / "by_id"
BY_SESSION_DIR = COLLAB_DIR / "by_session"
COLLAB_ID_RE = re.compile(r"^[a-f0-9]{32}$")

COLLAB_PRIVATE = "private"
COLLAB_VIEW_ONLY = "view_only"
COLLAB_PARTICIPATE = "participate"
VALID_COLLAB_MODES = {
    COLLAB_PRIVATE,
    COLLAB_VIEW_ONLY,
    COLLAB_PARTICIPATE,
}

ROLE_OWNER = "owner"
ROLE_VIEWER = "viewer"
ROLE_PARTICIPANT = "participant"

PERMISSION_VIEW = "view"
PERMISSION_CHAT = "chat"
PERMISSION_EDIT_SETTINGS = "edit_settings"
PERMISSION_MANAGE_SHARE = "manage_share"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_username(username):
    return (username or "").strip().lower()


def _session_index_key(owner, session_id):
    raw = f"{owner or ''}\0{session_id or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ensure_dirs():
    BY_ID_DIR.mkdir(parents=True, exist_ok=True)
    BY_SESSION_DIR.mkdir(parents=True, exist_ok=True)


from json_store import read_json as _read_json_store
from json_store import write_json as _write_json_store


def _read_json(path, default=None):
    value = _read_json_store(path, default=default)
    return default if value is None else value


def _write_json(path, data):
    _write_json_store(path, data)


def _normalize_mode(value):
    mode = (value or COLLAB_PRIVATE).strip().lower()
    return mode if mode in VALID_COLLAB_MODES else COLLAB_PRIVATE


def _normalize_settings(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    model_id = (raw.get("model_id") or "").strip()
    if model_id:
        out["model_id"] = model_id[:120]
    agent_id = (raw.get("custom_agent_id") or "").strip()
    if agent_id:
        out["custom_agent_id"] = agent_id[:120]
    tools = raw.get("chat_tools")
    if isinstance(tools, dict):
        out["chat_tools"] = {
            str(k)[:40]: bool(v) for k, v in tools.items() if isinstance(k, str)
        }
    return out


def _resolve_session_index(owner, session_id):
    path = BY_SESSION_DIR / f"{_session_index_key(owner, session_id)}.json"
    if not path.is_file():
        return None
    index = _read_json(path)
    if not index:
        return None
    collab_id = (index.get("collab_id") or "").strip()
    if not collab_id or not COLLAB_ID_RE.match(collab_id):
        return None
    return collab_id


def _load_record(collab_id):
    if not collab_id or not COLLAB_ID_RE.match(collab_id):
        return None
    data = _read_json(BY_ID_DIR / f"{collab_id}.json")
    if not data:
        return None
    data["id"] = collab_id
    data["mode"] = _normalize_mode(data.get("mode"))
    data["settings"] = _normalize_settings(data.get("settings"))
    return data


def _save_record(record):
    collab_id = (record.get("id") or "").strip()
    owner = _safe_username(record.get("owner"))
    session_id = (record.get("session_id") or "").strip()
    if not collab_id or not owner or not session_id:
        raise ValueError("collab record incomplete")
    _ensure_dirs()
    _write_json(BY_ID_DIR / f"{collab_id}.json", record)
    _write_json(
        BY_SESSION_DIR / f"{_session_index_key(owner, session_id)}.json",
        {"collab_id": collab_id, "owner": owner, "session_id": session_id},
    )


def get_collab_record(owner, session_id):
    owner = _safe_username(owner)
    session_id = (session_id or "").strip()
    if not owner or not session_id:
        return None
    collab_id = _resolve_session_index(owner, session_id)
    if not collab_id:
        return {
            "id": None,
            "owner": owner,
            "session_id": session_id,
            "mode": COLLAB_PRIVATE,
            "settings": {},
            "updated_at": None,
        }
    record = _load_record(collab_id)
    if not record:
        return {
            "id": None,
            "owner": owner,
            "session_id": session_id,
            "mode": COLLAB_PRIVATE,
            "settings": {},
            "updated_at": None,
        }
    return record


def set_collab_mode(owner, session_id, mode):
    owner = _safe_username(owner)
    session_id = (session_id or "").strip()
    mode = _normalize_mode(mode)
    if not owner or not session_id:
        raise ValueError("セッション情報が不足しています")

    existing = get_collab_record(owner, session_id)
    collab_id = existing.get("id") or uuid.uuid4().hex
    settings = existing.get("settings") or {}
    now = _now_iso()

    if mode == COLLAB_PRIVATE:
        record = {
            "id": collab_id,
            "owner": owner,
            "session_id": session_id,
            "mode": COLLAB_PRIVATE,
            "settings": settings,
            "updated_at": now,
        }
        _save_record(record)
        return record

    record = {
        "id": collab_id,
        "owner": owner,
        "session_id": session_id,
        "mode": mode,
        "settings": settings,
        "updated_at": now,
    }
    _save_record(record)
    return record


def update_collab_settings(owner, session_id, settings):
    owner = _safe_username(owner)
    session_id = (session_id or "").strip()
    if not owner or not session_id:
        raise ValueError("セッション情報が不足しています")
    record = get_collab_record(owner, session_id)
    merged = _normalize_settings({**(record.get("settings") or {}), **(settings or {})})
    collab_id = record.get("id") or uuid.uuid4().hex
    now = _now_iso()
    saved = {
        "id": collab_id,
        "owner": owner,
        "session_id": session_id,
        "mode": _normalize_mode(record.get("mode")),
        "settings": merged,
        "updated_at": now,
    }
    _save_record(saved)
    return saved


def find_collab_by_id(collab_id):
    record = _load_record((collab_id or "").strip())
    if not record:
        return None
    if record.get("mode") == COLLAB_PRIVATE:
        return None
    return record


def permissions_for_role(role):
    if role == ROLE_OWNER:
        return [
            PERMISSION_VIEW,
            PERMISSION_CHAT,
            PERMISSION_EDIT_SETTINGS,
            PERMISSION_MANAGE_SHARE,
        ]
    if role == ROLE_PARTICIPANT:
        return [PERMISSION_VIEW, PERMISSION_CHAT, PERMISSION_EDIT_SETTINGS]
    if role == ROLE_VIEWER:
        return [PERMISSION_VIEW]
    return []


def resolve_session_access(username, owner, session_id):
    owner = _safe_username(owner)
    viewer = _safe_username(username)
    session_id = (session_id or "").strip()
    if not viewer or not session_id:
        return None

    if not owner:
        owner = viewer

    if owner == viewer:
        return {
            "owner": owner,
            "session_id": session_id,
            "role": ROLE_OWNER,
            "permissions": permissions_for_role(ROLE_OWNER),
            "collab_mode": COLLAB_PRIVATE,
            "can_chat": True,
            "can_edit_settings": True,
        }

    record = get_collab_record(owner, session_id)
    mode = _normalize_mode(record.get("mode"))
    if mode == COLLAB_PRIVATE:
        return None

    if mode == COLLAB_VIEW_ONLY:
        role = ROLE_VIEWER
    else:
        role = ROLE_PARTICIPANT

    return {
        "owner": owner,
        "session_id": session_id,
        "role": role,
        "permissions": permissions_for_role(role),
        "collab_mode": mode,
        "can_chat": role == ROLE_PARTICIPANT,
        "can_edit_settings": role == ROLE_PARTICIPANT,
        "collab_id": record.get("id"),
    }


def has_permission(access, permission):
    if not access:
        return False
    perms = access.get("permissions") or []
    return permission in perms


def collab_public_payload(record, *, url_builder):
    if not record:
        return {
            "collab_mode": COLLAB_PRIVATE,
            "collab_id": None,
            "url": None,
        }
    mode = _normalize_mode(record.get("mode"))
    collab_id = record.get("id")
    if mode == COLLAB_PRIVATE or not collab_id:
        return {
            "collab_mode": COLLAB_PRIVATE,
            "collab_id": None,
            "url": None,
        }
    url = url_builder(collab_id) if url_builder else None
    return {
        "collab_mode": mode,
        "collab_id": collab_id,
        "url": url,
        "settings": record.get("settings") or {},
        "updated_at": record.get("updated_at"),
    }
