PLAN_LIMIT_KEYS = ("monthly_ai_budget_usd",)

SEARCH_PLAN_FLAG_KEYS = (
    "web_search_enabled",
    "search_tavily_enabled",
    "search_serper_enabled",
    "search_ddg_enabled",
)

PLAN_FLAG_KEYS = (
    "chat_enabled",
    "web_search_enabled",
    "search_tavily_enabled",
    "search_serper_enabled",
    "search_ddg_enabled",
    "geolocation_enabled",
    "file_upload_enabled",
    "ocr_enabled",
    "google_calendar_enabled",
    "google_gmail_enabled",
    "tasks_enabled",
    "memory_enabled",
    "projects_enabled",
    "deep_research_enabled",
    "image_generation_enabled",
    "computelab_enabled",
    "custom_agents_enabled",
    "api_access_enabled",
    "chat_share_enabled",
    "reasoning_cards_enabled",
    "tool_trace_enabled",
    "full_info_display_enabled",
)

PLAN_FLAG_LABELS = {
    "chat_enabled": "チャット",
    "web_search_enabled": "Web検索 / IntelligentSearch",
    "search_tavily_enabled": "検索: Tavily",
    "search_serper_enabled": "検索: Google (Serper)",
    "search_ddg_enabled": "検索: search-dg",
    "geolocation_enabled": "GeoLocation",
    "file_upload_enabled": "ファイル添付",
    "ocr_enabled": "画像の文字OCR（拡張モデル）",
    "google_calendar_enabled": "Googleカレンダー",
    "google_gmail_enabled": "Gmail",
    "tasks_enabled": "TASKS（試験）",
    "memory_enabled": "メモリ（試験）",
    "projects_enabled": "プロジェクトスペース（試験）",
    "deep_research_enabled": "DeepResearch（試験）",
    "image_generation_enabled": "画像生成",
    "computelab_enabled": "ComputeLab 連携",
    "custom_agents_enabled": "カスタムエージェント",
    "api_access_enabled": "API アクセス",
    "chat_share_enabled": "チャット共有",
    "reasoning_cards_enabled": "推論カード表示",
    "tool_trace_enabled": "ツールトレース表示",
    "full_info_display_enabled": "全情報の表示",
}

PLAN_FLAG_GROUPS = (
    (
        "core",
        "基本",
        (
            "chat_enabled",
            "file_upload_enabled",
            "ocr_enabled",
        ),
    ),
    ("search", "Web検索", SEARCH_PLAN_FLAG_KEYS),
    (
        "integrations",
        "連携",
        (
            "geolocation_enabled",
            "google_calendar_enabled",
            "google_gmail_enabled",
            "computelab_enabled",
        ),
    ),
    (
        "extensions",
        "拡張（試験）",
        (
            "tasks_enabled",
            "memory_enabled",
            "projects_enabled",
            "deep_research_enabled",
            "custom_agents_enabled",
        ),
    ),
    (
        "media",
        "メディア・表示",
        (
            "image_generation_enabled",
            "reasoning_cards_enabled",
            "tool_trace_enabled",
            "full_info_display_enabled",
        ),
    ),
    (
        "developer",
        "開発者",
        (
            "api_access_enabled",
            "chat_share_enabled",
        ),
    ),
)

DEFAULT_PLAN_FLAG_VALUES = {
    "web_search_enabled": True,
    "search_tavily_enabled": True,
    "search_serper_enabled": True,
    "search_ddg_enabled": True,
    "geolocation_enabled": False,
    "file_upload_enabled": True,
    "ocr_enabled": True,
    "google_calendar_enabled": False,
    "google_gmail_enabled": False,
    "tasks_enabled": False,
    "memory_enabled": False,
    "projects_enabled": False,
    "deep_research_enabled": False,
    "image_generation_enabled": False,
    "computelab_enabled": False,
    "custom_agents_enabled": False,
    "api_access_enabled": False,
    "chat_share_enabled": True,
    "reasoning_cards_enabled": True,
    "tool_trace_enabled": False,
    "full_info_display_enabled": False,
}

PLAN_EXTENDED_TIER_DEFAULTS = {
    "free": {
        "image_generation_enabled": False,
        "computelab_enabled": False,
        "custom_agents_enabled": False,
        "api_access_enabled": False,
        "chat_share_enabled": True,
        "reasoning_cards_enabled": True,
        "tool_trace_enabled": False,
        "full_info_display_enabled": False,
    },
    "plus": {
        "image_generation_enabled": True,
        "computelab_enabled": True,
        "custom_agents_enabled": True,
        "api_access_enabled": True,
        "chat_share_enabled": True,
        "reasoning_cards_enabled": True,
        "tool_trace_enabled": False,
    },
    "pro": {
        "image_generation_enabled": True,
        "computelab_enabled": True,
        "custom_agents_enabled": True,
        "api_access_enabled": True,
        "chat_share_enabled": True,
        "reasoning_cards_enabled": True,
        "tool_trace_enabled": True,
        "full_info_display_enabled": True,
    },
    "pro_plus": {
        "image_generation_enabled": True,
        "computelab_enabled": True,
        "custom_agents_enabled": True,
        "api_access_enabled": True,
        "chat_share_enabled": True,
        "reasoning_cards_enabled": True,
        "tool_trace_enabled": True,
        "full_info_display_enabled": True,
    },
    "max": {
        "image_generation_enabled": True,
        "computelab_enabled": True,
        "custom_agents_enabled": True,
        "api_access_enabled": True,
        "chat_share_enabled": True,
        "reasoning_cards_enabled": True,
        "tool_trace_enabled": True,
        "full_info_display_enabled": True,
    },
    "enterprise": {
        "image_generation_enabled": True,
        "computelab_enabled": True,
        "custom_agents_enabled": True,
        "api_access_enabled": True,
        "chat_share_enabled": True,
        "reasoning_cards_enabled": True,
        "tool_trace_enabled": True,
        "full_info_display_enabled": True,
    },
}

