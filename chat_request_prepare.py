"""Validate and prepare main-chat generation jobs (WebSocket)."""

from __future__ import annotations

CHAT_TOOL_OVERRIDE_KEYS = frozenset(
    {
        "web_search",
        "google_calendar",
        "google_gmail",
        "tasks",
        "memory",
        "computelab",
        "image_generation",
        "deep_research",
    }
)


def parse_chat_tool_overrides(data):
    raw = (data or {}).get("chat_tools")
    if not isinstance(raw, dict):
        return {}
    return {k: bool(raw[k]) for k in CHAT_TOOL_OVERRIDE_KEYS if k in raw}


def apply_chat_tool_override(overrides, key, enabled):
    if key not in overrides:
        return enabled
    return bool(enabled) and bool(overrides[key])


def prepare_chat_send_job(username, data, *, client_ip="", user_agent=""):
    messages = data.get("messages", [])
    if not messages:
        return None, "メッセージがありません"

    deps = data.get("_deps") or {}
    load_users = deps["load_users"]
    feature_blocked = deps["feature_blocked"]
    is_user_blocked = deps["is_user_blocked"]
    plan_allows_chat = deps["plan_allows_chat"]
    effective_plan_for_features = deps["effective_plan_for_features"]
    create_billing_event = deps["create_billing_event"]
    update_billing_event = deps["update_billing_event"]
    try_reserve_chat_usage = deps["try_reserve_chat_usage"]
    usage_summary_for_record = deps["usage_summary_for_record"]
    parse_overrides = parse_chat_tool_overrides
    apply_override = apply_chat_tool_override
    user_web_search_enabled = deps["user_web_search_enabled"]
    resolve_engines_for_plan = deps["resolve_engines_for_plan"]
    get_plan_features = deps["get_plan_features"]
    user_geolocation_enabled = deps["user_geolocation_enabled"]
    sanitize_location_context = deps["sanitize_location_context"]
    user_reasoning_cards_enabled = deps["user_reasoning_cards_enabled"]
    user_tool_trace_enabled = deps["user_tool_trace_enabled"]
    user_full_info_display_enabled = deps["user_full_info_display_enabled"]
    user_expression_extension_enabled = deps["user_expression_extension_enabled"]
    user_reasoning_disabled = deps["user_reasoning_disabled"]
    user_cost_performance_maximized = deps["user_cost_performance_maximized"]
    user_google_calendar_enabled = deps["user_google_calendar_enabled"]
    user_google_gmail_enabled = deps["user_google_gmail_enabled"]
    resolve_user_tasks_enabled = deps["resolve_user_tasks_enabled"]
    plan_tasks_enabled = deps["plan_tasks_enabled"]
    resolve_user_memory_enabled = deps["resolve_user_memory_enabled"]
    plan_memory_enabled = deps["plan_memory_enabled"]
    user_computelab_tools_enabled = deps["user_computelab_tools_enabled"]
    user_image_generation_enabled = deps["user_image_generation_enabled"]
    resolve_user_deep_research_enabled = deps["resolve_user_deep_research_enabled"]
    plan_deep_research_enabled = deps["plan_deep_research_enabled"]
    get_user_deep_research_prefs = deps["get_user_deep_research_prefs"]
    user_intelligent_search_override_enabled = deps["user_intelligent_search_override_enabled"]
    get_user_image_generation_prefs = deps["get_user_image_generation_prefs"]
    find_custom_agent = deps["find_custom_agent"]
    apply_custom_agent_chat_reasoning_prefs = deps["apply_custom_agent_chat_reasoning_prefs"]
    load_system_config = deps["load_system_config"]
    user_file_upload_enabled = deps["user_file_upload_enabled"]
    message_has_pdfs = deps["message_has_pdfs"]
    preprocess_messages_with_pdf = deps["preprocess_messages_with_pdf"]
    user_ocr_enabled = deps["user_ocr_enabled"]
    ocr_globally_enabled = deps["ocr_globally_enabled"]
    message_has_images = deps["message_has_images"]
    resolve_ocr_model_for_plan = deps["resolve_ocr_model_for_plan"]
    get_anthropic_api_key = deps["get_anthropic_api_key"]
    preprocess_messages_with_ocr = deps["preprocess_messages_with_ocr"]
    resolve_chat_model = deps["resolve_chat_model"]
    make_openai_client_for_provider = deps["make_openai_client_for_provider"]
    normalize_model_entry = deps["normalize_model_entry"]
    effective_reasoning_in_english = deps["effective_reasoning_in_english"]
    user_user_questions_enabled = deps["user_user_questions_enabled"]
    summarize_messages_for_audit = deps["summarize_messages_for_audit"]
    last_user_message_text = deps["last_user_message_text"]

    if feature_blocked("chat_disabled"):
        return None, "現在、チャット機能は一時的に制限されています"

    users = load_users()
    chat_user = users.get(username, {})
    if is_user_blocked(chat_user):
        return None, "アカウントが利用停止中のため、チャットを利用できません"

    allowed, plan_err = plan_allows_chat(username)
    if not allowed:
        return None, plan_err

    plan_key = effective_plan_for_features(chat_user)
    session_id = (data.get("session_id") or "").strip()
    if chat_user.get("role") == "admin" or usage_summary_for_record(chat_user).get(
        "usage_unlimited"
    ):
        payment_type = "included"
    else:
        payment_type = "subscription"

    tool_overrides = parse_overrides(data)
    search_allowed = apply_override(
        tool_overrides,
        "web_search",
        user_web_search_enabled(chat_user) and not feature_blocked("search_disabled"),
    )
    search_engines = (
        resolve_engines_for_plan(plan_key, get_plan_features(plan_key))
        if search_allowed
        else {"tavily": False, "serper": False, "ddg": False}
    )
    location_hint = None
    if user_geolocation_enabled(chat_user):
        location_hint = sanitize_location_context(data.get("location_context"))

    emit_reasoning_cards = user_reasoning_cards_enabled(chat_user)
    emit_tool_trace = user_tool_trace_enabled(chat_user)
    emit_full_info = user_full_info_display_enabled(chat_user)
    expression_extension_on = user_expression_extension_enabled(chat_user)
    disable_reasoning = user_reasoning_disabled(chat_user)
    cost_performance_on = user_cost_performance_maximized(chat_user)
    google_calendar_on = apply_override(
        tool_overrides,
        "google_calendar",
        user_google_calendar_enabled(chat_user, username),
    )
    google_gmail_on = apply_override(
        tool_overrides,
        "google_gmail",
        user_google_gmail_enabled(chat_user, username),
    )
    tasks_on = apply_override(
        tool_overrides,
        "tasks",
        resolve_user_tasks_enabled(chat_user, plan_tasks_enabled),
    )
    memory_on = apply_override(
        tool_overrides,
        "memory",
        resolve_user_memory_enabled(chat_user, plan_memory_enabled),
    )
    computelab_on = apply_override(
        tool_overrides,
        "computelab",
        user_computelab_tools_enabled(chat_user, username),
    )
    image_gen_on = apply_override(
        tool_overrides,
        "image_generation",
        user_image_generation_enabled(chat_user),
    )
    deep_research_on = apply_override(
        tool_overrides,
        "deep_research",
        resolve_user_deep_research_enabled(chat_user, plan_deep_research_enabled),
    )
    deep_research_prefs = (
        get_user_deep_research_prefs(chat_user) if deep_research_on else None
    )
    intelligent_search_override_on = (
        search_allowed and user_intelligent_search_override_enabled(chat_user)
    )
    image_gen_prefs = (
        get_user_image_generation_prefs(chat_user, plan_key) if image_gen_on else None
    )

    custom_agent = None
    custom_agent_id = (data.get("custom_agent_id") or "").strip()
    if custom_agent_id:
        custom_agent = find_custom_agent(username, custom_agent_id)
        if not custom_agent:
            return None, "エージェントが見つかりません"
        custom_agent["owner_username"] = (
            custom_agent.get("owner_username") or username
        ).strip().lower()
        emit_reasoning_cards, disable_reasoning = apply_custom_agent_chat_reasoning_prefs(
            custom_agent,
            username,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
        )

    config = load_system_config()
    messages_for_chat = list(messages)
    extended = config.get("extended_models") or {}
    if (
        user_file_upload_enabled(chat_user)
        and any(message_has_pdfs(m.get("content")) for m in messages if m.get("role") == "user")
    ):
        try:
            messages_for_chat = preprocess_messages_with_pdf(messages_for_chat, enabled=True)
        except Exception as pdf_err:
            return None, f"PDFの読み取りに失敗しました: {pdf_err}"

    if (
        user_ocr_enabled(chat_user)
        and ocr_globally_enabled(extended)
        and any(message_has_images(m.get("content")) for m in messages if m.get("role") == "user")
    ):
        from extended_models_registry import resolve_ocr_engine

        ocr_engine = resolve_ocr_engine(extended)
        ocr_api_key = ""
        ocr_api_model = ""
        if ocr_engine == "ai":
            ocr_resolved = resolve_ocr_model_for_plan(plan_key, extended)
            if not ocr_resolved:
                return None, "このプランで利用できる AI OCR モデルが設定されていません"
            anthropic_key = get_anthropic_api_key(config.get("providers"))
            if not anthropic_key:
                return None, (
                    "画像OCR用の Anthropic API キーが設定されていません"
                    "（ANTHROPIC_API_KEY または管理画面）"
                )
            ocr_api_key = anthropic_key
            ocr_api_model = ocr_resolved["api_model"]
        try:
            messages_for_chat = preprocess_messages_with_ocr(
                messages_for_chat,
                api_key=ocr_api_key,
                api_model=ocr_api_model,
                engine=ocr_engine,
                config=config,
                enabled=True,
            )
        except Exception as ocr_err:
            return None, f"画像の文字抽出に失敗しました: {ocr_err}"

    requested_model = (data.get("model") or "").strip()
    if custom_agent and (custom_agent.get("model_id") or "").strip():
        requested_model = custom_agent["model_id"].strip()
    try:
        resolved = resolve_chat_model(requested_model, config)
    except ValueError as exc:
        return None, str(exc)

    catalog_model_id = resolved["model_id"]
    api_model = resolved["api_model"]
    provider_id = resolved["provider"]
    agent_profile = resolved["agent_profile"]
    models_cfg = config.get("models") or {}
    catalog_model_entry = models_cfg.get(catalog_model_id) or normalize_model_entry(
        catalog_model_id, {}
    )
    reasoning_in_english = effective_reasoning_in_english(
        chat_user,
        provider_id=provider_id,
        disable_reasoning=disable_reasoning,
    )

    client, api_key = make_openai_client_for_provider(
        provider_id, config.get("providers")
    )
    if not api_key:
        return None, f"{provider_id} の API キーが設定されていません（管理画面または環境変数）"

    billing_event = create_billing_event(
        username,
        session_id=session_id,
        model_id=catalog_model_id,
        payment_type=payment_type,
        status="running",
    )

    if (
        chat_user.get("role") != "admin"
        and not usage_summary_for_record(chat_user).get("usage_unlimited")
    ):
        reserved, reserve_err = try_reserve_chat_usage(
            username, billing_event["id"], catalog_model_entry
        )
        if not reserved:
            update_billing_event(billing_event["id"], status="blocked")
            return None, reserve_err or "利用枠が不足しています"

    return {
        "request_id": billing_event["id"],
        "session_id": session_id,
        "username": username,
        "chat_user": chat_user,
        "messages_for_chat": messages_for_chat,
        "plan_key": plan_key,
        "search_allowed": search_allowed,
        "search_engines": search_engines,
        "location_hint": location_hint,
        "emit_reasoning_cards": emit_reasoning_cards,
        "emit_tool_trace": emit_tool_trace,
        "emit_full_info": emit_full_info,
        "expression_extension_on": expression_extension_on,
        "disable_reasoning": disable_reasoning,
        "cost_performance_on": cost_performance_on,
        "google_calendar_on": google_calendar_on,
        "google_gmail_on": google_gmail_on,
        "tasks_on": tasks_on,
        "memory_on": memory_on,
        "computelab_on": computelab_on,
        "image_gen_on": image_gen_on,
        "deep_research_on": deep_research_on,
        "deep_research_prefs": deep_research_prefs,
        "intelligent_search_override_on": intelligent_search_override_on,
        "image_gen_prefs": image_gen_prefs,
        "custom_agent": custom_agent,
        "config": config,
        "resolved": resolved,
        "catalog_model_id": catalog_model_id,
        "catalog_model_entry": catalog_model_entry,
        "api_model": api_model,
        "provider_id": provider_id,
        "agent_profile": agent_profile,
        "reasoning_in_english": reasoning_in_english,
        "client": client,
        "api_key": api_key,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "audit_messages_summary": summarize_messages_for_audit(messages),
        "audit_user_message": last_user_message_text(messages),
        "resume": None,
    }, None
