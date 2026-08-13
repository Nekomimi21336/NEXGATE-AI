import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

from search_settings import get_resolved_api_keys

SEARCH_DG_PROVIDER = "search-dg"
DDGS_BACKEND = os.getenv("DDGS_BACKEND", "auto,bing")

SEARCH_HTTP_TIMEOUT = float(os.getenv("SEARCH_HTTP_TIMEOUT", "10"))
SEARCH_CACHE_TTL_SEC = int(os.getenv("SEARCH_CACHE_TTL_SEC", "300"))
SEARCH_CACHE_MAX = int(os.getenv("SEARCH_CACHE_MAX", "256"))
SEARCH_POOL_WORKERS = int(os.getenv("SEARCH_POOL_WORKERS", "8"))
TAVILY_MAX_CONCURRENT = int(os.getenv("TAVILY_MAX_CONCURRENT", "3"))
SERPER_MAX_CONCURRENT = int(os.getenv("SERPER_MAX_CONCURRENT", "4"))
DDG_MAX_CONCURRENT = int(os.getenv("DDG_MAX_CONCURRENT", "2"))

AUTO_SEARCH_PATTERN = re.compile(
    r"(今の|現在の|最新|今日|今年|現職|誰が|何人|いつ|"
    r"総理|首相|大統領|国王|女王|"
    r"株価|為替|天気|予報|"
    r"ニュース|速報|発売日|価格|ランキング|"
    r"調べて|検索して|教えて.*誰)",
    re.IGNORECASE,
)

_NEWS_INTENT = re.compile(
    r"ニュース|速報|報道|ヘッドライン|最近の出来事|今日の.*(?:ニュース|話題)",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[\w\u3040-\u30ff\u4e00-\u9fff]{2,}", re.UNICODE)

_TRUSTED_JP_HOSTS = (
    "go.jp",
    "wikipedia.org",
    "nhk.or.jp",
    "reuters.com",
    "bloomberg.co.jp",
    "yahoo.co.jp/news",
    "asahi.com",
    "mainichi.jp",
    "nikkei.com",
)

_SEARCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=SEARCH_POOL_WORKERS, thread_name_prefix="web_search"
)
_PROVIDER_SEMAPHORES = {
    "tavily": threading.BoundedSemaphore(TAVILY_MAX_CONCURRENT),
    "serper": threading.BoundedSemaphore(SERPER_MAX_CONCURRENT),
    "serper_news": threading.BoundedSemaphore(SERPER_MAX_CONCURRENT),
    "ddg": threading.BoundedSemaphore(DDG_MAX_CONCURRENT),
}
_CACHE_LOCK = threading.Lock()
_SEARCH_CACHE = {}


def extract_user_text(messages):
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if p.get("type") == "text" and p.get("text")
            ]
            return "\n".join(parts).strip()
    return ""


def should_auto_web_search(text):
    if not text or len(text) < 4:
        return False
    return bool(AUTO_SEARCH_PATTERN.search(text))


def build_search_query(user_text):
    text = re.sub(r"\s+", " ", user_text.strip())
    now = datetime.now()
    if AUTO_SEARCH_PATTERN.search(text):
        return f"{text} {now.year}年{now.month}月"
    return text


def _normalize_cache_key(provider, query, max_results):
    q = re.sub(r"\s+", " ", (query or "").strip().lower())
    return f"{provider}|{max_results}|{q}"


def _cache_get(key):
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _SEARCH_CACHE.get(key)
        if not entry:
            return None
        expires, value = entry
        if expires <= now:
            _SEARCH_CACHE.pop(key, None)
            return None
        return value


def _cache_set(key, value):
    now = time.monotonic()
    with _CACHE_LOCK:
        if len(_SEARCH_CACHE) >= SEARCH_CACHE_MAX:
            oldest = min(_SEARCH_CACHE.items(), key=lambda item: item[1][0])
            _SEARCH_CACHE.pop(oldest[0], None)
        _SEARCH_CACHE[key] = (now + SEARCH_CACHE_TTL_SEC, value)


def _http_post_json(url, payload, headers=None, timeout=None):
    timeout = SEARCH_HTTP_TIMEOUT if timeout is None else timeout
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    last_err = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt == 0:
                time.sleep(0.35)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last_err = e
            break
    if last_err:
        raise last_err
    return {}


def _run_provider(provider_key, fn, query, max_results):
    cache_key = _normalize_cache_key(provider_key, query, max_results)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    sem = _PROVIDER_SEMAPHORES.get(provider_key)
    if sem is None:
        out = fn(query, max_results=max_results) or []
    else:
        with sem:
            out = fn(query, max_results=max_results) or []
    _cache_set(cache_key, out)
    return out


