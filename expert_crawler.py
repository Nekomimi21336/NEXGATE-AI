from __future__ import annotations

import asyncio
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urldefrag

import aiohttp
from bs4 import BeautifulSoup, Tag

_CONTENT_SELECTORS = [
    "main",
    "article",
    '[role="main"]',
    "#main-content",
    "#content",
    "#main",
    ".main-content",
    ".content",
    ".post-content",
    ".entry-content",
    ".article-body",
    ".page-content",
    ".markdown-body",
    ".document",
    ".docs-content",
    ".container",
]

_NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "header",
    "nav",
    "footer",
    "aside",
    "form",
    "button",
    "svg",
    "iframe",
    '[class*="sidebar"]',
    '[class*="menu"]',
    '[class*="breadcrumb"]',
    '[class*="toc"]',
    '[class*="cookie"]',
    '[class*="banner"]',
    '[class*="ad-"]',
    '[id*="sidebar"]',
]

_EXCLUDE_TAG = "<EXCLUDE/>"

_DEFAULT_SYSTEM_PROMPT = """\
あなたは Web サイトのページ内容を整理・要約する AI です。
以下のルールに従って処理してください。

【ステップ 1: ページ判定】
入力テキストが「意味のある情報を含むページ」かどうかを判断してください。
次のようなページは除外対象です:
- ログイン・会員登録ページ
- 404 / エラーページ
- 中身がほぼないページ（テキスト量が極端に少ない）
- カレンダーや空のリスト

除外と判断した場合は、出力の最初の行に以下の1行だけ出力して終了してください:
<EXCLUDE/>

【ステップ 2: 要約（有効なページの場合）】
次のルールで要約してください:
1. 数値・データ・コード・コマンド・URL・設定値・固有名詞は必ず原文のまま保持する
2. 接続詞・助詞・冗長な慣用表現は文脈に応じて省略してよい
3. ページの情報密度に応じて長さを調整する（簡潔なページは短く、詳細なページは詳しく）
4. Markdown 形式で出力する

【出力フォーマット】
## 概要
（このページが何を説明しているか 1〜2 文）

## 要点
（重要な情報を箇条書きまたは構造化テキストで。データ・数値・コマンドは必ず原文通り）
"""


@dataclass
class PageContent:
    url: str
    html: str | None = None
    status_code: int | None = None
    method: str = "static"
    error: str | None = None
    title: str | None = None
    text: str | None = None
    summary: str | None = None
    excluded: bool = False
    session_id: str = ""


def _clean(url: str) -> str:
    defragged, _ = urldefrag(url)
    return defragged


def _normalize_scheme(url: str, base_scheme: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.scheme != base_scheme:
        return parsed._replace(scheme=base_scheme).geturl()
    return url


def _same_host(url: str, netloc: str) -> bool:
    return urlparse(url).netloc == netloc


def _under_path(url: str, base_path: str) -> bool:
    p = urlparse(url).path
    norm_base = base_path if base_path.endswith("/") else base_path + "/"
    norm_p = p if p.endswith("/") else p + "/"
    return norm_p.startswith(norm_base)


def _is_localhost(netloc: str) -> bool:
    host = netloc.split(":")[0].lower()
    return host == "localhost" or host == "::1" or host.startswith("127.")


def _extract_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title = "untitled"

    for selector in _NOISE_TAGS:
        for tag in soup.select(selector):
            tag.decompose()

    content: Tag | None = None
    for selector in _CONTENT_SELECTORS:
        content = soup.select_one(selector)
        if content:
            break
    if content is None:
        content = soup.body or soup

    lines = []
    for elem in content.descendants:
        if not isinstance(elem, Tag):
            continue
        if elem.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = elem.get_text(" ", strip=True)
            if text:
                lines.append(f"\n## {text}\n")
        elif elem.name in ("p", "li", "dt", "dd", "td", "th", "blockquote", "pre", "code"):
            text = elem.get_text(" ", strip=True)
            if text:
                lines.append(text)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


async def _fetch_static(session, url, sem, timeout, delay):
    async with sem:
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True
            ) as resp:
                final_url = _clean(str(resp.url))
                status = resp.status
                if resp.status >= 400:
                    return final_url, status, None, f"HTTP {resp.status}"
                ct = resp.headers.get("Content-Type", "")
                if "text/html" not in ct:
                    return final_url, status, None, None
                html = await resp.text(errors="replace")
                return final_url, status, html, None
        except Exception as e:
            return url, None, None, str(e)


