import os
import re

_DEFAULT_EXTRACT_MAX = int(os.getenv("SEARCH_FETCH_EXTRACT_MAX_CHARS", "28000"))
_DEFAULT_RAW_MAX = int(os.getenv("SEARCH_FETCH_RAW_TEXT_CHARS", "80000"))

_BOILERPLATE_LINE = re.compile(
    r"cookie|クッキー|プライバシー|privacy|subscribe|newsletter|"
    r"sign\s*up|ログイン|login|follow\s+us|share\s+on|sns|広告|advertisement|"
    r"skip\s+to|breadcrumb|関連記事|人気記事|recommended\s+articles|"
    r"copyright|all\s+rights\s+reserved|©|お問い合わせ|contact\s+us|"
    r"accept\s+all|同意する|拒否|opt[\s-]?out",
    re.IGNORECASE,
)

_HEADING_LINE = re.compile(
    r"^(#{1,6}\s+|[\u25a0\u25a1\u25b2\u25b3\u25c6\u25c7]|\d+\.\s+[A-Z\u4e00-\u9fff])",
)
_LIST_LINE = re.compile(
    r"^\s*(?:[-•*●○◦▪►▸]\s+|\d+[.)]\s+|[一二三四五六七八九十百千万]+[、.．]\s*)",
)
_TABLE_LINE = re.compile(r"\|.+\|")
_CONFIG_HINT = re.compile(
    r"\.(yml|yaml|properties|json|toml|conf|cfg)\b|"
    r"^[a-zA-Z_][\w.-]*\s*[:=]\s*\S",
    re.MULTILINE,
)
_CODE_FENCE = re.compile(r"```|^ {4}\S", re.MULTILINE)
_DATA_HINT = re.compile(
    r"\d+\.\d+\.\d+|\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\b\d{2,5}\s*(ms|MB|GB|KB|TPS|fps|%)\b|"
    r"\b(true|false|null)\b",
    re.IGNORECASE,
)
_TERM_RE = re.compile(r"[\w\u3040-\u30ff\u4e00-\u9fff]{2,}", re.UNICODE)


def default_extract_max_chars():
    return _DEFAULT_EXTRACT_MAX


def default_raw_max_chars():
    return _DEFAULT_RAW_MAX


def _query_terms(*texts):
    seen = set()
    terms = []
    for raw in texts:
        if not raw:
            continue
        for m in _TERM_RE.finditer(raw.lower()):
            t = m.group(0)
            if len(t) < 2 or t in seen:
                continue
            seen.add(t)
            terms.append(t)
    return terms


def _drop_boilerplate_lines(text):
    kept = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            kept.append("")
            continue
        if len(s) < 120 and _BOILERPLATE_LINE.search(s):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _is_list_line(line):
    return bool(_LIST_LINE.match(line))


def _merge_list_runs(lines):
    blocks = []
    buf = []
    in_list = False

    def flush():
        nonlocal buf, in_list
        if not buf:
            return
        blocks.append("\n".join(buf).strip())
        buf = []
        in_list = False

    for line in lines:
        if _is_list_line(line):
            if not in_list and buf:
                flush()
            in_list = True
            buf.append(line)
        else:
            if in_list:
                flush()
            buf.append(line)
    flush()
    return [b for b in blocks if b]


def split_into_blocks(text):
    text = _drop_boilerplate_lines(text)
    if not text:
        return []

    parts = re.split(r"\n\s*\n", text)
    blocks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > 5000 and "\n" in part:
            sub_lines = part.splitlines()
            sub_blocks = _merge_list_runs(sub_lines)
            if len(sub_blocks) > 1:
                blocks.extend(sub_blocks)
                continue
        if len(part) > 9000:
            lines = part.splitlines()
            chunk = []
            size = 0
            for line in lines:
                chunk.append(line)
                size += len(line) + 1
                if size >= 3500 and (
                    _HEADING_LINE.match(line.strip())
                    or _is_list_line(line)
                    or size >= 5000
                ):
                    blocks.append("\n".join(chunk).strip())
                    chunk = []
                    size = 0
            if chunk:
                blocks.append("\n".join(chunk).strip())
        else:
            lines = part.splitlines()
            if sum(1 for ln in lines if _is_list_line(ln)) >= 3:
                blocks.extend(_merge_list_runs(lines))
            else:
                blocks.append(part)
    return [b for b in blocks if len(b.strip()) >= 24]


def _list_item_count(block):
    return sum(1 for ln in block.splitlines() if _is_list_line(ln))


