#!/usr/bin/env python
"""
realtime_summary.py - セッション履歴のリアルタイム要約

バックグラウンドで定期実行し、長いセッションの履歴を自動要約する。
要約結果は次回の応答時にコンテキストとして利用される。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
SUMMARY_FILE = DATA_DIR / "session_summaries.json"

# 要約を開始するメッセージ数
MIN_MESSAGES_FOR_SUMMARY = 20
# 要約を開始する概算トークン数
MIN_TOKENS_FOR_SUMMARY = 6000
# 要約生成間隔（秒）
SUMMARY_INTERVAL = 300


def _estimate_tokens(messages):
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(part.get("text", "")) // 4
    return total


def _make_naive_summary(messages, max_lines=50):
    """LLMを使わない簡易要約（フォールバック）"""
    lines = []
    for m in messages[-min(len(messages), max_lines * 2):]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        text = str(content)[:120]
        if text.strip():
            label = "ユーザー" if role == "user" else "AI"
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


class SessionSummaryStore:
    """セッション要約の保存・取得"""

    def __init__(self):
        self._lock = threading.Lock()
        self._summaries = {}
        self._load()

    def _load(self):
        try:
            if SUMMARY_FILE.exists():
                with open(SUMMARY_FILE, encoding="utf-8") as f:
                    self._summaries = json.load(f)
        except Exception:
            self._summaries = {}

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._summaries, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.debug("summary save failed: %s", exc)

    def get_summary(self, session_id):
        with self._lock:
            rec = self._summaries.get(session_id) or {}
            return rec.get("summary") or ""

    def update_summary(self, session_id, summary, message_count, token_estimate):
        with self._lock:
            self._summaries[session_id] = {
                "summary": summary,
                "message_count": int(message_count),
                "token_estimate": int(token_estimate),
                "updated_at": datetime.now().isoformat(),
            }
            self._save()

    def get_all(self):
        with self._lock:
            return dict(self._summaries)


# グローバルインスタンス
_summary_store = SessionSummaryStore()


def get_summary_store():
    return _summary_store


def needs_summary(messages):
    """セッション履歴が要約対象か判定"""
    if not messages or len(messages) < MIN_MESSAGES_FOR_SUMMARY:
        return False
    return _estimate_tokens(messages) >= MIN_TOKENS_FOR_SUMMARY


def summarize_session(session_id, messages):
    """セッション履歴を要約する（現在は簡易要約。LLM要約は将来拡張）"""
    if not messages or not needs_summary(messages):
        return None
    summary = _make_naive_summary(messages)
    _summary_store.update_summary(
        session_id,
        summary,
        len(messages),
        _estimate_tokens(messages),
    )
    return summary


class RealtimeSummarizer:
    """バックグラウンドでセッションを定期要約する"""

    def __init__(self, interval=SUMMARY_INTERVAL):
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._message_source = None

    def set_message_source(self, source_func):
        """セッションIDを受け取りメッセージリストを返す関数を登録"""
        self._message_source = source_func

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="realtime-summarizer")
        self._thread.start()
        logger.info("Realtime summarizer started (interval=%ss)", self._interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self):
        while not self._stop.is_set():
            try:
                self._process_once()
            except Exception as exc:
                logger.debug("summarizer pass failed: %s", exc)
            self._stop.wait(self._interval)

    def _process_once(self):
        if not self._message_source:
            return
        sessions = self._message_source()
        if not isinstance(sessions, dict):
            return
        for session_id, messages in sessions.items():
            try:
                summarize_session(session_id, messages)
            except Exception:
                continue


# グローバルサマライザ
_realtime_summarizer = RealtimeSummarizer()


def get_realtime_summarizer():
    return _realtime_summarizer


def start_realtime_summary():
    """アプリ起動時に呼び出す"""
    get_realtime_summarizer().start()
