from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal, Optional

from flask import request, session

from api_tokens_storage import verify_api_token
from server_split import INTERNAL_API_KEY_HEADER, internal_api_key
from system_api_keys import verify_system_api_key

AuthKind = Literal["internal", "session", "token", "system", "none"]


@dataclass
class ApiAuthContext:
    kind: AuthKind
    username: str
    token_id: Optional[str] = None
    unlimited: bool = False
    scopes: Optional[list] = None


def _bearer_token():
    header = (request.headers.get("Authorization") or "").strip()
    if not header.lower().startswith("bearer "):
        return ""
    return header[7:].strip()


def _user_record_for_username(username: str):
    key = (username or "").strip().lower()
    if not key:
        return {}
    app_mod = sys.modules.get("app")
    if app_mod is None or not hasattr(app_mod, "load_users"):
        return {}
    return app_mod.load_users().get(key, {}) or {}


def resolve_api_auth(
    *,
    allow_internal: bool = True,
    allow_session: bool = True,
    allow_bearer: bool = True,
) -> ApiAuthContext:
    if allow_internal:
        configured = internal_api_key()
        incoming = (request.headers.get(INTERNAL_API_KEY_HEADER) or "").strip()
        if configured and incoming and configured == incoming:
            user = session.get("user") or {}
            username = (user.get("username") or "").strip().lower()
            if username:
                return ApiAuthContext(
                    kind="internal",
                    username=username,
                    unlimited=True,
                )

    if allow_bearer:
        bearer = _bearer_token()
        if bearer:
            verified = verify_api_token(bearer)
            if verified:
                username = (verified.get("username") or "").strip().lower()
                record = _user_record_for_username(username)
                if user_api_access_enabled(record):
                    return ApiAuthContext(
                        kind="token",
                        username=username,
                        token_id=verified.get("token_id"),
                        unlimited=False,
                    )

            # NEXGATE AI API 用のシステムAPIキー（ngxa_）
            sys_verified = verify_system_api_key(bearer)
            if sys_verified:
                username = (sys_verified.get("owner_username") or "").strip().lower()
                record = _user_record_for_username(username)
                if user_api_access_enabled(record):
                    return ApiAuthContext(
                        kind="system",
                        username=username,
                        token_id=sys_verified.get("key_id"),
                        unlimited=False,
                        scopes=sys_verified.get("scopes") or None,
                    )

    if allow_session:
        user = session.get("user") or {}
        username = (user.get("username") or "").strip().lower()
        if username:
            return ApiAuthContext(
                kind="session",
                username=username,
                unlimited=False,
            )

    return ApiAuthContext(kind="none", username="")


def user_plan_api_access_allowed(record) -> bool:
    if not record:
        return False
    if bool(record.get("api_access_bypass_plan")):
        return True
    app_mod = sys.modules.get("app")
    if app_mod is not None and hasattr(app_mod, "effective_plan_for_features"):
        plan = app_mod.effective_plan_for_features(record)
    else:
        plan = (record.get("plan") or "free").strip().lower()
    if app_mod is not None and hasattr(app_mod, "plan_api_access_enabled"):
        return bool(app_mod.plan_api_access_enabled(plan))
    return plan not in ("", "free")


def user_api_access_enabled(record) -> bool:
    if not record:
        return False
    if not bool(record.get("api_enabled")):
        return False
    return user_plan_api_access_allowed(record)