def score_block(block, terms):
    if not block:
        return -100
    lower = block.lower()
    score = 0.0

    for term in terms:
        if term in lower:
            score += 6 + min(12, lower.count(term) * 2)

    list_n = _list_item_count(block)
    if list_n >= 2:
        score += 14 + min(28, list_n * 2)
    if list_n >= 8:
        score += 10

    if _TABLE_LINE.search(block):
        score += 16
    if _CONFIG_HINT.search(block):
        score += 14
    if _CODE_FENCE.search(block):
        score += 12
    if _DATA_HINT.search(block):
        score += 8

    if re.search(r"(手順|設定|インストール|install|setup|config|readme|api|version|"
                 r"要件|対応|サポート|parameter|option|default|有効|無効)",
                 block, re.I):
        score += 10

    heading_hits = sum(1 for ln in block.splitlines()[:3] if _HEADING_LINE.match(ln.strip()))
    score += heading_hits * 4

    blen = len(block)
    if blen < 50:
        score -= 8
    elif blen > 400 and score > 0:
        score += 3

    if blen > 12000 and list_n < 2:
        score -= 4

    if _BOILERPLATE_LINE.search(block[:300]):
        score -= 25

    return score


def extract_page_focus(text, user_text="", query="", max_chars=None):
    text = (text or "").strip()
    if not text:
        return ""

    max_chars = int(max_chars or _DEFAULT_EXTRACT_MAX)
    if max_chars <= 0:
        return text

    cleaned = _drop_boilerplate_lines(text)
    if len(cleaned) <= max_chars:
        return cleaned

    terms = _query_terms(user_text, query)
    blocks = split_into_blocks(cleaned)
    if not blocks:
        return cleaned[:max_chars] + "…"

    scored = [(i, b, score_block(b, terms)) for i, b in enumerate(blocks)]
    selected_idx = set()

    intro_i, intro_score = scored[0][0], scored[0][2]
    if intro_score >= -5 or len(blocks[0]) <= 1200:
        selected_idx.add(intro_i)

    for i, block, sc in scored:
        if sc >= 18 or (_list_item_count(block) >= 4 and sc >= 8):
            selected_idx.add(i)

    ranked = sorted(scored, key=lambda x: x[2], reverse=True)
    budget = max_chars
    used = sum(len(blocks[i]) + 2 for i in selected_idx)

    for i, block, sc in ranked:
        if i in selected_idx:
            continue
        if sc < 6:
            continue
        extra = len(block) + 2
        list_n = _list_item_count(block)
        cap = max_chars
        if list_n >= 3:
            cap = max(max_chars, int(max_chars * 0.55))
        if used + extra > cap:
            if sc < 14:
                continue
            room = cap - used
            if room < 400:
                continue
            trimmed = _trim_block_tail(block, room)
            if len(trimmed) < 120:
                continue
            blocks[i] = trimmed
            extra = len(trimmed) + 2
        selected_idx.add(i)
        used += extra
        if used >= max_chars * 0.98:
            break

    if not selected_idx:
        selected_idx.add(scored[0][0])
        for i, block, sc in ranked[1:4]:
            if used + len(block) > max_chars:
                break
            selected_idx.add(i)
            used += len(block)

    ordered = [blocks[i] for i in sorted(selected_idx)]
    out_parts = []
    total = 0
    prev_i = -2
    for i in sorted(selected_idx):
        block = blocks[i]
        if prev_i >= 0 and i - prev_i > 1:
            gap = "…（中略）…"
            if total + len(gap) <= max_chars:
                out_parts.append(gap)
                total += len(gap) + 1
        if total + len(block) > max_chars:
            room = max_chars - total
            if room > 200:
                block = _trim_block_tail(block, room)
            else:
                break
        out_parts.append(block)
        total += len(block) + 2
        prev_i = i
        if total >= max_chars:
            break

    out = "\n\n".join(out_parts).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out or cleaned[:max_chars] + "…"


def _trim_block_tail(block, max_len):
    if len(block) <= max_len:
        return block
    lines = block.splitlines()
    kept = []
    size = 0
    for line in lines:
        if size + len(line) + 1 > max_len and kept:
            break
        kept.append(line)
        size += len(line) + 1
    if not kept:
        return block[:max_len]
    tail = "\n".join(kept)
    if len(tail) < len(block):
        tail += "\n…"
    return tail


def prepare_page_text_for_context(
    text, user_text="", query="", max_chars=None, raw_max_chars=None
):
    text = (text or "").strip()
    if not text:
        return ""
    raw_cap = int(raw_max_chars or _DEFAULT_RAW_MAX)
    if len(text) > raw_cap:
        text = text[:raw_cap] + "…"
    return extract_page_focus(
        text, user_text=user_text, query=query, max_chars=max_chars
    )
