import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROLES = ("owner", "editor", "viewer")
ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
PERMISSIONS = {
    "view": {"owner", "editor", "viewer"},
    "chat": {"owner", "editor"},
    "edit_settings": {"owner", "editor"},
    "manage_members": {"owner"},
    "delete_project": {"owner"},
}

MEMBERS_INDEX_DIR = Path(__file__).parent / "data" / "project_members"
INCOMING_INVITES_DIR = Path(__file__).parent / "data" / "project_invites"


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_username(username):
    return (username or "").strip().lower()


def _members_index_path(username):
    safe = _safe_username(username)
    if not safe:
        raise ValueError("username required")
    return MEMBERS_INDEX_DIR / f"{safe}.json"


def _incoming_invites_path(username):
    safe = _safe_username(username)
    if not safe:
        raise ValueError("username required")
    return INCOMING_INVITES_DIR / f"{safe}.json"


def normalize_role(raw):
    role = (raw or "viewer").strip().lower()
    if role not in PROJECT_ROLES:
        return "viewer"
    return role


def normalize_member(raw, default_role="viewer"):
    if not isinstance(raw, dict):
        return None
    username = _safe_username(raw.get("username"))
    if not username:
        return None
    role = normalize_role(raw.get("role") or default_role)
    if role == "owner":
        role = "owner"
    return {
        "username": username,
        "role": role,
        "joined_at": str(raw.get("joined_at") or _now_iso()),
        "invited_by": _safe_username(raw.get("invited_by")) or None,
    }


def normalize_invite(raw):
    if not isinstance(raw, dict):
        return None
    invite_id = (raw.get("id") or "").strip() or str(uuid.uuid4())
    username = _safe_username(raw.get("username"))
    if not username:
        return None
    status = (raw.get("status") or "pending").strip().lower()
    if status not in {"pending", "accepted", "declined"}:
        status = "pending"
    return {
        "id": invite_id,
        "username": username,
        "role": normalize_role(raw.get("role")),
        "status": status,
        "created_at": str(raw.get("created_at") or _now_iso()),
        "invited_by": _safe_username(raw.get("invited_by")) or None,
    }


def normalize_members(raw_members, owner_username):
    owner = _safe_username(owner_username)
    members = []
    seen = set()
    if owner:
        members.append(
            {
                "username": owner,
                "role": "owner",
                "joined_at": _now_iso(),
                "invited_by": None,
            }
        )
        seen.add(owner)
    if isinstance(raw_members, list):
        for item in raw_members:
            member = normalize_member(item)
            if not member or member["username"] in seen:
                continue
            if member["role"] == "owner":
                member["role"] = "editor"
            members.append(member)
            seen.add(member["username"])
    if owner and members[0]["username"] != owner:
        members = [m for m in members if m["username"] != owner]
        members.insert(
            0,
            {
                "username": owner,
                "role": "owner",
                "joined_at": members[0]["joined_at"] if members else _now_iso(),
                "invited_by": None,
            },
        )
    return members


def normalize_invites(raw_invites):
    if not isinstance(raw_invites, list):
        return []
    invites = []
    seen_ids = set()
    for item in raw_invites:
        invite = normalize_invite(item)
        if not invite or invite["id"] in seen_ids:
            continue
        if invite["status"] != "pending":
            continue
        invites.append(invite)
        seen_ids.add(invite["id"])
    return invites


def attach_project_access(project, username):
    owner = _safe_username(project.get("owner"))
    role = get_member_role(project, username)
    enriched = dict(project)
    enriched["owner"] = owner
    enriched["my_role"] = role
    enriched["my_permissions"] = sorted(
        perm for perm, roles in PERMISSIONS.items() if role in roles
    )
    return enriched


def get_member_role(project, username):
    user = _safe_username(username)
    owner = _safe_username(project.get("owner"))
    if owner and user == owner:
        return "owner"
    for member in project.get("members") or []:
        if _safe_username(member.get("username")) == user:
            return normalize_role(member.get("role"))
    return None


def has_permission(project, username, permission):
    role = get_member_role(project, username)
    if not role:
        return False
    allowed = PERMISSIONS.get(permission) or set()
    return role in allowed


def load_member_index(username):
    path = _members_index_path(username)
    if not path.exists():
        return {"entries": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"entries": []}
    entries = []
    if isinstance(raw, dict) and isinstance(raw.get("entries"), list):
        for item in raw["entries"]:
            if not isinstance(item, dict):
                continue
            project_id = (item.get("project_id") or "").strip()
            owner = _safe_username(item.get("owner"))
            if not project_id or not owner:
                continue
            entries.append(
                {
                    "project_id": project_id,
                    "owner": owner,
                    "role": normalize_role(item.get("role")),
                    "project_name": str(item.get("project_name") or ""),
                    "updated_at": int(item.get("updated_at") or 0),
                }
            )
    return {"entries": entries}


