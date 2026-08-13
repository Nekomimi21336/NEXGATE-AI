"""data/ ディレクトリの保持ポリシーに基づくクリーンアップ。"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent

DEFAULT_REQUEST_DETAILS_RETENTION_DAYS = 30


def _retention_days(env_name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(env_name, str(default)).strip()))
    except (TypeError, ValueError):
        return default


def prune_request_details(*, days: int | None = None, dry_run: bool = False) -> int:
    """data/request_details 内の古い JSON を削除する。

    request_details はリクエスト単位のデバッグログであり、ユーザーに
    直接見えるデータではないため、保持日数を過ぎたものを自動削除する。
    """
    if days is None:
        days = _retention_days(
            "REQUEST_DETAILS_RETENTION_DAYS", DEFAULT_REQUEST_DETAILS_RETENTION_DAYS
        )
    folder = ROOT / "data" / "request_details"
    if not folder.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for path in folder.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            if not dry_run:
                try:
                    path.unlink()
                except OSError as exc:
                    logger.warning("failed to remove %s: %s", path, exc)
                    continue
            removed += 1
    return removed


def run_cleanup_on_startup() -> None:
    """サーバー起動時に一度だけ実行するクリーンアップ。"""
    try:
        removed = prune_request_details()
        if removed:
            logger.info("request_details cleanup: removed %d old file(s)", removed)
    except Exception:
        logger.exception("request_details cleanup failed")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    print(f"prune_request_details(dry_run={dry}) -> {prune_request_details(dry_run=dry)}")
