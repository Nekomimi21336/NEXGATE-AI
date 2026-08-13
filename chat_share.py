import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHARE_DIR = Path(__file__).parent / "data" / "shared_chats"
INDEX_DIR = SHARE_DIR / "by_session"
SHARE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
MAX_MESSAGES = 200
MAX_CONTENT_LEN = 32000
SHARE_TTL_DAYS = 30

VISIBILITY_PRIVATE = "private"
VISIBILITY_LOGIN_REQUIRED = "login_required"
VISIBILITY_PUBLIC = "public"
VALID_VISIBILITIES = {
    VISIBILITY_PRIVATE,
    VISIBILITY_LOGIN_REQUIRED,
    VISIBILITY_PUBLIC,
}


def _ensure_dir():
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _now():
    return datetime.now(timezone.utc)


def _session_index_key(owner, session_id):
    raw = f"{owner or ''}\0{session_id or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _index_path(owner, session_id):
    return INDEX_DIR / f"{_session_index_key(owner, session_id)}.json"


def _share_path(share_id):
    return SHARE_DIR / f"{share_id}.json"


def _normalize_visibility(value):
    vis = (value or VISIBILITY_PRIVATE).strip().lower()
    return vis if vis in VALID_VISIBILITIES else VISIBILITY_PRIVATE


from json_store import read_json as _read_json_store
from json_store import write_json as _write_json_store


def _read_json(path):
    value = _read_json_store(path, default=None)
    return value


def _write_json(path, data):
    _write_json_store(path, data)


def _is_expired(data):
    expires_at = data.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < _now()
    except ValueError:
        return False


def _load_share_file(share_id):
    if not share_id or not SHARE_ID_RE.match(share_id):
        return None
    path = _share_path(share_id)
    if not path.is_file():
        return None
    data = _read_json(path)
    if not data or _is_expired(data):
        return None
    return data


def _resolve_index(owner, session_id):
    if not owner or not session_id:
        return None
    path = _index_path(owner, session_id)
    if not path.is_file():
        return None
    index = _read_json(path)
    if not index:
        return None
    share_id = index.get("share_id")
    if not share_id or not SHARE_ID_RE.match(share_id):
        return None
    return share_id


def sanitize_messages(raw_messages):
    cleaned = []
    if not isinstance(raw_messages, list):
        return cleaned
    for item in raw_messages[:MAX_MESSAGES]:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = item.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = (part.get("text") or "").strip()
                    if text:
                        parts.append(text)
            content = "\n".join(parts)
        else:
            content = str(content or "").strip()
        if not content:
            continue
        if len(content) > MAX_CONTENT_LEN:
            content = content[:MAX_CONTENT_LEN] + "…"
        entry = {"role": role, "content": content}
        created_at = item.get("created_at")
        if isinstance(created_at, str) and created_at.strip():
            entry["created_at"] = created_at.strip()[:40]
        cleaned.append(entry)
    return cleaned


def get_session_share(owner, session_id):
    share_id = _resolve_index(owner, session_id)
    if not share_id:
        return None
    data = _load_share_file(share_id)
    if not data:
        _remove_index(owner, session_id)
        return None
    visibility = _normalize_visibility(data.get("visibility", VISIBILITY_PUBLIC))
    if visibility == VISIBILITY_PRIVATE:
        return {
            "id": share_id,
            "owner": data.get("owner") or owner,
            "session_id": data.get("session_id") or session_id,
            "visibility": VISIBILITY_PRIVATE,
        }
    messages = sanitize_messages(data.get("messages"))
    if not messages:
        return None
    return {
        "id": share_id,
        "owner": data.get("owner") or owner,
        "session_id": data.get("session_id") or session_id,
        "title": data.get("title") or "共有された会話",
        "messages": messages,
        "visibility": visibility,
        "created_at": data.get("created_at"),
        "expires_at": data.get("expires_at"),
    }


def _save_index(owner, session_id, share_id):
    _ensure_dir()
    _write_json(
        _index_path(owner, session_id),
        {
            "share_id": share_id,
            "owner": owner,
            "session_id": session_id,
        },
    )


def _remove_index(owner, session_id):
    path = _index_path(owner, session_id)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def upsert_share(owner, session_id, title, messages, visibility):
    visibility = _normalize_visibility(visibility)
    session_id = (session_id or "")[:64]
    owner = (owner or "").strip()
    if not owner or not session_id:
        raise ValueError("セッション情報が不足しています")

    _ensure_dir()
    existing_id = _resolve_index(owner, session_id)
    share_id = existing_id or uuid.uuid4().hex
    now = _now()

    if visibility == VISIBILITY_PRIVATE:
        if existing_id:
            data = _load_share_file(existing_id) or {}
            data["id"] = share_id
            data["owner"] = owner
            data["session_id"] = session_id
            data["visibility"] = VISIBILITY_PRIVATE
            data["updated_at"] = now.isoformat()
            _write_json(_share_path(share_id), data)
            _save_index(owner, session_id, share_id)
            return {
                "id": share_id,
                "owner": owner,
                "session_id": session_id,
                "visibility": VISIBILITY_PRIVATE,
            }
        return {
            "id": None,
            "owner": owner,
            "session_id": session_id,
            "visibility": VISIBILITY_PRIVATE,
        }

    cleaned = sanitize_messages(messages)
    if not cleaned:
        raise ValueError("共有できるメッセージがありません")

    existing = _load_share_file(share_id) if existing_id else None
    created_at = (existing or {}).get("created_at") or now.isoformat()
    record = {
        "id": share_id,
        "owner": owner,
        "session_id": session_id,
        "title": (title or "共有された会話").strip()[:120] or "共有された会話",
        "messages": cleaned,
        "visibility": visibility,
        "created_at": created_at,
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(days=SHARE_TTL_DAYS)).isoformat(),
    }
    _write_json(_share_path(share_id), record)
    _save_index(owner, session_id, share_id)
    return record


def load_share(share_id):
    data = _load_share_file(share_id)
    if not data:
        return None
    visibility = _normalize_visibility(data.get("visibility", VISIBILITY_PUBLIC))
    if visibility == VISIBILITY_PRIVATE:
        return None
    messages = sanitize_messages(data.get("messages"))
    if not messages:
        return None
    data["messages"] = messages
    data["visibility"] = visibility
    return data


def create_share(username, session_id, title, messages):
    return upsert_share(
        username,
        session_id,
        title,
        messages,
        VISIBILITY_PUBLIC,
    )
