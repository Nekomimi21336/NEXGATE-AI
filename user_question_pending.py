import json
import secrets
import time
from pathlib import Path

PENDING_FILE = Path(__file__).parent / "data" / "user_question_pending.json"
PENDING_TTL_SECONDS = 1800


def _load_pending() -> dict:
    if not PENDING_FILE.exists():
        return {}
    try:
        with PENDING_FILE.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_pending(store: dict) -> None:
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PENDING_FILE.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False)


def _prune_pending(store: dict, *, now: float | None = None) -> dict:
    current = now if now is not None else time.time()
    return {
        token: payload
        for token, payload in store.items()
        if isinstance(payload, dict) and float(payload.get("expires", 0)) > current
    }


def create_user_question_pending(username: str, payload: dict) -> str:
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("username required")
    if not isinstance(payload, dict):
        raise ValueError("payload required")
    token = secrets.token_urlsafe(32)
    now = time.time()
    store = _prune_pending(_load_pending(), now=now)
    store[token] = {
        **payload,
        "username": username,
        "expires": now + PENDING_TTL_SECONDS,
        "created_at": now,
    }
    _save_pending(store)
    return token


def consume_user_question_pending(token: str, username: str) -> dict | None:
    token = (token or "").strip()
    username = (username or "").strip().lower()
    if not token or not username:
        return None
    now = time.time()
    store = _prune_pending(_load_pending(), now=now)
    payload = store.pop(token, None)
    _save_pending(store)
    if not isinstance(payload, dict):
        return None
    if (payload.get("username") or "").strip().lower() != username:
        return None
    if float(payload.get("expires", 0)) <= now:
        return None
    return payload
