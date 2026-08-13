from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

INFO_EXPERTS_DIR = Path(__file__).parent / "data" / "info_experts"
MAX_EXPERTS_PER_USER = 50
MAX_NAME_LEN = 80
MAX_DESCRIPTION_LEN = 400
MAX_INSTRUCTIONS_LEN = 12000
DEFAULT_EXPERT_NAME = "新しい専門家"


def _experts_path(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return INFO_EXPERTS_DIR / f"{safe}.json"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(text, limit):
    s = str(text or "").strip()
    if len(s) > limit:
        return s[:limit]
    return s


def _load_store(username):
    path = _experts_path(username)
    if not path.exists():
        return {"experts": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"experts": []}
    experts = data.get("experts") if isinstance(data, dict) else []
    return {"experts": experts if isinstance(experts, list) else []}


def _save_store(username, store):
    INFO_EXPERTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _experts_path(username)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def default_expert_name(experts):
    existing = {(e.get("name") or "").strip() for e in experts or []}
    if DEFAULT_EXPERT_NAME not in existing:
        return DEFAULT_EXPERT_NAME
    n = 2
    while f"{DEFAULT_EXPERT_NAME} {n}" in existing:
        n += 1
    return f"{DEFAULT_EXPERT_NAME} {n}"


def normalize_expert(raw, *, experts=None):
    if not isinstance(raw, dict):
        return None
    expert_id = (raw.get("id") or "").strip() or str(uuid.uuid4())
    name = _clip(raw.get("name"), MAX_NAME_LEN) or default_expert_name(experts or [])
    return {
        "id": expert_id,
        "name": name,
        "description": _clip(raw.get("description"), MAX_DESCRIPTION_LEN),
        "instructions": _clip(raw.get("instructions"), MAX_INSTRUCTIONS_LEN),
        "created_at": (raw.get("created_at") or _now_iso()),
        "updated_at": (raw.get("updated_at") or raw.get("created_at") or _now_iso()),
    }


def serialize_expert(expert):
    if not expert:
        return None
    return {
        "id": expert.get("id") or "",
        "name": expert.get("name") or "",
        "description": expert.get("description") or "",
        "instructions": expert.get("instructions") or "",
        "created_at": expert.get("created_at") or "",
        "updated_at": expert.get("updated_at") or "",
    }


def load_user_info_experts(username):
    store = _load_store(username)
    experts = []
    for raw in store.get("experts") or []:
        item = normalize_expert(raw, experts=experts)
        if item:
            experts.append(item)
    experts.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    return experts


def find_info_expert(username, expert_id):
    expert_id = (expert_id or "").strip()
    if not expert_id:
        return None
    for expert in load_user_info_experts(username):
        if expert.get("id") == expert_id:
            return expert
    return None


def create_info_expert(username, *, name="", description="", instructions=""):
    store = _load_store(username)
    experts = store.get("experts") or []
    if len(experts) >= MAX_EXPERTS_PER_USER:
        return None, "専門家の上限に達しています"
    now = _now_iso()
    entry = normalize_expert(
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "instructions": instructions,
            "created_at": now,
            "updated_at": now,
        },
        experts=experts,
    )
    experts.append(entry)
    store["experts"] = experts
    _save_store(username, store)
    return entry, None


def update_info_expert(username, expert_id, **fields):
    store = _load_store(username)
    experts = store.get("experts") or []
    found = None
    for i, raw in enumerate(experts):
        if (raw.get("id") or "").strip() != (expert_id or "").strip():
            continue
        merged = dict(raw)
        if "name" in fields:
            merged["name"] = fields["name"]
        if "description" in fields:
            merged["description"] = fields["description"]
        if "instructions" in fields:
            merged["instructions"] = fields["instructions"]
        merged["updated_at"] = _now_iso()
        entry = normalize_expert(merged, experts=experts)
        experts[i] = entry
        found = entry
        break
    if not found:
        return None, "専門家が見つかりません"
    store["experts"] = experts
    _save_store(username, store)
    return found, None


def delete_info_expert(username, expert_id):
    store = _load_store(username)
    experts = store.get("experts") or []
    next_experts = [e for e in experts if (e.get("id") or "").strip() != (expert_id or "").strip()]
    if len(next_experts) == len(experts):
        return False, "専門家が見つかりません"
    store["experts"] = next_experts
    _save_store(username, store)
    return True, None
