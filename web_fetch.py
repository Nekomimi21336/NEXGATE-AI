import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_URL_IN_TEXT = re.compile(
    r"https?://[^\s<>\]\)\"'】」、。]+",
    re.IGNORECASE,
)
_MAX_FETCH_BYTES = 600_000
_MAX_TEXT_CHARS = int(os.getenv("WEB_FETCH_TEXT_CHARS", "14000"))
_MAX_TEXT_CHARS_SEARCH = int(os.getenv("SEARCH_FETCH_RAW_TEXT_CHARS", "80000"))
_FETCH_TIMEOUT = 20
_USER_AGENT = "Mozilla/5.0 (compatible; NexgateAI/1.0; +https://nexgate.ai)"
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_TOKEN_RE = re.compile(r"[\w\u3040-\u30ff\u4e00-\u9fff]{2,}", re.UNICODE)
_BOT_WALL_RE = re.compile(
    r"just a moment|enable javascript|cf-browser-verification|"
    r"access denied|captcha|robot check|bot detection|"
    r"cloudflare|please verify you are a human|attention required",
    re.IGNORECASE,
)
_LINK_SKIP_RE = re.compile(
    r"(?:^#|javascript:|mailto:|tel:)|"
    r"(?:login|signin|sign-in|signup|sign-up|register|logout|"
    r"cart|checkout|privacy|terms|cookie-policy|/auth|/oauth)",
    re.IGNORECASE,
)
_LINK_HINT_RE = re.compile(
    r"doc|guide|tutorial|wiki|help|manual|setup|config|faq|article|"
    r"how-to|reference|readme|detail|仕様|設定|手順|使い方",
    re.IGNORECASE,
)
_MAX_INTERNAL_LINKS_LIST = 120


class _HtmlTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = 0
        self._title_parts = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section", "article"):
            if not self._skip:
                self._parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._in_title:
            t = data.strip()
            if t:
                self._title_parts.append(t)
            return
        if self._skip:
            return
        t = data.strip()
        if t:
            self._parts.append(t + " ")

    @property
    def title(self):
        return re.sub(r"\s+", " ", "".join(self._title_parts)).strip()

    def text(self):
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def extract_urls_from_text(text, limit=3):
    if not text:
        return []
    seen = set()
    out = []
    for m in _URL_IN_TEXT.finditer(text):
        url = m.group(0).rstrip(".,;:!?)】」")
        key = url.lower()
        if key in seen:
            continue
        if not is_fetchable_url(url):
            continue
        seen.add(key)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def is_fetchable_url(url):
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False
    if host.endswith(".local"):
        return False
    if re.match(r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)", host):
        return False
    return True


def _decode_body(raw, content_type=""):
    charset = "utf-8"
    if content_type:
        m = re.search(r"charset=([^\s;]+)", content_type, re.I)
        if m:
            charset = m.group(1).strip("\"'")
    try:
        return raw.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def _extract_title_from_html(html):
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def html_to_text(html, max_text_chars=None):
    cap = max_text_chars if max_text_chars is not None else _MAX_TEXT_CHARS
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    title = parser.title or _extract_title_from_html(html)
    text = parser.text()
    if not text:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
    if len(text) > cap:
        text = text[:cap] + "…"
    return title, text


