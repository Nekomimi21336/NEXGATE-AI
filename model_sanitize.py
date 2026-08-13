import re

_DSML_BLOCK = re.compile(
    r"<[｜|]+DSML[｜|]+[\s\S]*?(?:</[｜|]+DSML[｜|]+[^>]+>|$)",
    re.IGNORECASE,
)
_DSML_TAG = re.compile(r"</?[｜|]+DSML[｜|]+[^>]*>", re.IGNORECASE)
_DSML_INVOKE = re.compile(
    r"</?[｜|]+(?:DSML[｜|]+)?(?:invoke|function_calls?|parameter)[｜|][^>]*>",
    re.IGNORECASE,
)
_DSML_START = re.compile(r"<[｜|/]+DSML[｜|]+", re.IGNORECASE)
_THINK_BLOCK = re.compile(r"<\s*think\s*>[\s\S]*?<\s*/\s*think\s*>", re.IGNORECASE)
_META_INTENT = re.compile(
    r"(?:検索結果に[^。\n]*スニペット[^。\n]*含まれていません[。.]?|"
    r"より詳細な情報を取得します[。.]?|"
    r"該当ページを開いて[^。\n]*確認[^。\n]*[。.]?)\s*",
    re.IGNORECASE,
)
_TOOL_PLANNING_LINE = re.compile(
    r"^(?:ユーザー(?:は|の)[^\n。]{0,120}(?:確認|取得|調べ)[^\n。]{0,80}ようです|"
    r"(?:Gmail|カレンダー|受信|予定|メール)[^\n。]{0,80}(?:取得|確認)しましょう)[。.]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_TOOL_PLANNING_HINT = re.compile(
    r"(?:Gmail|カレンダー|受信一覧|google_calendar|gmail_list|予定を)",
    re.IGNORECASE,
)
_PARTIAL_MARKUP = re.compile(
    r"<(?:[｜|/]|/?think\b|/?DSML|DSML|\w)[^>]*$|<$",
    re.IGNORECASE,
)


def _strip_dsml_markup(text: str) -> str:
    if not text:
        return ""
    text = _DSML_BLOCK.sub("", text)
    text = _DSML_TAG.sub("", text)
    text = _DSML_INVOKE.sub("", text)
    text = re.sub(r"DSML[｜|]+tool_calls", "", text, flags=re.IGNORECASE)
    return text


def _strip_meta_intent(text: str) -> str:
    text = _META_INTENT.sub("", text)
    return re.sub(r"<+\s*$", "", text)


_PLANNING_SENTENCE = re.compile(
    r"確認したいようです|(?:一覧|予定|メール).{0,40}(?:取得|確認)しましょう",
    re.IGNORECASE,
)


def _is_planning_sentence(chunk: str) -> bool:
    if not chunk:
        return False
    if _TOOL_PLANNING_LINE.match(chunk):
        return True
    if not _PLANNING_SENTENCE.search(chunk):
        return False
    return bool(
        _TOOL_PLANNING_HINT.search(chunk)
        or re.search(r"ユーザー(?:は|の)", chunk)
    )