async def _crawl_static(
    base_url,
    max_pages,
    concurrency,
    timeout,
    delay,
    exclude_re,
):
    base_parsed = urlparse(base_url)
    base_netloc = base_parsed.netloc
    base_scheme = base_parsed.scheme
    raw_path = base_parsed.path
    if raw_path.endswith("/") or "." not in raw_path.rsplit("/", 1)[-1]:
        base_path = raw_path.rstrip("/") + "/"
    else:
        base_path = raw_path.rsplit("/", 1)[0] + "/"

    visited: set[str] = set()
    queue: asyncio.Queue[str] = asyncio.Queue()
    queue.put_nowait(base_url)
    visited.add(base_url)

    collected: list[PageContent] = []
    in_flight = 0
    sem = asyncio.Semaphore(concurrency)

    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:

        async def worker(url: str) -> None:
            nonlocal in_flight
            in_flight += 1
            try:
                final_url, status, html, error = await _fetch_static(
                    session, url, sem, timeout, delay
                )
                final_url = _normalize_scheme(final_url, base_scheme)
                if not _same_host(final_url, base_netloc):
                    error = f"redirected to external: {final_url}"

                entry = PageContent(
                    url=final_url,
                    status_code=status,
                    method="static",
                    error=error,
                )
                collected.append(entry)

                if error or html is None:
                    return

                entry.title, entry.text = _extract_text(html)
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    new_url = _normalize_scheme(
                        _clean(urljoin(final_url, a["href"])), base_scheme
                    )
                    if (
                        new_url not in visited
                        and _same_host(new_url, base_netloc)
                        and _under_path(new_url, base_path)
                        and not (exclude_re and exclude_re.search(new_url))
                    ):
                        visited.add(new_url)
                        if max_pages is None or len(collected) + queue.qsize() < max_pages:
                            queue.put_nowait(new_url)
            finally:
                in_flight -= 1

        tasks: set[asyncio.Task] = set()
        while True:
            if queue.empty() and in_flight == 0:
                break
            if max_pages is not None and len(collected) >= max_pages:
                break
            while not queue.empty():
                if max_pages is not None and len(collected) + in_flight >= max_pages:
                    break
                url = queue.get_nowait()
                task = asyncio.create_task(worker(url))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            if tasks:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(0.01)

    return collected


async def _summarize_one(session, page, api_base_url, api_key, model, system_prompt, sem):
    if not page.text or page.error:
        return 0
    async with sem:
        endpoint = api_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"タイトル: {page.title or '(不明)'}\n\n{page.text}",
                },
            ],
        }
        try:
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    return 0
                data = await resp.json()
                result = data["choices"][0]["message"]["content"].strip()
                if result.startswith(_EXCLUDE_TAG):
                    page.excluded = True
                else:
                    page.summary = result
                return int(data.get("usage", {}).get("total_tokens", 0) or 0)
        except Exception:
            return 0


async def _summarize_all(pages, api_base_url, api_key, model, system_prompt, concurrency):
    targets = [p for p in pages if p.text and not p.error]
    if not targets:
        return 0
    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        counts = await asyncio.gather(
            *[
                _summarize_one(session, page, api_base_url, api_key, model, system_prompt, sem)
                for page in targets
            ]
        )
    return sum(counts)


def crawl_site(
    base_url: str,
    max_pages: int | None = 30,
    timeout: float = 10.0,
    concurrency: int = 12,
    *,
    exclude_pattern: str = r"/cdn-cgi/|/wp-login\.php|/wp-admin/|/wp-json/",
) -> list[PageContent]:
    exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
    netloc = urlparse(base_url).netloc
    delay = 0.0 if _is_localhost(netloc) else 1.0

    async def _run():
        return await _crawl_static(
            base_url, max_pages, concurrency, timeout, delay, exclude_re
        )

    return asyncio.run(_run())


def summarize_pages(
    pages: list[PageContent],
    api_base_url: str,
    api_key: str,
    model: str,
    *,
    system_prompt: str | None = None,
    concurrency: int = 4,
    session_id: str = "",
) -> int:
    targets = [p for p in pages if not session_id or p.session_id == session_id]
    prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
    return asyncio.run(
        _summarize_all(targets, api_base_url, api_key, model, prompt, concurrency)
    )


def pages_to_knowledge_payloads(pages: list[PageContent], *, crawl_session_id: str = ""):
    out = []
    for page in pages:
        if page.error or page.excluded:
            continue
        content = page.summary or page.text
        if not content:
            continue
        title = page.title or "untitled"
        for sep in (" – ", " — ", " | ", " - "):
            if sep in title:
                title = title.rsplit(sep, 1)[0].strip()
                break
        out.append(
            {
                "title": title,
                "content": content,
                "source_url": page.url,
                "tags": ["crawl"],
                "crawl_session_id": crawl_session_id,
            }
        )
    return out