def _host_key(hostname):
    host = (hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _same_site(host_a, host_b):
    a = _host_key(host_a)
    b = _host_key(host_b)
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _browser_headers(url):
    parsed = urlparse(url.strip())
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    return {
        "User-Agent": _BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        **({"Referer": origin} if origin else {}),
    }


def looks_like_bot_wall(text):
    t = (text or "").strip()
    if len(t) < 120:
        return True
    return bool(_BOT_WALL_RE.search(t[:2500]))


def query_term_coverage(text, user_text="", query=""):
    blob = f"{user_text} {query}".lower()
    tokens = {t for t in _TOKEN_RE.findall(blob) if len(t) >= 2}
    if not tokens:
        return 1.0
    lower = (text or "").lower()
    hits = sum(1 for token in tokens if token in lower)
    return hits / len(tokens)


def _http_get_bytes(url, headers, timeout=None):
    timeout = _FETCH_TIMEOUT if timeout is None else timeout
    req = urllib.request.Request(url.strip(), headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read(_MAX_FETCH_BYTES + 1)
    if len(raw) > _MAX_FETCH_BYTES:
        raw = raw[:_MAX_FETCH_BYTES]
    return raw, content_type


def _http_post_json(url, payload, timeout=None):
    timeout = _FETCH_TIMEOUT if timeout is None else timeout
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_via_tavily_extract(url):
    try:
        from search_settings import get_resolved_api_keys

        api_key = get_resolved_api_keys().get("tavily") or ""
        if not api_key:
            return None
        data = _http_post_json(
            "https://api.tavily.com/extract",
            {"api_key": api_key, "urls": [url.strip()]},
        )
        results = data.get("results") or []
        if not results:
            return None
        item = results[0]
        raw = (item.get("raw_content") or item.get("content") or "").strip()
        if len(raw) < 80:
            return None
        return {
            "url": item.get("url") or url,
            "title": (item.get("title") or "").strip(),
            "text": raw,
            "html": "",
            "content_type": "text/html",
            "via_tavily": True,
        }
    except Exception:
        return None


def list_all_internal_links(html, base_url, limit=_MAX_INTERNAL_LINKS_LIST):
    if not html or not base_url:
        return []
    base = urlparse(base_url.strip())
    base_host = base.hostname or ""
    href_re = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    out = []
    seen = set()
    cap = int(limit) if limit else _MAX_INTERNAL_LINKS_LIST
    for match in href_re.finditer(html):
        href = (match.group(1) or "").strip()
        anchor = re.sub(r"<[^>]+>", " ", match.group(2) or "")
        anchor = re.sub(r"\s+", " ", anchor).strip()
        if not href or _LINK_SKIP_RE.search(href):
            continue
        absolute = urljoin(base_url, href)
        if not is_fetchable_url(absolute):
            continue
        parsed = urlparse(absolute)
        if not _same_site(parsed.hostname, base_host):
            continue
        key = absolute.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append({"url": absolute, "anchor": anchor})
        if len(out) >= cap:
            break
    return out


def extract_internal_links(html, base_url, limit=40):
    return list_all_internal_links(html, base_url, limit=limit)


def score_internal_link(link, user_text="", query=""):
    url = (link.get("url") or "").strip()
    anchor = (link.get("anchor") or "").strip()
    blob = f"{url} {anchor}".lower()
    score = 0.0
    coverage = query_term_coverage(blob, user_text=user_text, query=query)
    score += coverage * 40.0
    if _LINK_HINT_RE.search(blob):
        score += 14.0
    path = urlparse(url).path or ""
    depth = len([part for part in path.split("/") if part])
    if 1 <= depth <= 4:
        score += 4.0
    if len(anchor) >= 4:
        score += 2.0
    if re.search(r"\.(pdf|zip|png|jpe?g|gif|webp|mp4|mp3)$", url, re.I):
        score -= 30.0
    return score


def pick_follow_up_links(html, base_url, user_text="", query="", limit=3):
    ranked = sorted(
        extract_internal_links(html, base_url, limit=limit * 6),
        key=lambda link: score_internal_link(link, user_text=user_text, query=query),
        reverse=True,
    )
    out = []
    seen = set()
    for link in ranked:
        url = (link.get("url") or "").strip()
        key = url.lower().rstrip("/")
        if not url or key in seen:
            continue
        if score_internal_link(link, user_text=user_text, query=query) < 6:
            continue
        seen.add(key)
        out.append(link)
        if len(out) >= limit:
            break
    return out


def _page_from_bytes(url, raw, content_type, max_text_chars, include_html=False):
    text_cap = max_text_chars if max_text_chars is not None else _MAX_TEXT_CHARS
    if "html" not in content_type.lower() and "xml" not in content_type.lower():
        text = _decode_body(raw, content_type).strip()
        if len(text) > text_cap:
            text = text[:text_cap] + "…"
        page = {
            "url": url,
            "title": "",
            "text": text or "（テキストを抽出できませんでした）",
            "content_type": content_type,
        }
        if include_html:
            page["html"] = ""
        return page

    html = _decode_body(raw, content_type)
    title, text = html_to_text(html, max_text_chars=text_cap)
    if not text:
        text = "（ページ本文を抽出できませんでした）"
    page = {
        "url": url,
        "title": title,
        "text": text,
        "content_type": content_type,
    }
    if include_html:
        page["html"] = html
    return page


def fetch_page_content(url, max_text_chars=None, enhanced=False, include_html=False):
    if not is_fetchable_url(url):
        raise ValueError("取得できないURLです（http/https の公開URLのみ）")

    headers = _browser_headers(url) if enhanced else {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.8",
    }
    last_err = None
    for attempt in range(2 if enhanced else 1):
        try:
            raw, content_type = _http_get_bytes(
                url,
                headers,
                timeout=_FETCH_TIMEOUT + (4 if enhanced else 0),
            )
            page = _page_from_bytes(
                url,
                raw,
                content_type,
                max_text_chars,
                include_html=include_html or enhanced,
            )
            if enhanced and looks_like_bot_wall(page.get("text") or ""):
                raise ValueError("bot protection")
            return page
        except urllib.error.HTTPError as e:
            last_err = ValueError(f"HTTP {e.code}")
            if enhanced and e.code in (403, 429, 503) and attempt == 0:
                continue
            raise last_err from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_err = ValueError(str(getattr(e, "reason", None) or e))
            if enhanced and attempt == 0:
                continue
            break
        except OSError as e:
            last_err = ValueError(str(e))
            break

    if enhanced:
        tavily_page = fetch_via_tavily_extract(url)
        if tavily_page:
            text_cap = max_text_chars if max_text_chars is not None else _MAX_TEXT_CHARS
            text = (tavily_page.get("text") or "").strip()
            if len(text) > text_cap:
                text = text[:text_cap] + "…"
            page = {
                "url": tavily_page.get("url") or url,
                "title": tavily_page.get("title") or "",
                "text": text,
                "content_type": tavily_page.get("content_type") or "text/html",
                "via_tavily": True,
            }
            if include_html or enhanced:
                page["html"] = ""
            return page

    if last_err:
        raise last_err
    raise ValueError("ページ取得に失敗しました")


def stream_web_fetch(url, reason=""):
    url = (url or "").strip()
    yield {"type": "intent", "url": url, "reason": (reason or "").strip()}
    yield {"type": "url", "url": url}
    try:
        page = fetch_page_content(url)
        ok = True
        err = ""
    except ValueError as e:
        page = {
            "url": url,
            "title": "",
            "text": f"ページ取得エラー: {e}",
        }
        ok = False
        err = str(e)
    yield {
        "type": "done",
        "url": url,
        "title": page.get("title") or "",
        "chars": len(page.get("text") or ""),
        "ok": ok,
        "error": err,
        "_page": page,
    }


def format_fetch_context(page, user_text="", query=""):
    from page_content_extract import prepare_page_text_for_context

    url = page.get("url") or ""
    title = page.get("title") or ""
    raw = (page.get("text") or "").strip()
    text = prepare_page_text_for_context(raw, user_text=user_text, query=query)
    lines = [f"取得URL: {url}"]
    if title:
        lines.append(f"ページタイトル: {title}")
    if raw and len(text) < len(raw) * 0.92:
        lines.append(
            f"本文: ページから要点・リスト・設定値を抽出（元 {len(raw):,} 字 → {len(text):,} 字）"
        )
    lines.append("")
    lines.append(text or "（本文なし）")
    return "\n".join(lines).strip()


def build_web_fetch_system_message(context, user_text="", agent_profile="deepseek"):
    from model_registry import is_deepseek_agent_profile

    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    if is_deepseek_agent_profile(agent_profile):
        rules = (
            "- 以下の取得ページ本文を最優先して回答する\n"
            "- 「URLを開けない」「ページを確認できない」とは書かない\n"
            "- 追加の web_fetch / web_search の予告はしない\n"
            "- DSML・tool_calls 形式の出力は禁止\n"
        )
    else:
        rules = (
            "- 以下の取得ページ本文を最優先する\n"
            "- 日本語で読みやすく、番号脚注は使わない\n"
            "- 追加ツールの予告はしない\n"
            "- DSML・tool_calls 形式の出力は禁止\n"
        )
    return (
        "あなたはWebページの取得結果に基づいて回答するアシスタントです。\n"
        f"現在日時（サーバー）: {now}\n\n"
        f"ルール:\n{rules}\n\n"
        "## 取得したページ\n"
        f"{context}"
    )
