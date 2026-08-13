import json
import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)


class ProjectRealtimeHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._project_rooms = defaultdict(set)
        self._user_rooms = defaultdict(set)
        self._connections = {}

    def register(self, ws, username):
        safe = (username or "").strip().lower()
        if not safe:
            return
        with self._lock:
            self._connections[ws] = {"username": safe, "projects": set()}
            self._user_rooms[safe].add(ws)

    def unregister(self, ws):
        with self._lock:
            meta = self._connections.pop(ws, None)
            if not meta:
                return
            username = meta["username"]
            self._user_rooms[username].discard(ws)
            if not self._user_rooms[username]:
                del self._user_rooms[username]
            for project_id in list(meta["projects"]):
                self._project_rooms[project_id].discard(ws)
                if not self._project_rooms[project_id]:
                    del self._project_rooms[project_id]

    def join_project(self, ws, project_id):
        project_key = (project_id or "").strip()
        if not project_key:
            return False
        with self._lock:
            meta = self._connections.get(ws)
            if not meta:
                return False
            meta["projects"].add(project_key)
            self._project_rooms[project_key].add(ws)
        return True

    def leave_project(self, ws, project_id):
        project_key = (project_id or "").strip()
        if not project_key:
            return
        with self._lock:
            meta = self._connections.get(ws)
            if meta:
                meta["projects"].discard(project_key)
            self._project_rooms[project_key].discard(ws)
            if not self._project_rooms[project_key]:
                del self._project_rooms[project_key]

    def _send(self, ws, payload):
        try:
            ws.send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:
            logger.debug("project realtime send failed: %s", exc)
            self.unregister(ws)
            return False

    def broadcast_project(self, project_id, payload, exclude_ws=None):
        project_key = (project_id or "").strip()
        if not project_key:
            return
        with self._lock:
            targets = list(self._project_rooms.get(project_key, set()))
        for ws in targets:
            if exclude_ws is not None and ws is exclude_ws:
                continue
            self._send(ws, payload)

    def broadcast_user(self, username, payload, exclude_ws=None):
        safe = (username or "").strip().lower()
        if not safe:
            return
        with self._lock:
            targets = list(self._user_rooms.get(safe, set()))
        for ws in targets:
            if exclude_ws is not None and ws is exclude_ws:
                continue
            self._send(ws, payload)


_hub = ProjectRealtimeHub()


def get_hub():
    return _hub


def project_public_patch(project):
    if not isinstance(project, dict):
        return {}
    return {
        "id": project.get("id"),
        "owner": project.get("owner"),
        "name": project.get("name"),
        "description": project.get("description"),
        "messages": project.get("messages") or [],
        "settings": project.get("settings") or {},
        "workers": project.get("workers") or [],
        "archive": project.get("archive") or [],
        "updatedAt": project.get("updatedAt"),
    }


def publish_project_patch(project_id, owner, project, event_type="project.updated"):
    patch = project_public_patch(project)
    payload = {
        "type": event_type,
        "project_id": project_id,
        "owner": (owner or project.get("owner") or "").strip().lower(),
        "patch": patch,
    }
    get_hub().broadcast_project(project_id, payload)


def publish_project_deleted(project_id, owner):
    payload = {
        "type": "project.deleted",
        "project_id": project_id,
        "owner": (owner or "").strip().lower(),
    }
    get_hub().broadcast_project(project_id, payload)


def publish_members_updated(project_id):
    payload = {
        "type": "members.updated",
        "project_id": project_id,
    }
    get_hub().broadcast_project(project_id, payload)


def publish_user_sync(username, reason, **extra):
    payload = {"type": "user.sync", "reason": reason, **extra}
    get_hub().broadcast_user((username or "").strip().lower(), payload)


def notify_project_participants(project, reason, **extra):
    owner = (project.get("owner") or "").strip().lower()
    seen = set()
    if owner:
        seen.add(owner)
        publish_user_sync(owner, reason, **extra)
    for member in project.get("members") or []:
        username = (member.get("username") or "").strip().lower()
        if not username or username in seen:
            continue
        seen.add(username)
        publish_user_sync(username, reason, **extra)


def init_project_realtime(app, handlers):
    from flask_sock import Sock

    sock = Sock(app)

    @sock.route("/ws/projects")
    def projects_ws(ws):
        from flask import session

        username = (session.get("user") or {}).get("username")
        if not username:
            ws.close(4401, "Unauthorized")
            return

        hub = get_hub()
        hub.register(ws, username)
        hub._send(ws, {"type": "connected", "username": username})

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    hub._send(ws, {"type": "error", "error": "invalid_json"})
                    continue
                handlers.handle(ws, username, message, hub)
        finally:
            hub.unregister(ws)

    return sock