def save_member_index(username, index):
    path = _members_index_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def sync_member_indexes(owner_username, project):
    owner = _safe_username(owner_username)
    project_id = (project.get("id") or "").strip()
    if not owner or not project_id:
        return
    project_name = str(project.get("name") or "")
    updated_at = int(project.get("updatedAt") or time.time() * 1000)
    active_members = {
        _safe_username(m.get("username"))
        for m in (project.get("members") or [])
        if _safe_username(m.get("username")) and _safe_username(m.get("username")) != owner
    }
    for member_username in active_members:
        member = next(
            (
                m
                for m in project.get("members") or []
                if _safe_username(m.get("username")) == member_username
            ),
            None,
        )
        if not member:
            continue
        index = load_member_index(member_username)
        entries = [
            e
            for e in index.get("entries", [])
            if not (e.get("project_id") == project_id and e.get("owner") == owner)
        ]
        entries.append(
            {
                "project_id": project_id,
                "owner": owner,
                "role": normalize_role(member.get("role")),
                "project_name": project_name,
                "updated_at": updated_at,
            }
        )
        save_member_index(member_username, {"entries": entries})
    all_indexes = MEMBERS_INDEX_DIR.glob("*.json")
    for path in all_indexes:
        member_username = path.stem
        if member_username in active_members or member_username == owner:
            continue
        index = load_member_index(member_username)
        filtered = [
            e
            for e in index.get("entries", [])
            if not (e.get("project_id") == project_id and e.get("owner") == owner)
        ]
        if len(filtered) != len(index.get("entries", [])):
            save_member_index(member_username, {"entries": filtered})


def load_incoming_invites(username):
    path = _incoming_invites_path(username)
    if not path.exists():
        return {"invites": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"invites": []}
    invites = []
    if isinstance(raw, dict) and isinstance(raw.get("invites"), list):
        for item in raw["invites"]:
            if not isinstance(item, dict):
                continue
            invite_id = (item.get("id") or "").strip()
            project_id = (item.get("project_id") or "").strip()
            owner = _safe_username(item.get("owner"))
            if not invite_id or not project_id or not owner:
                continue
            invites.append(
                {
                    "id": invite_id,
                    "project_id": project_id,
                    "owner": owner,
                    "role": normalize_role(item.get("role")),
                    "project_name": str(item.get("project_name") or ""),
                    "invited_by": _safe_username(item.get("invited_by")) or owner,
                    "created_at": str(item.get("created_at") or _now_iso()),
                }
            )
    return {"invites": invites}


def save_incoming_invites(username, payload):
    path = _incoming_invites_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def add_incoming_invite(invitee, invite, owner, project):
    invitee_name = _safe_username(invitee)
    index = load_incoming_invites(invitee_name)
    invites = [
        item
        for item in index.get("invites", [])
        if not (
            item.get("id") == invite.get("id")
            or (
                item.get("project_id") == project.get("id")
                and item.get("owner") == owner
            )
        )
    ]
    invites.append(
        {
            "id": invite["id"],
            "project_id": project.get("id"),
            "owner": owner,
            "role": invite.get("role"),
            "project_name": str(project.get("name") or ""),
            "invited_by": invite.get("invited_by") or owner,
            "created_at": invite.get("created_at") or _now_iso(),
        }
    )
    save_incoming_invites(invitee_name, {"invites": invites})


def remove_incoming_invite(invitee, invite_id, owner=None, project_id=None):
    invitee_name = _safe_username(invitee)
    index = load_incoming_invites(invitee_name)
    invites = []
    for item in index.get("invites", []):
        if invite_id and item.get("id") == invite_id:
            continue
        if owner and project_id:
            if item.get("owner") == owner and item.get("project_id") == project_id:
                continue
        invites.append(item)
    save_incoming_invites(invitee_name, {"invites": invites})


def merge_owned_projects_on_save(username, incoming_state, existing_state):
    existing_by_id = {
        (p.get("id") or ""): p for p in (existing_state or {}).get("projects", [])
    }
    merged_projects = []
    for item in (incoming_state or {}).get("projects", []):
        if not isinstance(item, dict):
            continue
        project_id = (item.get("id") or "").strip()
        existing = existing_by_id.get(project_id) or {}
        owner = _safe_username(existing.get("owner") or username)
        if owner != _safe_username(username):
            continue
        merged = dict(item)
        merged["owner"] = owner
        merged["members"] = normalize_members(
            existing.get("members") or merged.get("members"),
            owner,
        )
        merged["invites"] = normalize_invites(existing.get("invites") or merged.get("invites"))
        merged_projects.append(merged)
    for project_id, existing in existing_by_id.items():
        if not project_id:
            continue
        if any(p.get("id") == project_id for p in merged_projects):
            continue
        owner = _safe_username(existing.get("owner") or username)
        if owner == _safe_username(username):
            merged_projects.append(existing)
    return {"projects": merged_projects}


def serialize_member_public(member, users):
    username = _safe_username(member.get("username"))
    record = (users or {}).get(username) or {}
    return {
        "username": username,
        "display_name": str(record.get("display_name") or username),
        "role": normalize_role(member.get("role")),
        "joined_at": member.get("joined_at"),
        "invited_by": member.get("invited_by"),
    }


def serialize_invite_public(invite, users):
    username = _safe_username(invite.get("username"))
    record = (users or {}).get(username) or {}
    return {
        "id": invite.get("id"),
        "username": username,
        "display_name": str(record.get("display_name") or username),
        "role": normalize_role(invite.get("role")),
        "status": invite.get("status") or "pending",
        "created_at": invite.get("created_at"),
        "invited_by": invite.get("invited_by"),
    }
