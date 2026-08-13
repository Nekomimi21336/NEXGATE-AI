from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "data" / "expert_knowledge"
MAX_ITEMS_PER_EXPERT = 500
MAX_TITLE_LEN = 200
MAX_CONTENT_LEN = 120_000
MAX_SOURCE_URL_LEN = 2000
MAX_TAGS = 20
MAX_TAG_LEN = 40


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(text, limit):
    s = str(text or "").strip()
    if len(s) > limit:
        return s[:limit]
    return s


def _knowledge_path(username, expert_id):
    safe_user = (username or "").strip().lower()
    safe_expert = (expert_id or "").strip()
    if not safe_user or not safe_expert:
        raise ValueError("username and expert_id required")
    return KNOWLEDGE_DIR / safe_user / f"{safe_expert}.json"


def _load_store(username, expert_id):
    path = _knowledge_path(username, expert_id)
    if not path.is_file():
        return {"items": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"items": []}
    items = data.get("items") if isinstance(data, dict) else []
    return {"items": items if isinstance(items, list) else []}


def _save_store(username, expert_id, store):
    path = _knowledge_path(username, expert_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _normalize_tags(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        tag = _clip(item, MAX_TAG_LEN)
        if tag and tag not in out:
            out.append(tag)
        if len(out) >= MAX_TAGS:
            break
    return out


def normalize_knowledge_item(raw, *, existing_id=None):
    if not isinstance(raw, dict):
        return None
    item_id = (raw.get("id") or existing_id or "").strip() or str(uuid.uuid4())
    title = _clip(raw.get("title"), MAX_TITLE_LEN) or "無題"
    content = _clip(raw.get("content"), MAX_CONTENT_LEN)
    if not content:
        return None
    return {
        "id": item_id,
        "title": title,
        "content": content,
        "source_url": _clip(raw.get("source_url"), MAX_SOURCE_URL_LEN),
        "tags": _normalize_tags(raw.get("tags")),
        "crawl_session_id": _clip(raw.get("crawl_session_id"), 64),
        "created_at": (raw.get("created_at") or _now_iso()),
        "updated_at": (raw.get("updated_at") or raw.get("created_at") or _now_iso()),
    }


def serialize_knowledge_item(item):
    if not item:
        return None
    return {
        "id": item.get("id") or "",
        "title": item.get("title") or "",
        "content": item.get("content") or "",
        "source_url": item.get("source_url") or "",
        "tags": list(item.get("tags") or []),
        "crawl_session_id": item.get("crawl_session_id") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
    }


def list_knowledge_items(username, expert_id, *, max_items=80):
    store = _load_store(username, expert_id)
    items = []
    for raw in store.get("items") or []:
        item = normalize_knowledge_item(raw)
        if item:
            items.append(item)
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return [serialize_knowledge_item(i) for i in items[:max_items]]


def list_knowledge_summaries(username, expert_id, *, max_items=40):
    return [
        {
            "id": i["id"],
            "title": i["title"],
            "source_url": i.get("source_url") or "",
            "tags": i.get("tags") or [],
            "content_preview": (i.get("content") or "")[:240],
            "updated_at": i.get("updated_at") or "",
        }
        for i in list_knowledge_items(username, expert_id, max_items=max_items)
    ]


def get_knowledge_item(username, expert_id, item_id):
    item_id = (item_id or "").strip()
    for item in list_knowledge_items(username, expert_id, max_items=MAX_ITEMS_PER_EXPERT):
        if item.get("id") == item_id:
            return item
    return None


def upsert_knowledge_item(
    username,
    expert_id,
    *,
    item_id=None,
    title="",
    content="",
    source_url="",
    tags=None,
    crawl_session_id="",
):
    store = _load_store(username, expert_id)
    items = store.get("items") or []
    now = _now_iso()
    target_id = (item_id or "").strip()
    found_idx = -1
    for i, raw in enumerate(items):
        if (raw.get("id") or "").strip() == target_id and target_id:
            found_idx = i
            break
    if found_idx < 0 and len(items) >= MAX_ITEMS_PER_EXPERT:
        return None, "知識ベースの上限に達しています"
    merged = {
        "id": target_id or str(uuid.uuid4()),
        "title": title,
        "content": content,
        "source_url": source_url,
        "tags": tags,
        "crawl_session_id": crawl_session_id,
        "created_at": items[found_idx].get("created_at") if found_idx >= 0 else now,
        "updated_at": now,
    }
    if found_idx >= 0:
        merged["created_at"] = items[found_idx].get("created_at") or now
    entry = normalize_knowledge_item(merged, existing_id=merged["id"])
    if not entry:
        return None, "content が必要です"
    if found_idx >= 0:
        items[found_idx] = entry
    else:
        items.append(entry)
    store["items"] = items
    _save_store(username, expert_id, store)
    return serialize_knowledge_item(entry), None


def delete_knowledge_item(username, expert_id, item_id):
    item_id = (item_id or "").strip()
    store = _load_store(username, expert_id)
    items = store.get("items") or []
    next_items = [i for i in items if (i.get("id") or "").strip() != item_id]
    if len(next_items) == len(items):
        return False, "項目が見つかりません"
    store["items"] = next_items
    _save_store(username, expert_id, store)
    return True, None


def delete_all_knowledge(username, expert_id):
    path = _knowledge_path(username, expert_id)
    if path.is_file():
        path.unlink(missing_ok=True)
    return True


def search_knowledge_items(username, expert_id, query, *, max_results=12):
    q = (query or "").strip().lower()
    if not q:
        return list_knowledge_summaries(username, expert_id, max_items=max_results)
    tokens = [t for t in re.split(r"\s+", q) if t]
    scored = []
    for item in list_knowledge_items(username, expert_id, max_items=MAX_ITEMS_PER_EXPERT):
        hay = " ".join(
            [
                item.get("title") or "",
                item.get("content") or "",
                item.get("source_url") or "",
                " ".join(item.get("tags") or []),
            ]
        ).lower()
        score = sum(1 for t in tokens if t in hay)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1].get("updated_at") or ""), reverse=True)
    return [
        {
            "id": i["id"],
            "title": i["title"],
            "source_url": i.get("source_url") or "",
            "tags": i.get("tags") or [],
            "snippet": _clip(_extract_snippet(i.get("content") or "", q), 400),
            "score": score,
        }
        for score, i in scored[:max_results]
    ]


def _extract_snippet(content, query):
    lower = content.lower()
    pos = lower.find((query or "").strip().lower())
    if pos < 0:
        return content[:300]
    start = max(0, pos - 80)
    end = min(len(content), pos + 220)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet += "…"
    return snippet


def format_knowledge_for_prompt(username, expert_id, *, max_items=12, max_chars=12000):
    items = list_knowledge_items(username, expert_id, max_items=max_items)
    if not items:
        return ""
    parts = ["## 専門家の知識ベース（参照用）"]
    used = 0
    for item in items:
        block = (
            f"### [{item['id']}] {item['title']}\n"
            f"URL: {item.get('source_url') or '(なし)'}\n"
            f"{item.get('content') or ''}"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)