PLAN_OCR_TIER_DEFAULTS = {
    "free": {"ocr_enabled": False},
    "plus": {"ocr_enabled": True},
    "pro": {"ocr_enabled": True},
    "pro_plus": {"ocr_enabled": True},
    "max": {"ocr_enabled": True},
    "enterprise": {"ocr_enabled": True},
}

PLAN_SEARCH_TIER_DEFAULTS = {
    "free": {
        "search_tavily_enabled": False,
        "search_serper_enabled": False,
        "search_ddg_enabled": True,
    },
    "plus": {
        "search_tavily_enabled": True,
        "search_serper_enabled": True,
        "search_ddg_enabled": True,
    },
    "pro": {
        "search_tavily_enabled": True,
        "search_serper_enabled": True,
        "search_ddg_enabled": True,
    },
    "pro_plus": {
        "search_tavily_enabled": True,
        "search_serper_enabled": True,
        "search_ddg_enabled": True,
    },
    "max": {
        "search_tavily_enabled": True,
        "search_serper_enabled": True,
        "search_ddg_enabled": True,
    },
    "enterprise": {
        "search_tavily_enabled": True,
        "search_serper_enabled": True,
        "search_ddg_enabled": True,
    },
}

PLAN_GOOGLE_TIER_DEFAULTS = {
    "free": {"google_calendar_enabled": False, "google_gmail_enabled": False},
    "plus": {"google_calendar_enabled": True, "google_gmail_enabled": True},
    "pro": {"google_calendar_enabled": True, "google_gmail_enabled": True},
    "pro_plus": {"google_calendar_enabled": True, "google_gmail_enabled": True},
    "max": {"google_calendar_enabled": True, "google_gmail_enabled": True},
    "enterprise": {"google_calendar_enabled": True, "google_gmail_enabled": True},
}


def admin_flag_catalog():
    return [
        {"key": key, "label": PLAN_FLAG_LABELS[key]}
        for key in PLAN_FLAG_KEYS
    ]


def admin_flag_groups():
    groups = []
    for group_id, group_label, keys in PLAN_FLAG_GROUPS:
        features = [
            {"key": key, "label": PLAN_FLAG_LABELS[key]}
            for key in keys
            if key in PLAN_FLAG_LABELS
        ]
        if features:
            groups.append(
                {"id": group_id, "label": group_label, "features": features}
            )
    return groups


def search_plan_flag_catalog():
    return [
        {"key": key, "label": PLAN_FLAG_LABELS[key]}
        for key in SEARCH_PLAN_FLAG_KEYS
    ]


def extract_search_plan_flags(feature_dict):
    if not isinstance(feature_dict, dict):
        feature_dict = {}
    out = {}
    for key in SEARCH_PLAN_FLAG_KEYS:
        if key in feature_dict:
            out[key] = bool(feature_dict[key])
        elif key in DEFAULT_PLAN_FLAG_VALUES:
            out[key] = bool(DEFAULT_PLAN_FLAG_VALUES[key])
    return out


def normalize_search_plan_flags_payload(raw_features):
    if not isinstance(raw_features, dict):
        return None
    out = {}
    for key in SEARCH_PLAN_FLAG_KEYS:
        if key in raw_features:
            out[key] = bool(raw_features[key])
    return out or None


def apply_search_plan_flag_overrides(merged, feat_ov):
    if not isinstance(feat_ov, dict):
        return merged
    for key in SEARCH_PLAN_FLAG_KEYS:
        if key in feat_ov:
            merged[key] = bool(feat_ov[key])
    return merged


def apply_flag_overrides(merged, feat_ov):
    if not isinstance(feat_ov, dict):
        return merged
    for key in PLAN_FLAG_KEYS:
        if key in feat_ov:
            merged[key] = bool(feat_ov[key])
    return merged


def normalize_plan_flags_payload(raw_features):
    if not isinstance(raw_features, dict):
        return None
    out = {}
    for key in PLAN_FLAG_KEYS:
        if key in raw_features:
            out[key] = bool(raw_features[key])
    return out or None


def extract_plan_flags(feature_dict):
    if not isinstance(feature_dict, dict):
        feature_dict = {}
    out = {}
    for key in PLAN_FLAG_KEYS:
        if key in feature_dict:
            out[key] = bool(feature_dict[key])
        elif key in DEFAULT_PLAN_FLAG_VALUES:
            out[key] = bool(DEFAULT_PLAN_FLAG_VALUES[key])
    return out
