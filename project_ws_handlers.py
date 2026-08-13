import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ProjectWsHandlers:
    def __init__(self, **deps):
        for key, value in deps.items():
            setattr(self, key, value)
        self._gen_lock = threading.Lock()
        self._generations = {}

    def _send(self, hub, ws, payload):
        hub._send(ws, payload)

    def _respond(self, hub, ws, request_id, ok=True, action=None, data=None, error=None):
        payload = {"type": "response", "request_id": request_id, "ok": ok}
        if action:
            payload["action"] = action
        if data is not None:
            payload["data"] = data
        if error:
            payload["error"] = error
        self._send(hub, ws, payload)

    def _chat_guard(self, username):
        users = self.load_users()
        record = users.get(username) or {}
        if self.feature_blocked("chat_disabled"):
            return None, "現在、チャット機能は一時的に制限されています"
        if not self.user_projects_enabled(record):
            return None, "プロジェクトスペースが有効ではありません"
        if self.is_user_blocked(record):
            return None, "アカウントが利用停止中のため、チャットを利用できません"
        allowed, plan_err = self.plan_allows_chat(username)
        if not allowed:
            return None, plan_err
        return record, None

    def _projects_guard(self, username):
        users = self.load_users()
        record = users.get(username) or {}
        if not self.user_projects_enabled(record):
            return None, None, "プロジェクトスペースが有効ではありません"
        return users, record, None

    def _parse_sse_payload(self, chunk):
        if not isinstance(chunk, str) or not chunk.startswith("data:"):
            return None
        raw = chunk[5:].strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _broadcast_chat(self, hub, project_id, payload):
        payload = dict(payload)
        payload["project_id"] = project_id
        hub.broadcast_project(project_id, payload)

    def _stop_generation(self, ws, request_id=None):
        with self._gen_lock:
            entry = self._generations.get(ws)
            if not entry:
                return False
            if request_id and entry.get("request_id") != request_id:
                return False
            entry["stop_event"].set()
            return True

    def handle(self, ws, username, message, hub):
        action = (message.get("action") or "").strip().lower()
        request_id = message.get("request_id")

        if action == "ping":
            self._send(hub, ws, {"type": "pong"})
            return

        if action == "join":
            project_id = (message.get("project_id") or "").strip()
            project, _source = self.find_accessible_project(username, project_id)
            if not project or not self.has_permission(project, username, "view"):
                self._send(
                    hub,
                    ws,
                    {"type": "error", "error": "forbidden", "project_id": project_id},
                )
                return
            hub.join_project(ws, project_id)
            self._send(hub, ws, {"type": "joined", "project_id": project_id})
            return

        if action == "leave":
            project_id = (message.get("project_id") or "").strip()
            hub.leave_project(ws, project_id)
            self._send(hub, ws, {"type": "left", "project_id": project_id})
            return

        if action == "chat.stop":
            self._stop_generation(ws, message.get("request_id"))
            return

        if action == "bundle.get":
            self._bundle_get(ws, username, request_id, hub)
            return

        if action == "bundle.save":
            self._bundle_save(ws, username, message, request_id, hub)
            return

        if action == "project.save":
            self._project_save(ws, username, message, request_id, hub)
            return

        if action == "members.list":
            self._members_list(ws, username, message, request_id, hub)
            return

        if action == "members.invite":
            self._members_invite(ws, username, message, request_id, hub)
            return

        if action == "members.update":
            self._members_update(ws, username, message, request_id, hub)
            return

        if action == "members.remove":
            self._members_remove(ws, username, message, request_id, hub)
            return

        if action == "invites.accept":
            self._invites_accept(ws, username, message, request_id, hub)
            return

        if action == "invites.decline":
            self._invites_decline(ws, username, message, request_id, hub)
            return

        if action == "chat.send":
            self._chat_send(ws, username, message, hub)
            return

        if request_id:
            self._respond(hub, ws, request_id, ok=False, error="unknown_action")

    def _bundle_get(self, ws, username, request_id, hub):
        _users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="bundle.get", error=err)
            return
        bundle = self.load_user_projects_bundle(username)
        self._respond(hub, ws, request_id, ok=True, action="bundle.get", data=bundle)

    def _bundle_save(self, ws, username, message, request_id, hub):
        users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="bundle.save", error=err)
            return
        incoming = message.get("projects")
        if not isinstance(incoming, list):
            self._respond(hub, ws, request_id, ok=False, action="bundle.save", error="projects が必要です")
            return
        existing = self.load_user_projects(username)
        saved = self.save_user_projects(username, {"projects": incoming})
        existing_ids = {item.get("id") for item in existing.get("projects", []) if item.get("id")}
        saved_ids = {item.get("id") for item in saved.get("projects", []) if item.get("id")}
        for deleted_id in existing_ids - saved_ids:
            deleted = next(
                (item for item in existing.get("projects", []) if item.get("id") == deleted_id),
                None,
            )
            if deleted:
                self.emit_project_deleted(deleted)
        for project in saved.get("projects", []):
            self.emit_project_saved(project)
        bundle = self.load_user_projects_bundle(username)
        bundle["projects"] = [
            self.attach_project_access(project, username) for project in saved.get("projects", [])
        ]
        self._respond(hub, ws, request_id, ok=True, action="bundle.save", data=bundle)

    def _project_save(self, ws, username, message, request_id, hub):
        users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="project.save", error=err)
            return
        project_id = (message.get("project_id") or "").strip()
        data = message.get("project")
        if not project_id or not isinstance(data, dict):
            self._respond(hub, ws, request_id, ok=False, action="project.save", error="project が必要です")
            return
        project, source = self.find_accessible_project(username, project_id)
        if not project:
            self._respond(hub, ws, request_id, ok=False, action="project.save", error="プロジェクトが見つかりません")
            return
        owner = (project.get("owner") or username).strip().lower()
        if source == "owned":
            owner = username
        if not self.has_permission(project, username, "edit_settings"):
            self._respond(hub, ws, request_id, ok=False, action="project.save", error="プロジェクトを編集する権限がありません")
            return
        updated = dict(project)
        if "name" in data:
            updated["name"] = str(data.get("name") or "")
        if "description" in data:
            updated["description"] = str(data.get("description") or "")
        if "messages" in data and self.has_permission(project, username, "chat"):
            updated["messages"] = data.get("messages") or []
        if "settings" in data and isinstance(data.get("settings"), dict):
            updated["settings"] = data.get("settings")
        if "workers" in data:
            updated["workers"] = data.get("workers") or []
        if "archive" in data:
            updated["archive"] = data.get("archive") or []
        updated["members"] = self.normalize_members(project.get("members"), owner)
        updated["invites"] = self.normalize_invites(project.get("invites"))
        updated["owner"] = owner
        updated["updatedAt"] = int(time.time() * 1000)
        saved_state = self.save_owner_project(owner, updated)
        saved = next(
            (item for item in saved_state.get("projects", []) if item.get("id") == project_id),
            updated,
        )
        self.emit_project_saved(saved)
        enriched = self.attach_project_access(saved, username)
        self._respond(
            hub,
            ws,
            request_id,
            ok=True,
            action="project.save",
            data={"project": enriched},
        )

    def _members_list(self, ws, username, message, request_id, hub):
        users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="members.list", error=err)
            return
        project_id = (message.get("project_id") or "").strip()
        project, _source = self.find_accessible_project(username, project_id)
        if not project:
            self._respond(hub, ws, request_id, ok=False, action="members.list", error="プロジェクトが見つかりません")
            return
        if not self.has_permission(project, username, "view"):
            self._respond(hub, ws, request_id, ok=False, action="members.list", error="権限がありません")
            return
        members = [
            self.serialize_member_public(member, users)
            for member in self.normalize_members(project.get("members"), project.get("owner"))
        ]
        invites = []
        if self.has_permission(project, username, "manage_members"):
            invites = [
                self.serialize_invite_public(invite, users)
                for invite in self.normalize_invites(project.get("invites"))
            ]
        self._respond(
            hub,
            ws,
            request_id,
            ok=True,
            action="members.list",
            data={
                "members": members,
                "invites": invites,
                "my_role": self.get_member_role(project, username),
                "permissions": sorted(
                    perm
                    for perm, roles in self.PERMISSIONS.items()
                    if self.get_member_role(project, username) in roles
                ),
            },
        )

    def _members_invite(self, ws, username, message, request_id, hub):
        users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error=err)
            return
        project_id = (message.get("project_id") or "").strip()
        project, _source, denied = self._resolve_owned_project(username, project_id)
        if denied:
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error="権限がありません")
            return
        if not self.has_permission(project, username, "manage_members"):
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error="メンバーを招待する権限がありません")
            return
        invitee = self.normalize_username(message.get("username"))
        invitee_error = self.validate_new_username(invitee)
        if invitee_error:
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error=invitee_error)
            return
        if invitee not in users:
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error="指定されたユーザーが見つかりません")
            return
        if not self.user_projects_enabled(users.get(invitee) or {}):
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error="招待先ユーザーはプロジェクト機能が有効ではありません")
            return
        if invitee == username:
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error="自分自身は招待できません")
            return
        role = self.normalize_role(message.get("role"))
        if role == "owner":
            role = "editor"
        members = self.normalize_members(project.get("members"), username)
        if any(m.get("username") == invitee for m in members):
            self._respond(hub, ws, request_id, ok=False, action="members.invite", error="このユーザーは既にメンバーです")
            return
        invites = self.normalize_invites(project.get("invites"))
        invites = [item for item in invites if item.get("username") != invitee]
        invite = {
            "id": str(uuid.uuid4()),
            "username": invitee,
            "role": role,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "invited_by": username,
        }
        invites.append(invite)
        project["invites"] = invites
        project["members"] = members
        project["updatedAt"] = int(time.time() * 1000)
        self.save_owner_project(username, project)
        self.add_incoming_invite(invitee, invite, username, project)
        self.publish_members_updated(project_id)
        self.publish_user_sync(invitee, "invites.updated", project_id=project_id)
        self.emit_project_saved(project)
        self._respond(
            hub,
            ws,
            request_id,
            ok=True,
            action="members.invite",
            data={
                "invite": self.serialize_invite_public(invite, users),
                "members": [self.serialize_member_public(member, users) for member in members],
                "invites": [self.serialize_invite_public(item, users) for item in invites],
            },
        )

    def _members_update(self, ws, username, message, request_id, hub):
        users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="members.update", error=err)
            return
        project_id = (message.get("project_id") or "").strip()
        target = self.normalize_username(message.get("member_username"))
        project, _source, denied = self._resolve_owned_project(username, project_id)
        if denied:
            self._respond(hub, ws, request_id, ok=False, action="members.update", error="権限がありません")
            return
        if not self.has_permission(project, username, "manage_members"):
            self._respond(hub, ws, request_id, ok=False, action="members.update", error="メンバーを管理する権限がありません")
            return
        role = self.normalize_role(message.get("role"))
        if role == "owner":
            self._respond(hub, ws, request_id, ok=False, action="members.update", error="オーナー権限は付与できません")
            return
        members = self.normalize_members(project.get("members"), username)
        if not any(m.get("username") == target for m in members):
            self._respond(hub, ws, request_id, ok=False, action="members.update", error="メンバーが見つかりません")
            return
        updated_members = []
        for member in members:
            if member.get("username") == target:
                member = dict(member)
                member["role"] = role
            updated_members.append(member)
        project["members"] = updated_members
        project["updatedAt"] = int(time.time() * 1000)
        self.save_owner_project(username, project)
        self.sync_member_indexes(username, project)
        self.publish_members_updated(project_id)
        self.publish_user_sync(target, "projects.updated", project_id=project_id)
        self.emit_project_saved(project)
        self._respond(
            hub,
            ws,
            request_id,
            ok=True,
            action="members.update",
            data={"members": [self.serialize_member_public(member, users) for member in updated_members]},
        )

    def _members_remove(self, ws, username, message, request_id, hub):
        users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="members.remove", error=err)
            return
        project_id = (message.get("project_id") or "").strip()
        target = self.normalize_username(message.get("member_username"))
        project, _source, denied = self._resolve_owned_project(username, project_id)
        if denied:
            self._respond(hub, ws, request_id, ok=False, action="members.remove", error="権限がありません")
            return
        if not self.has_permission(project, username, "manage_members"):
            self._respond(hub, ws, request_id, ok=False, action="members.remove", error="メンバーを管理する権限がありません")
            return
        members = self.normalize_members(project.get("members"), username)
        if target == username:
            self._respond(hub, ws, request_id, ok=False, action="members.remove", error="オーナー自身は変更できません")
            return
        if not any(m.get("username") == target for m in members):
            invites = self.normalize_invites(project.get("invites"))
            if any(i.get("username") == target for i in invites):
                project["invites"] = [i for i in invites if i.get("username") != target]
                self.remove_incoming_invite(target, None, owner=username, project_id=project_id)
                project["updatedAt"] = int(time.time() * 1000)
                self.save_owner_project(username, project)
                self.publish_members_updated(project_id)
                self.publish_user_sync(target, "invites.updated", project_id=project_id)
                self.emit_project_saved(project)
                self._respond(hub, ws, request_id, ok=True, action="members.remove", data={"ok": True})
                return
            self._respond(hub, ws, request_id, ok=False, action="members.remove", error="メンバーが見つかりません")
            return
        project["members"] = [m for m in members if m.get("username") != target]
        project["updatedAt"] = int(time.time() * 1000)
        self.save_owner_project(username, project)
        self.sync_member_indexes(username, project)
        self.publish_members_updated(project_id)
        self.publish_user_sync(target, "projects.updated", project_id=project_id)
        self.emit_project_saved(project)
        self._respond(hub, ws, request_id, ok=True, action="members.remove", data={"ok": True})

    def _invites_accept(self, ws, username, message, request_id, hub):
        _users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="invites.accept", error=err)
            return
        invite_id = (message.get("invite_id") or "").strip()
        incoming = self.load_incoming_invites(username).get("invites", [])
        invite_ref = next((item for item in incoming if item.get("id") == invite_id), None)
        if not invite_ref:
            self._respond(hub, ws, request_id, ok=False, action="invites.accept", error="招待が見つかりません")
            return
        owner = invite_ref.get("owner")
        project_id = invite_ref.get("project_id")
        owner_state = self.load_user_projects(owner)
        project = next(
            (item for item in owner_state.get("projects", []) if item.get("id") == project_id),
            None,
        )
        if not project:
            self.remove_incoming_invite(username, invite_id)
            self._respond(hub, ws, request_id, ok=False, action="invites.accept", error="プロジェクトが見つかりません")
            return
        pending = next(
            (item for item in self.normalize_invites(project.get("invites")) if item.get("id") == invite_id),
            None,
        )
        if not pending:
            self.remove_incoming_invite(username, invite_id)
            self._respond(hub, ws, request_id, ok=False, action="invites.accept", error="招待は無効です")
            return
        members = self.normalize_members(project.get("members"), owner)
        if not any(m.get("username") == username for m in members):
            members.append(
                {
                    "username": username,
                    "role": pending.get("role") or "viewer",
                    "joined_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "invited_by": pending.get("invited_by") or owner,
                }
            )
        project["members"] = members
        project["invites"] = [
            item for item in self.normalize_invites(project.get("invites")) if item.get("id") != invite_id
        ]
        project["updatedAt"] = int(time.time() * 1000)
        self.save_owner_project(owner, project)
        self.sync_member_indexes(owner, project)
        self.remove_incoming_invite(username, invite_id)
        self.publish_members_updated(project_id)
        self.publish_user_sync(username, "projects.updated", project_id=project_id)
        self.emit_project_saved(project)
        enriched = self.attach_project_access(dict(project), username)
        self._respond(hub, ws, request_id, ok=True, action="invites.accept", data={"project": enriched})

    def _invites_decline(self, ws, username, message, request_id, hub):
        _users, record, err = self._projects_guard(username)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="invites.decline", error=err)
            return
        invite_id = (message.get("invite_id") or "").strip()
        incoming = self.load_incoming_invites(username).get("invites", [])
        invite_ref = next((item for item in incoming if item.get("id") == invite_id), None)
        if not invite_ref:
            self._respond(hub, ws, request_id, ok=False, action="invites.decline", error="招待が見つかりません")
            return
        owner = invite_ref.get("owner")
        project_id = invite_ref.get("project_id")
        owner_state = self.load_user_projects(owner)
        project = next(
            (item for item in owner_state.get("projects", []) if item.get("id") == project_id),
            None,
        )
        if project:
            project["invites"] = [
                item
                for item in self.normalize_invites(project.get("invites"))
                if item.get("id") != invite_id
            ]
            project["updatedAt"] = int(time.time() * 1000)
            self.save_owner_project(owner, project)
            self.publish_members_updated(project_id)
            self.emit_project_saved(project)
        self.remove_incoming_invite(username, invite_id)
        self._respond(hub, ws, request_id, ok=True, action="invites.decline", data={"ok": True})

    def _chat_send(self, ws, username, message, hub):
        request_id = (message.get("request_id") or str(uuid.uuid4())).strip()
        project_id = (message.get("project_id") or "").strip()
        content = str(message.get("content") or "").strip()
        if not project_id or not content:
            self._broadcast_chat(
                hub,
                project_id,
                {
                    "type": "chat.error",
                    "request_id": request_id,
                    "error": "project_id と content が必要です",
                    "sender": username,
                },
            )
            return

        record, err = self._chat_guard(username)
        if err:
            self._broadcast_chat(
                hub,
                project_id,
                {"type": "chat.error", "request_id": request_id, "error": err, "sender": username},
            )
            return

        project, source = self.find_accessible_project(username, project_id)
        if not project:
            self._broadcast_chat(
                hub,
                project_id,
                {"type": "chat.error", "request_id": request_id, "error": "プロジェクトが見つかりません", "sender": username},
            )
            return
        if not self.has_permission(project, username, "chat"):
            self._broadcast_chat(
                hub,
                project_id,
                {"type": "chat.error", "request_id": request_id, "error": "このプロジェクトでチャットする権限がありません", "sender": username},
            )
            return

        owner = (project.get("owner") or username).strip().lower()
        user_message = {
            "role": "user",
            "content": content,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        updated = dict(project)
        updated["messages"] = list(updated.get("messages") or []) + [user_message]
        updated["updatedAt"] = int(time.time() * 1000)
        saved_state = self.save_owner_project(owner, updated)
        project = next(
            (item for item in saved_state.get("projects", []) if item.get("id") == project_id),
            updated,
        )
        self.emit_project_saved(project)
        self._broadcast_chat(
            hub,
            project_id,
            {"type": "chat.user", "request_id": request_id, "message": user_message, "sender": username},
        )

        stop_event = threading.Event()
        with self._gen_lock:
            previous = self._generations.get(ws)
            if previous:
                previous["stop_event"].set()
            self._generations[ws] = {
                "request_id": request_id,
                "stop_event": stop_event,
                "project_id": project_id,
            }

        thread = threading.Thread(
            target=self._run_chat_generation,
            args=(ws, username, project_id, owner, request_id, stop_event, hub, message, record),
            daemon=True,
        )
        thread.start()

    def _run_chat_generation(self, ws, username, project_id, owner, request_id, stop_event, hub, message, record):
        mode = self.normalize_project_mode(message.get("mode"))
        emit_reasoning_cards = self.user_reasoning_cards_enabled(record)
        disable_reasoning = self.user_reasoning_disabled(record)
        config = self.load_system_config()
        requested_model = (message.get("model") or "").strip()
        segment_text = ""
        provider_id = None
        try:
            resolved = self.resolve_chat_model(requested_model, config)
        except ValueError as exc:
            self._broadcast_chat(
                hub,
                project_id,
                {"type": "chat.error", "request_id": request_id, "error": str(exc), "sender": username},
            )
            return

        catalog_model_id = resolved["model_id"]
        api_model = resolved["api_model"]
        provider_id = resolved["provider"]
        reasoning_in_english = self.effective_reasoning_in_english(
            record,
            provider_id=provider_id,
            disable_reasoning=disable_reasoning,
        )
        client, api_key = self.make_openai_client_for_provider(provider_id, config.get("providers"))
        if not api_key:
            self._broadcast_chat(
                hub,
                project_id,
                {
                    "type": "chat.error",
                    "request_id": request_id,
                    "error": f"{provider_id} の API キーが設定されていません",
                    "sender": username,
                },
            )
            return

        project, _source = self.find_accessible_project(username, project_id)
        if not project:
            return

        turn_usage = self.empty_usage()
        prepared = None

        def make_client(_key):
            return client

        try:
            prepared = self.filter_chat_messages(
                self.prepare_project_chat_messages(project, mode),
                provider_id=provider_id,
            )
            stream = self.stream_project_chat(
                project,
                mode,
                api_key=api_key,
                model=api_model,
                make_client=make_client,
                sse_event=self.sse_event,
                usage_out=turn_usage,
                emit_reasoning_cards=emit_reasoning_cards,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
                reasoning_in_english=reasoning_in_english,
                filter_messages_fn=self.filter_chat_messages,
            )
            for chunk in stream:
                if stop_event.is_set():
                    break
                payload = self._parse_sse_payload(chunk)
                if not payload:
                    continue
                if payload.get("error"):
                    self._broadcast_chat(
                        hub,
                        project_id,
                        {
                            "type": "chat.error",
                            "request_id": request_id,
                            "error": payload.get("error"),
                            "sender": username,
                        },
                    )
                    return
                if payload.get("content"):
                    segment_text += payload.get("content")
                    self._broadcast_chat(
                        hub,
                        project_id,
                        {
                            "type": "chat.stream",
                            "request_id": request_id,
                            "content": payload.get("content"),
                            "sender": username,
                        },
                    )
                if payload.get("done"):
                    break
        except Exception as exc:
            logger.warning(
                "project ws chat error user=%s project=%s: %s",
                username,
                project_id,
                exc,
            )
            self._broadcast_chat(
                hub,
                project_id,
                {
                    "type": "chat.error",
                    "request_id": request_id,
                    "error": self.format_chat_provider_error(exc, provider_id=provider_id),
                    "sender": username,
                },
            )
            return
        finally:
            if prepared is not None and not int(turn_usage.get("total_tokens") or 0):
                self.merge_usage(
                    turn_usage,
                    self.estimate_turn_tokens(prepared, "", "", api_model),
                )
            self.record_chat_usage(username, turn_usage, model=catalog_model_id)

        text = segment_text.strip()
        if not text or stop_event.is_set():
            self._broadcast_chat(
                hub,
                project_id,
                {"type": "chat.done", "request_id": request_id, "sender": username, "stopped": True},
            )
            return

        assistant_message = {
            "role": "assistant",
            "content": text,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        owner_state = self.load_user_projects(owner)
        fresh = next(
            (item for item in owner_state.get("projects", []) if item.get("id") == project_id),
            None,
        )
        if fresh:
            fresh = dict(fresh)
            fresh["messages"] = list(fresh.get("messages") or []) + [assistant_message]
            fresh["updatedAt"] = int(time.time() * 1000)
            saved_state = self.save_owner_project(owner, fresh)
            saved = next(
                (item for item in saved_state.get("projects", []) if item.get("id") == project_id),
                fresh,
            )
            self.emit_project_saved(saved)
        self._broadcast_chat(
            hub,
            project_id,
            {
                "type": "chat.done",
                "request_id": request_id,
                "message": assistant_message,
                "sender": username,
            },
        )

        with self._gen_lock:
            entry = self._generations.get(ws)
            if entry and entry.get("request_id") == request_id:
                self._generations.pop(ws, None)


def build_project_ws_handlers(**deps):
    return ProjectWsHandlers(**deps)