def is_tool_planning_content(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 600:
        return False
    if not _TOOL_PLANNING_HINT.search(t):
        return False
    if not re.search(r"ようです|しましょう|しますね", t):
        return False
    parts = re.split(r"(?<=[。.!?])\s*", t)
    chunks = [p.strip() for p in parts if p.strip()]
    if not chunks:
        return False
    if all(_is_planning_sentence(c) for c in chunks):
        return True
    return len(t) < 120 and bool(_PLANNING_SENTENCE.search(t))


def _strip_tool_planning(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[。.!?])\s*", text)
    kept = []
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        if _is_planning_sentence(chunk):
            continue
        kept.append(chunk)
    return " ".join(kept).strip()


_READABILITY_SKIP = re.compile(
    r"```|^#{1,6}\s|^\s*[-*+]\s|^\s*\d+\.\s",
    re.MULTILINE,
)
_HOST_LABEL_DOT_SPACE = re.compile(
    r"(?<=[a-z0-9_-])\.\s+(?=[a-z0-9])",
    re.IGNORECASE,
)
_FENCE_BLOCK = re.compile(r"```[\s\S]*?```")
_UNCLOSED_DIAGRAM_FENCE = re.compile(
    r"```(?:flow|sequence)\s*\r?\n[\s\S]*$",
    re.IGNORECASE,
)


def _iter_fence_spans(text: str):
    last = 0
    for match in _FENCE_BLOCK.finditer(text):
        if match.start() > last:
            yield last, match.start(), False
        yield match.start(), match.end(), True
        last = match.end()
    tail = text[last:]
    unclosed = _UNCLOSED_DIAGRAM_FENCE.search(tail)
    if unclosed:
        abs_start = last + unclosed.start()
        if abs_start > last:
            yield last, abs_start, False
        yield abs_start, len(text), True
        return
    if last < len(text):
        yield last, len(text), False
_BARE_HOST_RE = re.compile(
    r"(?<![/@])\b(?:[a-z0-9][\w-]*\.\s+){1,6}"
    r"(?:com|net|org|io|ai|dev|co|uk|jp|app|cloud)\b",
    re.IGNORECASE,
)
_HTTP_URL_RE = re.compile(r"https?://[^\s\)\]>\"]+", re.IGNORECASE)


def _collapse_dot_spaces_in_segment(segment: str) -> str:
    if not segment or ". " not in segment:
        return segment
    segment = _HOST_LABEL_DOT_SPACE.sub(".", segment)
    segment = re.sub(r"(?<=\\)\. (?=[a-zA-Z0-9_$\\])", ".", segment)
    segment = re.sub(r"(?<=%)\. (?=[a-zA-Z0-9_\\])", ".", segment)
    return segment


def _collapse_dot_spaced_code_fence(block: str) -> str:
    if not block or not block.startswith("```") or ". " not in block:
        return block
    close = block.rfind("```")
    if close <= 3:
        return _collapse_dot_spaces_in_segment(block)
    head_end = block.find("\n")
    if head_end < 0:
        return _collapse_dot_spaces_in_segment(block)
    head = block[: head_end + 1]
    body = block[head_end + 1 : close]
    tail = block[close:]
    return head + _collapse_dot_spaces_in_segment(body) + tail


_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _collapse_dot_spaced_inline_code(text: str) -> str:
    def fix(match):
        inner = match.group(0)[1:-1]
        return "`" + _collapse_dot_spaces_in_segment(inner) + "`"

    return _INLINE_CODE_RE.sub(fix, text)


def collapse_dot_spaced_literals(text: str) -> str:
    """
    Fix model output like ``8.8. 8.8``, ``liteserver. jp``, ``discord. py``.
    Skips markdown code fences. Does not merge ``end. The`` (uppercase after space).
    """
    if not text or ". " not in text:
        return text

    parts = []
    for start, end, protected in _iter_fence_spans(text):
        segment = text[start:end]
        if protected and segment.startswith("```"):
            parts.append(_collapse_dot_spaced_code_fence(segment))
        elif protected:
            parts.append(segment)
        else:
            parts.append(_collapse_dot_spaces_in_segment(segment))
    merged = "".join(parts)
    return _collapse_dot_spaced_inline_code(merged)


def repair_dot_spaced_urls_and_hosts(text: str) -> str:
    """Fix model output like ``status. claude. com`` → ``status.claude.com``."""
    if not text or ". " not in text:
        return text

    out = []
    last = 0
    for m in _HTTP_URL_RE.finditer(text):
        out.append(text[last : m.start()])
        out.append(_collapse_dot_spaces_in_segment(m.group(0)))
        last = m.end()
    out.append(text[last:])
    text = "".join(out)

    text = re.sub(
        r"\]\((https?://[^)]+)\)",
        lambda m: "](" + _collapse_dot_spaces_in_segment(m.group(1)) + ")",
        text,
        flags=re.IGNORECASE,
    )

    text = _BARE_HOST_RE.sub(
        lambda m: _collapse_dot_spaces_in_segment(m.group(0)),
        text,
    )

    def _fix_label(m):
        label = m.group(1)
        if " " not in label or ". " not in label:
            return m.group(0)
        collapsed = _collapse_dot_spaces_in_segment(label)
        if collapsed.count(".") < 1:
            return m.group(0)
        return collapsed

    text = re.sub(
        r"\b([a-z][\w-]*(?:\.\s+[\w-]+)+)\b",
        _fix_label,
        text,
        flags=re.IGNORECASE,
    )
    return collapse_dot_spaced_literals(text)


def split_inline_source_citations(text: str) -> str:
    if not text or "（[" not in text:
        return text

    def _split_segment(segment: str) -> str:
        if not segment or "（[" not in segment:
            return segment
        segment = re.sub(r"）\s*（(?=\[[^\]]+\]\()", "）\n（", segment)
        segment = re.sub(
            r"([。．!?！？:：])\s*（(?=\[[^\]]+\]\()",
            r"\1\n（",
            segment,
        )
        segment = re.sub(
            r"([^\n\s])\s+（(?=\[[^\]]+\]\()",
            r"\1\n（",
            segment,
        )
        return segment

    parts = []
    for start, end, protected in _iter_fence_spans(text):
        segment = text[start:end]
        parts.append(segment if protected else _split_segment(segment))
    return "".join(parts)


def improve_readability(text: str) -> str:
    text = (text or "").strip()
    if not text or len(text) < 72:
        return text
    if _READABILITY_SKIP.search(text):
        return text

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = split_inline_source_citations(text)

    def _break_sentences(chunk: str) -> str:
        return re.sub(
            r"。(\s*)(?=[\u4e00-\u9fff\u300c\u3010【「]|20\d{2}年|[A-Za-z])",
            "。\n\n",
            chunk,
        )

    if "\n\n" in text:
        parts = re.split(r"(\n\n)", text)
        text = "".join(
            p if p == "\n\n" else _break_sentences(p) for p in parts
        )
    else:
        text = _break_sentences(text)

    if text.count("\n\n") < 1 and len(text) > 180:
        text = re.sub(
            r"。(\s*)(?=\S)",
            "。\n\n",
            text,
        )

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip()


def sanitize_assistant_text(text: str) -> str:
    if not text:
        return ""
    text = _THINK_BLOCK.sub("", text)
    text = _strip_dsml_markup(text)
    m = _DSML_START.search(text)
    if m:
        text = text[: m.start()]
    text = _strip_meta_intent(text)
    text = _strip_tool_planning(text)
    if is_tool_planning_content(text):
        return ""
    text = improve_readability(text.strip())
    return repair_dot_spaced_urls_and_hosts(text)


def sanitize_stream_buffer(text: str) -> tuple[str, bool]:
    """Return (safe_visible_text, frozen_after_dsml)."""
    if not text:
        return "", False

    work = _THINK_BLOCK.sub("", text)
    work = _strip_dsml_markup(work)
    m = _DSML_START.search(work)
    if m:
        return _strip_meta_intent(work[: m.start()]).rstrip(), True

    m2 = _PARTIAL_MARKUP.search(work)
    if m2:
        visible = _strip_meta_intent(work[: m2.start()]).rstrip()
    else:
        visible = _strip_meta_intent(work).rstrip()
    visible = _strip_tool_planning(visible)
    if is_tool_planning_content(visible):
        return "", False
    return collapse_dot_spaced_literals(visible), False


class StreamSanitizer:
    def __init__(self) -> None:
        self._buffer = ""
        self._emitted_text = ""
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def feed(self, piece: str) -> str:
        if self._frozen or not piece:
            return ""
        self._buffer += piece
        visible, frozen = sanitize_stream_buffer(self._buffer)
        if frozen:
            self._frozen = True
        delta = self._delta_from_visible(visible)
        if delta:
            self._emitted_text += delta
        return delta

    def _delta_from_visible(self, visible: str) -> str:
        if not visible:
            return ""
        if visible.startswith(self._emitted_text):
            return visible[len(self._emitted_text) :]
        if self._emitted_text.startswith(visible):
            return ""
        return ""

    def finalize(self) -> str:
        if self._frozen:
            return ""
        clean = sanitize_assistant_text(self._buffer)
        delta = self._delta_from_visible(clean)
        if delta:
            self._emitted_text += delta
        return delta
