import json
import time
import uuid
from pathlib import Path

from google_services import format_tool_result

TASKS_DIR = Path(__file__).parent / "data" / "tasks"
CARD_TYPES = frozenset({"todo", "task", "list", "memo"})
CARD_WIDTH = 260
CARD_GAP = 16


def resolve_user_tasks_enabled(record, plan_tasks_enabled):
    if not record:
        return False
    plan = (record.get("plan") or "free").strip().lower()
    if not plan_tasks_enabled(plan):
        return False
    if "tasks_enabled" in record:
        return bool(record.get("tasks_enabled"))
    return False


def resolve_user_memory_enabled(record, plan_memory_enabled):
    if not record:
        return False
    plan = (record.get("plan") or "free").strip().lower()
    if not plan_memory_enabled(plan):
        return False
    if "memory_enabled" in record:
        return bool(record.get("memory_enabled"))
    return False


def _tasks_path(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return TASKS_DIR / f"{safe}.json"


def _empty_state():
    return {"layoutMode": "free", "cards": []}


def normalize_tasks_state(raw):
    if not isinstance(raw, dict):
        return _empty_state()
    layout = raw.get("layoutMode")
    cards_in = raw.get("cards")
    if not isinstance(cards_in, list):
        return _empty_state()
    cards = []
    for c in cards_in:
        if not isinstance(c, dict):
            continue
        ctype = (c.get("type") or "").strip().lower()
        if ctype not in CARD_TYPES:
            continue
        card_id = (c.get("id") or "").strip() or str(uuid.uuid4())
        items = []
        if ctype in ("todo", "list"):
            for item in c.get("items") or []:
                if not isinstance(item, dict):
                    continue
                items.append(
                    {
                        "id": (item.get("id") or "").strip() or str(uuid.uuid4()),
                        "text": str(item.get("text") or ""),
                        "done": bool(item.get("done")),
                    }
                )
        cards.append(
            {
                "id": card_id,
                "type": ctype,
                "title": str(c.get("title") or ""),
                "body": str(c.get("body") or ""),
                "items": items,
                "x": c.get("x"),
                "y": c.get("y"),
                "createdAt": int(c.get("createdAt") or time.time() * 1000),
            }
        )
    return {
        "layoutMode": "grid" if layout == "grid" else "free",
        "cards": cards,
    }


def load_user_tasks(username):
    path = _tasks_path(username)
    if not path.exists():
        return _empty_state()
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_state()
    return normalize_tasks_state(raw)


def save_user_tasks(username, state):
    normalized = normalize_tasks_state(state)
    path = _tasks_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized


def _default_position(index):
    col = index % 4
    row = index // 4
    return {
        "x": 24 + col * (CARD_WIDTH + CARD_GAP),
        "y": 24 + row * (CARD_GAP + 120),
    }


def _new_item(text=""):
    return {"id": str(uuid.uuid4()), "text": text or "", "done": False}


def create_task_card(
    username,
    card_type,
    title="",
    body="",
    items=None,
    x=None,
    y=None,
):
    ctype = (card_type or "").strip().lower()
    if ctype not in CARD_TYPES:
        return None, f"Invalid type: {card_type!r} (use todo|task|list|memo)"

    state = load_user_tasks(username)
    index = len(state["cards"])
    pos = _default_position(index)
    card_items = []
    if ctype in ("todo", "list"):
        raw_items = items if isinstance(items, list) else []
        if raw_items:
            for entry in raw_items:
                if isinstance(entry, dict):
                    card_items.append(
                        {
                            "id": str(uuid.uuid4()),
                            "text": str(entry.get("text") or entry.get("label") or ""),
                            "done": bool(entry.get("done")),
                        }
                    )
                else:
                    card_items.append(_new_item(str(entry)))
        else:
            card_items = [_new_item("")]

    card = {
        "id": str(uuid.uuid4()),
        "type": ctype,
        "title": str(title or ""),
        "body": str(body or ""),
        "items": card_items,
        "x": float(x) if x is not None else pos["x"],
        "y": float(y) if y is not None else pos["y"],
        "createdAt": int(time.time() * 1000),
    }
    if ctype == "memo" and not card["body"] and card["title"]:
        card["body"] = card["title"]
    state["cards"].append(card)
    save_user_tasks(username, state)
    return card, None


def list_task_cards_summary(username, max_cards=40):
    state = load_user_tasks(username)
    cards = state.get("cards") or []
    summary = []
    for c in cards[: max(1, min(int(max_cards or 40), 80))]:
        entry = {
            "id": c.get("id"),
            "type": c.get("type"),
            "title": c.get("title") or "",
        }
        if c.get("type") in ("todo", "list"):
            entry["items"] = [
                {"text": i.get("text", ""), "done": bool(i.get("done"))}
                for i in (c.get("items") or [])
            ]
        elif c.get("type") == "task":
            body = (c.get("body") or "")[:500]
            if body:
                entry["body"] = body
        elif c.get("type") == "memo":
            text = (c.get("body") or c.get("title") or "")[:500]
            if text:
                entry["body"] = text
        summary.append(entry)
    return {
        "layoutMode": state.get("layoutMode", "free"),
        "count": len(cards),
        "cards": summary,
    }
