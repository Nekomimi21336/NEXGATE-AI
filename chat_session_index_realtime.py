from chat_realtime import get_chat_hub


def session_index_payload(entry):
    if not entry or not entry.get("id"):
        return None
    payload = {
        "id": entry["id"],
        "title": entry.get("title") or "新しいチャット",
        "updated_at": entry.get("updated_at"),
        "favorite": bool(entry.get("favorite")),
    }
    created_at = entry.get("created_at")
    if created_at:
        payload["created_at"] = created_at
    return payload


def publish_sessions_index(
    username,
    action,
    *,
    session=None,
    session_id=None,
    editor=None,
    exclude_ws=None,
):
    username = (username or "").strip().lower()
    action = (action or "").strip().lower()
    if not username or not action:
        return
    payload = {"type": "sessions.index", "action": action}
    if session:
        payload["session"] = session
    if session_id:
        payload["session_id"] = session_id
    editor_key = (editor or "").strip().lower()
    if editor_key:
        payload["editor"] = editor_key
    get_chat_hub().broadcast_user(username, payload, exclude_ws=exclude_ws)


def notify_after_upsert(username, result, *, was_new=False, editor=None, exclude_ws=None):
    if not result:
        return
    session = session_index_payload(result)
    if not session:
        return
    action = "created" if was_new else "updated"
    publish_sessions_index(
        username,
        action,
        session=session,
        editor=editor,
        exclude_ws=exclude_ws,
    )


def notify_session_deleted(username, session_id, *, editor=None, exclude_ws=None):
    session_id = (session_id or "").strip()
    if not session_id:
        return
    publish_sessions_index(
        username,
        "deleted",
        session_id=session_id,
        editor=editor,
        exclude_ws=exclude_ws,
    )
