import json
import logging

logger = logging.getLogger(__name__)


def _parse_sse_payload(chunk):
    if not isinstance(chunk, str) or not chunk.startswith("data:"):
        return None
    raw = chunk[5:].strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def run_chat_generation(job, hub, deps):
    request_id = job["request_id"]
    session_id = job.get("session_id") or ""
    username = job["username"]
    chat_user = job["chat_user"]
    config = job["config"]
    api_model = job["api_model"]
    catalog_model_id = job["catalog_model_id"]
    catalog_model_entry = job["catalog_model_entry"]
    provider_id = job["provider_id"]
    agent_profile = job["agent_profile"]
    client = job["client"]
    emit_full_info = job.get("emit_full_info", False)

    begin_monitored_chat = deps["begin_monitored_chat"]
    begin_request_detail = deps["begin_request_detail"]
    update_billing_event = deps["update_billing_event"]
    admin_monitor_token_snapshot = deps["admin_monitor_token_snapshot"]
    compute_turn_price_usd = deps["compute_turn_price_usd"]
    update_monitored_chat = deps["update_monitored_chat"]
    record_request_detail_sse = deps["record_request_detail_sse"]
    filter_chat_messages = deps["filter_chat_messages"]
    stream_agent_chat = deps["stream_agent_chat"]
    stream_chat_completion = deps["stream_chat_completion"]
    stream_resume_after_ask_user = deps["stream_resume_after_ask_user"]
    stream_with_abort = deps["stream_with_abort"]
    is_chat_aborted = deps["is_chat_aborted"]
    format_chat_provider_error = deps["format_chat_provider_error"]
    resolve_turn_token_usage = deps["resolve_turn_token_usage"]
    record_chat_usage = deps["record_chat_usage"]
    finish_request_detail = deps["finish_request_detail"]
    end_monitored_chat = deps["end_monitored_chat"]
    merge_usage = deps["merge_usage"]
    empty_usage = deps["empty_usage"]
    public_base_url = deps["public_base_url"]
    user_user_questions_enabled = deps["user_user_questions_enabled"]

    update_billing_event(request_id, model_id=catalog_model_id)
    owner = username
    hub.register_job(request_id, owner, session_id, username)
    hub.publish_status(owner, session_id, request_id, "running")

    begin_monitored_chat(
        request_id=request_id,
        username=username,
        display_name=chat_user.get("display_name") or username,
        session_id=session_id,
        model_id=catalog_model_id,
    )
    begin_request_detail(
        request_id,
        username=username,
        display_name=chat_user.get("display_name") or username,
        session_id=session_id,
        model_id=catalog_model_id,
        client_ip=job.get("client_ip") or "",
        user_agent=job.get("user_agent") or "",
        messages_summary=job.get("audit_messages_summary"),
        user_message=job.get("audit_user_message"),
    )

    turn_usage = empty_usage()
    stream_text = {"output": "", "reasoning": ""}
    prepared = None
    event_status = "completed"
    stream_error_message = ""
    tool_stats = {"tool_call_count": 0, "tool_cost_usd": 0.0}
    paused_for_user = False

    def push_monitor_update(force=False):
        display_usage = admin_monitor_token_snapshot(
            turn_usage, prepared, stream_text, api_model
        )
        est_cost = compute_turn_price_usd(display_usage, catalog_model_entry)
        update_monitored_chat(
            request_id,
            token_usage=display_usage,
            cost_usd=est_cost,
            tool_call_count=tool_stats["tool_call_count"],
            force=force,
        )

    def publish_payload(payload, *, mirror_for_full_info=False):
        nonlocal stream_error_message, paused_for_user
        if not isinstance(payload, dict):
            return
        if payload.get("paused_for_user"):
            paused_for_user = True
        piece = payload.get("content")
        if piece:
            stream_text["output"] += piece
        reasoning = payload.get("reasoning")
        if isinstance(reasoning, dict) and reasoning.get("type") == "delta":
            stream_text["reasoning"] += reasoning.get("text") or ""
        usage_payload = payload.get("usage")
        if usage_payload and not payload.get("done"):
            merge_usage(turn_usage, usage_payload)
        if payload.get("error"):
            stream_error_message = str(payload.get("error") or "")
        for key in (
            "search",
            "fetch",
            "image_generation",
            "tasks_tool_used",
            "memory_tool_used",
            "computelab_tool_used",
        ):
            if payload.get(key):
                tool_stats["tool_call_count"] += 1
        img_evt = payload.get("image_generation")
        if isinstance(img_evt, dict) and img_evt.get("type") == "done":
            try:
                tool_stats["tool_cost_usd"] += max(
                    0.0, float(img_evt.get("price_usd") or 0)
                )
            except (TypeError, ValueError):
                pass
        if payload.get("tool_trace"):
            tool_stats["tool_call_count"] += 1
        record_request_detail_sse(request_id, payload)
        mirror = None
        if mirror_for_full_info and emit_full_info:
            from full_info_trace import mirror_sse_payload_to_full_info

            mirror = mirror_sse_payload_to_full_info(payload)
        hub.publish_event(owner, session_id, request_id, payload, mirror=mirror)
        push_monitor_update()

    sse_event = deps["sse_event"]

    def traced_emit(payload):
        publish_payload(payload, mirror_for_full_info=True)
        return sse_event(payload)

    def make_client(_key):
        return client

    def consume_stream(stream):
        nonlocal event_status
        for _chunk in stream_with_abort(stream, request_id):
            if is_chat_aborted(request_id):
                event_status = "cancelled"
                return

    try:
        resume = job.get("resume")
        if resume:
            prepared = filter_chat_messages(
                resume.get("pending", {}).get("messages") or [],
                provider_id=provider_id,
            )
            agent_stream = stream_resume_after_ask_user(
                resume.get("pending"),
                answers=resume.get("answers") or [],
                dismissed=bool(resume.get("dismissed")),
                client=client,
                model=api_model,
                sse_event=traced_emit,
                usage_out=turn_usage,
                emit_reasoning_cards=job["emit_reasoning_cards"],
                disable_reasoning=job["disable_reasoning"],
                provider_id=provider_id,
                agent_profile=agent_profile,
            )
            consume_stream(agent_stream)
        else:
            prepared = filter_chat_messages(
                job["messages_for_chat"], provider_id=provider_id
            )
            push_monitor_update(force=True)
            try:
                agent_stream = stream_agent_chat(
                    prepared,
                    api_key=job["api_key"],
                    model=api_model,
                    make_client=make_client,
                    sse_event=traced_emit,
                    usage_out=turn_usage,
                    allow_web_search=job["search_allowed"],
                    search_engines=job["search_engines"],
                    location_hint=job.get("location_hint"),
                    emit_reasoning_cards=job["emit_reasoning_cards"],
                    disable_reasoning=job["disable_reasoning"],
                    provider_id=provider_id,
                    agent_profile=agent_profile,
                    chat_username=username,
                    user_questions_enabled=user_user_questions_enabled(chat_user),
                    google_username=username,
                    google_calendar_enabled=job["google_calendar_on"],
                    google_gmail_enabled=job["google_gmail_on"],
                    tasks_enabled=job["tasks_on"],
                    tasks_username=username if job["tasks_on"] else None,
                    memory_enabled=job["memory_on"],
                    memory_username=username if job["memory_on"] else None,
                    computelab_enabled=job["computelab_on"],
                    computelab_username=username if job["computelab_on"] else None,
                    image_generation_enabled=job["image_gen_on"],
                    image_generation_config=config.get("image_generation"),
                    providers_config=config.get("providers"),
                    plan_key=job["plan_key"],
                    image_generation_prefs=job.get("image_gen_prefs"),
                    image_generation_username=username,
                    image_generation_public_base_url=public_base_url(),
                    reasoning_in_english=job["reasoning_in_english"],
                    emit_tool_trace=job["emit_tool_trace"],
                    emit_full_info=job["emit_full_info"],
                    deep_research_enabled=job["deep_research_on"] and job["search_allowed"],
                    deep_research_prefs=job.get("deep_research_prefs"),
                    intelligent_search_override=job.get("intelligent_search_override_on")
                    and job["search_allowed"],
                    custom_agent=job.get("custom_agent"),
                    cost_performance_maximized=job["cost_performance_on"],
                    expression_extension_enabled=job["expression_extension_on"],
                )
                consume_stream(agent_stream)
            except Exception as tool_err:
                err_text = str(tool_err).lower()
                if "tool" not in err_text and "function" not in err_text:
                    raise
                has_integrations = (
                    job["computelab_on"]
                    or job["google_calendar_on"]
                    or job["google_gmail_on"]
                    or job["tasks_on"]
                    or job["memory_on"]
                )
                if has_integrations:
                    logger.warning(
                        "agent tools failed user=%s provider=%s model=%s: %s",
                        username,
                        provider_id,
                        api_model,
                        tool_err,
                    )
                    publish_payload(
                        {
                            "error": (
                                "連携ツールの実行に失敗しました。"
                                f" {format_chat_provider_error(tool_err, provider_id=provider_id)}"
                            )
                        }
                    )
                    publish_payload({"done": True, "usage": turn_usage})
                else:
                    logger.warning(
                        "agent tools unavailable, falling back to plain chat user=%s: %s",
                        username,
                        tool_err,
                    )
                    plain_stream = stream_chat_completion(
                        prepared,
                        api_key=job["api_key"],
                        model=api_model,
                        make_client=make_client,
                        sse_event=traced_emit,
                        usage_out=turn_usage,
                        emit_reasoning_cards=job["emit_reasoning_cards"],
                        disable_reasoning=job["disable_reasoning"],
                        provider_id=provider_id,
                        reasoning_in_english=job["reasoning_in_english"],
                        cost_performance_maximized=job["cost_performance_on"],
                    )
                    consume_stream(plain_stream)
    except Exception as exc:
        event_status = "failed"
        logger.warning(
            "chat generation error user=%s provider=%s model=%s: %s",
            username,
            provider_id,
            api_model,
            exc,
        )
        publish_payload(
            {"error": format_chat_provider_error(exc, provider_id=provider_id)}
        )
    finally:
        if prepared is not None:
            resolved_usage = resolve_turn_token_usage(
                turn_usage,
                prepared,
                stream_text["output"],
                stream_text.get("reasoning") or "",
                api_model,
            )
            turn_usage.update(resolved_usage)
        if is_chat_aborted(request_id):
            event_status = "cancelled"
        push_monitor_update(force=True)
        turn_cost = record_chat_usage(
            username,
            turn_usage,
            model=catalog_model_id,
            tool_cost_usd=tool_stats.get("tool_cost_usd") or 0.0,
            billing_event_id=request_id,
        )
        update_billing_event(
            request_id,
            status=event_status,
            tool_call_count=tool_stats["tool_call_count"],
            token_usage=turn_usage,
            model_id=catalog_model_id,
        )
        detail_row = finish_request_detail(
            request_id,
            status=event_status,
            assistant_response=stream_text["output"],
            reasoning_text=stream_text.get("reasoning") or "",
            token_usage=turn_usage,
            cost_usd=turn_cost,
            tool_call_count=tool_stats["tool_call_count"],
            model_id=catalog_model_id,
            error_message=stream_error_message,
        )
        duration_seconds = (
            float(detail_row.get("duration_seconds"))
            if detail_row and detail_row.get("duration_seconds") is not None
            else None
        )
        end_monitored_chat(
            request_id,
            status=event_status,
            token_usage=turn_usage,
            cost_usd=turn_cost,
            tool_call_count=tool_stats["tool_call_count"],
            model_id=catalog_model_id,
            duration_seconds=duration_seconds,
        )
        final_output = stream_text.get("output") or ""
        hub.publish_status(
            owner,
            session_id,
            request_id,
            event_status,
            paused_for_user=paused_for_user,
            usage=turn_usage,
            assistant_content=final_output,
        )
        hub.broadcast_session(
            owner,
            session_id,
            {
                "type": "chat.generation.ended",
                "request_id": request_id,
                "status": event_status,
                "paused_for_user": paused_for_user,
                "assistant_content": final_output,
            },
        )
        hub.finish_job(request_id, status=event_status)
