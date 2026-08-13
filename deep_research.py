DEFAULT_DEEP_RESEARCH_PREFS = {"max_search_rounds": 5}
MIN_MAX_SEARCH_ROUNDS = 2
MAX_MAX_SEARCH_ROUNDS = 8


def normalize_deep_research_prefs(raw):
    prefs = dict(DEFAULT_DEEP_RESEARCH_PREFS)
    if not isinstance(raw, dict):
        return prefs
    try:
        n = int(raw.get("max_search_rounds", prefs["max_search_rounds"]))
    except (TypeError, ValueError):
        return prefs
    prefs["max_search_rounds"] = max(
        MIN_MAX_SEARCH_ROUNDS, min(MAX_MAX_SEARCH_ROUNDS, n)
    )
    return prefs


def get_user_deep_research_prefs(record):
    if not record:
        return normalize_deep_research_prefs(None)
    return normalize_deep_research_prefs(record.get("deep_research_prefs"))


def resolve_user_deep_research_enabled(record, plan_deep_research_enabled):
    if not record:
        return False
    plan = (record.get("plan") or "free").strip().lower()
    if not plan_deep_research_enabled(plan):
        return False
    if "deep_research_enabled" in record:
        return bool(record.get("deep_research_enabled"))
    return False


def deep_research_system_prompt_append(max_search_rounds):
    rounds = int(max_search_rounds)
    return (
        "\n\n【DeepResearch】\n"
        "徹底調査モードです。複数ソースを横断し、出典の信頼性と矛盾を確認してから結論を書いてください。\n"
        f"- `web_search` を最大 {rounds} 回まで使えます（不足分は queries を変えて追加検索）\n"
        "- 1回目: 全体像・公式情報・主要論点\n"
        "- 2回目以降: 未解決の事実・数値・日付・反対意見のみを深掘り\n"
        "- 十分な根拠が揃ったら追加検索は止め、出典付きで最終回答のみ書く\n"
    )


def effective_max_web_search_rounds(
    user_text,
    computelab_active,
    *,
    deep_research_active=False,
    deep_research_prefs=None,
):
    from web_search import max_web_search_rounds

    base = max_web_search_rounds(user_text, computelab_active)
    if not deep_research_active:
        return base
    prefs = normalize_deep_research_prefs(deep_research_prefs)
    return max(base, int(prefs["max_search_rounds"]))
