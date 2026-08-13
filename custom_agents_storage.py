import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

CUSTOM_AGENTS_DIR = Path(__file__).parent / "data" / "custom_agents"
MAX_AGENTS_PER_USER = 30
MAX_NAME_LEN = 80
MAX_DESCRIPTION_LEN = 400
MAX_INSTRUCTIONS_LEN = 12000
MAX_KNOWLEDGE_LEN = 80000
MAX_KNOWLEDGE_ITEMS = 50
MAX_KNOWLEDGE_TITLE_LEN = 120
MAX_KNOWLEDGE_TAGS_LEN = 200
MAX_KNOWLEDGE_ITEM_CONTENT_LEN = 16000
MAX_MODEL_ID_LEN = 120
SHARE_ID_RE = re.compile(r"^[a-f0-9]{32}$")

VISIBILITY_PRIVATE = "private"
VISIBILITY_UNLISTED = "unlisted"
VISIBILITY_PUBLIC = "public"
VALID_VISIBILITIES = {
    VISIBILITY_PRIVATE,
    VISIBILITY_UNLISTED,
    VISIBILITY_PUBLIC,
}

REASONING_DISPLAY_FORCE_SHOW = "force_show"
REASONING_DISPLAY_HIDE = "hide"
REASONING_DISPLAY_USER = "user"
VALID_REASONING_DISPLAYS = {
    REASONING_DISPLAY_FORCE_SHOW,
    REASONING_DISPLAY_HIDE,
    REASONING_DISPLAY_USER,
}

DEFAULT_AGENT_NAME = "新しいエージェント"


