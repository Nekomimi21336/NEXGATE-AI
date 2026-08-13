import json
import time
import uuid
from pathlib import Path

from project_members import (
    attach_project_access,
    load_incoming_invites,
    load_member_index,
    merge_owned_projects_on_save,
    normalize_invites,
    normalize_members,
    sync_member_indexes,
)

PROJECTS_DIR = Path(__file__).parent / "data" / "projects"


def resolve_user_projects_enabled(record, plan_projects_enabled):
    if not record:
        return False
    plan = (record.get("plan") or "free").strip().lower()
    if not plan_projects_enabled(plan):
        return False
    if "projects_enabled" in record:
        return bool(record.get("projects_enabled"))
    return False


def _projects_path(username):
    safe = (username or "").strip().lower()
    if not safe:
        raise ValueError("username required")
    return PROJECTS_DIR / f"{safe}.json"


def _empty_state():
    return {"projects": []}


def _normalize_messages(raw_messages):
    if not isinstance(raw_messages, list):
        return []
    messages = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "")
        if not content.strip():
            continue
        messages.append(
            {
                "role": role,
                "content": content,
                "created_at": str(item.get("created_at") or ""),
            }
        )
    return messages


def _normalize_section_entries(raw_entries):
    if not isinstance(raw_entries, list):
        return []
    entries = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        entry_id = (item.get("id") or "").strip() or str(uuid.uuid4())
        entries.append(
            {
                "id": entry_id,
                "title": str(item.get("title") or ""),
                "summary": str(item.get("summary") or ""),
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
            }
        )
    return entries


def _normalize_project_settings(raw_settings):
    defaults = {
        "default_mode": "chat",
        "custom_instructions": "",
        "status": "active",
        "scope": "",
        "tools": {
            "web_search": False,
            "geolocation": False,
            "memory": False,
            "tasks": False,
            "google_calendar": False,
            "google_gmail": False,
        },
    }
    if not isinstance(raw_settings, dict):
        return defaults
    mode = (raw_settings.get("default_mode") or "chat").strip().lower()
    if mode not in {"agent", "multitask", "chat", "plan", "ask"}:
        mode = "chat"
    status = (raw_settings.get("status") or "active").strip().lower()
    if status not in {"active", "paused", "archived"}:
        status = "active"
    raw_tools = raw_settings.get("tools")
    tools_in = raw_tools if isinstance(raw_tools, dict) else {}
    tools = {}
    for key in defaults["tools"]:
        tools[key] = bool(tools_in.get(key))
    return {
        "default_mode": mode,
        "custom_instructions": str(raw_settings.get("custom_instructions") or ""),
        "status": status,
        "scope": str(raw_settings.get("scope") or ""),
        "tools": tools,
    }


def _normalize_stats_items(raw_items):
    if not isinstance(raw_items, list):
        return []
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = (item.get("id") or "").strip() or str(uuid.uuid4())
        items.append(
            {
                "id": item_id,
                "label": str(item.get("label") or ""),
                "value": str(item.get("value") or ""),
                "updated_at": str(item.get("updated_at") or ""),
            }
        )
    return items


def normalize_projects_state(raw):
    if not isinstance(raw, dict):
        return _empty_state()
    projects_in = raw.get("projects")
    if not isinstance(projects_in, list):
        return _empty_state()
    projects = []
    for item in projects_in:
        if not isinstance(item, dict):
            continue
        project_id = (item.get("id") or "").strip() or str(uuid.uuid4())
        owner = (item.get("owner") or "").strip().lower()
        projects.append(
            {
                "id": project_id,
                "owner": owner,
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "messages": _normalize_messages(item.get("messages")),
                "stats_items": _normalize_stats_items(item.get("stats_items")),
                "workers": _normalize_section_entries(item.get("workers")),
                "archive": _normalize_section_entries(item.get("archive")),
                "settings": _normalize_project_settings(item.get("settings")),
                "members": normalize_members(item.get("members"), owner),
                "invites": normalize_invites(item.get("invites")),
                "createdAt": int(item.get("createdAt") or time.time() * 1000),
                "updatedAt": int(item.get("updatedAt") or item.get("createdAt") or time.time() * 1000),
            }
        )
    return {"projects": projects}


def _ensure_project_owner(project, username):
    owner = (username or "").strip().lower()
    if not owner:
        return project
    if not project.get("owner"):
        project["owner"] = owner
    project["members"] = normalize_members(project.get("members"), project.get("owner") or owner)
    project["invites"] = normalize_invites(project.get("invites"))
    return project


def _load_owner_project(owner, project_id):
    owner_name = (owner or "").strip().lower()
    project_key = (project_id or "").strip()
    if not owner_name or not project_key:
        return None
    state = load_user_projects(owner_name)
    return next(
        (item for item in state.get("projects", []) if item.get("id") == project_key),
        None,
    )


def load_user_projects_bundle(username):
    safe = (username or "").strip().lower()
    owned_state = load_user_projects(safe)
    owned = []
    for project in owned_state.get("projects", []):
        normalized = _ensure_project_owner(dict(project), safe)
        owned.append(attach_project_access(normalized, safe))
    shared = []
    index = load_member_index(safe)
    for entry in index.get("entries", []):
        source = _load_owner_project(entry.get("owner"), entry.get("project_id"))
        if not source:
            continue
        copy = dict(source)
        copy["members"] = normalize_members(copy.get("members"), copy.get("owner"))
        copy["invites"] = []
        shared.append(attach_project_access(copy, safe))
    invites = load_incoming_invites(safe).get("invites", [])
    return {"projects": owned, "shared_projects": shared, "pending_invites": invites}


def load_user_projects(username):
    path = _projects_path(username)
    if not path.exists():
        return _empty_state()
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_state()
    return normalize_projects_state(raw)


def save_user_projects(username, state):
    safe = (username or "").strip().lower()
    existing = load_user_projects(safe)
    merged_input = merge_owned_projects_on_save(safe, state, existing)
    normalized = normalize_projects_state(merged_input)
    projects = []
    for project in normalized.get("projects", []):
        project = _ensure_project_owner(project, safe)
        projects.append(project)
        sync_member_indexes(safe, project)
    normalized["projects"] = projects
    path = _projects_path(safe)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized


def find_accessible_project(username, project_id):
    safe = (username or "").strip().lower()
    project_key = (project_id or "").strip()
    if not safe or not project_key:
        return None, None
    owned_state = load_user_projects(safe)
    owned = next(
        (item for item in owned_state.get("projects", []) if item.get("id") == project_key),
        None,
    )
    if owned:
        project = _ensure_project_owner(dict(owned), safe)
        return project, "owned"
    index = load_member_index(safe)
    entry = next(
        (
            item
            for item in index.get("entries", [])
            if item.get("project_id") == project_key
        ),
        None,
    )
    if not entry:
        return None, None
    source = _load_owner_project(entry.get("owner"), project_key)
    if not source:
        return None, None
    project = dict(source)
    project["members"] = normalize_members(project.get("members"), project.get("owner"))
    project["invites"] = []
    return project, "shared"


def save_owner_project(owner, project):
    safe = (owner or "").strip().lower()
    state = load_user_projects(safe)
    projects = []
    replaced = False
    for item in state.get("projects", []):
        if item.get("id") == project.get("id"):
            projects.append(project)
            replaced = True
        else:
            projects.append(item)
    if not replaced:
        projects.append(project)
    return save_user_projects(safe, {"projects": projects})
