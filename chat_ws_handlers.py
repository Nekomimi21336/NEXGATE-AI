import logging
import threading
import uuid

from chat_generation import run_chat_generation
from chat_request_prepare import prepare_chat_send_job
from chat_session_collab import (
    COLLAB_PARTICIPATE,
    COLLAB_PRIVATE,
    COLLAB_VIEW_ONLY,
    PERMISSION_CHAT,
    PERMISSION_EDIT_SETTINGS,
    PERMISSION_MANAGE_SHARE,
    has_permission,
    resolve_session_access,
    set_collab_mode,
    update_collab_settings,
)

logger = logging.getLogger(__name__)


class ChatWsHandlers:
    def __init__(self, **deps):
        for key, value in deps.items():
            setattr(self, key, value)
        self._gen_lock = threading.Lock()
        self._active_by_session = {}

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

    def _session_key(self, owner, session_id):
        return f"{(owner or '').strip().lower()}:{(session_id or '').strip()}"

    def _resolve_access(self, username, owner, session_id):
        owner = (owner or username or "").strip().lower()
        session_id = (session_id or "").strip()
        if not session_id:
            return None, "session_id が必要です"
        access = resolve_session_access(username, owner, session_id)
        if not access:
            return None, "forbidden"
        if access["role"] != "owner":
            meta = self.get_chat_session_meta(owner, session_id)
            if not meta:
                return None, "forbidden"
        return access, None

    def _build_session_state(self, access):
        owner = access["owner"]
        session_id = access["session_id"]
        meta = self.get_chat_session_meta(owner, session_id) or {}
        messages = self.get_chat_session_messages(owner, session_id) or []
        collab = self.get_collab_record(owner, session_id) or {}
        return {
            "owner": owner,
            "session_id": session_id,
            "role": access.get("role"),
            "permissions": access.get("permissions") or [],
            "collab_mode": collab.get("mode") or COLLAB_PRIVATE,
            "title": meta.get("title") or "新しいチャット",
            "messages": messages,
            "settings": collab.get("settings") or {},
            "updated_at": meta.get("updated_at"),
        }

    def _broadcast_session_patch(self, hub, owner, session_id, patch, *, editor=None, exclude_ws=None):
        hub.publish_session_update(owner, session_id, patch, editor=editor, exclude_ws=exclude_ws)

    def _active_generation_id(self, owner, session_id):
        key = self._session_key(owner, session_id)
        with self._gen_lock:
            return self._active_by_session.get(key)

    def _reject_if_generating(self, hub, ws, owner, session_id, request_id):
        active = self._active_generation_id(owner, session_id)
        if not active:
            return False
        self._send(
            hub,
            ws,
            {
                "type": "chat.error",
                "request_id": request_id,
                "session_id": session_id,
                "owner": owner,
                "error": "このセッションでは既に生成が進行中です",
                "code": "generation_in_progress",
                "active_request_id": active,
            },
        )
        return True

    def _broadcast_user_message(self, hub, owner, session_id, username, messages):
        last_user = None
        for item in reversed(messages or []):
            if isinstance(item, dict) and (item.get("role") or "").strip().lower() == "user":
                last_user = item
                break
        if not last_user:
            return None
        from chat_sessions_storage import _sanitize_message

        entry = _sanitize_message(last_user)
        if not entry:
            return None
        current = self.get_chat_session_messages(owner, session_id) or []
        merged = list(current)
        duplicate = False
        for existing in reversed(merged[-5:]):
            if (
                existing.get("role") == "user"
                and existing.get("content") == entry.get("content")
                and (existing.get("created_at") or "") == (entry.get("created_at") or "")
            ):
                duplicate = True
                break
        if not duplicate:
            merged.append(entry)
            was_new = self.get_chat_session_meta(owner, session_id) is None
            saved = self.upsert_chat_session(owner, session_id, messages=merged)
            if saved:
                from chat_session_index_realtime import notify_after_upsert

                notify_after_upsert(owner, saved, was_new=was_new, editor=username)
        hub.broadcast_session(
            owner,
            session_id,
            {
                "type": "chat.user_message",
                "message": entry,
                "editor": username,
            },
        )
        return entry

    def _notify_generation_started(
        self,
        hub,
        owner,
        session_id,
        request_id,
        username,
        *,
        user_message=None,
        exclude_ws=None,
    ):
        payload = {
            "type": "chat.generation.started",
            "request_id": request_id,
            "session_id": session_id,
            "owner": owner,
            "started_by": username,
        }
        if user_message:
            payload["user_message"] = user_message
        hub.broadcast_session(owner, session_id, payload, exclude_ws=exclude_ws)

    def _persist_messages(
        self,
        owner,
        session_id,
        messages,
        *,
        title=None,
        editor=None,
        exclude_ws=None,
    ):
        if not messages:
            return None
        was_new = self.get_chat_session_meta(owner, session_id) is None
        saved = self.upsert_chat_session(
            owner,
            session_id,
            title=title,
            messages=messages,
        )
        if saved:
            from chat_session_index_realtime import notify_after_upsert

            notify_after_upsert(
                owner,
                saved,
                was_new=was_new,
                editor=editor,
                exclude_ws=exclude_ws,
            )
        elif was_new:
            from chat_session_index_realtime import notify_session_deleted

            notify_session_deleted(owner, session_id, editor=editor, exclude_ws=exclude_ws)
        return saved

    def _chat_deps(self):
        return {
            "load_users": self.load_users,
            "feature_blocked": self.feature_blocked,
            "is_user_blocked": self.is_user_blocked,
            "plan_allows_chat": self.plan_allows_chat,
            "effective_plan_for_features": self.effective_plan_for_features,
            "create_billing_event": self.create_billing_event,
            "update_billing_event": self.update_billing_event,
            "try_reserve_chat_usage": self.try_reserve_chat_usage,
            "usage_summary_for_record": self.usage_summary_for_record,
            "user_web_search_enabled": self.user_web_search_enabled,
            "resolve_engines_for_plan": self.resolve_engines_for_plan,
            "get_plan_features": self.get_plan_features,
            "user_geolocation_enabled": self.user_geolocation_enabled,
            "sanitize_location_context": self.sanitize_location_context,
            "user_reasoning_cards_enabled": self.user_reasoning_cards_enabled,
            "user_tool_trace_enabled": self.user_tool_trace_enabled,
            "user_full_info_display_enabled": self.user_full_info_display_enabled,
            "user_expression_extension_enabled": self.user_expression_extension_enabled,
            "user_reasoning_disabled": self.user_reasoning_disabled,
            "user_cost_performance_maximized": self.user_cost_performance_maximized,
            "user_google_calendar_enabled": self.user_google_calendar_enabled,
            "user_google_gmail_enabled": self.user_google_gmail_enabled,
            "resolve_user_tasks_enabled": self.resolve_user_tasks_enabled,
            "plan_tasks_enabled": self.plan_tasks_enabled,
            "resolve_user_memory_enabled": self.resolve_user_memory_enabled,
            "plan_memory_enabled": self.plan_memory_enabled,
            "user_computelab_tools_enabled": self.user_computelab_tools_enabled,
            "user_image_generation_enabled": self.user_image_generation_enabled,
            "resolve_user_deep_research_enabled": self.resolve_user_deep_research_enabled,
            "plan_deep_research_enabled": self.plan_deep_research_enabled,
            "get_user_deep_research_prefs": self.get_user_deep_research_prefs,
            "user_intelligent_search_override_enabled": self.user_intelligent_search_override_enabled,
            "get_user_image_generation_prefs": self.get_user_image_generation_prefs,
            "find_custom_agent": self.find_custom_agent,
            "apply_custom_agent_chat_reasoning_prefs": self.apply_custom_agent_chat_reasoning_prefs,
            "load_system_config": self.load_system_config,
            "user_file_upload_enabled": self.user_file_upload_enabled,
            "message_has_pdfs": self.message_has_pdfs,
            "preprocess_messages_with_pdf": self.preprocess_messages_with_pdf,
            "user_ocr_enabled": self.user_ocr_enabled,
            "ocr_globally_enabled": self.ocr_globally_enabled,
            "message_has_images": self.message_has_images,
            "resolve_ocr_model_for_plan": self.resolve_ocr_model_for_plan,
            "get_anthropic_api_key": self.get_anthropic_api_key,
            "preprocess_messages_with_ocr": self.preprocess_messages_with_ocr,
            "resolve_chat_model": self.resolve_chat_model,
            "make_openai_client_for_provider": self.make_openai_client_for_provider,
            "normalize_model_entry": self.normalize_model_entry,
            "effective_reasoning_in_english": self.effective_reasoning_in_english,
            "user_user_questions_enabled": self.user_user_questions_enabled,
            "summarize_messages_for_audit": self.summarize_messages_for_audit,
            "last_user_message_text": self.last_user_message_text,
        }

    def _generation_deps(self):
        return {
            "begin_monitored_chat": self.begin_monitored_chat,
            "begin_request_detail": self.begin_request_detail,
            "update_billing_event": self.update_billing_event,
            "admin_monitor_token_snapshot": self.admin_monitor_token_snapshot,
            "compute_turn_price_usd": self.compute_turn_price_usd,
            "update_monitored_chat": self.update_monitored_chat,
            "record_request_detail_sse": self.record_request_detail_sse,
            "filter_chat_messages": self.filter_chat_messages,
            "stream_agent_chat": self.stream_agent_chat,
            "stream_chat_completion": self.stream_chat_completion,
            "stream_resume_after_ask_user": self.stream_resume_after_ask_user,
            "stream_with_abort": self.stream_with_abort,
            "is_chat_aborted": self.is_chat_aborted,
            "format_chat_provider_error": self.format_chat_provider_error,
            "resolve_turn_token_usage": self.resolve_turn_token_usage,
            "record_chat_usage": self.record_chat_usage,
            "finish_request_detail": self.finish_request_detail,
            "end_monitored_chat": self.end_monitored_chat,
            "merge_usage": self.merge_usage,
            "empty_usage": self.empty_usage,
            "public_base_url": self.public_base_url,
            "user_user_questions_enabled": self.user_user_questions_enabled,
            "sse_event": self.sse_event,
        }

    def handle(self, ws, username, message, hub):
        action = (message.get("action") or "").strip().lower()
        request_id = message.get("request_id")

        if action == "ping":
            self._send(hub, ws, {"type": "pong"})
            return

        if action == "join":
            self._handle_join(ws, username, message, hub)
            return

        if action == "leave":
            session_id = (message.get("session_id") or "").strip()
            owner = (message.get("owner") or username).strip().lower()
            hub.leave_session(ws, owner, session_id)
            self._send(hub, ws, {"type": "left", "session_id": session_id, "owner": owner})
            return

        if action == "chat.stop":
            rid = (message.get("request_id") or "").strip()
            if rid:
                self.request_chat_abort(rid)
            return

        if action == "session.save":
            self._session_save(ws, username, message, request_id, hub)
            return

        if action == "session.share":
            self._session_share(ws, username, message, request_id, hub)
            return

        if action == "chat.send":
            self._chat_send(ws, username, message, hub)
            return

        if action == "chat.resume":
            self._chat_resume(ws, username, message, hub)
            return

        if request_id:
            self._respond(hub, ws, request_id, ok=False, error="unknown_action")
            return
        self._send(hub, ws, {"type": "error", "error": "unknown_action"})

    def _handle_join(self, ws, username, message, hub):
        session_id = (message.get("session_id") or "").strip()
        owner = (message.get("owner") or username).strip().lower()
        access, err = self._resolve_access(username, owner, session_id)
        if err:
            self._send(
                hub,
                ws,
                {"type": "error", "error": err, "session_id": session_id, "owner": owner},
            )
            return
        hub.join_session(ws, access["owner"], session_id)
        state = self._build_session_state(access)
        self._send(
            hub,
            ws,
            {
                "type": "joined",
                "session_id": session_id,
                "owner": access["owner"],
                "role": access.get("role"),
                "permissions": access.get("permissions") or [],
                "collab_mode": state.get("collab_mode") or COLLAB_PRIVATE,
            },
        )
        self._send(hub, ws, {"type": "session.state", **state})
        snapshot = hub.session_snapshot(access["owner"], session_id)
        if snapshot:
            self._send(hub, ws, snapshot)
        active_request_id = self._active_generation_id(access["owner"], session_id)
        if active_request_id:
            self._send(
                hub,
                ws,
                {
                    "type": "chat.generation.started",
                    "request_id": active_request_id,
                    "session_id": session_id,
                    "owner": access["owner"],
                    "resumed": True,
                },
            )

    def _session_save(self, ws, username, message, request_id, hub):
        session_id = (message.get("session_id") or "").strip()
        owner = (message.get("owner") or username).strip().lower()
        access, err = self._resolve_access(username, owner, session_id)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="session.save", error=err)
            return

        patch = message.get("patch") if isinstance(message.get("patch"), dict) else {}
        if not patch:
            self._respond(hub, ws, request_id, ok=False, action="session.save", error="patch が必要です")
            return

        outgoing = {}
        if patch.get("settings") is not None:
            if not has_permission(access, PERMISSION_EDIT_SETTINGS):
                self._respond(hub, ws, request_id, ok=False, action="session.save", error="forbidden")
                return
            settings = patch.get("settings") if isinstance(patch.get("settings"), dict) else {}
            record = update_collab_settings(owner, session_id, settings)
            outgoing["settings"] = record.get("settings") or {}

        if patch.get("messages") is not None:
            if not has_permission(access, PERMISSION_CHAT) and access.get("role") != "owner":
                self._respond(hub, ws, request_id, ok=False, action="session.save", error="forbidden")
                return
            messages = patch.get("messages")
            if not isinstance(messages, list):
                self._respond(hub, ws, request_id, ok=False, action="session.save", error="invalid messages")
                return
            title = patch.get("title")
            saved = self._persist_messages(
                owner,
                session_id,
                messages,
                title=title,
                editor=username,
                exclude_ws=ws,
            )
            outgoing["messages"] = messages
            if title:
                outgoing["title"] = title
            if saved:
                outgoing["updated_at"] = saved.get("updated_at")

        if patch.get("message_append") is not None:
            if not has_permission(access, PERMISSION_CHAT):
                self._respond(hub, ws, request_id, ok=False, action="session.save", error="forbidden")
                return
            entry = patch.get("message_append")
            if not isinstance(entry, dict):
                self._respond(hub, ws, request_id, ok=False, action="session.save", error="invalid message")
                return
            current = self.get_chat_session_messages(owner, session_id) or []
            current = list(current)
            current.append(entry)
            saved = self._persist_messages(
                owner,
                session_id,
                current,
                editor=username,
                exclude_ws=ws,
            )
            outgoing["message_append"] = entry
            if saved:
                outgoing["updated_at"] = saved.get("updated_at")

        if patch.get("title") is not None and patch.get("messages") is None:
            if access.get("role") != "owner":
                self._respond(hub, ws, request_id, ok=False, action="session.save", error="forbidden")
                return
            title = str(patch.get("title") or "").strip()
            saved = self.upsert_chat_session(owner, session_id, title=title)
            outgoing["title"] = title
            if saved:
                outgoing["updated_at"] = saved.get("updated_at")
                from chat_session_index_realtime import notify_after_upsert

                notify_after_upsert(
                    owner,
                    saved,
                    was_new=False,
                    editor=username,
                    exclude_ws=ws,
                )

        if not outgoing:
            self._respond(hub, ws, request_id, ok=False, action="session.save", error="empty patch")
            return

        self._broadcast_session_patch(
            hub,
            owner,
            session_id,
            outgoing,
            editor=username,
            exclude_ws=ws,
        )
        self._respond(hub, ws, request_id, ok=True, action="session.save", data=outgoing)

    def _session_share(self, ws, username, message, request_id, hub):
        session_id = (message.get("session_id") or "").strip()
        owner = (message.get("owner") or username).strip().lower()
        access, err = self._resolve_access(username, owner, session_id)
        if err:
            self._respond(hub, ws, request_id, ok=False, action="session.share", error=err)
            return
        if not has_permission(access, PERMISSION_MANAGE_SHARE):
            self._respond(hub, ws, request_id, ok=False, action="session.share", error="forbidden")
            return

        mode = (message.get("collab_mode") or COLLAB_PRIVATE).strip().lower()
        if mode not in {COLLAB_PRIVATE, COLLAB_VIEW_ONLY, COLLAB_PARTICIPATE}:
            self._respond(hub, ws, request_id, ok=False, action="session.share", error="invalid collab_mode")
            return

        try:
            record = set_collab_mode(owner, session_id, mode)
        except ValueError as exc:
            self._respond(hub, ws, request_id, ok=False, action="session.share", error=str(exc))
            return

        payload = self.collab_public_payload(record)
        patch = {
            "collab_mode": payload.get("collab_mode") or COLLAB_PRIVATE,
            "collab_id": payload.get("collab_id"),
            "collab_url": payload.get("url"),
        }
        self._broadcast_session_patch(hub, owner, session_id, patch, editor=username, exclude_ws=ws)
        self._respond(hub, ws, request_id, ok=True, action="session.share", data=payload)

    def _start_generation(self, job, hub):
        session_id = job.get("session_id") or ""
        owner = (job.get("owner") or job.get("username") or "").strip().lower()
        request_id = job["request_id"]

        def runner():
            try:
                run_chat_generation(job, hub, self._generation_deps())
            except Exception as exc:
                logger.exception("chat generation thread failed request=%s: %s", request_id, exc)
                hub.publish_status(owner, session_id, request_id, "failed", error=str(exc))
                hub.broadcast_session(
                    owner,
                    session_id,
                    {
                        "type": "chat.generation.ended",
                        "request_id": request_id,
                        "status": "failed",
                    },
                )
                hub.finish_job(request_id, status="failed")
            finally:
                with self._gen_lock:
                    key = self._session_key(owner, session_id)
                    if self._active_by_session.get(key) == request_id:
                        del self._active_by_session[key]

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

    def _chat_send(self, ws, username, message, hub):
        request_id = (message.get("request_id") or str(uuid.uuid4())).strip()
        session_id = (message.get("session_id") or "").strip()
        owner = (message.get("owner") or username).strip().lower()

        access, err = self._resolve_access(username, owner, session_id)
        if err:
            self._send(
                hub,
                ws,
                {
                    "type": "chat.error",
                    "request_id": request_id,
                    "session_id": session_id,
                    "owner": owner,
                    "error": err,
                },
            )
            return
        if not has_permission(access, PERMISSION_CHAT):
            self._send(
                hub,
                ws,
                {
                    "type": "chat.error",
                    "request_id": request_id,
                    "session_id": session_id,
                    "owner": owner,
                    "error": "このセッションでは送信できません",
                },
            )
            return

        body = {
            "messages": message.get("messages") or [],
            "model": message.get("model"),
            "session_id": session_id,
            "location_context": message.get("location_context"),
            "chat_tools": message.get("chat_tools"),
            "custom_agent_id": message.get("custom_agent_id"),
            "_deps": self._chat_deps(),
        }
        job, err = prepare_chat_send_job(
            username,
            body,
            client_ip=message.get("client_ip") or "",
            user_agent=message.get("user_agent") or "",
        )
        if err:
            self._send(
                hub,
                ws,
                {
                    "type": "chat.error",
                    "request_id": request_id,
                    "session_id": session_id,
                    "owner": owner,
                    "error": err,
                },
            )
            return

        job["request_id"] = job.get("request_id") or request_id
        job["owner"] = owner

        settings_patch = {}
        if message.get("model"):
            settings_patch["model_id"] = message.get("model")
        if message.get("custom_agent_id"):
            settings_patch["custom_agent_id"] = message.get("custom_agent_id")
        if isinstance(message.get("chat_tools"), dict):
            settings_patch["chat_tools"] = message.get("chat_tools")
        if settings_patch and has_permission(access, PERMISSION_EDIT_SETTINGS):
            record = update_collab_settings(owner, session_id, settings_patch)
            self._broadcast_session_patch(
                hub,
                owner,
                session_id,
                {"settings": record.get("settings") or {}},
                editor=username,
            )

        with self._gen_lock:
            key = self._session_key(owner, session_id)
            if self._active_by_session.get(key):
                self._reject_if_generating(hub, ws, owner, session_id, job["request_id"])
                return
            self._active_by_session[key] = job["request_id"]

        user_entry = self._broadcast_user_message(
            hub, owner, session_id, username, body.get("messages") or []
        )

        if session_id:
            hub.join_session(ws, owner, session_id)

        self._send(
            hub,
            ws,
            {
                "type": "chat.accepted",
                "request_id": job["request_id"],
                "session_id": session_id,
                "owner": owner,
                "started_by": username,
            },
        )
        self._notify_generation_started(
            hub,
            owner,
            session_id,
            job["request_id"],
            username,
            user_message=user_entry,
        )
        self._start_generation(job, hub)

    def _chat_resume(self, ws, username, message, hub):
        token = (message.get("token") or "").strip()
        if not token:
            self._send(hub, ws, {"type": "error", "error": "token が必要です"})
            return

        session_id = (message.get("session_id") or "").strip()
        owner = (message.get("owner") or username).strip().lower()
        access, err = self._resolve_access(username, owner, session_id)
        if err:
            self._send(hub, ws, {"type": "chat.error", "error": err})
            return
        if not has_permission(access, PERMISSION_CHAT):
            self._send(hub, ws, {"type": "chat.error", "error": "このセッションでは送信できません"})
            return

        if self.feature_blocked("chat_disabled"):
            self._send(hub, ws, {"type": "chat.error", "error": "現在、チャット機能は一時的に制限されています"})
            return

        users = self.load_users()
        chat_user = users.get(username, {})
        if self.is_user_blocked(chat_user):
            self._send(hub, ws, {"type": "chat.error", "error": "アカウントが利用停止中のため、チャットを利用できません"})
            return
        if not self.user_user_questions_enabled(chat_user):
            self._send(hub, ws, {"type": "chat.error", "error": "ユーザーへの質問は無効です"})
            return

        pending = self.consume_user_question_pending(token, username)
        if not pending:
            self._send(hub, ws, {"type": "chat.error", "error": "質問の有効期限が切れたか、既に回答済みです"})
            return

        allowed, plan_err = self.plan_allows_chat(username)
        if not allowed:
            self._send(hub, ws, {"type": "chat.error", "error": plan_err})
            return

        request_id = (message.get("request_id") or str(uuid.uuid4())).strip()
        dismissed = bool(message.get("dismissed"))
        answers = message.get("answers") if isinstance(message.get("answers"), list) else []

        config = self.load_system_config()
        model_id = (pending.get("model") or "").strip()
        if not model_id:
            self._send(hub, ws, {"type": "chat.error", "error": "再開データが不正です"})
            return

        try:
            resolved = self.resolve_chat_model(model_id, config)
        except ValueError as exc:
            self._send(hub, ws, {"type": "chat.error", "error": str(exc)})
            return

        catalog_model_id = resolved["model_id"]
        api_model = resolved["api_model"]
        provider_id = resolved["provider"]
        agent_profile = resolved["agent_profile"]
        models_cfg = config.get("models") or {}
        catalog_model_entry = models_cfg.get(catalog_model_id) or self.normalize_model_entry(
            catalog_model_id, {}
        )
        client, api_key = self.make_openai_client_for_provider(
            provider_id, config.get("providers")
        )
        if not api_key:
            self._send(
                hub,
                ws,
                {"type": "chat.error", "error": f"{provider_id} の API キーが設定されていません"},
            )
            return

        if chat_user.get("role") == "admin" or self.usage_summary_for_record(chat_user).get(
            "usage_unlimited"
        ):
            payment_type = "included"
        else:
            payment_type = "subscription"
        billing_event = self.create_billing_event(
            username,
            session_id=session_id,
            model_id=catalog_model_id,
            payment_type=payment_type,
            status="running",
        )

        if (
            chat_user.get("role") != "admin"
            and not self.usage_summary_for_record(chat_user).get("usage_unlimited")
        ):
            reserved, reserve_err = self.try_reserve_chat_usage(
                username, billing_event["id"], catalog_model_entry
            )
            if not reserved:
                self.update_billing_event(billing_event["id"], status="blocked")
                self._send(hub, ws, {"type": "chat.error", "error": reserve_err or "利用枠が不足しています"})
                return

        job = {
            "request_id": billing_event["id"],
            "owner": owner,
            "session_id": session_id,
            "username": username,
            "chat_user": chat_user,
            "messages_for_chat": pending.get("messages") or [],
            "plan_key": self.effective_plan_for_features(chat_user),
            "emit_reasoning_cards": self.user_reasoning_cards_enabled(chat_user),
            "emit_tool_trace": self.user_tool_trace_enabled(chat_user),
            "emit_full_info": self.user_full_info_display_enabled(chat_user),
            "disable_reasoning": self.user_reasoning_disabled(chat_user),
            "cost_performance_on": False,
            "google_calendar_on": False,
            "google_gmail_on": False,
            "tasks_on": False,
            "memory_on": False,
            "computelab_on": False,
            "image_gen_on": False,
            "deep_research_on": False,
            "deep_research_prefs": None,
            "image_gen_prefs": None,
            "custom_agent": None,
            "config": config,
            "resolved": resolved,
            "catalog_model_id": catalog_model_id,
            "catalog_model_entry": catalog_model_entry,
            "api_model": api_model,
            "provider_id": provider_id,
            "agent_profile": agent_profile,
            "reasoning_in_english": self.effective_reasoning_in_english(
                chat_user,
                provider_id=provider_id,
                disable_reasoning=self.user_reasoning_disabled(chat_user),
            ),
            "client": client,
            "api_key": api_key,
            "client_ip": "",
            "user_agent": "",
            "audit_messages_summary": None,
            "audit_user_message": "",
            "search_allowed": False,
            "search_engines": {"tavily": False, "serper": False, "ddg": False},
            "location_hint": None,
            "resume": {
                "pending": pending,
                "answers": answers,
                "dismissed": dismissed,
            },
        }

        with self._gen_lock:
            key = self._session_key(owner, session_id)
            if self._active_by_session.get(key):
                self._reject_if_generating(hub, ws, owner, session_id, job["request_id"])
                return
            self._active_by_session[key] = job["request_id"]

        if session_id:
            hub.join_session(ws, owner, session_id)

        self._send(
            hub,
            ws,
            {
                "type": "chat.accepted",
                "request_id": job["request_id"],
                "session_id": session_id,
                "owner": owner,
                "started_by": username,
            },
        )
        self._notify_generation_started(
            hub,
            owner,
            session_id,
            job["request_id"],
            username,
        )
        self._start_generation(job, hub)


def build_chat_ws_handlers(**deps):
    return ChatWsHandlers(**deps)
