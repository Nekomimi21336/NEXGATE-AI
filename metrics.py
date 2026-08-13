#!/usr/bin/env python
"""
metrics.py - NEXGATE AI パフォーマンス監視・メトリクス収集

各ステップの処理時間、トークン使用量、ツール使用回数、エラー率を
スレッドセーフに収集する。管理者ダッシュボードや分析用に利用する。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
METRICS_FILE = DATA_DIR / "metrics.json"


class MetricsCollector:
    """スレッドセーフなメトリクス収集器"""

    def __init__(self, max_history=5000):
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._request_count = 0
        self._error_count = 0
        self._total_tokens = 0
        self._tool_usage = defaultdict(int)
        self._step_times = defaultdict(lambda: {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        self._recent_requests = deque(maxlen=max_history)
        self._recent_errors = deque(maxlen=200)

    # ── 基本カウンタ ──
    def record_request(self, *, request_id="", model="", provider="", duration_ms=0, tokens=0, ok=True, error=""):
        with self._lock:
            self._request_count += 1
            self._total_tokens += max(0, int(tokens))
            if not ok:
                self._error_count += 1
            entry = {
                "ts": datetime.now().isoformat(),
                "request_id": request_id,
                "model": model,
                "provider": provider,
                "duration_ms": round(duration_ms, 1),
                "tokens": int(tokens or 0),
                "ok": bool(ok),
                "error": (error or "")[:240],
            }
            self._recent_requests.append(entry)
            if not ok:
                self._recent_errors.append(entry)

    def record_tool_usage(self, tool_name):
        with self._lock:
            self._tool_usage[str(tool_name or "unknown")] += 1

    def record_step_time(self, step, duration_ms):
        with self._lock:
            bucket = self._step_times[str(step or "unknown")]
            bucket["count"] += 1
            bucket["total_ms"] += float(duration_ms)
            bucket["max_ms"] = max(bucket["max_ms"], float(duration_ms))

    def record_error(self, *, context="", error=""):
        with self._lock:
            self._error_count += 1
            self._recent_errors.append({
                "ts": datetime.now().isoformat(),
                "context": (context or "")[:80],
                "error": (error or "")[:240],
            })

    # ── スナップショット ──
    def snapshot(self):
        with self._lock:
            step_stats = {}
            for step, s in self._step_times.items():
                avg = (s["total_ms"] / s["count"]) if s["count"] else 0
                step_stats[step] = {
                    "count": s["count"],
                    "avg_ms": round(avg, 1),
                    "max_ms": round(s["max_ms"], 1),
                }
            return {
                "uptime_sec": round(time.monotonic() - self._started, 1),
                "request_count": self._request_count,
                "error_count": self._error_count,
                "error_rate": round((self._error_count / self._request_count), 4) if self._request_count else 0,
                "total_tokens": self._total_tokens,
                "tool_usage": dict(self._tool_usage),
                "steps": step_stats,
                "recent_requests": list(self._recent_requests)[-50:],
                "recent_errors": list(self._recent_errors)[-20:],
            }

    def to_json(self):
        return json.dumps(self.snapshot(), ensure_ascii=False, indent=2)

    def save_to_file(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(METRICS_FILE, "w", encoding="utf-8") as f:
                f.write(self.to_json())
        except Exception as exc:
            logger.debug("metrics save failed: %s", exc)


# グローバルインスタンス
_metrics = MetricsCollector()


def get_metrics():
    return _metrics


def record_chat_request(**kwargs):
    _metrics.record_request(**kwargs)


def record_tool(tool_name):
    _metrics.record_tool_usage(tool_name)


def record_step(step, duration_ms):
    _metrics.record_step_time(step, duration_ms)


def record_error(context="", error=""):
    _metrics.record_error(context=context, error=error)


# ── コンテキストマネージャ／デコレータ ──
class step_timer:
    """処理時間を計測して記録するコンテキストマネージャ

    with step_timer("prepare_agent_messages"):
        ...
    """

    def __init__(self, step_name):
        self.step_name = step_name

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ms = (time.perf_counter() - self._start) * 1000
        _metrics.record_step_time(self.step_name, ms)
        return False


def timed(step_name):
    """処理時間を計測するデコレータ"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                _metrics.record_step_time(step_name, (time.perf_counter() - start) * 1000)
                return result
            except Exception as exc:
                _metrics.record_step_time(step_name, (time.perf_counter() - start) * 1000)
                _metrics.record_error(context=step_name, error=str(exc))
                raise
        return wrapper
    return decorator


def load_saved_metrics():
    """起動時に前回のメトリクスを読み込む"""
    try:
        if METRICS_FILE.exists():
            with open(METRICS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}
