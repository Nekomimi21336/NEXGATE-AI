import json
import re
from datetime import datetime

MAX_LINKS_PER_SOURCE_PAGE = 120
MAX_LINK_CATALOG = 160
MAX_AI_SELECTED_FETCHES = 12

_ADMISSION_RE = re.compile(
    r"入試|AO入試|AO\s|総合型(?:選抜)?|エントリー|出願|受験|"
    r"学部.*(?:入試|選抜)|大学.*(?:入試|選抜)|いつから|日程|締切",
    re.IGNORECASE,
)
_SCHEDULE_SIGNAL_RE = re.compile(
    r"(?:エントリー|出願|選考|総合型|AO).{0,24}(?:開始|期間|日程|締切|スケジュール)|"
    r"(?:\d{4}年|\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}).{0,12}(?:から|～|〜|ー)|"
    r"(?:令和|R)\d+年度",
    re.IGNORECASE,
)
_UNIVERSITY_RE = re.compile(r"([\w\u3040-\u30ff\u4e00-\u9fff]{2,20}大学)")
_FACULTY_RE = re.compile(r"([\w\u3040-\u30ff\u4e00-\u9fff]{2,20}学部)")
_NENDO_IN_QUERY_RE = re.compile(r"(\d{4})\s*年度")

_FETCH_IDS_RE = re.compile(r'"fetch_ids"\s*:\s*\[([^\]]*)\]', re.DOTALL)
_INT_RE = re.compile(r"\d+")


def resolve_user_intelligent_search_override_enabled(record):
    if not record:
        return False
    return bool(record.get("intelligent_search_override_enabled"))


def wants_admission_exam_search(text):
    return bool(_ADMISSION_RE.search(text or ""))


def japanese_entrance_exam_nendos(now=None):
    now = now or datetime.now()
    calendar_year = now.year
    month = now.month
    if month >= 4:
        primary = calendar_year + 1
    else:
        primary = calendar_year
    return {
        "calendar_year": calendar_year,
        "primary_nendo": primary,
        "candidates": [primary - 1, primary, primary + 1],
    }


def _extract_institution_names(user_text):
    uni = ""
    faculty = ""
    m = _UNIVERSITY_RE.search(user_text or "")
    if m:
        uni = m.group(1).strip()
    m = _FACULTY_RE.search(user_text or "")
    if m:
        faculty = m.group(1).strip()
    return uni, faculty