def _agents_path(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return CUSTOM_AGENTS_DIR / f"{safe}.json"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(text, limit):
    s = str(text or "").strip()
    if len(s) > limit:
        return s[:limit]
    return s


def _normalize_visibility(value):
    vis = (value or VISIBILITY_PRIVATE).strip().lower()
    return vis if vis in VALID_VISIBILITIES else VISIBILITY_PRIVATE


def _normalize_reasoning_display(value, *, legacy_show_reasoning=None):
    mode = (value or "").strip().lower()
    if mode in VALID_REASONING_DISPLAYS:
        return mode
    if legacy_show_reasoning is not None:
        return REASONING_DISPLAY_FORCE_SHOW if legacy_show_reasoning else REASONING_DISPLAY_HIDE
    return REASONING_DISPLAY_HIDE


def _resolve_reasoning_display(raw):
    if isinstance(raw, dict) and raw.get("reasoning_display") is not None:
        return _normalize_reasoning_display(raw.get("reasoning_display"))
    if isinstance(raw, dict) and "show_reasoning" in raw:
        return _normalize_reasoning_display(
            None,
            legacy_show_reasoning=bool(raw.get("show_reasoning")),
        )
    return REASONING_DISPLAY_HIDE


def _new_share_id():
    return uuid.uuid4().hex


def default_custom_agent_name(agents):
    existing = {(a.get("name") or "").strip() for a in agents or []}
    if DEFAULT_AGENT_NAME not in existing:
        return DEFAULT_AGENT_NAME
    n = 2
    while f"{DEFAULT_AGENT_NAME} {n}" in existing:
        n += 1
    return f"{DEFAULT_AGENT_NAME} {n}"


def _resolve_agent_name(raw_name, agents):
    name = _clip(raw_name, MAX_NAME_LEN)
    if name:
        return name
    return default_custom_agent_name(agents)


def _normalize_knowledge_tags(raw):
    if isinstance(raw, list):
        parts = [str(t).strip() for t in raw if str(t).strip()]
    else:
        parts = [t.strip() for t in str(raw or "").replace("、", ",").split(",") if t.strip()]
    deduped = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    return _clip(", ".join(deduped[:20]), MAX_KNOWLEDGE_TAGS_LEN)


def _normalize_knowledge_items(raw_items=None, *, legacy_knowledge=None):
    items = []
    if isinstance(raw_items, list):
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            title = _clip(raw.get("title"), MAX_KNOWLEDGE_TITLE_LEN)
            content = _clip(raw.get("content"), MAX_KNOWLEDGE_ITEM_CONTENT_LEN)
            tags = _normalize_knowledge_tags(raw.get("tags"))
            if not title and not content:
                continue
            items.append(
                {
                    "id": (raw.get("id") or "").strip() or str(uuid.uuid4()),
                    "title": title or "（無題）",
                    "tags": tags,
                    "content": content,
                }
            )
            if len(items) >= MAX_KNOWLEDGE_ITEMS:
                break
    legacy = _clip(legacy_knowledge, MAX_KNOWLEDGE_LEN)
    if not items and legacy:
        items.append(
            {
                "id": str(uuid.uuid4()),
                "title": "（無題）",
                "tags": "",
                "content": legacy,
            }
        )
    total = sum(len((item.get("content") or "")) for item in items)
    if total > MAX_KNOWLEDGE_LEN:
        trimmed = []
        used = 0
        for item in items:
            content = item.get("content") or ""
            room = MAX_KNOWLEDGE_LEN - used
            if room <= 0:
                break
            if len(content) > room:
                content = content[:room]
            trimmed.append({**item, "content": content})
            used += len(content)
        items = trimmed
    return items


def format_knowledge_items_for_prompt(items):
    blocks = []
    for index, item in enumerate(items or [], start=1):
        if not isinstance(item, dict):
            continue
        title = _clip(item.get("title"), MAX_KNOWLEDGE_TITLE_LEN) or "（無題）"
        tags = _normalize_knowledge_tags(item.get("tags"))
        content = (item.get("content") or "").strip()
        if not content:
            continue
        block = f"--- 項目 {index}: {title} ---"
        if tags:
            block += f"\nタグ: {tags}"
        block += f"\n内容:\n{content}"
        blocks.append(block)
    if not blocks:
        return ""
    return (
        "\n【知識ベース】\n"
        "以下の項目を参照してください。質問に関連するタイトル・タグを手がかりに"
        "適切な項目を選び、内容を事実として活用して回答してください。\n\n"
        + "\n\n".join(blocks)
    )


def _apply_visibility_share(agent):
    vis = _normalize_visibility(agent.get("visibility"))
    agent["visibility"] = vis
    share_id = (agent.get("share_id") or "").strip()
    if vis == VISIBILITY_PRIVATE:
        agent["share_id"] = None
    else:
        if not share_id or not SHARE_ID_RE.match(share_id):
            agent["share_id"] = _new_share_id()
    return agent


def _normalize_agent(raw, *, agents_for_name=None):
    if not isinstance(raw, dict):
        return None
    name = _clip(raw.get("name"), MAX_NAME_LEN)
    if not name and agents_for_name is not None:
        name = default_custom_agent_name(agents_for_name)
    if not name:
        return None
    agent_id = (raw.get("id") or "").strip() or str(uuid.uuid4())
    created = (raw.get("created_at") or "").strip() or _now_iso()
    updated = (raw.get("updated_at") or "").strip() or created
    model_id = _clip(raw.get("model_id"), MAX_MODEL_ID_LEN)
    owner_username = (raw.get("owner_username") or "").strip().lower() or None
    agent = {
        "id": agent_id,
        "name": name,
        "description": _clip(raw.get("description"), MAX_DESCRIPTION_LEN),
        "instructions": _clip(raw.get("instructions"), MAX_INSTRUCTIONS_LEN),
        "knowledge_items": _normalize_knowledge_items(
            raw.get("knowledge_items"),
            legacy_knowledge=raw.get("knowledge") if "knowledge_items" not in raw else None,
        ),
        "favorite": bool(raw.get("favorite")),
        "visibility": _normalize_visibility(raw.get("visibility")),
        "share_id": (raw.get("share_id") or "").strip() or None,
        "usage_count": max(0, int(raw.get("usage_count") or 0)),
        "model_id": model_id,
        "force_reasoning": bool(raw.get("force_reasoning")),
        "reasoning_display": _resolve_reasoning_display(raw),
        "show_knowledge": bool(raw.get("show_knowledge")),
        "show_personality": bool(raw.get("show_personality")),
        "owner_username": owner_username,
        "created_at": created,
        "updated_at": updated,
    }
    return _apply_visibility_share(agent)


def custom_agent_viewer_is_owner(agent, viewer_username):
    owner = (agent.get("owner_username") or "").strip().lower()
    viewer = (viewer_username or "").strip().lower()
    return bool(owner and viewer and owner == viewer)


def apply_custom_agent_chat_reasoning_prefs(
    custom_agent,
    viewer_username,
    *,
    emit_reasoning_cards,
    disable_reasoning,
):
    if not custom_agent:
        return emit_reasoning_cards, disable_reasoning
    if custom_agent.get("force_reasoning"):
        disable_reasoning = False
    if not custom_agent_viewer_is_owner(custom_agent, viewer_username):
        mode = _normalize_reasoning_display(custom_agent.get("reasoning_display"))
        if mode == REASONING_DISPLAY_FORCE_SHOW:
            emit_reasoning_cards = True
        elif mode == REASONING_DISPLAY_HIDE:
            emit_reasoning_cards = False
    return emit_reasoning_cards, disable_reasoning


def format_agent_created_label(iso_value):
    raw = (iso_value or "").strip()
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y/%m/%d %H:%M")
    except ValueError:
        return raw[:16] if len(raw) >= 16 else raw


def enrich_custom_agent(agent, *, viewer_username=None, share_url_builder=None):
    if not agent:
        return None
    out = dict(agent)
    vis = _normalize_visibility(out.get("visibility"))
    out["visibility"] = vis
    out["favorite"] = bool(out.get("favorite"))
    out["force_reasoning"] = bool(out.get("force_reasoning"))
    out["reasoning_display"] = _normalize_reasoning_display(out.get("reasoning_display"))
    out["show_knowledge"] = bool(out.get("show_knowledge"))
    out["show_personality"] = bool(out.get("show_personality"))
    out["usage_count"] = max(0, int(out.get("usage_count") or 0))
    share_id = (out.get("share_id") or "").strip()
    if vis == VISIBILITY_PRIVATE or not share_id:
        out["share_url"] = None
    elif share_url_builder:
        out["share_url"] = share_url_builder(share_id)
    else:
        out["share_url"] = None
    out["created_label"] = format_agent_created_label(out.get("created_at"))
    is_owner = (
        custom_agent_viewer_is_owner(out, viewer_username)
        if viewer_username
        else None
    )
    out["is_owner"] = is_owner
    if viewer_username and is_owner is False and not out.get("show_knowledge"):
        out["knowledge_items"] = []
    if viewer_username and is_owner is False and not out.get("show_personality"):
        out["instructions"] = ""
    return out


def load_user_custom_agents(username):
    path = _agents_path(username)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    agents = []
    for item in raw:
        norm = _normalize_agent(item, agents_for_name=agents)
        if norm:
            norm["owner_username"] = (norm.get("owner_username") or username).strip().lower()
            agents.append(norm)
    agents.sort(key=lambda a: a.get("updated_at") or "", reverse=True)
    agents.sort(key=lambda a: not bool(a.get("favorite")))
    return agents


def save_user_custom_agents(username, agents):
    normalized = []
    for item in agents or []:
        norm = _normalize_agent(item, agents_for_name=normalized)
        if norm:
            normalized.append(norm)
    if len(normalized) > MAX_AGENTS_PER_USER:
        raise ValueError(f"エージェントは最大{MAX_AGENTS_PER_USER}件までです")
    path = _agents_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized


def find_custom_agent(username, agent_id):
    aid = (agent_id or "").strip()
    if not aid:
        return None
    for agent in load_user_custom_agents(username):
        if agent.get("id") == aid:
            return agent
    return None


def find_custom_agent_by_share_id(share_id):
    sid = (share_id or "").strip()
    if not sid or not SHARE_ID_RE.match(sid):
        return None
    if not CUSTOM_AGENTS_DIR.is_dir():
        return None
    for path in CUSTOM_AGENTS_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            if (item.get("share_id") or "").strip() != sid:
                continue
            vis = _normalize_visibility(item.get("visibility"))
            if vis == VISIBILITY_PRIVATE:
                continue
            norm = _normalize_agent(item)
            if norm:
                norm["owner_username"] = (norm.get("owner_username") or path.stem).strip().lower()
                return norm
    return None


def create_custom_agent(
    username,
    *,
    name,
    description="",
    instructions="",
    knowledge_items=None,
    favorite=False,
    visibility=VISIBILITY_PRIVATE,
    model_id="",
):
    agents = load_user_custom_agents(username)
    if len(agents) >= MAX_AGENTS_PER_USER:
        return None, f"エージェントは最大{MAX_AGENTS_PER_USER}件までです"
    now = _now_iso()
    resolved_name = _resolve_agent_name(name, agents)
    entry = _normalize_agent(
        {
            "id": str(uuid.uuid4()),
            "name": resolved_name,
            "description": description,
            "instructions": instructions,
            "knowledge_items": knowledge_items or [],
            "favorite": favorite,
            "visibility": visibility,
            "model_id": model_id,
            "force_reasoning": False,
            "reasoning_display": REASONING_DISPLAY_HIDE,
            "show_knowledge": False,
            "show_personality": False,
            "owner_username": (username or "").strip().lower(),
            "usage_count": 0,
            "created_at": now,
            "updated_at": now,
        },
        agents_for_name=agents,
    )
    if not entry:
        return None, "エージェントの作成に失敗しました"
    entry["owner_username"] = (username or "").strip().lower()
    agents.append(entry)
    save_user_custom_agents(username, agents)
    return entry, None


def update_custom_agent(
    username,
    agent_id,
    *,
    name=None,
    description=None,
    instructions=None,
    knowledge_items=None,
    favorite=None,
    visibility=None,
    model_id=None,
    force_reasoning=None,
    reasoning_display=None,
    show_knowledge=None,
    show_personality=None,
):
    agents = load_user_custom_agents(username)
    aid = (agent_id or "").strip()
    for i, agent in enumerate(agents):
        if agent.get("id") != aid:
            continue
        updated = dict(agent)
        if name is not None:
            others = [a for a in agents if a.get("id") != aid]
            updated["name"] = _resolve_agent_name(name, others)
        if description is not None:
            updated["description"] = description
        if instructions is not None:
            updated["instructions"] = instructions
        if knowledge_items is not None:
            updated["knowledge_items"] = _normalize_knowledge_items(knowledge_items)
        if favorite is not None:
            updated["favorite"] = bool(favorite)
        if visibility is not None:
            updated["visibility"] = _normalize_visibility(visibility)
        if model_id is not None:
            updated["model_id"] = _clip(model_id, MAX_MODEL_ID_LEN)
        if force_reasoning is not None:
            updated["force_reasoning"] = bool(force_reasoning)
        if reasoning_display is not None:
            updated["reasoning_display"] = _normalize_reasoning_display(reasoning_display)
        if show_knowledge is not None:
            updated["show_knowledge"] = bool(show_knowledge)
        if show_personality is not None:
            updated["show_personality"] = bool(show_personality)
        updated["owner_username"] = (updated.get("owner_username") or username).strip().lower()
        updated["updated_at"] = _now_iso()
        norm = _normalize_agent(updated, agents_for_name=agents)
        if not norm:
            return None, "エージェントの更新に失敗しました"
        agents[i] = norm
        save_user_custom_agents(username, agents)
        return norm, None
    return None, "エージェントが見つかりません"


def delete_custom_agent(username, agent_id):
    agents = load_user_custom_agents(username)
    aid = (agent_id or "").strip()
    next_agents = [a for a in agents if a.get("id") != aid]
    if len(next_agents) == len(agents):
        return False, "エージェントが見つかりません"
    save_user_custom_agents(username, next_agents)
    return True, None


def increment_custom_agent_usage(share_id):
    sid = (share_id or "").strip()
    if not sid or not SHARE_ID_RE.match(sid):
        return
    if not CUSTOM_AGENTS_DIR.is_dir():
        return
    for path in CUSTOM_AGENTS_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                agents = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(agents, list):
            continue
        changed = False
        for i, item in enumerate(agents):
            if not isinstance(item, dict):
                continue
            if (item.get("share_id") or "").strip() != sid:
                continue
            if _normalize_visibility(item.get("visibility")) != VISIBILITY_PUBLIC:
                continue
            item["usage_count"] = max(0, int(item.get("usage_count") or 0)) + 1
            item["updated_at"] = _now_iso()
            agents[i] = item
            changed = True
            break
        if changed:
            try:
                path.write_text(
                    json.dumps(agents, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass
            return


def build_custom_agent_system_append(agent):
    if not agent:
        return ""
    parts = [
        "\n\n【カスタムエージェント】",
        f"名前: {agent.get('name') or 'エージェント'}",
    ]
    desc = (agent.get("description") or "").strip()
    if desc:
        parts.append(f"概要: {desc}")
    instructions = (agent.get("instructions") or "").strip()
    if instructions:
        parts.append(
            "\n【性格・回答方針】\n"
            "以下を最優先で守り、このエージェントとして一貫して応答してください。\n"
            f"{instructions}"
        )
    knowledge_prompt = format_knowledge_items_for_prompt(agent.get("knowledge_items"))
    if knowledge_prompt:
        parts.append(knowledge_prompt)
    parts.append(
        "\n上記のエージェント設定は、他の一般的な指示より優先します。"
        "設定と矛盾する場合はエージェント設定に従ってください。"
    )
    return "".join(parts)
