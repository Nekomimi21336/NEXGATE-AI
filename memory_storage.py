import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

MEMORY_DIR = Path(__file__).parent / "data" / "memory"
CATEGORIES = frozenset({"person", "conversation", "thing", "general"})
SOURCES = frozenset({"chat", "manual"})
PROMPT_MAX_ENTRIES = 40
PROMPT_MAX_CONTENT_LEN = 800


def _memory_path(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return MEMORY_DIR / f"{safe}.json"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_entry(raw):
    if not isinstance(raw, dict):
        return None
    entry_id = (raw.get("id") or "").strip() or str(uuid.uuid4())
    category = (raw.get("category") or "general").strip().lower()
    if category not in CATEGORIES:
        category = "general"
    created = (raw.get("created_at") or "").strip() or _now_iso()
    updated = (raw.get("updated_at") or "").strip() or created
    source = (raw.get("source") or "manual").strip().lower()
    if source not in SOURCES:
        source = "manual"
    return {
        "id": entry_id,
        "category": category,
        "title": str(raw.get("title") or ""),
        "content": str(raw.get("content") or ""),
        "source": source,
        "created_at": created,
        "updated_at": updated,
    }


def load_user_memories(username):
    path = _memory_path(username)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    entries = []
    for item in raw:
        norm = _normalize_entry(item)
        if norm:
            entries.append(norm)
    return entries


def save_user_memories(username, entries):
    normalized = []
    for item in entries or []:
        norm = _normalize_entry(item)
        if norm:
            normalized.append(norm)
    path = _memory_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized


def add_memory(
    username,
    title="",
    content="",
    category="general",
    source="manual",
):
    entries = load_user_memories(username)
    now = _now_iso()
    cat = (category or "general").strip().lower()
    if cat not in CATEGORIES:
        cat = "general"
    src = (source or "manual").strip().lower()
    if src not in SOURCES:
        src = "manual"
    entry = {
        "id": str(uuid.uuid4()),
        "category": cat,
        "title": str(title or ""),
        "content": str(content or ""),
        "source": src,
        "created_at": now,
        "updated_at": now,
    }
    entries.append(entry)
    save_user_memories(username, entries)
    return entry, None


def build_memory_summary(entries):
    summary = {
        "total": len(entries),
        "by_category": {cat: 0 for cat in sorted(CATEGORIES)},
    }
    for e in entries:
        cat = e.get("category") or "general"
        if cat not in summary["by_category"]:
            summary["by_category"][cat] = 0
        summary["by_category"][cat] += 1
    return summary


def update_memory(username, entry_id, title=None, content=None, category=None):
    entries = load_user_memories(username)
    target = None
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            target = i
            break
    if target is None:
        return None, "Memory not found"
    entry = dict(entries[target])
    if title is not None:
        entry["title"] = str(title)
    if content is not None:
        entry["content"] = str(content)
    if category is not None:
        cat = str(category).strip().lower()
        if cat in CATEGORIES:
            entry["category"] = cat
    entry["updated_at"] = _now_iso()
    entries[target] = entry
    save_user_memories(username, entries)
    return entry, None


def delete_memory(username, entry_id):
    entries = load_user_memories(username)
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries):
        return False, "Memory not found"
    save_user_memories(username, new_entries)
    return True, None


def list_memories_summary(username, max_entries=40):
    entries = load_user_memories(username)
    limit = max(1, min(int(max_entries or 40), 80))
    summary = []
    for e in entries[:limit]:
        content = (e.get("content") or "")[:500]
        summary.append(
            {
                "id": e.get("id"),
                "category": e.get("category"),
                "title": e.get("title") or "",
                "content": content,
                "source": e.get("source") or "manual",
                "updated_at": e.get("updated_at"),
            }
        )
    return {"count": len(entries), "memories": summary}


def format_memories_for_prompt(username, max_entries=PROMPT_MAX_ENTRIES):
    entries = load_user_memories(username)
    if not entries:
        return ""
    limit = max(1, min(int(max_entries or PROMPT_MAX_ENTRIES), PROMPT_MAX_ENTRIES))
    lines = []
    for e in entries[-limit:]:
        title = (e.get("title") or "").strip()
        content = (e.get("content") or "").strip()
        if len(content) > PROMPT_MAX_CONTENT_LEN:
            content = content[:PROMPT_MAX_CONTENT_LEN] + "…"
        cat = e.get("category") or "general"
        label = title or "(無題)"
        if content:
            lines.append(f"- [{cat}] {label}: {content}")
        elif title:
            lines.append(f"- [{cat}] {label}")
    if not lines:
        return ""
    return "\n".join(lines)
