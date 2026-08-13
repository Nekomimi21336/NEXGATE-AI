#!/usr/bin/env python
"""
feedback.py - ユーザーフィードバック収集とA/Bテスト基盤

👍/👎 フィードバックと回答品質評価を収集し、A/Bテストの割り当てと
結果集計を行う。
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FEEDBACK_FILE = DATA_DIR / "feedback.json"
AB_ASSIGN_FILE = DATA_DIR / "ab_assignments.json"

# A/Bテスト対象のバリエーション
AB_VARIANTS = {
    # プロンプト最適化実験
    "system_prompt": {
        "name": "システムプロンプト最適化",
        "variants": ["standard", "concise", "detailed"],
        "description": "システムプロンプトの長さ・詳細度の違い",
    },
    # 検索ラウンド数実験
    "search_rounds": {
        "name": "検索ラウンド数",
        "variants": ["auto", "max2", "max4"],
        "description": "Web検索の最大ラウンド数の違い",
    },
    # 応答文体実験
    "response_style": {
        "name": "応答文体",
        "variants": ["default", "concise", "bulleted"],
        "description": "回答の文体・フォーマットの違い",
    },
}


class FeedbackStore:
    """フィードバックの収集・保存"""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = []
        self._load()

    def _load(self):
        try:
            if FEEDBACK_FILE.exists():
                with open(FEEDBACK_FILE, encoding="utf-8") as f:
                    self._items = json.load(f)
        except Exception:
            self._items = []

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.debug("feedback save failed: %s", exc)

    def add_feedback(self, *, username="", session_id="", message_index=0, rating=0, comment="", variant=None):
        """フィードバックを記録。rating: 1=👍, -1=👎, 0=中立"""
        with self._lock:
            item = {
                "id": str(uuid.uuid4()),
                "ts": datetime.now().isoformat(),
                "username": username,
                "session_id": session_id,
                "message_index": int(message_index or 0),
                "rating": int(rating or 0),
                "comment": (comment or "")[:500],
                "variant": variant,
            }
            self._items.append(item)
            self._save()
        return item["id"]

    def get_summary(self):
        with self._lock:
            total = len(self._items)
            pos = sum(1 for i in self._items if i["rating"] > 0)
            neg = sum(1 for i in self._items if i["rating"] < 0)
            by_variant = defaultdict(lambda: {"pos": 0, "neg": 0, "total": 0})
            for i in self._items:
                v = i.get("variant") or "default"
                by_variant[v]["total"] += 1
                if i["rating"] > 0:
                    by_variant[v]["pos"] += 1
                elif i["rating"] < 0:
                    by_variant[v]["neg"] += 1
            return {
                "total": total,
                "positive": pos,
                "negative": neg,
                "positive_rate": round(pos / total, 3) if total else 0,
                "by_variant": {k: dict(v) for k, v in by_variant.items()},
                "recent": list(self._items)[-20:],
            }


class ABTestManager:
    """A/Bテストの割り当て管理"""

    def __init__(self):
        self._lock = threading.Lock()
        self._assignments = {}
        self._load()

    def _load(self):
        try:
            if AB_ASSIGN_FILE.exists():
                with open(AB_ASSIGN_FILE, encoding="utf-8") as f:
                    self._assignments = json.load(f)
        except Exception:
            self._assignments = {}

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(AB_ASSIGN_FILE, "w", encoding="utf-8") as f:
                json.dump(self._assignments, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.debug("ab save failed: %s", exc)

    def get_variant(self, username, experiment):
        """ユーザーに実験のバリアントを割り当てる（一貫性を保つ）"""
        if experiment not in AB_VARIANTS:
            return None
        with self._lock:
            key = f"{username}:{experiment}"
            if key in self._assignments:
                return self._assignments[key]
            variants = AB_VARIANTS[experiment]["variants"]
            # ラウンドロビンで割り当て
            counts = defaultdict(int)
            for k, v in self._assignments.items():
                if k.endswith(f":{experiment}"):
                    counts[v] += 1
            # 最も少ないバリアントを選択
            variant = min(variants, key=lambda v: counts.get(v, 0))
            self._assignments[key] = variant
            self._save()
            return variant

    def get_all_assignments(self):
        with self._lock:
            return dict(self._assignments)


# グローバルインスタンス
_feedback = FeedbackStore()
_ab = ABTestManager()


def get_feedback_store():
    return _feedback


def get_ab_manager():
    return _ab


def add_user_feedback(**kwargs):
    return _feedback.add_feedback(**kwargs)


def get_feedback_summary():
    return _feedback.get_summary()


def assign_variant(username, experiment):
    return _ab.get_variant(username, experiment)
