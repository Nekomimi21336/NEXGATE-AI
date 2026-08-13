"""NEXGATE AI API 用（下流）のシステムAPIキー管理。

ユーザー単位の開発者トークン（ngx_）とは別系統の、管理者が
システムレベルで発行・管理するAPIキー（ngxa_）。

- ストア: data/system_api_keys.json（ユーザーの開発者トークンとは別ファイル）
- プレフィックス: ngxa_（ユーザートークン ngx_ と視覚的・機能的に分離）
- 所有者（owner_username）に課金・レートリミットを紐づける
- scopes で /v1/ の利用範囲を制限可能（未指定 = 全て許可）
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SYSTEM_API_KEYS_FILE = Path(__file__).parent / "data" / "system_api_keys.json"
TOKEN_PREFIX = "ngxa_"
MAX_SYSTEM_API_KEYS = 50
# last_used_at の書き込み間引き（秒）
TOUCH_MIN_INTERVAL_SEC = 60

DEFAULT_SCOPES = ("chat_completions", "models")

_lock = threading.RLock()


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_token(plaintext):
    return hashlib.sha256((plaintext or "").encode("utf-8")).hexdigest()


def _load_keys():
    with _lock:
        if not SYSTEM_API_KEYS_FILE.exists():
            return []
        try:
            with open(SYSTEM_API_KEYS_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, list):
            return []
        return [k for k in raw if isinstance(k, dict)]


def _save_keys(keys):
    with _lock:
        SYSTEM_API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SYSTEM_API_KEYS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(keys, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SYSTEM_API_KEYS_FILE)


def _public_entry(key):
    return {
        "id": key.get("id"),
        "name": key.get("name") or "",
        "owner_username": key.get("owner_username") or "",
        "scopes": list(key.get("scopes") or DEFAULT_SCOPES),
        "prefix": key.get("prefix") or "",
        "created_at": key.get("created_at") or "",
        "last_used_at": key.get("last_used_at") or "",
        "revoked_at": key.get("revoked_at") or "",
        "active": not bool(key.get("revoked_at")),
    }


def list_system_api_keys(*, include_revoked=False):
    rows = []
    for key in _load_keys():
        if key.get("revoked_at") and not include_revoked:
            continue
        rows.append(_public_entry(key))
    rows.sort(key=lambda k: k.get("created_at") or "", reverse=True)
    return rows


def _normalize_scopes(scopes):
    if scopes is None:
        return list(DEFAULT_SCOPES)
    if isinstance(scopes, str):
        scopes = [scopes]
    if not isinstance(scopes, (list, tuple)):
        return list(DEFAULT_SCOPES)
    cleaned = []
    for s in scopes:
        s = (s or "").strip().lower()
        if s:
            cleaned.append(s)
    return cleaned or list(DEFAULT_SCOPES)


def create_system_api_key(name="", owner_username="", scopes=None):
    """システムAPIキーを新規作成。

    owner_username は課金・レートリミットの帰属先（必須）。
    戻り値: (public, secret, err)
    """
    owner = (owner_username or "").strip().lower()
    if not owner:
        return None, "所有者ユーザー名（owner_username）は必須です"
    with _lock:
        keys = _load_keys()
        active = [k for k in keys if not k.get("revoked_at")]
        if len(active) >= MAX_SYSTEM_API_KEYS:
            return None, f"システムAPIキーは最大{MAX_SYSTEM_API_KEYS}件までです"

        key_id = str(uuid.uuid4())
        secret = secrets.token_urlsafe(32)
        plaintext = f"{TOKEN_PREFIX}{secret}"
        prefix = plaintext[:12]
        now = _now_iso()
        entry = {
            "id": key_id,
            "name": (name or "").strip()[:64] or "System API Key",
            "owner_username": owner,
            "scopes": _normalize_scopes(scopes),
            "prefix": prefix,
            "hash": _hash_token(plaintext),
            "created_at": now,
            "last_used_at": "",
            "revoked_at": "",
        }
        keys.append(entry)
        _save_keys(keys)
    return {"token": _public_entry(entry), "secret": plaintext}, None


def revoke_system_api_key(key_id):
    key_id = (key_id or "").strip()
    with _lock:
        keys = _load_keys()
        changed = False
        for key in keys:
            if key.get("id") != key_id:
                continue
            if key.get("revoked_at"):
                return True
            key["revoked_at"] = _now_iso()
            changed = True
            break
        if not changed:
            return False
        _save_keys(keys)
        return True


def _touch_key(key_id):
    """last_used_at を更新。短時間の再認証では書き込みを省略し、
    並列リクエスト時のファイル競合とI/Oコストを抑える。"""
    now = _now_iso()
    with _lock:
        keys = _load_keys()
        for key in keys:
            if key.get("id") != key_id:
                continue
            last = key.get("last_used_at") or ""
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
                    if (now_dt - last_dt).total_seconds() < TOUCH_MIN_INTERVAL_SEC:
                        return
                except (ValueError, TypeError):
                    pass
            key["last_used_at"] = now
            _save_keys(keys)
            return
        return


def verify_system_api_key(plaintext):
    """平文キーを検証し、有効なら公開情報を返す。無効なら None。"""
    raw = (plaintext or "").strip()
    if not raw.startswith(TOKEN_PREFIX):
        return None
    digest = _hash_token(raw)
    for key in _load_keys():
        if key.get("revoked_at"):
            continue
        if key.get("hash") != digest:
            continue
        _touch_key(key.get("id"))
        return {
            "key_id": key.get("id"),
            "key_name": key.get("name") or "",
            "owner_username": key.get("owner_username") or "",
            "scopes": list(key.get("scopes") or DEFAULT_SCOPES),
            "prefix": key.get("prefix") or "",
        }
    return None