def search_tavily(query, max_results=8):
    api_key = get_resolved_api_keys().get("tavily") or ""
    if not api_key:
        return []
    try:
        data = _http_post_json(
            "https://api.tavily.com/search",
            {
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": True,
                "include_raw_content": False,
            },
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    results = []
    for item in data.get("results") or []:
        results.append(
            enrich_search_result(
                {
                    "title": item.get("title") or "",
                    "href": item.get("url") or "",
                    "body": item.get("content") or "",
                    "published_date": item.get("published_date") or "",
                },
                "Tavily",
            )
        )
    answer = (data.get("answer") or "").strip()
    if answer:
        summary = enrich_search_result(
            {
                "title": "Tavily要約（複数ソースの統合・URLなし）",
                "href": "",
                "body": answer,
                "published_date": datetime.now().strftime("%Y-%m-%d"),
            },
            "Tavily",
        )
        summary["synthetic"] = True
        results.append(summary)
    return results[: max_results + 1]


def search_serper(query, max_results=8):
    api_key = get_resolved_api_keys().get("serper") or ""
    if not api_key:
        return []
    num = min(max(max_results, 5), 10)
    try:
        data = _http_post_json(
            "https://google.serper.dev/search",
            {"q": query, "num": num, "gl": "jp", "hl": "ja"},
            headers={"X-API-KEY": api_key},
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    results = []
    for item in data.get("organic") or []:
        results.append(
            enrich_search_result(
                {
                    "title": item.get("title") or "",
                    "href": item.get("link") or "",
                    "body": item.get("snippet") or "",
                    "date": item.get("date") or "",
                },
                "Google (Serper)",
            )
        )
    return results[:max_results]


def search_serper_news(query, max_results=6):
    api_key = get_resolved_api_keys().get("serper") or ""
    if not api_key:
        return []
    num = min(max(max_results, 4), 8)
    try:
        data = _http_post_json(
            "https://google.serper.dev/news",
            {"q": query, "num": num, "gl": "jp", "hl": "ja"},
            headers={"X-API-KEY": api_key},
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    results = []
    for item in data.get("news") or []:
        results.append(
            enrich_search_result(
                {
                    "title": item.get("title") or "",
                    "href": item.get("link") or "",
                    "body": item.get("snippet") or "",
                    "date": item.get("date") or "",
                },
                "Google News (Serper)",
            )
        )
    return results[:max_results]


def site_from_url(url):
    if not url:
        return ""
    try:
        host = urlparse(url).netloc or ""
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


_DATE_IN_TEXT = re.compile(
    r"(20\d{2})[年/.-](\d{1,2})(?:[月/.-](\d{1,2}))?日?"
    r"|(20\d{2})年(\d{1,2})月"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(20\d{2})"
    r"|(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])",
    re.IGNORECASE,
)
_DATE_IN_URL = re.compile(
    r"/(20\d{2})[/-](0?[1-9]|1[0-2])(?:[/-](0?[1-9]|[12]\d|3[01]))?(?:/|$)"
)


def _extract_date_from_text(text):
    if not text:
        return ""
    m = _DATE_IN_TEXT.search(text)
    if not m:
        return ""
    groups = [g for g in m.groups() if g]
    if len(groups) >= 3 and groups[0].isdigit():
        y, mo = groups[0], groups[1]
        d = groups[2] if len(groups) > 2 and groups[2].isdigit() else "01"
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    if len(groups) >= 2 and groups[0].isdigit() and len(groups[0]) == 4:
        return f"{groups[0]}-{int(groups[1]):02d}-01"
    return m.group(0).strip()


def _extract_date_from_url(url):
    if not url:
        return ""
    m = _DATE_IN_URL.search(url)
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2), m.group(3) or "1"
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def format_date_label(date_raw):
    if not date_raw or not str(date_raw).strip():
        return "日付不明"
    raw = str(date_raw).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        try:
            y, m, d = raw[:10].split("-")
            return f"{int(y)}年{int(m)}月{int(d)}日"
        except ValueError:
            pass
    return raw


def enrich_search_result(item, provider=""):
    enriched = {
        "title": item.get("title") or "",
        "href": item.get("href") or "",
        "body": item.get("body") or "",
        "provider": provider,
        "synthetic": bool(item.get("synthetic")),
    }
    date_raw = (
        item.get("date")
        or item.get("published")
        or item.get("published_date")
        or ""
    )
    if not date_raw:
        blob = f"{enriched['title']} {enriched['body']}"
        date_raw = _extract_date_from_text(blob)
    if not date_raw:
        date_raw = _extract_date_from_url(enriched["href"])
    enriched["date"] = str(date_raw).strip() if date_raw else ""
    enriched["date_label"] = format_date_label(enriched["date"])
    return enriched


def _ddgs_backend_list():
    raw = (DDGS_BACKEND or "").strip()
    if not raw:
        return ["auto"]
    backends = [b.strip() for b in raw.split(",") if b.strip()]
    if "auto" not in backends:
        backends.append("auto")
    return backends


def _search_dg_iter(query, max_results=8, timelimit=None, backend=None):
    try:
        from ddgs import DDGS
    except ImportError:
        return

    backends = [backend] if backend else _ddgs_backend_list()
    for bk in backends:
        kwargs = {
            "max_results": max_results,
            "region": "jp-jp",
            "safesearch": "moderate",
            "backend": bk,
        }
        if timelimit:
            kwargs["timelimit"] = timelimit

        count = 0
        try:
            with DDGS() as ddgs:
                for item in ddgs.text(query, **kwargs):
                    yield enrich_search_result(
                        {
                            "title": item.get("title") or "",
                            "href": item.get("href") or "",
                            "body": item.get("body") or "",
                            "date": item.get("date") or "",
                        },
                        SEARCH_DG_PROVIDER,
                    )
                    count += 1
                    if count >= max_results:
                        return
        except Exception:
            continue


def search_dg(query, max_results=8):
    results = []
    seen = set()
    for timelimit in ("m", None):
        for item in _search_dg_iter(query, max_results=max_results, timelimit=timelimit):
            key = item.get("href") or item.get("title") or ""
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(item)
            if len(results) >= max_results:
                return results
    return results[:max_results]


def _supplementary_queries(user_text):
    extras = []
    if re.search(r"総理|首相|内閣", user_text):
        now = datetime.now()
        extras.append(f"日本 内閣総理大臣 現職 {now.year}年")
        extras.append("内閣総理大臣 首相官邸")
    topic = infer_search_topic(user_text)
    if topic == "software_setup":
        if re.search(r"petteri|nukkit", user_text or "", re.IGNORECASE):
            extras.append("Nukkit PetteriM1 Edition multiversion configuration wiki")
            extras.append("PetteriM1 Nukkit github multiversion default enabled")
        if re.search(r"minecraft|bedrock|マイクラ", user_text or "", re.IGNORECASE):
            extras.append("Nukkit Bedrock server multiversion setup nukkit.yml")
    return extras


def infer_search_topic(user_text):
    text = user_text or ""
    from search_retry import wants_named_product_search

    if wants_named_product_search(text):
        return "named_product"
    from intelligent_search_override import wants_admission_exam_search

    if wants_admission_exam_search(text):
        return "admission_exam"
    if wants_news_search(text):
        return "news"
    from service_status import wants_service_status_search

    if wants_service_status_search(text):
        return "service_status"
    if re.search(
        r"llm|language model|chatgpt|claude|gemini|gpt-?4|openai|"
        r"ランキング|最強.*モデル|ベンチマーク|chatbot arena|lmsys",
        text,
        re.IGNORECASE,
    ):
        return "llm_ranking"
    if re.search(
        r"nukkit|bedrock edition|minecraft\s*bedrock|petteri\s*m1|"
        r"multiversion|マルチバージョン|サーバー\s*ソフト|server\s*software|"
        r"plugins?\.yml|nukkit\.yml|server\.properties",
        text,
        re.IGNORECASE,
    ):
        return "software_setup"
    return "general"


_FETCH_PAGE_HOST_HINTS = (
    "github.com",
    "github.io",
    "wiki",
    "readthedocs",
    "fandom.com",
    "minecraft.",
    "docs.",
    "developer.",
    "learn.microsoft.com",
    "apache.org",
)

_URL_SKIP_FETCH = re.compile(
    r"(youtube\.com|youtu\.be|twitter\.com|x\.com/|facebook\.com|instagram\.com|"
    r"tiktok\.com|linkedin\.com/feed|google\.com/search|bing\.com/search|"
    r"play\.google\.com|apps\.apple\.com)",
    re.IGNORECASE,
)

_DETAIL_REQUEST_RE = re.compile(
    r"詳しく|詳細|具体的|手順|設定|方法|やり方|どうやって|どうすれば|"
    r"使い方|マニュアル|ドキュメント|readme|wiki|比較|違い|仕組み|"
    r"そのまま|必要|有効|無効|デフォルト|default|setup|install|configure|"
    r"how\s+to|tutorial|guide|手動|構築|導入|起動|multiversion|マルチバージョン|"
    r"とは何|what\s+is|explain|説明して",
    re.IGNORECASE,
)

_FETCH_PAGE_EXTRACT_CHARS = int(os.getenv("SEARCH_FETCH_EXTRACT_MAX_CHARS", "28000"))
_FETCH_PAGE_RAW_CHARS = int(os.getenv("SEARCH_FETCH_RAW_TEXT_CHARS", "80000"))
_FETCH_PAGE_TIMEOUT = float(os.getenv("SEARCH_FETCH_PAGE_TIMEOUT", "18"))


def user_needs_detailed_fetch(user_text):
    text = (user_text or "").strip()
    if not text:
        return False
    return bool(_DETAIL_REQUEST_RE.search(text))


def plan_search_page_fetches(user_text, results):
    """Return (max_pages, extract_max_chars) — 0 means skip fetching."""
    if not results:
        return 0, _FETCH_PAGE_EXTRACT_CHARS

    topic = infer_search_topic(user_text)
    href_results = [r for r in results if (r.get("href") or "").strip()]
    if not href_results:
        return 0, _FETCH_PAGE_EXTRACT_CHARS

    bodies = [len((r.get("body") or "").strip()) for r in href_results]
    avg_body = sum(bodies) / len(bodies)
    thin_count = sum(1 for b in bodies if b < 220)
    thin_ratio = thin_count / len(bodies)
    needs_detail = user_needs_detailed_fetch(user_text)

    if topic == "admission_exam":
        return 6, _FETCH_PAGE_EXTRACT_CHARS
    if topic == "named_product":
        return 4, _FETCH_PAGE_EXTRACT_CHARS
    if needs_detail:
        return 5, _FETCH_PAGE_EXTRACT_CHARS
    if topic == "service_status":
        return 2, _FETCH_PAGE_EXTRACT_CHARS
    if topic == "software_setup":
        return 4, _FETCH_PAGE_EXTRACT_CHARS
    if topic == "llm_ranking":
        return 4, _FETCH_PAGE_EXTRACT_CHARS
    if thin_ratio >= 0.45 or avg_body < 380:
        return 3, _FETCH_PAGE_EXTRACT_CHARS
    if avg_body < 520:
        return 2, min(_FETCH_PAGE_EXTRACT_CHARS, 18000)
    return 0, _FETCH_PAGE_EXTRACT_CHARS


def _fetch_priority_score(item, topic, user_text, query):
    href = (item.get("href") or "").strip()
    if not href or item.get("fetched_full"):
        return -10_000
    if _URL_SKIP_FETCH.search(href):
        return -10_000
    from web_fetch import is_fetchable_url

    if not is_fetchable_url(href):
        return -10_000

    body_len = len((item.get("body") or "").strip())
    score = score_search_result(item, topic, user_text, query)
    if body_len < 180:
        score += 18
    elif body_len < 450:
        score += 10
    elif body_len < 800:
        score += 4

    lower = href.lower()
    if any(h in lower for h in _FETCH_PAGE_HOST_HINTS):
        score += 12
    if re.search(
        r"docs?\.|/wiki|readme|guide|manual|tutorial|設定|setup|install|config",
        lower,
    ):
        score += 8
    if topic == "admission_exam" and re.search(r"\.ac\.jp", lower):
        score += 28
    if topic == "admission_exam" and re.search(
        r"入試|admission|nyushi|ao|総合型",
        lower,
    ):
        score += 12
    if topic == "service_status" and re.search(
        r"status\.|githubstatus|cloudflarestatus|vercel-status",
        lower,
    ):
        score += 40
    return score


def _build_fetched_page_result(item, page, raw, excerpt, excerpt_chars, href):
    meta = ""
    if len(raw) > len(excerpt) + 200:
        meta = f"（元ページ {len(raw):,} 字から要点・リスト・設定を抽出 → {len(excerpt):,} 字）\n"
    if page.get("via_tavily"):
        meta = "（Tavily extract 経由で取得）\n" + meta
    return enrich_search_result(
        {
            "title": f"（ページ本文）{page.get('title') or item.get('title') or href}",
            "href": href,
            "body": meta + excerpt,
            "fetched_full": True,
        },
        "page_fetch",
    )


def _fetch_page_for_result(
    item, excerpt_chars, user_text="", query="", *, search_override=False
):
    from page_content_extract import prepare_page_text_for_context
    from web_fetch import fetch_page_content, list_all_internal_links

    href = (item.get("href") or "").strip()
    try:
        page = fetch_page_content(
            href,
            max_text_chars=_FETCH_PAGE_RAW_CHARS,
            enhanced=search_override,
            include_html=search_override,
        )
    except ValueError:
        return None

    html = page.get("html") or ""
    page_links = (
        list_all_internal_links(html, href) if search_override and html else []
    )
    raw = (page.get("text") or "").strip()
    if len(raw) < 80:
        if search_override and page_links:
            return {"result": None, "page_links": page_links, "source_url": href}
        return None

    extract_max = max(4000, int(excerpt_chars))
    excerpt = prepare_page_text_for_context(
        raw,
        user_text=user_text,
        query=query,
        max_chars=extract_max,
        raw_max_chars=_FETCH_PAGE_RAW_CHARS,
    )
    if len(excerpt) < 80:
        if search_override and page_links:
            return {"result": None, "page_links": page_links, "source_url": href}
        return None

    result = _build_fetched_page_result(
        item, page, raw, excerpt, excerpt_chars, href
    )
    if not search_override:
        return result
    return {"result": result, "page_links": page_links, "source_url": href}


def _fetch_selected_link_page(link, excerpt_chars, user_text="", query=""):
    from page_content_extract import prepare_page_text_for_context
    from web_fetch import fetch_page_content

    href = (link.get("url") or "").strip()
    anchor = (link.get("anchor") or "").strip()
    if not href:
        return None
    try:
        page = fetch_page_content(
            href,
            max_text_chars=_FETCH_PAGE_RAW_CHARS,
            enhanced=True,
        )
    except ValueError:
        return None
    raw = (page.get("text") or "").strip()
    if len(raw) < 80:
        return None
    extract_max = max(4000, int(excerpt_chars))
    excerpt = prepare_page_text_for_context(
        raw,
        user_text=user_text,
        query=query,
        max_chars=extract_max,
        raw_max_chars=_FETCH_PAGE_RAW_CHARS,
    )
    if len(excerpt) < 80:
        return None
    label = anchor or page.get("title") or href
    meta = "（AI選別・関連リンク先）\n"
    if page.get("via_tavily"):
        meta = "（AI選別・関連リンク先・Tavily extract）\n"
    if len(raw) > len(excerpt) + 200:
        meta += f"（元ページ {len(raw):,} 字から要点抽出 → {len(excerpt):,} 字）\n"
    return enrich_search_result(
        {
            "title": f"（関連ページ）{label}",
            "href": href,
            "body": meta + excerpt,
            "fetched_full": True,
        },
        "page_follow",
    )


def augment_results_with_fetched_pages(
    results,
    user_text="",
    queries=None,
    max_pages=None,
    search_override=False,
    llm_client=None,
    llm_model=None,
    provider_id=None,
):
    """Fetch page bodies when the question needs detail or snippets are too thin."""
    from intelligent_search_override import (
        boost_search_page_fetch_plan,
        build_link_catalog,
        select_links_with_ai,
    )
    from service_status import prepend_official_status_results

    results = prepend_official_status_results(results, user_text)
    if not results:
        return results

    plan_max, excerpt_chars = plan_search_page_fetches(user_text, results)
    if search_override:
        plan_max, excerpt_chars = boost_search_page_fetch_plan(
            plan_max, excerpt_chars, _FETCH_PAGE_EXTRACT_CHARS
        )
    if max_pages is not None:
        plan_max = int(max_pages)
    if plan_max <= 0:
        return results

    topic = infer_search_topic(user_text)
    query_blob = " ".join(queries or [])
    ranked = sorted(
        results,
        key=lambda r: _fetch_priority_score(r, topic, user_text, query_blob),
        reverse=True,
    )

    candidates = []
    seen_href = set()
    for item in ranked:
        href = (item.get("href") or "").strip().lower().rstrip("/")
        if not href or href in seen_href:
            continue
        if _fetch_priority_score(item, topic, user_text, query_blob) < 0:
            continue
        seen_href.add(href)
        candidates.append(item)
        if len(candidates) >= plan_max:
            break

    if not candidates:
        return results

    augmented = list(results)
    page_entries = []
    futures = {
        _SEARCH_EXECUTOR.submit(
            _fetch_page_for_result,
            item,
            excerpt_chars,
            user_text,
            query_blob,
            search_override=search_override,
        ): item
        for item in candidates
    }
    for fut in as_completed(futures, timeout=_FETCH_PAGE_TIMEOUT + 2):
        try:
            fetched = fut.result(timeout=_FETCH_PAGE_TIMEOUT)
        except Exception:
            continue
        if not fetched:
            continue
        if isinstance(fetched, dict):
            result_item = fetched.get("result")
            if search_override:
                page_entries.append(fetched)
        else:
            result_item = fetched
        if result_item:
            augmented.append(result_item)

    if search_override and page_entries and llm_client and llm_model:
        catalog = build_link_catalog(page_entries, seen_urls=seen_href)
        selected_links = select_links_with_ai(
            llm_client,
            llm_model,
            user_text=user_text,
            query=query_blob,
            catalog=catalog,
            provider_id=provider_id,
            disable_reasoning=True,
        )
        if selected_links:
            follow_futures = {
                _SEARCH_EXECUTOR.submit(
                    _fetch_selected_link_page,
                    link,
                    excerpt_chars,
                    user_text,
                    query_blob,
                ): link
                for link in selected_links
            }
            for fut in as_completed(follow_futures, timeout=_FETCH_PAGE_TIMEOUT + 2):
                try:
                    fetched = fut.result(timeout=_FETCH_PAGE_TIMEOUT)
                except Exception:
                    continue
                if fetched:
                    augmented.append(fetched)

    return augmented


def search_limits_for_topic(topic):
    if topic == "admission_exam":
        return 14, 7
    if topic == "named_product":
        return 14, 7
    if topic == "llm_ranking":
        return 16, 8
    if topic == "software_setup":
        return 14, 8
    return 12, 6


def _body_limits_for_topic(topic, result_count):
    if topic == "llm_ranking":
        base = [1200, 1000, 850, 700, 600]
    elif topic == "software_setup":
        base = [1600, 1400, 1200, 1000, 900, 800]
    else:
        base = [750, 650, 550, 480, 420]
    return [base[min(i, len(base) - 1)] for i in range(result_count)]


def _web_search_answer_rules(topic):
    common = (
        "- 冒頭1〜2文でユーザーの質問に直接答える（はい/いいえ/一部設定が必要 など）\n"
        "- 読みやすさ: 1段落は1〜3文まで。段落の間は必ず空行を入れる。1文に出典リンクを2つ以上詰め込まず、リンクは別段落に分けてよい\n"
        "- URL・ドメイン名はドットの直後にスペースを入れない（正: status.claude.com / 誤: status. claude. com）\n"
        "- 「検索結果の範囲では」「与えられた検索結果だけでは」などのメタ前置きは禁止\n"
        "- [1][2] 形式の番号出典・「各ソース」「Tavily要約」など内部用語は書かない\n"
        "- スニペットやページ本文に書いてある事実は、そのまま分かりやすく説明する\n"
        "- 未記載の細部は「一般的な Nukkit 系サーバーでは〜（要公式 Wiki 確認）」と短く補足してよい\n"
        "- 「断言できません」「確認できない」だけで終えず、分かったこと・確認手順・次のステップを書く\n"
        "- 「さらに検索します」「詳しく調べてみます」は禁止（検索は完了済み）\n"
    )
    if topic == "software_setup":
        return (
            common
            + "- 設定ファイル名（nukkit.yml / server.properties 等）や起動手順が分かれば具体的に書く\n"
            + "- マルチバージョンが「標準で有効か」「プラグイン/設定が必要か」は、取得した README・Wiki の記述を優先する\n"
        )
    if topic == "service_status":
        return (
            common
            + "- 「（公式ステータス・最優先）」の行は Statuspage API の生データ。これを他の検索結果より必ず優先する\n"
            + "- 進行中インシデント（Investigating / Identified 等）がある場合、「全サービス正常」「All Systems Operational」とは書かない\n"
            + "- インシデント名・状態・最新更新文・UTC時刻をそのまま書く\n"
            + "- ブログやSEO記事の古い「稼働中」表現は、公式ステータスと矛盾する場合は無視する\n"
        )
    if topic == "news":
        return (
            common
            + "- 各ニュース項目の直後に、必ず Markdown リンクで出典URLを書く（例: （[NHKニュース](https://...)））\n"
            + "- [1][2][3] のような番号だけの脚注は禁止（番号を使わずリンクを書く）\n"
            + "- 回答の末尾に「### 参考リンク」見出しを付け、使用したソースをタイトル付きURLの箇条書きで列挙する\n"
            + "- 検索結果の「情報の日付」が今日でない記事を、最新ニュースのように書かない\n"
        )
    if topic == "admission_exam":
        from intelligent_search_override import japanese_entrance_exam_nendos

        years = japanese_entrance_exam_nendos()
        primary = years["primary_nendo"]
        return (
            common
            + "- 入試・AO・総合型選抜の日程は「（ページ本文）」「（関連ページ）」を最優先する\n"
            + f"- 日本の大学入試は入学年度表記（例: 現在時点の次入試は {primary}年度 であることが多い）に注意する\n"
            + "- エントリー開始日・期間・締切が本文にあれば具体的な日付で答える\n"
            + "- スニペットだけで「確認できません」と書かない\n"
        )
    return common


def wants_news_search(user_text):
    return bool(_NEWS_INTENT.search(user_text or ""))


_MULTI_SEARCH_HINT = re.compile(
    r"複数|それぞれ|各々|まとめて|併せて|あわせて|"
    r"と.*(?:インストール|セットアップ|構築|導入)|"
    r"(?:インストール|セットアップ).*(?:と|、|,).*(?:インストール|セットアップ)",
    re.IGNORECASE,
)


def user_needs_multi_search(user_text, computelab_active=False):
    text = (user_text or "").strip()
    if not text:
        return False
    if computelab_active and re.search(
        r"インストール|セットアップ|deploy|構築|環境|サーバー|compose|docker",
        text,
        re.IGNORECASE,
    ):
        return True
    topic = infer_search_topic(text)
    if topic == "software_setup":
        if _MULTI_SEARCH_HINT.search(text):
            return True
        if len(
            re.findall(
                r"インストール|セットアップ|install|setup|構築|導入",
                text,
                re.IGNORECASE,
            )
        ) >= 2:
            return True
    if topic == "service_status":
        return False
    if topic == "news" or _MULTI_SEARCH_HINT.search(text):
        return True
    return False


def max_web_search_rounds(user_text, computelab_active=False):
    if user_needs_multi_search(user_text, computelab_active):
        return max(2, int(os.getenv("WEB_SEARCH_MAX_ROUNDS", "3")))
    return max(1, int(os.getenv("WEB_SEARCH_MAX_ROUNDS_SIMPLE", "2")))


def merge_search_result_lists(*lists):
    seen = set()
    merged = []
    for results in lists:
        for item in results or []:
            key = _result_dedupe_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def web_search_system_prompt_multi_append():
    return (
        "\n\n【複数回Web検索】\n"
        "複数ソフトの導入・ComputeLab作業・大規模調査では、1回の検索で足りなければ "
        "`web_search` を追加で呼び出せる（最大3回程度）。\n"
        "- 1回目: 全体像と公式ドキュメント\n"
        "- 2回目以降: 不足している製品名・バージョン・手順だけ queries を変えて再検索\n"
        "- 十分なら追加検索せず、最終回答のみ書く\n"
    )


def _token_set(text):
    if not text:
        return set()
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def _result_dedupe_key(item):
    href = (item.get("href") or "").strip().lower().rstrip("/")
    if href:
        return href
    title = re.sub(r"\s+", " ", (item.get("title") or "").strip().lower())
    return f"title:{title}" if title else ""


_LLM_RELEVANT = (
    "llm",
    "gpt",
    "claude",
    "gemini",
    "grok",
    "deepseek",
    "llama",
    "mistral",
    "arena",
    "lmsys",
    "leaderboard",
    "benchmark",
    "elo",
    "chatbot",
    "openai",
    "anthropic",
    "モデル",
    "ランキング",
    "ベンチマーク",
)

_LLM_IRRELEVANT = (
    "twitter",
    "twihub",
    "沖縄",
    "シュノーケル",
    "動画保存",
    "diginoiz",
    "dtmer",
    "android 16",
    "yahoo!ニュース",
    "youtube.com/watch",
    "design arena",
    "replit ai:",
)

_LLM_BOOST_HOSTS = (
    "huggingface.co",
    "lmsys.ai",
    "openlm.ai",
    "chatbotarena",
    "chatbot-arena",
    "arena.ai",
    "leaderboard",
    "open-llm",
    "ollama.com",
)

_MODEL_NAME_PATTERN = re.compile(
    r"(Qwen[\w./-]*|Llama[\s-]?[\d.]+\w*|DeepSeek[\w./-]*|Mistral[\w./-]*|"
    r"Gemma[\s-]?[\d.]+\w*|Phi-[\w./-]*|GLM-[\w./-]*|Mixtral[\w./-]*|"
    r"Command[\s-]?[\w./-]*|Yi-[\w./-]*|Grok[\w./-]*|o\d-mini|GPT-[\w./-]*)",
    re.IGNORECASE,
)


_COMPUTELAB_DENIAL_RESULT = re.compile(
    r"computelab.*(見つから|存在し|不明|とは何|what is)|"
    r"ホスティング.*見つから|サービス.*見つかりません|"
    r"具体的にどのサービス",
    re.IGNORECASE,
)
_COMPUTELAB_IDENTITY_QUERY = re.compile(
    r"^computelab\s|computelab.*(とは|サービス|hosting|vps|ホスティング|会社)",
    re.IGNORECASE,
)


def filter_computelab_confusion_results(results, user_text="", computelab_active=False):
    if not computelab_active:
        return results
    if not re.search(r"computelab", user_text or "", re.IGNORECASE):
        return results
    kept = []
    for item in results or []:
        blob = " ".join(
            [
                item.get("title") or "",
                item.get("body") or "",
                item.get("href") or "",
            ]
        )
        if _COMPUTELAB_DENIAL_RESULT.search(blob):
            continue
        kept.append(item)
    return kept


def refine_search_queries(
    user_text, queries, computelab_active=False, intelligent_search_override=False
):
    seen = set()
    out = []
    for q in queries or []:
        q = re.sub(r"\s+", " ", str(q).strip())
        if not q:
            continue
        if computelab_active and _COMPUTELAB_IDENTITY_QUERY.search(q):
            continue
        if computelab_active and len(q) > 180 and "computelab" in q.lower():
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)

    topic = infer_search_topic(user_text)
    from search_retry import expand_named_entity_queries, extract_search_focus_terms

    focus_terms = extract_search_focus_terms(user_text)
    if focus_terms:
        out = expand_named_entity_queries(user_text, out)

    topic = infer_search_topic(user_text)
    if topic == "llm_ranking" and not focus_terms:
        year = datetime.now().year
        preferred = [
            f"huggingface open llm leaderboard top models {year}",
            "lmsys chatbot arena open source model Elo ranking",
            f"best open weight local LLM ranking Qwen Llama DeepSeek {year}",
        ]
        if re.search(r"ローカル|local", user_text or "", re.IGNORECASE):
            preferred.append(f"ローカル実行 オープンソース LLM ランキング 最強 {year}")
        merged = []
        for q in preferred + out:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(q)
            if len(merged) >= 4:
                break
        out = merged[:4]

    if topic == "software_setup":
        preferred = []
        if re.search(r"petteri|nukkit", user_text or "", re.IGNORECASE):
            preferred.extend(
                [
                    "Nukkit PetteriM1 Edition multiversion wiki",
                    "PetteriM1 Nukkit github README multiversion",
                ]
            )
        merged = []
        for q in preferred + out:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(q)
            if len(merged) >= 4:
                break
        out = merged[:4]

    if topic == "service_status":
        from service_status import resolve_status_services

        preferred = []
        for svc in resolve_status_services(user_text):
            host = svc["base_url"].replace("https://", "").rstrip("/")
            preferred.append(f"site:{host}")
            preferred.append(f"{svc['label']} status incident")
        merged = []
        for q in preferred + out:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(q)
            if len(merged) >= 4:
                break
        out = merged[:4]

    if wants_news_search(user_text):
        today = datetime.now()
        preferred = [
            f"日本 ニュース {today.strftime('%Y年%m月%d日')}",
            f"世界 ニュース {today.strftime('%Y-%m-%d')}",
            "最新ニュース 速報 今日",
        ]
        merged = []
        for q in preferred + out:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(q)
            if len(merged) >= 4:
                break
        out = merged[:4]

    from intelligent_search_override import expand_admission_search_queries

    expanded = expand_admission_search_queries(
        user_text,
        out,
        force=intelligent_search_override,
    )
    if expanded != out:
        out = expanded

    if not out and user_text:
        out = [build_search_query(user_text)]

    topic = infer_search_topic(user_text)
    if topic == "admission_exam":
        return out[:5]
    if topic == "named_product":
        return out[:5]
    return out[:3]


def _score_llm_ranking(item):
    blob = " ".join(
        [
            item.get("title") or "",
            item.get("body") or "",
            item.get("href") or "",
        ]
    ).lower()
    score = 0
    host = site_from_url(item.get("href") or "").lower()
    for hint in _LLM_RELEVANT:
        if hint in blob:
            score += 2
    for boost in _LLM_BOOST_HOSTS:
        if boost in host or boost in blob:
            score += 4
    if _MODEL_NAME_PATTERN.search(blob):
        score += 5
    for bad in _LLM_IRRELEVANT:
        if bad in blob:
            score -= 6
    if item.get("synthetic"):
        score -= 4
    return score


def _score_general(item, user_text, query):
    blob = " ".join(
        [
            item.get("title") or "",
            item.get("body") or "",
            item.get("href") or "",
        ]
    )
    blob_lower = blob.lower()
    ref_tokens = _token_set(f"{user_text} {query}")
    item_tokens = _token_set(blob)
    overlap = len(ref_tokens & item_tokens) if ref_tokens else 0
    score = min(overlap * 3, 24)

    host = site_from_url(item.get("href") or "").lower()
    for trusted in _TRUSTED_JP_HOSTS:
        if trusted in host:
            score += 4
            break

    body = (item.get("body") or "").strip()
    if len(body) >= 60:
        score += 3
    elif len(body) < 15:
        score -= 4

    if item.get("date"):
        score += 3

    if item.get("href"):
        score += 2
    else:
        score -= 10

    if item.get("synthetic"):
        corroboration = 0
        if ref_tokens and item_tokens:
            corroboration = len(ref_tokens & item_tokens)
        score += min(corroboration * 2, 8) - 12

    provider = (item.get("provider") or "").lower()
    if "serper" in provider or "google" in provider:
        score += 1
    if "tavily" in provider and item.get("href"):
        score += 1

    if re.search(r"login|sign in|ログイン|会員登録", blob_lower):
        score -= 5

    return score


def _score_news(item):
    blob = " ".join(
        [
            item.get("title") or "",
            item.get("body") or "",
            item.get("href") or "",
        ]
    ).lower()
    score = _score_general(item, "", "")
    host = site_from_url(item.get("href") or "").lower()
    for hint in _TRUSTED_JP_HOSTS:
        if hint in host:
            score += 8
    if any(
        h in host
        for h in (
            "news.",
            "/news/",
            "nhk.or.jp",
            "reuters.com",
            "bbc.com",
            "cnn.com",
        )
    ):
        score += 6
    if re.search(r"20\d{2}[-/年]\d{1,2}", blob):
        score += 3
    if item.get("synthetic"):
        score -= 12
    return score


def _score_service_status(item, user_text, query):
    blob = " ".join(
        [
            item.get("title") or "",
            item.get("body") or "",
            item.get("href") or "",
        ]
    ).lower()
    score = _score_general(item, user_text, query)
    if (item.get("provider") or "") == "official_status_api":
        return score + 100
    host = site_from_url(item.get("href") or "").lower()
    if re.search(r"status\.|githubstatus|cloudflarestatus|vercel-status", host):
        score += 35
    if re.search(r"株式会社|とは\？|解説|予測|ベスト|ランキング", blob):
        score -= 12
    if "all systems operational" in blob and "official_status" not in blob:
        score -= 8
    return score


def _score_named_product(item, user_text, query):
    from search_retry import extract_search_focus_terms, _normalize_term_key

    score = _score_general(item, user_text, query)
    blob = _normalize_term_key(
        " ".join(
            [
                item.get("title") or "",
                item.get("body") or "",
                item.get("href") or "",
            ]
        )
    )
    for term in extract_search_focus_terms(user_text):
        if _normalize_term_key(term) in blob:
            score += 28
    host = site_from_url(item.get("href") or "").lower()
    if re.search(r"z\.ai|zhipu|huggingface|modelscope|github\.com", host):
        score += 8
    if item.get("synthetic"):
        score -= 6
    return score


def score_search_result(item, topic, user_text="", query=""):
    if topic == "named_product":
        return _score_named_product(item, user_text, query)
    if topic == "llm_ranking":
        return _score_llm_ranking(item)
    if topic == "news":
        return _score_news(item)
    if topic == "service_status":
        return _score_service_status(item, user_text, query)
    return _score_general(item, user_text, query)


def collect_models_from_results(results):
    seen = set()
    names = []
    for item in results or []:
        blob = f"{item.get('title', '')} {item.get('body', '')}"
        for m in _MODEL_NAME_PATTERN.finditer(blob):
            name = m.group(1).strip()
            key = name.lower()
            if key not in seen and len(name) >= 3:
                seen.add(key)
                names.append(name)
    return names


def filter_search_results(results, user_text, limit=12, queries=None):
    if not results:
        return []
    topic = infer_search_topic(user_text)
    query_blob = " ".join(queries or [])
    ranked = sorted(
        (
            (score_search_result(r, topic, user_text, query_blob), r)
            for r in results
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    good = [r for s, r in ranked if s > 0]
    if good:
        return good[:limit]
    return [r for _, r in ranked[: min(limit, 8)]]


def _collect_query_parallel(search_query, per_query, user_text, engines=None):
    engines = engines or {"tavily": True, "serper": True, "ddg": True}
    keys = get_resolved_api_keys()
    jobs = []
    if engines.get("tavily") and keys.get("tavily"):
        jobs.append(
            ("tavily", "Tavily", lambda q, n: _run_provider("tavily", search_tavily, q, n))
        )
    if engines.get("serper") and keys.get("serper"):
        jobs.append(
            (
                "serper",
                "Google (Serper)",
                lambda q, n: _run_provider("serper", search_serper, q, n),
            )
        )
        if wants_news_search(user_text):
            jobs.append(
                (
                    "serper_news",
                    "Google News (Serper)",
                    lambda q, n: _run_provider("serper_news", search_serper_news, q, n),
                )
            )

    merged = []
    providers_used = []
    if jobs:
        futures = {
            _SEARCH_EXECUTOR.submit(fn, search_query, per_query): label
            for _, label, fn in jobs
        }
        deadline = time.monotonic() + SEARCH_HTTP_TIMEOUT + 1.5
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                batch = fut.result(timeout=max(0.1, deadline - time.monotonic()))
            except Exception:
                batch = []
            if batch:
                providers_used.append(label)
                merged.extend(batch)

    topic = infer_search_topic(user_text)
    ddg_ok = engines.get("ddg") or engines.get("ddg_fallback")
    needs_ddg = False
    if ddg_ok:
        if not merged or len(merged) < 3:
            needs_ddg = True
        elif topic == "named_product":
            from search_retry import results_match_focus_terms

            if not results_match_focus_terms(merged, user_text):
                needs_ddg = True
    if needs_ddg and ddg_ok:
        ddg_batch = _run_provider("ddg", search_dg, search_query, per_query)
        if ddg_batch:
            if SEARCH_DG_PROVIDER not in providers_used:
                providers_used.append(SEARCH_DG_PROVIDER)
            merged.extend(ddg_batch)

    provider_label = " + ".join(dict.fromkeys(providers_used)) or SEARCH_DG_PROVIDER
    query_blob = search_query
    ranked = sorted(
        merged,
        key=lambda r: score_search_result(r, topic, user_text, query_blob),
        reverse=True,
    )
    seen = set()
    ordered = []
    for item in ranked:
        key = _result_dedupe_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
        if len(ordered) >= per_query + 2:
            break
    return provider_label, ordered


def perform_web_search(query, max_results=8):
    results = []
    final_query = ""
    for event in stream_web_search(query, max_results=max_results):
        if event["type"] == "done":
            results = event["results"]
            final_query = event["query"]
    return results, final_query


def stream_web_search_for_queries(
    queries, max_results=6, user_text="", search_engines=None, computelab_active=False
):
    query_list = refine_search_queries(
        user_text, queries, computelab_active=computelab_active
    )
    if not query_list:
        yield {"type": "done", "results": [], "query": ""}
        return

    yield {"type": "start"}

    all_results = []
    seen = set()
    topic = infer_search_topic(user_text)
    max_total, per_query = search_limits_for_topic(topic)
    per_query = max(per_query, max_results)

    def try_add(item, provider, search_query):
        key = _result_dedupe_key(item)
        if not key or key in seen:
            return None
        if topic == "llm_ranking" and score_search_result(
            item, topic, user_text, search_query
        ) <= 0:
            return None
        if topic == "named_product" and score_search_result(
            item, topic, user_text, search_query
        ) <= 0:
            return None
        seen.add(key)
        all_results.append(item)
        return {
            "type": "hit",
            "title": item.get("title") or "",
            "url": item.get("href") or "",
            "site": site_from_url(item.get("href", "")),
            "provider": provider,
            "query": search_query,
            "date": item.get("date") or "",
            "date_label": item.get("date_label") or "日付不明",
        }

    engines = search_engines or {"tavily": True, "serper": True, "ddg": True}
    futures = {
        _SEARCH_EXECUTOR.submit(
            _collect_query_parallel, q, per_query, user_text, engines
        ): q
        for q in query_list
    }
    for fut in as_completed(futures):
        if len(all_results) >= max_total:
            break
        search_query = futures[fut]
        try:
            provider_label, items = fut.result(timeout=SEARCH_HTTP_TIMEOUT + 2)
        except Exception:
            provider_label, items = SEARCH_DG_PROVIDER, []

        if not items:
            continue

        yield {
            "type": "query",
            "query": search_query,
            "provider": provider_label,
        }
        for item in items:
            if len(all_results) >= max_total:
                break
            hit = try_add(item, item.get("provider") or provider_label, search_query)
            if hit:
                yield hit

    filtered = filter_search_results(
        all_results, user_text, limit=max_total, queries=query_list
    )
    filtered = filter_computelab_confusion_results(
        filtered, user_text, computelab_active=computelab_active
    )
    yield {
        "type": "done",
        "results": filtered,
        "query": ", ".join(query_list),
        "total": len(filtered),
    }


def stream_web_search(user_text, max_results=8, search_engines=None):
    query = build_search_query(user_text)
    if not query:
        yield {"type": "done", "results": [], "query": ""}
        return

    queries = [query]
    for extra in _supplementary_queries(user_text):
        if extra not in queries:
            queries.append(extra)

    yield from stream_web_search_for_queries(
        queries,
        max_results=max_results,
        user_text=user_text,
        search_engines=search_engines,
    )


def format_search_context(results, search_query, user_text=""):
    if not results:
        return (
            f"検索クエリ: {search_query}\n"
            "（Web検索を実行しましたが、結果を取得できませんでした。）"
        )

    topic = infer_search_topic(user_text)
    body_limits = _body_limits_for_topic(topic, len(results))
    now_label = datetime.now().strftime("%Y年%m月%d日")
    lines = [
        f"検索クエリ: {search_query}",
        f"回答基準日（サーバー）: {now_label}",
        "複数の検索APIの結果に加え、必要な場合は上位URLのページ本文も取得しています。",
        "（ページ本文）は URL 全文を読み、質問に関連する要点・データ・リスト全体・設定値を優先抽出したもの。",
        "",
    ]
    for i, item in enumerate(results, 1):
        title = item.get("title") or "（タイトルなし）"
        href = item.get("href") or ""
        body = (item.get("body") or "").strip()
        if item.get("fetched_full"):
            limit = max(
                body_limits[min(i - 1, len(body_limits) - 1)],
                _FETCH_PAGE_EXTRACT_CHARS,
            )
        else:
            limit = body_limits[min(i - 1, len(body_limits) - 1)]
        if len(body) > limit:
            body = body[:limit] + "…"
        date_label = item.get("date_label") or format_date_label(item.get("date"))
        provider = item.get("provider") or ""
        lines.append(f"[{i}] {title}")
        lines.append(f"情報の日付: {date_label}")
        if provider:
            lines.append(f"取得元: {provider}")
        if href:
            lines.append(f"URL: {href}")
        if item.get("fetched_full"):
            lines.append("種別: ページ本文（優先して参照）")
        elif item.get("synthetic"):
            lines.append("種別: API統合要約（単独では確定事実にしない）")
        if body:
            lines.append(body)
        lines.append("")

    models = collect_models_from_results(results)
    if models:
        lines.append("---")
        lines.append("スニペットから検出したモデル名（回答に必ず反映）:")
        lines.append(", ".join(models))

    if topic == "llm_ranking":
        lines.append("")
        lines.append(
            "※ ユーザーはローカル実行可能なオープンウェイトLLMの最優秀モデルを質問。"
            "ハードウェア無制限なら大規模モデル（70B級など）も含めて論じる。"
        )
    elif topic == "named_product":
        lines.append("")
        lines.append(
            "※ 特定製品・AIモデル名の質問。検索結果・ページ本文にモデル名が含まれるソースを優先し、"
            "見つからない場合のみ「公開情報が限定的」と述べる。"
        )
    elif topic == "software_setup":
        lines.append("")
        lines.append(
            "※ セットアップ・マルチバージョン・設定の質問。README/Wiki/ページ本文の記述を最優先し、"
            "起動だけで有効か・設定が必要かを明確に述べる。"
        )
    elif topic == "news":
        lines.append("")
        lines.append(
            "※ ニュース質問: 回答では [n] の番号脚注を使わず、下記インデックスの URL を"
            "Markdown リンクで必ず記載する。"
        )
    elif topic == "service_status":
        lines.append("")
        lines.append(
            "※ サービス稼働状況: 「（公式ステータス・最優先）」は status.* の API から取得した最新情報。"
            "進行中インシデントがあれば障害ありとして答える。"
        )

    lines.extend(_format_source_index_lines(results))
    return "\n".join(lines).strip()


_NUMERIC_CITATION_RE = re.compile(r"\[(\d{1,2})\]")
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
_BROKEN_INLINE_LINK_RE = re.compile(
    r"\[([^\]]+?)\((https?://[^\s)）]+)\)"
)


def _protect_markdown_links(text):
    links = []

    def repl(match):
        links.append(match.group(0))
        return f"\x00MDLINK{len(links) - 1}\x00"

    return _MD_LINK_RE.sub(repl, text), links


def _restore_markdown_links(text, links):
    for i, link in enumerate(links):
        text = text.replace(f"\x00MDLINK{i}\x00", link)
    return text


def repair_broken_inline_links(text):
    return _BROKEN_INLINE_LINK_RE.sub(r"[\1](\2)", text or "")


def build_search_source_index(results):
    index = {}
    for i, item in enumerate(results or [], 1):
        href = (item.get("href") or "").strip()
        if not href:
            continue
        title = re.sub(r"\s+", " ", (item.get("title") or href).strip())
        if len(title) > 120:
            title = title[:117] + "…"
        index[i] = {"href": href, "title": title or href}
    return index


def _format_source_index_lines(results, max_items=14):
    lines = ["", "---", "## 出典インデックス（[n] → このURLを回答に貼る）"]
    for i, item in enumerate((results or [])[:max_items], 1):
        title = (item.get("title") or "（タイトルなし）").strip()
        href = (item.get("href") or "").strip()
        date_label = item.get("date_label") or format_date_label(item.get("date"))
        if href:
            lines.append(f"[{i}] {title}")
            lines.append(f"    日付: {date_label}")
            lines.append(f"    URL: {href}")
        else:
            lines.append(f"[{i}] {title}（URLなし — 出典に使わない）")
    return lines


def fix_search_answer_citations(text, results):
    text = (text or "").strip()
    if not text:
        return text

    index = build_search_source_index(results)
    cited = {int(m.group(1)) for m in _NUMERIC_CITATION_RE.finditer(text)}

    def repl(match):
        num = int(match.group(1))
        src = index.get(num)
        if not src:
            return ""
        title = src["title"]
        href = src["href"]
        return f"（[{title}]({href})）"

    fixed = _NUMERIC_CITATION_RE.sub(repl, text)
    fixed = repair_broken_inline_links(fixed)
    fixed = re.sub(r"（{2,}\s*\[", "（[", fixed)
    fixed = re.sub(r"（\s*）", "", fixed)
    protected, md_links = _protect_markdown_links(fixed)
    protected = re.sub(r"[】\]]{2,}。?", "。", protected)
    fixed = _restore_markdown_links(protected, md_links)
    fixed = re.sub(r"。{2,}", "。", fixed)
    fixed = re.sub(r"（\s*）", "", fixed)
    fixed = re.sub(r"[ \t]{2,}", " ", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    fixed = re.sub(r"\n+\s*（\[", "\n（[", fixed)
    fixed = re.sub(r"）\s*（(?=\[[^\]]+\]\()", "）\n（", fixed)
    fixed = re.sub(
        r"([。．!?！？:：])\s*（(?=\[[^\]]+\]\()",
        r"\1\n（",
        fixed,
    )
    fixed = repair_broken_inline_links(fixed)

    has_http = bool(re.search(r"https?://", fixed))
    if not has_http and index:
        used = sorted(cited & set(index.keys())) or sorted(index.keys())[:8]
        lines = ["", "### 参考リンク"]
        for num in used:
            src = index[num]
            lines.append(f"- [{src['title']}]({src['href']})")
        fixed = fixed.rstrip() + "\n" + "\n".join(lines)

    from model_sanitize import improve_readability, repair_dot_spaced_urls_and_hosts

    fixed = improve_readability(fixed.strip())
    return repair_dot_spaced_urls_and_hosts(fixed)


def build_web_search_system_message(context, user_text="", agent_profile="deepseek"):
    from model_registry import is_deepseek_agent_profile

    if is_deepseek_agent_profile(agent_profile):
        return _build_web_search_system_message_deepseek(context, user_text)
    return _build_web_search_system_message_standard(context, user_text)


def _build_web_search_system_message_deepseek(context, user_text=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    topic = infer_search_topic(user_text)
    topic_rules = ""
    if topic == "llm_ranking":
        topic_rules = (
            "\n【ローカルLLMランキング】\n"
            "- 検索スニペットと「検出したモデル名」から、順位付き表（順位|モデル|根拠|情報の日付）を必ず作る\n"
            "- 複数ソースで繰り返し出るモデルを上位に置く\n"
            "- 検索だけで確定順位が作れない場合も、検出モデルを整理し、確度の高い候補を提示する\n"
            "- 末尾に「参考（学習データ・日付不確実）」として候補を3〜5件補足してよい（最新と断定しない）\n"
            "- 「ページを確認します」「断定できませんでした」だけで終えない\n"
        )
    elif topic == "service_status":
        topic_rules = (
            "\n【サービス稼働状況】\n"
            "- 「（公式ステータス・最優先）」の API データを他ソースより優先\n"
            "- 進行中インシデントがあれば障害あり。Investigating / Identified をそのまま書く\n"
        )
    elif topic == "admission_exam":
        from intelligent_search_override import japanese_entrance_exam_nendos

        primary = japanese_entrance_exam_nendos()["primary_nendo"]
        topic_rules = (
            f"\n【大学入試・AO】\n"
            f"- 「（ページ本文）」「（関連ページ）」の日程・エントリー期間を最優先\n"
            f"- 入学年度表記に注意（次の入試は {primary}年度 と書かれていることが多い）\n"
            f"- 具体的な開始日・期間が本文にあれば日付で答える\n"
        )
    answer_rules = _web_search_answer_rules(topic)
    return (
        "あなたはWeb検索結果に基づいて回答するアシスタントです。\n"
        f"現在日時（サーバー）: {now}\n\n"
        "ルール:\n"
        "- 以下のWeb検索結果を最優先し、学習データと矛盾する場合は検索結果に従う\n"
        "- 「（公式ステータス・最優先）」「（ページ本文）」の行は最も信頼できる根拠として扱う\n"
        "- URLなしのAPI要約行だけでは断定しない\n"
        "- 各結果の「情報の日付」を確認し、古い情報を最新のように書かない\n"
        "- 追加の web_search / web_fetch の予告はしない\n"
        "- DSML・tool_calls 形式の出力は禁止\n"
        "- 回答は日本語で行う\n"
        "- 改行: 文ごと、または事実のまとまりごとに空行を入れ、横に長い1段落にしない\n"
        f"{answer_rules}"
        f"{topic_rules}\n\n"
        "## Web検索結果\n"
        f"{context}"
    )


def _build_web_search_system_message_standard(context, user_text=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    topic = infer_search_topic(user_text)
    topic_rules = ""
    if topic == "llm_ranking":
        topic_rules = (
            "\n【ランキング質問】\n"
            "- 検索結果から分かる範囲で順位付きの簡潔な表か箇条書きにする\n"
            "- 不確実な点は短く補足する\n"
        )
    elif topic == "news":
        topic_rules = (
            "\n【ニュース】\n"
            "- 各項目に Markdown リンクの出典URLを必ず付ける\n"
            "- [1][2] 形式の番号脚注は使わない\n"
            "- 末尾に「### 参考リンク」の箇条書きを付ける\n"
        )
    elif topic == "service_status":
        topic_rules = (
            "\n【サービス稼働状況】\n"
            "- 公式ステータス API の内容を最優先し、インシデントを明示する\n"
        )
    elif topic == "admission_exam":
        from intelligent_search_override import japanese_entrance_exam_nendos

        primary = japanese_entrance_exam_nendos()["primary_nendo"]
        topic_rules = (
            f"\n【大学入試・AO】\n"
            f"- 「（ページ本文）」「（関連ページ）」を最優先\n"
            f"- 次の入試は {primary}年度 表記であることが多い\n"
        )
    answer_rules = _web_search_answer_rules(topic)
    return (
        "あなたはWeb検索結果に基づいて、ユーザー向けの読みやすい回答を書くアシスタントです。\n"
        f"現在日時（サーバー）: {now}\n\n"
        "ルール:\n"
        "- 以下のWeb検索結果を最優先する\n"
        "- 「（ページ本文）」の行は最も信頼できる根拠として扱う\n"
        "- 日本語で、短い段落と箇条書きで整理する（段落の間は空行）\n"
        "- 1文に複数の出典リンクを並べない。参考リンクは末尾の「### 参考リンク」にまとめる\n"
        "- 追加検索・ツールの予告はしない\n"
        "- DSML・tool_calls 形式の出力は禁止\n"
        f"{answer_rules}"
        f"{topic_rules}\n\n"
        "## Web検索結果\n"
        f"{context}"
    )
