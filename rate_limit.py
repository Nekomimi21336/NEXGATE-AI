#!/usr/bin/env python
"""
rate_limit.py - API レートリミット

ユーザー単位・APIトークン単位のリクエスト数制限をスライディングウィンドウで
管理する。超過時は HTTP 429 を返す。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# デフォルト制限（1分あたり）
DEFAULT_LIMITS = {
    "user": {"window_sec": 60, "max_requests": 60},   # ユーザー: 60 req/min
    "token": {"window_sec": 60, "max_requests": 120},  # トークン: 120 req/min
    "ip": {"window_sec": 60, "max_requests": 120},     # IP: 120 req/min
}


class SlidingWindowRateLimiter:
    """スライディングウィンドウ方式のレートリミッタ"""

    def __init__(self, limits=None, max_keys=10000):
        self._lock = threading.Lock()
        self._limits = {**DEFAULT_LIMITS, **(limits or {})}
        self._windows = defaultdict(deque)  # key -> deque of timestamps
        self._max_keys = max_keys

    def _prune(self, key, window_sec):
        now = time.monotonic()
        dq = self._windows[key]
        while dq and now - dq[0] > window_sec:
            dq.popleft()
        return dq

    def check(self, key, kind="user"):
        """現在のウィンドウで許可されるか判定。許可なら True、超過なら False"""
        if not key:
            return True
        limit_cfg = self._limits.get(kind) or self._limits["user"]
        window_sec = int(limit_cfg.get("window_sec") or 60)
        max_requests = int(limit_cfg.get("max_requests") or 60)
        with self._lock:
            dq = self._prune(key, window_sec)
            if len(dq) >= max_requests:
                return False
            dq.append(time.monotonic())
            if len(self._windows) > self._max_keys:
                # 古いキーを整理（簡易対策）
                self._trim_lru()
            return True

    def _trim_lru(self):
        # 最も古いアクセスのキーを一部削除
        now = time.monotonic()
        for key in list(self._windows.keys()):
            dq = self._windows[key]
            if not dq or now - dq[-1] > 3600:
                del self._windows[key]

    def remaining(self, key, kind="user"):
        limit_cfg = self._limits.get(kind) or self._limits["user"]
        window_sec = int(limit_cfg.get("window_sec") or 60)
        max_requests = int(limit_cfg.get("max_requests") or 60)
        with self._lock:
            dq = self._prune(key, window_sec)
            return max(0, max_requests - len(dq))

    def reset(self):
        with self._lock:
            self._windows.clear()


# グローバルインスタンス
_limiter = SlidingWindowRateLimiter()


def get_limiter():
    return _limiter


def check_rate_limit(*, username="", token_id="", ip=""):
    """リクエストをチェック。結果と429応答用の情報を返す。

    Returns: (allowed: bool, retry_after_sec: int, detail: dict)
    """
    limiter = get_limiter()

    # ユーザー単位
    if username:
        if not limiter.check(username, kind="user"):
            return False, _retry_after(username, "user"), {"kind": "user", "key": username}
    # トークン単位
    if token_id:
        if not limiter.check(f"tok:{token_id}", kind="token"):
            return False, _retry_after(f"tok:{token_id}", "token"), {"kind": "token"}
    # IP単位
    if ip:
        if not limiter.check(f"ip:{ip}", kind="ip"):
            return False, _retry_after(f"ip:{ip}", "ip"), {"kind": "ip"}

    return True, 0, {}


def _retry_after(key, kind):
    limit_cfg = DEFAULT_LIMITS.get(kind) or DEFAULT_LIMITS["user"]
    window_sec = int(limit_cfg.get("window_sec") or 60)
    with get_limiter()._lock:
        dq = get_limiter()._windows.get(key)
        if dq:
            oldest = dq[0]
            now = time.monotonic()
            wait = int(window_sec - (now - oldest)) + 1
            return max(1, wait)
    return window_sec
