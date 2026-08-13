import json
from pathlib import Path

ANNOUNCEMENTS_FILE = Path(__file__).parent / "data" / "announcements.json"


def _load_raw() -> list:
    if not ANNOUNCEMENTS_FILE.exists():
        return []
    try:
        with ANNOUNCEMENTS_FILE.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        items = data.get("announcements")
        return items if isinstance(items, list) else []
    return data if isinstance(data, list) else []


def list_announcements() -> list[dict]:
    items = []
    for row in _load_raw():
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not item_id or not title:
            continue
        items.append(
            {
                "id": item_id,
                "title": title,
                "body": str(row.get("body") or ""),
                "published_at": str(row.get("published_at") or ""),
            }
        )
    items.sort(key=lambda row: row.get("published_at") or "", reverse=True)
    return items
