import json
import secrets
import time
from pathlib import Path

SSO_FILE = Path(__file__).parent / "data" / "portal_sso_tokens.json"
SSO_TTL_SECONDS = 120


def _load_tokens() -> dict:
    if not SSO_FILE.exists():
        return {}
    try:
        with SSO_FILE.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_tokens(tokens: dict) -> None:
    SSO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SSO_FILE.open("w", encoding="utf-8") as handle:
        json.dump(tokens, handle, ensure_ascii=False, indent=2)


def _prune_tokens(tokens: dict, *, now: float | None = None) -> dict:
    current = now if now is not None else time.time()
    return {
        token: payload
        for token, payload in tokens.items()
        if isinstance(payload, dict) and float(payload.get("expires", 0)) > current
    }


def create_portal_sso_token(username: str) -> str:
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("username required")
    token = secrets.token_urlsafe(32)
    now = time.time()
    tokens = _prune_tokens(_load_tokens(), now=now)
    tokens[token] = {"username": username, "expires": now + SSO_TTL_SECONDS}
    _save_tokens(tokens)
    return token


def consume_portal_sso_token(token: str) -> str | None:
    token = (token or "").strip()
    if not token:
        return None
    now = time.time()
    tokens = _prune_tokens(_load_tokens(), now=now)
    payload = tokens.pop(token, None)
    _save_tokens(tokens)
    if not isinstance(payload, dict):
        return None
    username = (payload.get("username") or "").strip().lower()
    if not username:
        return None
    if float(payload.get("expires", 0)) <= now:
        return None
    return username
