import json
import logging
import threading
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

MAX_JOB_EVENTS = 4000


def _room_key(owner, session_id):
    owner_key = (owner or "").strip().lower()
    session_key = (session_id or "").strip()
    if not owner_key or not session_key:
        return ""
    return f"{owner_key}:{session_key}"


class ChatRealtimeHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._session_rooms = defaultdict(set)
        self._user_rooms = defaultdict(set)
        self._connections = {}
        self._jobs = {}
        self._session_active = {}

    def register(self, ws, username):
        safe = (username or "").strip().lower()
        if not safe:
            return
        with self._lock:
            self._connections[ws] = {"username": safe, "sessions": set()}
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
            for room in list(meta["sessions"]):
                self._session_rooms[room].discard(ws)
                if not self._session_rooms[room]:
                    del self._session_rooms[room]

    def join_session(self, ws, owner, session_id):
        room = _room_key(owner, session_id)
        if not room:
            return False
        with self._lock:
            meta = self._connections.get(ws)
            if not meta:
                return False
            meta["sessions"].add(room)
            self._session_rooms[room].add(ws)
        return True

    def leave_session(self, ws, owner, session_id):
        room = _room_key(owner, session_id)
        if not room:
            return
        with self._lock:
            meta = self._connections.get(ws)
            if meta:
                meta["sessions"].discard(room)
            self._session_rooms[room].discard(ws)
            if not self._session_rooms[room]:
                del self._session_rooms[room]

    def _send(self, ws, payload):
        try:
            ws.send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:
            logger.debug("chat realtime send failed: %s", exc)
            self.unregister(ws)
            return False

    def broadcast_session(self, owner, session_id, payload, exclude_ws=None):
        room = _room_key(owner, session_id)
        if not room:
            return
        enriched = dict(payload)
        enriched.setdefault("owner", (owner or "").strip().lower())
        enriched.setdefault("session_id", (session_id or "").strip())
        with self._lock:
            targets = list(self._session_rooms.get(room, set()))
        for ws in targets:
            if exclude_ws is not None and ws is exclude_ws:
                continue
            self._send(ws, enriched)

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

    def register_job(self, request_id, owner, session_id, username):
        request_id = (request_id or "").strip()
        session_id = (session_id or "").strip()
        owner = (owner or username or "").strip().lower()
        if not request_id:
            return None
        room = _room_key(owner, session_id)
        job = {
            "request_id": request_id,
            "owner": owner,
            "session_id": session_id,
            "username": (username or "").strip().lower(),
            "status": "running",
            "seq": 0,
            "events": deque(maxlen=MAX_JOB_EVENTS),
        }
        with self._lock:
            self._jobs[request_id] = job
            if room:
                self._session_active[room] = request_id
        return job

    def get_job(self, request_id):
        request_id = (request_id or "").strip()
        if not request_id:
            return None
        with self._lock:
            job = self._jobs.get(request_id)
            return dict(job) if job else None

    def get_active_job_for_session(self, owner, session_id):
        room = _room_key(owner, session_id)
        if not room:
            return None
        with self._lock:
            request_id = self._session_active.get(room)
            if not request_id:
                return None
            job = self._jobs.get(request_id)
            if not job or job.get("status") != "running":
                return None
            return {
                "request_id": job["request_id"],
                "owner": job.get("owner") or "",
                "session_id": job["session_id"],
                "status": job["status"],
                "seq": job["seq"],
                "events": list(job["events"]),
            }

    def append_job_event(self, request_id, data):
        request_id = (request_id or "").strip()
        if not request_id:
            return 0
        with self._lock:
            job = self._jobs.get(request_id)
            if not job:
                return 0
            job["seq"] += 1
            seq = job["seq"]
            job["events"].append({"seq": seq, "data": data})
        return seq

    def finish_job(self, request_id, status="completed"):
        request_id = (request_id or "").strip()
        if not request_id:
            return
        with self._lock:
            job = self._jobs.pop(request_id, None)
            if not job:
                return
            room = _room_key(job.get("owner"), job.get("session_id"))
            if room and self._session_active.get(room) == request_id:
                del self._session_active[room]

    def publish_event(self, owner, session_id, request_id, data, *, mirror=None):
        seq = self.append_job_event(request_id, data)
        if mirror:
            mirror_seq = self.append_job_event(request_id, mirror)
            self.broadcast_session(
                owner,
                session_id,
                {
                    "type": "chat.event",
                    "request_id": request_id,
                    "seq": mirror_seq,
                    "data": mirror,
                },
            )
        self.broadcast_session(
            owner,
            session_id,
            {
                "type": "chat.event",
                "request_id": request_id,
                "seq": seq,
                "data": data,
            },
        )

    def publish_status(self, owner, session_id, request_id, status, **extra):
        payload = {
            "type": "chat.status",
            "request_id": request_id,
            "status": status,
            **extra,
        }
        self.broadcast_session(owner, session_id, payload)

    def publish_session_update(self, owner, session_id, patch, *, editor=None, exclude_ws=None):
        payload = {
            "type": "session.updated",
            "patch": patch,
            "editor": (editor or "").strip().lower() or None,
        }
        self.broadcast_session(owner, session_id, payload, exclude_ws=exclude_ws)

    def session_snapshot(self, owner, session_id):
        active = self.get_active_job_for_session(owner, session_id)
        if not active:
            return None
        return {"type": "chat.snapshot", **active}


_hub = ChatRealtimeHub()


def get_chat_hub():
    return _hub


def init_chat_realtime(app, handlers):
    from flask_sock import Sock

    sock = Sock(app)

    @sock.route("/ws/chat")
    def chat_ws(ws):
        from flask import session

        username = (session.get("user") or {}).get("username")
        if not username:
            ws.close(4401, "Unauthorized")
            return

        hub = get_chat_hub()
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
