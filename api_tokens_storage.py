import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

API_TOKENS_DIR = Path(__file__).parent / "data" / "api_tokens"
TOKEN_PREFIX = "ngx_"
MAX_TOKENS_PER_USER = 20
# last_used_at の書き込み間引き（秒）。並列リクエスト時の書き込み競合とコストを削減。
TOUCH_MIN_INTERVAL_SEC = 60

# 読み書きを直列化（RLock: _touch_token 等の入れ子呼び出しでも安全）
_lock = threading.RLock()


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _user_path(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return API_TOKENS_DIR / f"{safe}.json"


def _hash_token(plaintext):
    return hashlib.sha256((plaintext or "").encode("utf-8")).hexdigest()


def _load_user_tokens(username):
    with _lock:
        path = _user_path(username)
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, list):
            return []
        return [t for t in raw if isinstance(t, dict)]


def _save_user_tokens(username, tokens):
    with _lock:
        API_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
        path = _user_path(username)
        # アトミック書き込み：一時ファイル → 置換。書き込み途中を他スレッドが読まないようにする。
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def _public_entry(token):
    return {
        "id": token.get("id"),
        "name": token.get("name") or "",
        "prefix": token.get("prefix") or "",
        "created_at": token.get("created_at") or "",
        "last_used_at": token.get("last_used_at") or "",
        "revoked_at": token.get("revoked_at") or "",
        "active": not bool(token.get("revoked_at")),
    }


def list_user_tokens(username, *, include_revoked=False):
    rows = []
    for token in _load_user_tokens(username):
        if token.get("revoked_at") and not include_revoked:
            continue
        rows.append(_public_entry(token))
    rows.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return rows


def create_user_token(username, name=""):
    username = (username or "").strip().lower()
    tokens = _load_user_tokens(username)
    active = [t for t in tokens if not t.get("revoked_at")]
    if len(active) >= MAX_TOKENS_PER_USER:
        return None, f"APIトークンは最大{MAX_TOKENS_PER_USER}件までです"

    token_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    plaintext = f"{TOKEN_PREFIX}{secret}"
    prefix = plaintext[:12]
    now = _now_iso()
    entry = {
        "id": token_id,
        "name": (name or "").strip()[:64] or "API Token",
        "prefix": prefix,
        "hash": _hash_token(plaintext),
        "created_at": now,
        "last_used_at": "",
        "revoked_at": "",
    }
    tokens.append(entry)
    _save_user_tokens(username, tokens)
    return {"token": _public_entry(entry), "secret": plaintext}, None


def revoke_user_token(username, token_id):
    username = (username or "").strip().lower()
    token_id = (token_id or "").strip()
    tokens = _load_user_tokens(username)
    changed = False
    for token in tokens:
        if token.get("id") != token_id:
            continue
        if token.get("revoked_at"):
            return True
        token["revoked_at"] = _now_iso()
        changed = True
        break
    if not changed:
        return False
    _save_user_tokens(username, tokens)
    return True


def _touch_token(username, token_id):
    """last_used_at を更新。短時間の再認証では書き込みを省略し、
    並列リクエスト時のファイル競合とI/Oコストを抑える。"""
    now = _now_iso()
    with _lock:
        tokens = _load_user_tokens(username)
        for token in tokens:
            if token.get("id") != token_id:
                continue
            last = token.get("last_used_at") or ""
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
                    if (now_dt - last_dt).total_seconds() < TOUCH_MIN_INTERVAL_SEC:
                        return
                except (ValueError, TypeError):
                    pass
            token["last_used_at"] = now
            _save_user_tokens(username, tokens)
            return
    return


def verify_api_token(plaintext):
    raw = (plaintext or "").strip()
    if not raw.startswith(TOKEN_PREFIX):
        return None
    digest = _hash_token(raw)
    if not API_TOKENS_DIR.is_dir():
        return None
    for path in API_TOKENS_DIR.glob("*.json"):
        username = path.stem
        for token in _load_user_tokens(username):
            if token.get("revoked_at"):
                continue
            if token.get("hash") != digest:
                continue
            _touch_token(username, token.get("id"))
            return {
                "username": username,
                "token_id": token.get("id"),
                "token_name": token.get("name") or "",
                "prefix": token.get("prefix") or "",
            }
    return None