def _clip_preview(text, limit=180):
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _page_path_label(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def _site_info(base_url: str) -> dict:
    parsed = urlparse(base_url)
    return {
        "host": parsed.netloc,
        "base_url": base_url,
        "scheme": parsed.scheme or "http",
    }


def _sync_drain_async(agen):
    loop = asyncio.new_event_loop()
    try:
        while True:
            try:
                yield loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def _async_iter_crawl_static(
    base_url,
    max_pages,
    concurrency,
    timeout,
    delay,
    exclude_re,
):
    base_parsed = urlparse(base_url)
    base_netloc = base_parsed.netloc
    base_scheme = base_parsed.scheme
    raw_path = base_parsed.path
    if raw_path.endswith("/") or "." not in raw_path.rsplit("/", 1)[-1]:
        base_path = raw_path.rstrip("/") + "/"
    else:
        base_path = raw_path.rsplit("/", 1)[0] + "/"

    visited: set[str] = set()
    queue: asyncio.Queue[str] = asyncio.Queue()
    queue.put_nowait(base_url)
    visited.add(base_url)

    collected: list[PageContent] = []
    in_flight = 0
    sem = asyncio.Semaphore(concurrency)
    event_q: asyncio.Queue[dict | None] = asyncio.Queue()

    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:

        async def worker(url: str) -> None:
            nonlocal in_flight
            in_flight += 1
            page_id = uuid.uuid4().hex[:10]
            started = time.perf_counter()
            await event_q.put(
                {
                    "type": "page_start",
                    "page_id": page_id,
                    "url": url,
                    "path": _page_path_label(url),
                }
            )
            try:
                final_url, status, html, error = await _fetch_static(
                    session, url, sem, timeout, delay
                )
                final_url = _normalize_scheme(final_url, base_scheme)
                if not _same_host(final_url, base_netloc):
                    error = f"redirected to external: {final_url}"

                entry = PageContent(
                    url=final_url,
                    status_code=status,
                    method="static",
                    error=error,
                )
                collected.append(entry)
                duration_ms = round((time.perf_counter() - started) * 1000, 1)

                if error or html is None:
                    await event_q.put(
                        {
                            "type": "page_done",
                            "page_id": page_id,
                            "url": final_url,
                            "path": _page_path_label(final_url),
                            "title": None,
                            "status": "error",
                            "error": error or "empty response",
                            "duration_ms": duration_ms,
                            "text_preview": "",
                            "summary_preview": "",
                            "chars": 0,
                        }
                    )
                    return

                entry.title, entry.text = _extract_text(html)
                await event_q.put(
                    {
                        "type": "page_done",
                        "page_id": page_id,
                        "url": final_url,
                        "path": _page_path_label(final_url),
                        "title": entry.title,
                        "status": "ok",
                        "duration_ms": duration_ms,
                        "text_preview": _clip_preview(entry.text),
                        "summary_preview": "",
                        "chars": len(entry.text or ""),
                    }
                )

                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    new_url = _normalize_scheme(
                        _clean(urljoin(final_url, a["href"])), base_scheme
                    )
                    if (
                        new_url not in visited
                        and _same_host(new_url, base_netloc)
                        and _under_path(new_url, base_path)
                        and not (exclude_re and exclude_re.search(new_url))
                    ):
                        visited.add(new_url)
                        if max_pages is None or len(collected) + queue.qsize() < max_pages:
                            queue.put_nowait(new_url)
            finally:
                in_flight -= 1

        tasks: set[asyncio.Task] = set()

        async def crawl_loop() -> None:
            while True:
                if queue.empty() and in_flight == 0:
                    break
                if max_pages is not None and len(collected) >= max_pages:
                    break
                while not queue.empty():
                    if max_pages is not None and len(collected) + in_flight >= max_pages:
                        break
                    url = queue.get_nowait()
                    task = asyncio.create_task(worker(url))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                if tasks:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                else:
                    await asyncio.sleep(0.01)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        crawl_task = asyncio.create_task(crawl_loop())
        while not crawl_task.done() or not event_q.empty():
            try:
                evt = await asyncio.wait_for(event_q.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            if evt is not None:
                yield evt
        await crawl_task
        while not event_q.empty():
            evt = event_q.get_nowait()
            if evt is not None:
                yield evt

    yield {"type": "_pages_collected", "pages": collected}


async def _async_iter_summarize(
    pages: list[PageContent],
    api_base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    concurrency: int,
):
    targets = [p for p in pages if p.text and not p.error]
    if not targets:
        yield {"type": "summarize_phase_done", "count": 0, "duration_ms": 0}
        return

    yield {"type": "summarize_phase_start", "count": len(targets)}
    phase_started = time.perf_counter()
    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency)

    async def summarize_page(session, page: PageContent):
        started = time.perf_counter()
        tokens = await _summarize_one(
            session,
            page,
            api_base_url,
            api_key,
            model,
            system_prompt,
            sem,
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if page.excluded:
            status = "excluded"
        elif page.summary:
            status = "summarized"
        else:
            status = "skipped"
        return {
            "type": "page_summarized",
            "url": page.url,
            "path": _page_path_label(page.url),
            "title": page.title,
            "status": status,
            "duration_ms": duration_ms,
            "text_preview": _clip_preview(page.text),
            "summary_preview": _clip_preview(page.summary, 220),
            "tokens": tokens,
        }

    async with aiohttp.ClientSession(connector=connector) as session:
        pending = [asyncio.create_task(summarize_page(session, p)) for p in targets]
        for task in asyncio.as_completed(pending):
            yield await task

    yield {
        "type": "summarize_phase_done",
        "count": len(targets),
        "duration_ms": round((time.perf_counter() - phase_started) * 1000, 1),
    }


def iter_crawl_pipeline(
    base_url: str,
    *,
    max_pages: int = 30,
    summarize: bool = True,
    api_base_url: str = "",
    api_key: str = "",
    model: str = "",
    timeout: float = 10.0,
    concurrency: int = 12,
    exclude_pattern: str = r"/cdn-cgi/|/wp-login\.php|/wp-admin/|/wp-json/",
):
    crawl_session_id = uuid.uuid4().hex[:8]
    site = _site_info(base_url)
    pipeline_started = time.perf_counter()
    exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
    netloc = urlparse(base_url).netloc
    delay = 0.0 if _is_localhost(netloc) else 1.0

    yield {
        "type": "start",
        "crawl_session_id": crawl_session_id,
        "site": site,
        "max_pages": max_pages,
    }

    crawl_phase_started = time.perf_counter()
    yield {"type": "crawl_phase_start", "site": site}

    pages: list[PageContent] = []
    for evt in _sync_drain_async(
        _async_iter_crawl_static(
            base_url, max_pages, concurrency, timeout, delay, exclude_re
        )
    ):
        if evt.get("type") == "_pages_collected":
            pages = evt.get("pages") or []
            continue
        enriched = {**evt, "phase": "crawl", "site": site, "crawl_session_id": crawl_session_id}
        yield enriched

    for page in pages:
        page.session_id = crawl_session_id

    yield {
        "type": "crawl_phase_done",
        "phase": "crawl",
        "site": site,
        "crawl_session_id": crawl_session_id,
        "duration_ms": round((time.perf_counter() - crawl_phase_started) * 1000, 1),
        "pages_total": len(pages),
        "pages_ok": sum(1 for p in pages if p.text and not p.error),
        "pages_error": sum(1 for p in pages if p.error),
    }

    tokens = 0
    if summarize and api_base_url and api_key and model:
        for evt in _sync_drain_async(
            _async_iter_summarize(
                pages,
                api_base_url,
                api_key,
                model,
                _DEFAULT_SYSTEM_PROMPT,
                min(4, concurrency),
            )
        ):
            enriched = {
                **evt,
                "phase": "summarize",
                "site": site,
                "crawl_session_id": crawl_session_id,
            }
            yield enriched
            if evt.get("type") == "page_summarized":
                tokens += int(evt.get("tokens") or 0)

    payloads = pages_to_knowledge_payloads(pages, crawl_session_id=crawl_session_id)
    yield {
        "type": "complete",
        "phase": "done",
        "site": site,
        "crawl_session_id": crawl_session_id,
        "duration_ms": round((time.perf_counter() - pipeline_started) * 1000, 1),
        "result": {
            "crawl_session_id": crawl_session_id,
            "pages_total": len(pages),
            "pages_saved": len(payloads),
            "pages_excluded": sum(1 for p in pages if p.excluded),
            "pages_error": sum(1 for p in pages if p.error),
            "tokens_used": tokens,
            "items": payloads,
        },
    }


def run_crawl_pipeline(
    base_url: str,
    *,
    max_pages: int = 30,
    summarize: bool = True,
    api_base_url: str = "",
    api_key: str = "",
    model: str = "",
) -> dict:
    result = None
    for evt in iter_crawl_pipeline(
        base_url,
        max_pages=max_pages,
        summarize=summarize,
        api_base_url=api_base_url,
        api_key=api_key,
        model=model,
    ):
        if evt.get("type") == "complete":
            result = evt.get("result")
    if not result:
        raise RuntimeError("crawl pipeline produced no result")
    return result
