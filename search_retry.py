import re

_MODEL_NAME_PATTERN = re.compile(
    r"(Qwen[\w./-]*|Llama[\s-]?[\d.]+\w*|DeepSeek[\w./-]*|Mistral[\w./-]*|"
    r"Gemma[\s-]?[\d.]+\w*|Phi-[\w./-]*|GLM-[\d.]+[A-Za-z0-9_-]*|Mixtral[\w./-]*|"
    r"Command[\s-]?[\w./-]*|Yi-[\w./-]*|Grok[\w./-]*|o\d-mini|GPT-[\w./-]*)",
    re.IGNORECASE,
)

_MODEL_EXTRA_RE = re.compile(
    r"\b((?:GLM|Qwen|DeepSeek|Llama|Mistral|Gemma|Phi|Grok|GPT)"
    r"[\s.-]?\d+(?:\.\d+)?[A-Za-z0-9_-]*)(?![0-9A-Za-z.])",
    re.IGNORECASE,
)

_VENDOR_QUERY_HINTS = {
    "glm": ("zhipu", "z.ai"),
    "qwen": ("alibaba", "qwen"),
    "deepseek": ("deepseek",),
    "llama": ("meta", "llama"),
    "gemma": ("google", "gemma"),
    "grok": ("xai", "grok"),
}

_PRODUCT_LOOKUP_RE = re.compile(
    r"調べて|検索|について|リリース|最新|とは何|とは\?|what\s+is|release|announce|"
    r"モデル|model|benchmark|性能|スペック|特徴",
    re.IGNORECASE,
)


def _normalize_term_key(term):
    return re.sub(r"[\s._-]+", "", (term or "").lower())


def extract_search_focus_terms(user_text):
    text = user_text or ""
    seen = set()
    terms = []

    def add(term):
        key = _normalize_term_key(term)
        if not key or len(key) < 3 or key in seen:
            return
        seen.add(key)
        terms.append(term.strip())

    for m in _MODEL_NAME_PATTERN.finditer(text):
        add(m.group(1))
    for m in _MODEL_EXTRA_RE.finditer(text):
        add(m.group(1))

    return terms


def wants_named_product_search(user_text):
    terms = extract_search_focus_terms(user_text)
    if not terms:
        return False
    if _PRODUCT_LOOKUP_RE.search(user_text or ""):
        return True
    if re.search(
        r"ランキング|最強|比較|versus|vs\.|chatbot arena|lmsys|leaderboard",
        user_text or "",
        re.IGNORECASE,
    ):
        return False
    return True


def _vendor_hints_for_term(term):
    key = _normalize_term_key(term)
    for prefix, hints in _VENDOR_QUERY_HINTS.items():
        if key.startswith(prefix):
            return hints
    return ()


def _term_variants(term):
    raw = (term or "").strip()
    if not raw:
        return []
    variants = [raw]
    compact = re.sub(r"\s+", "", raw)
    if compact != raw:
        variants.append(compact)
    dashed = re.sub(r"[\s.]+", "-", raw)
    if dashed not in variants:
        variants.append(dashed)
    dotted = re.sub(r"[\s-]+", ".", raw)
    if dotted not in variants:
        variants.append(dotted)
    return variants


def expand_named_entity_queries(user_text, queries):
    terms = extract_search_focus_terms(user_text)
    for q in queries or []:
        terms.extend(extract_search_focus_terms(str(q)))
    if not terms:
        return list(queries or [])

    seen_terms = set()
    unique_terms = []
    for term in terms:
        key = _normalize_term_key(term)
        if key in seen_terms:
            continue
        seen_terms.add(key)
        unique_terms.append(term)
    terms = unique_terms

    seen = set()
    out = []
    for q in queries or []:
        key = re.sub(r"\s+", " ", str(q).strip().lower())
        if key and key not in seen:
            seen.add(key)
            out.append(str(q).strip())

    for term in terms[:2]:
        for variant in _term_variants(term)[:3]:
            candidates = [
                f'"{variant}" AI model',
                f"{variant} release announcement",
            ]
            hints = _vendor_hints_for_term(term)
            if hints:
                candidates.append(f"{variant} {hints[0]}")
                if len(hints) > 1:
                    candidates.append(f"{variant} {hints[1]}")
            for q in candidates:
                key = q.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(q)
                if len(out) >= 5:
                    return out[:5]

    return out[:5]


def _results_blob(results):
    parts = []
    for item in results or []:
        parts.append(item.get("title") or "")
        parts.append(item.get("body") or "")
        parts.append(item.get("href") or "")
    return "\n".join(parts)


def results_match_focus_terms(results, user_text):
    terms = extract_search_focus_terms(user_text)
    if not terms:
        return True
    blob = _normalize_term_key(_results_blob(results))
    if not blob:
        return False
    for term in terms:
        if _normalize_term_key(term) in blob:
            return True
    return False


def search_needs_retry(results, user_text, queries=None):
    from intelligent_search_override import (
        admission_search_needs_retry,
        wants_admission_exam_search,
    )

    if wants_admission_exam_search(user_text):
        return admission_search_needs_retry(results, user_text)

    terms = extract_search_focus_terms(user_text)
    if not terms:
        if not results and _PRODUCT_LOOKUP_RE.search(user_text or ""):
            return True
        return False

    if not results:
        return True
    if not results_match_focus_terms(results, user_text):
        return True

    fetched = sum(1 for r in results if r.get("fetched_full"))
    if fetched == 0 and len(_results_blob(results)) < 1200:
        return True
    return False


def build_search_retry_queries(user_text, tried_queries):
    from intelligent_search_override import (
        build_admission_retry_queries,
        wants_admission_exam_search,
    )

    if wants_admission_exam_search(user_text):
        return build_admission_retry_queries(user_text, tried_queries)

    terms = extract_search_focus_terms(user_text)
    tried = {re.sub(r"\s+", " ", str(q).strip().lower()) for q in tried_queries or []}
    retry = []

    for term in terms[:2]:
        for variant in _term_variants(term):
            hints = _vendor_hints_for_term(term)
            candidates = [
                f"{variant} official blog",
                f"{variant} huggingface model card",
            ]
            if hints:
                candidates.insert(0, f"{variant} {hints[0]} official")
                if len(hints) > 1:
                    candidates.insert(1, f'site:{hints[1]} {variant}')
            for q in candidates:
                key = re.sub(r"\s+", " ", q.strip().lower())
                if key not in tried:
                    retry.append(q)
                    if len(retry) >= 3:
                        break
            if len(retry) >= 3:
                break

    if not retry and terms:
        retry.append(f"{terms[0]} news 2026")

    out = []
    for q in retry:
        key = re.sub(r"\s+", " ", q.strip().lower())
        if key not in tried:
            out.append(q)
    return out[:3]