def expand_admission_search_queries(user_text, queries, *, force=False):
    if not force and not wants_admission_exam_search(user_text):
        return list(queries or [])

    seen = set()
    out = []
    for q in queries or []:
        key = re.sub(r"\s+", " ", str(q).strip().lower())
        if key and key not in seen:
            seen.add(key)
            out.append(str(q).strip())

    uni, faculty = _extract_institution_names(user_text)
    years = japanese_entrance_exam_nendos()
    primary = years["primary_nendo"]
    calendar = years["calendar_year"]

    extras = []
    for nendo in years["candidates"]:
        if uni and faculty:
            extras.append(f"{nendo}年度 {uni} {faculty} 総合型選抜 AO 日程 エントリー")
            extras.append(f"{nendo}年度 {uni} {faculty} 入試日程")
        elif uni:
            extras.append(f"{nendo}年度 {uni} 総合型選抜 AO 入試日程")
            extras.append(f"{nendo}年度 {uni} 入試 エントリー")

    if uni:
        extras.append(f"{uni} 入試日程 公式 {primary}年度")
        extras.append(f"{uni} 総合型選抜 site:ac.jp {primary}年度")
    if "今年" in (user_text or "") or "今年度" in (user_text or ""):
        extras.append(
            f"{calendar}年 {primary}年度入試 {uni} {faculty}".strip()
        )

    merged = []
    for q in extras + out:
        key = re.sub(r"\s+", " ", str(q).strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(str(q).strip())
        if len(merged) >= 5:
            break
    return merged or out


def build_admission_retry_queries(user_text, tried_queries):
    if not wants_admission_exam_search(user_text):
        return []

    uni, faculty = _extract_institution_names(user_text)
    years = japanese_entrance_exam_nendos()
    tried = {re.sub(r"\s+", " ", str(q).strip().lower()) for q in tried_queries or []}
    tried_nendos = set()
    for q in tried_queries or []:
        for m in _NENDO_IN_QUERY_RE.finditer(str(q)):
            tried_nendos.add(int(m.group(1)))

    retry = []
    for nendo in years["candidates"]:
        if nendo in tried_nendos:
            continue
        if uni and faculty:
            retry.append(f"{nendo}年度 {uni} {faculty} 総合型選抜 エントリー 開始")
        elif uni:
            retry.append(f"{nendo}年度 {uni} 入試 総合型選抜 公式")
        if retry:
            break

    if not retry and uni:
        retry.append(f"{uni} 入試案内 総合型選抜 PDF 日程")

    out = []
    for q in retry:
        key = re.sub(r"\s+", " ", q.strip().lower())
        if key not in tried:
            out.append(q)
    return out[:2]


def admission_schedule_signals_in_text(text):
    blob = re.sub(r"\s+", " ", str(text or ""))
    if len(blob) < 40:
        return False
    return bool(_SCHEDULE_SIGNAL_RE.search(blob))


def admission_search_needs_retry(results, user_text):
    if not wants_admission_exam_search(user_text):
        return False
    if not results:
        return True

    chunks = []
    fetched = 0
    for item in results:
        body = (item.get("body") or "").strip()
        if body:
            chunks.append(body)
        if item.get("fetched_full"):
            fetched += 1

    combined = "\n".join(chunks)
    if admission_schedule_signals_in_text(combined):
        return False
    if fetched == 0:
        return True
    return len(combined) < 900


def boost_search_page_fetch_plan(plan_max, excerpt_chars, fetch_extract_chars):
    boosted_max = 4 if plan_max <= 0 else plan_max
    boosted_max = max(boosted_max, 6)
    boosted_excerpt = max(int(excerpt_chars or 0), int(fetch_extract_chars or 28000))
    return boosted_max, boosted_excerpt


def intelligent_search_override_system_prompt_append():
    years = japanese_entrance_exam_nendos()
    primary = years["primary_nendo"]
    return (
        "\n\n【IntelligentSearchオーバーライド（試験）】\n"
        "有効時、web_search 実行後に上位URLの本文取得と同一サイト内リンクのAI選別取得が自動で行われます。\n"
        "- 検索スニペットだけで「確認できません」と答えない。「（ページ本文）」「（関連ページ）」行を最優先する\n"
        "- 公式ページ（.ac.jp）の記述を優先する\n"
        "- 大学入試・AO・総合型選抜では「入学年度」の表記に注意。"
        f" 現在は {years['calendar_year']}年で、次の春入学向け入試は多くの場合 **{primary}年度** と表記される"
        f"（{primary - 1}年度 ではない場合がある）\n"
        "- 日程が見つからない場合、年度を変えた queries で web_search を追加実行してから結論を書く\n"
        "- 検索結果に公式URLがあれば web_fetch でも直接確認できる\n"
    )


def build_link_catalog(page_entries, *, seen_urls=None):
    seen = set(seen_urls or [])
    catalog = []
    next_id = 1
    for entry in page_entries or []:
        source_url = (entry.get("source_url") or "").strip()
        for link in entry.get("page_links") or []:
            url = (link.get("url") or "").strip()
            if not url:
                continue
            key = url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            catalog.append(
                {
                    "id": next_id,
                    "url": url,
                    "anchor": (link.get("anchor") or "").strip(),
                    "source_url": source_url,
                }
            )
            next_id += 1
            if len(catalog) >= MAX_LINK_CATALOG:
                return catalog
    return catalog


def _format_catalog_for_prompt(catalog):
    lines = []
    for item in catalog:
        anchor = item.get("anchor") or "（ラベルなし）"
        lines.append(
            f'{item["id"]}. [{anchor}] {item["url"]}\n'
            f'   元ページ: {item.get("source_url") or ""}'
        )
    return "\n".join(lines)


def _parse_fetch_ids(text):
    if not text:
        return []
    raw = str(text).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            ids = data.get("fetch_ids") or data.get("ids") or []
            if isinstance(ids, list):
                return [int(x) for x in ids if str(x).strip().isdigit()]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    match = _FETCH_IDS_RE.search(raw)
    if match:
        return [int(x) for x in _INT_RE.findall(match.group(1))]
    return [int(x) for x in _INT_RE.findall(raw)][:MAX_AI_SELECTED_FETCHES]


def select_links_with_ai(
    client,
    model,
    *,
    user_text="",
    query="",
    catalog=None,
    provider_id=None,
    disable_reasoning=True,
):
    catalog = list(catalog or [])
    if not catalog or not client or not model:
        return []

    from chat_agent import complete_model_round

    prompt = (
        "あなたはWeb検索の補助役です。ユーザーの質問に答えるために、"
        "同一サイト内リンクの一覧から本文取得すべきページを選んでください。\n\n"
        "選ぶ基準:\n"
        "- 質問の答えがありそうな詳細ページ、入試日程・AO・エントリー・設定・手順・ドキュメントを優先\n"
        "- ログイン、会員登録、利用規約、プライバシー、カート、SNS共有は除外\n"
        "- ナビゲーションだけの重複リンクは除外\n"
        f"- 最大 {MAX_AI_SELECTED_FETCHES} 件まで\n\n"
        f"ユーザーの質問:\n{user_text.strip()}\n\n"
        f"検索クエリ:\n{query.strip()}\n\n"
        "リンク一覧:\n"
        f"{_format_catalog_for_prompt(catalog)}\n\n"
        'JSONのみ返答: {"fetch_ids":[1,2,3]}'
    )
    try:
        round_data = complete_model_round(
            client,
            model,
            [
                {
                    "role": "system",
                    "content": "リンク選別のみ行い、説明文は書かない。JSONのみ返す。",
                },
                {"role": "user", "content": prompt},
            ],
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        )
    except Exception:
        return []

    content = (round_data.get("content") or "").strip()
    fetch_ids = set(_parse_fetch_ids(content))
    if not fetch_ids:
        return []

    selected = []
    for item in catalog:
        if item.get("id") in fetch_ids:
            selected.append(
                {
                    "url": item.get("url") or "",
                    "anchor": item.get("anchor") or "",
                    "source_url": item.get("source_url") or "",
                }
            )
        if len(selected) >= MAX_AI_SELECTED_FETCHES:
            break
    return selected
