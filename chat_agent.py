import json
import re
import time
import logging
from datetime import datetime

from metrics import (
    get_metrics,
    record_chat_request,
    record_tool,
    record_step,
    record_error,
    step_timer,
    timed,
)
from feedback import assign_variant, add_user_feedback, get_feedback_summary

from model_sanitize import StreamSanitizer, sanitize_assistant_text
from token_usage import empty_usage, estimate_turn_tokens, merge_usage, usage_from_openai
from model_registry import is_deepseek_agent_profile
from web_fetch import (
    build_web_fetch_system_message,
    extract_urls_from_text,
    format_fetch_context,
    is_fetchable_url,
    stream_web_fetch,
)
from web_search import (
    augment_results_with_fetched_pages,
    plan_search_page_fetches,
    _FETCH_PAGE_EXTRACT_CHARS,
    fix_search_answer_citations,
    build_web_search_system_message,
    extract_user_text,
    filter_search_results,
    format_search_context,
    infer_search_topic,
    merge_search_result_lists,
    refine_search_queries,
    stream_web_search_for_queries,
    search_limits_for_topic,
    user_needs_multi_search,
    web_search_system_prompt_multi_append,
)
from deep_research import (
    deep_research_system_prompt_append,
    effective_max_web_search_rounds,
)
from google_agent_tools import (
    GOOGLE_TOOL_NAMES,
    build_google_tool_list,
    execute_google_tool,
    google_system_prompt_append,
)
from memory_agent_tools import (
    MEMORY_TOOL_NAMES,
    build_memory_tool_list,
    execute_memory_tool,
    memory_system_prompt_append,
)
from user_question_agent_tools import (
    ASK_USER_TOOL_NAME,
    ASK_USER_TOOL_NAMES,
    build_ask_user_tool_list,
    ask_user_system_prompt_append,
    format_ask_user_tool_result,
    parse_ask_user_tool_args,
)

# ロガー設定
logger = logging.getLogger(__name__)

MAX_MEMORY_TOOL_ROUNDS = 8
MAX_COMPUTELAB_TOOL_ROUNDS = 20
MAX_COMPUTELAB_COMPLETION_ROUNDS = 8
WEB_TOOL_NAMES = frozenset({"web_search", "web_fetch"})

# 履歴管理設定
MAX_HISTORY_TOKENS = 8000  # 履歴の最大トークン数
SUMMARY_THRESHOLD_TOKENS = 4000  # 要約を開始する閾値
MAX_RECENT_TURNS = 10  # 直近の完全なターン数

WEB_SEARCH_FINAL_ANSWER_NUDGE = (
    "【システム】Web検索は完了です。これ以上 web_search / web_fetch は呼ばず、"
    "これまでの全検索結果を統合してユーザーの質問への最終回答を日本語で書いてください。"
)

COMPUTELAB_COMPLETION_NUDGE = (
    "公開URL（http:// または https:// で始まる形式）と、ブラウザでのアクセス手順を、"
    "これまでの ComputeLab ツール結果だけに基づいて必ず提示してタスクを完了してください。"
    "「確認します」「調べます」だけで終えないでください。不足なら get_instance / list_instances / exec を実行してください。"
)
COMPUTELAB_SETUP_CONTINUE_NUDGE = (
    "【システム】ComputeLab の作業はまだ完了していません。"
    "「書き込みます」「これから〜」だけで終えず、残りの手順を computelab_write_file / "
    "computelab_exec / computelab_add_port 等で実際に実行してから完了報告してください。"
    "API が Internal Server Error のときは、コマンドを短くする・write_file でスクリプトを置いてから "
    "exec する・数秒待って再試行してください。"
)
COMPUTELAB_TOOL_REQUIRED_NUDGE = (
    "直前の応答では ComputeLab ツールを実行していません。"
    "サーバー操作・ファイル編集・デプロイの報告は、必ず computelab_list_instances → "
    "computelab_list_files / computelab_read_file → computelab_write_file（/data 配下 app/ 等）→ "
    "computelab_mkdir → computelab_exec（再起動）の順で実際にツールを呼び出してから行ってください。"
    "設置場所は /data のみ（/opt 直書き禁止）。"
    "ツール未実行で「作成しました」「デプロイ完了」と書くことは禁止です。"
)
COMPUTELAB_VERIFY_NUDGE = (
    "【システム】直前の完了報告はツール結果と一致していません（推測での報告は禁止）。"
    "computelab_get_instance と computelab_exec で実状態を確認してから報告してください。"
    "例: ls -la /data/mc/plugins; cat /data/mc/ops.json; screen -ls; ss -lntp | grep 25565"
    "IP・URL・バージョン番号はツール JSON / exec の stdout にある文字列だけを写す。"
    "確認できない項目は「未確認」と書く。"
)
from tool_trace import run_tool_calls_parallel, tool_trace_payload
from computelab_setup_verify import (
    hallucinated_setup_completion,
    setup_intent_text,
    setup_requirement_pending,
    setup_verified_complete,
    tool_evidence_blob,
)
from tasks_agent_tools import (
    TASKS_TOOL_NAMES,
    build_tasks_tool_list,
    execute_tasks_tool,
    tasks_system_prompt_append,
)
from computelab_agent_tools import (
    COMPUTELAB_TOOL_NAMES,
    build_computelab_tool_list,
    computelab_system_prompt_append,
    execute_computelab_tool,
)
from image_generation_agent_tools import (
    IMAGE_GENERATION_TOOL_NAMES,
    IMAGE_GENERATION_TOOL_REQUIRED_NUDGE,
    build_image_generation_tool_list,
    build_image_generation_followup_system,
    image_generation_system_prompt_append,
    parse_generate_image_tool_args,
    stream_image_generation_events,
    user_wants_image_generation,
)
from image_ocr import (
    build_ocr_chat_system_append,
    build_structured_document_chat_system_append,
    messages_include_ocr_context,
    messages_include_structured_document,
)
from pdf_extract import build_pdf_chat_system_append, messages_include_pdf_context

MARKDOWN_FORMAT_APPEND = """
書式（Markdown / GFM。チャット画面でそのままレンダリングされます）:
- 見出し: `#`〜`######` の後に半角スペース1つ。見出し行の前には空行を入れる
- 段落: 段落の間は空行。同一段落内の改行は行末に半角スペース2つ
- 箇条書き: 行頭に `- ` / `* ` / `+ ` または `1. `（直前の行との間に空行を入れる）
- ネスト: 子項目は行頭に半角スペース4つ（または Tab）
- タスクリスト: `- [ ] 未完了` / `- [x] 完了`
- 引用: 行頭に `> `
- コード: `` `インライン` `` または ` ``` ` フェンス。フェンスの前後には空行を入れる
- 強調: `**太字**`、`*斜体*`、`~~打消し~~`。`**` と `*` の内側にスペースを入れない
- リンク: `[表示文字](URL)`、画像: `![代替](URL)`
- 表: `| 列 | 列 |` と区切り行 `| --- | --- |`。表の前後には空行を入れる
- 水平線: 単独行に `---` または `***`。前後に空行を入れる
- 数式（LaTeX）:
  - インライン: `$E = mc^2$`（`$` で囲む）
  - ブロック: `$$` で始めて次の行から式を書き `$$` で閉じる。前後に空行を入れる
- 図（Mermaid）: ` ```mermaid ` でフローチャートやシーケンス図を描ける
  - 例:
    ```mermaid
    flowchart TD
        A[開始] --> B{判断}
        B -->|Yes| C[実行]
        B -->|No| D[終了]
    ```

【重要】レンダリングを壊さないためのルール（ストリーミング対策）:
- `**太字**`、`*斜体*`、`[リンク](URL)`、`![画像](URL)` の途中で絶対に改行しない
- 1つの `**〜**` や `[〜](〜)` は必ず1行に収める
- コードフェンス ` ``` ` は単独行に書き、前後に空行を入れる
- 表の前後には必ず空行を入れる。区切り行 `| --- |` を忘れない
- リスト項目の `- ` や `1. ` の前に空行がないと別の段落扱いになるので注意
- `**` の内側にスペースを入れると太字にならない: `** 太字 **` はNG、`**太字**` が正しい
- `. `（ドットスペース）で終わる日本語文の直後に箇条書きを続けない。間に空行を入れる
"""

AGENT_SYSTEM_PROMPT = """あなたは NEXGATE AI のアシスタントです。日本語で回答してください。

文体:
- 1段落は1〜3文まで。段落の間は必ず空行を入れ、横に長い塊文にしない
- 複数の要点は Markdown の箇条書き（`- `）や見出し（`##`）で整理する
- 出典や補足リンクは詰め込まず、本文の後に改行してから付ける

簡単な挨拶・雑談・感謝だけのメッセージでは、検索や長い内部推論は不要です。すぐ自然に返答してください。

## ツール使用ルール
- ツールは各ツール定義の description に従って必要なときだけ呼び出す
- ツールを呼ぶ前の本文は1文まで。長い前置き・[1][2]形式・DSML/XML記法は禁止
- ツールの出力形式は各ツールの説明に記載されている。結果を受け取ったらそれに従って回答する
- 定義されていないツール名（web_open 等）は存在しない。指定のツールのみ使用すること
- 「URLを開けない」「ページを確認できない」とは言わない。web_fetch で取得できる""" + MARKDOWN_FORMAT_APPEND

AGENT_SYSTEM_PROMPT_NO_SEARCH = """あなたは NEXGATE AI のアシスタントです。日本語で回答してください。

文体:
- 短い段落と Markdown 箇条書き（`- `）で要点を整理する

Web検索や外部ツールは利用できません。学習データと推論のみで回答してください。

**禁止**
- Web検索・ツール呼び出しの宣言や実行
- DSML や XML 風の tool_calls 記法を本文に出力すること""" + MARKDOWN_FORMAT_APPEND

AGENT_SYSTEM_PROMPT_STANDARD = """あなたは NEXGATE AI のアシスタントです。日本語で、読みやすく自然な文章で回答してください。

文体:
- 短い段落と Markdown 箇条書き（`- `）で要点を整理する（段落の間は空行）
- 1文に出典リンクを2つ以上並べない
- 出典は Markdown リンク（https://...）で書く。番号だけの [1][2] 脚注は使わない
- ニュース・最新情報では各項目に出典URLを付け、末尾に「### 参考リンク」を付ける

簡単な挨拶・雑談・感謝だけのメッセージでは、検索や長い内部推論は不要です。すぐ自然に返答してください。

## ツール使用ルール
- ツールは各ツール定義の description に従って必要なときだけ呼び出す
- ツールを呼ぶ前の本文は1文まで。長い前置き・[1][2]形式・DSML/XML記法は禁止
- ツールの出力形式は各ツールの説明に記載されている。結果を受け取ったらそれに従って回答する
- 定義されていないツール名は存在しない。指定のツールのみ使用すること
- 「URLを開けない」とは言わない。web_fetch で取得できる""" + MARKDOWN_FORMAT_APPEND

AGENT_SYSTEM_PROMPT_NO_SEARCH_STANDARD = """あなたは NEXGATE AI のアシスタントです。日本語で、読みやすく自然な文章で回答してください。

文体:
- 短い段落と Markdown 箇条書き（`- `）で要点を整理する
- 番号脚注や長い出典リストは使わない

Web検索や外部ツールは利用できません。学習データと推論のみで回答してください。

**禁止**
- Web検索・ツール呼び出しの宣言や実行
- DSML や XML 風の tool_calls 記法を本文に出力すること""" + MARKDOWN_FORMAT_APPEND

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "【Web検索】最新情報をWeb検索する。"
            "使う: 現在の役職者・内閣・政権、直近のニュース・株価・為替・天気、"
            "製品の最新価格・発売情報、学習データだけでは不確実な事実。"
            "使わない: 安定した一般知識、数学、プログラミングの説明、創作、翻訳、挨拶。"
            "【出力】{results: [{title, url, snippet, date?}], query}。"
            "出典は Markdownリンク([表示文字](URL))で記載。不足なら再検索可(最大3回)。"
            " (Web search; use for time-sensitive facts. Output: list of {title,url,snippet,date} per query.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "ユーザー向け：なぜ検索するか、何を調べるか",
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "検索クエリ 1〜3件。英語・日本語の具体的な語。LLMランキングなら Chatbot Arena LLM leaderboard Elo 等",
                    "minItems": 1,
                    "maxItems": 3,
                },
            },
            "required": ["reason", "queries"],
        },
    },
}

WEB_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "【Webページ取得】指定URLのWebページ本文を取得して読む。"
            "使う: ユーザーがURLを貼った質問、検索スニペットでは不足する公式ドキュメントの詳細確認。"
            "使わない: URLが提示されていない質問、一般知識で回答できる内容。"
            "【出力】{url, text(ページ本文), title?}。本文を根拠に回答。取得失敗時は正直に伝える。"
            " (Fetch web page by URL. Output: {url, text, title}. Use only when user provides URL.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "取得するURL（http または https）",
                },
                "reason": {
                    "type": "string",
                    "description": "ユーザー向け：なぜこのページを取得するか",
                },
            },
            "required": ["url"],
        },
    },
}

AGENT_TOOL_NAMES = ("web_search", "web_fetch")

REASONING_ENGLISH_SYSTEM_APPEND = (
    "\n\n【推論言語】内部推論（思考）フェーズでは英語で考えてください。"
    "ユーザーへの最終回答は、これまでどおりユーザーの言語（通常は日本語）で行ってください。"
)


def _agent_has_integration_tools(
    *,
    google_calendar_enabled=False,
    google_gmail_enabled=False,
    tasks_enabled=False,
    memory_enabled=False,
    computelab_enabled=False,
    image_generation_enabled=False,
):
    return bool(
        google_calendar_enabled
        or google_gmail_enabled
        or tasks_enabled
        or memory_enabled
        or computelab_enabled
        or image_generation_enabled
    )


def filter_tool_calls_for_web_access(tool_calls, allow_web_search, allow_image_generation=True):
    blocked = set()
    if not allow_web_search:
        blocked |= WEB_TOOL_NAMES
    if not allow_image_generation:
        blocked |= IMAGE_GENERATION_TOOL_NAMES
    if not blocked:
        return tool_calls
    return [
        tc
        for tc in tool_calls
        if tc.get("function", {}).get("name") not in blocked
    ]


def agent_system_message(
    allow_web_search=True,
    agent_profile="deepseek",
    google_calendar_enabled=False,
    google_gmail_enabled=False,
    tasks_enabled=False,
    memory_enabled=False,
    memory_username=None,
    computelab_enabled=False,
    image_generation_enabled=False,
    user_questions_enabled=False,
    cost_performance_maximized=False,
    expression_extension_enabled=False,
    user_text="",
    deep_research_enabled=False,
    deep_research_prefs=None,
    intelligent_search_override_enabled=False,
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    has_integrations = _agent_has_integration_tools(
        google_calendar_enabled=google_calendar_enabled,
        google_gmail_enabled=google_gmail_enabled,
        tasks_enabled=tasks_enabled,
        memory_enabled=memory_enabled,
        computelab_enabled=computelab_enabled,
        image_generation_enabled=image_generation_enabled,
    )
    use_search_prompt = allow_web_search or has_integrations
    if is_deepseek_agent_profile(agent_profile):
        base = AGENT_SYSTEM_PROMPT if use_search_prompt else AGENT_SYSTEM_PROMPT_NO_SEARCH
    else:
        base = (
            AGENT_SYSTEM_PROMPT_STANDARD
            if use_search_prompt
            else AGENT_SYSTEM_PROMPT_NO_SEARCH_STANDARD
        )
    if not allow_web_search and has_integrations:
        base += (
            "\n\n【制限】web_search と web_fetch は無効です。"
            "Google・TASKS・メモリ・ComputeLab など、下記の連携ツールのみ使用してください。"
        )
    base += google_system_prompt_append(google_calendar_enabled, google_gmail_enabled)
    if tasks_enabled:
        base += tasks_system_prompt_append()
    if memory_enabled:
        base += memory_system_prompt_append(
            memory_username if memory_username else None
        )
    if computelab_enabled:
        base += computelab_system_prompt_append()
        base += (
            "\n\n【ComputeLab 優先】\n"
            "ユーザーが ComputeLab / computelab での作業を依頼しているとき、"
            "外部VPSの調査に流れず computelab_catalog から着手する。"
            "web_search は Paper・Via 等のバージョン情報に限定する。"
            "詳細は docs/COMPUTELAB.md（リポジトリ内）を参照。\n"
        )
    if image_generation_enabled:
        base += image_generation_system_prompt_append()
    if user_questions_enabled:
        base += ask_user_system_prompt_append()
    if cost_performance_maximized:
        from cost_performance import cost_performance_system_prompt_append

        base += cost_performance_system_prompt_append()
    if expression_extension_enabled:
        from expression_extension import expression_extension_system_prompt_append

        base += expression_extension_system_prompt_append()
    if intelligent_search_override_enabled and allow_web_search:
        from intelligent_search_override import intelligent_search_override_system_prompt_append

        base += intelligent_search_override_system_prompt_append()
    if allow_web_search and (
        deep_research_enabled
        or user_needs_multi_search(user_text, computelab_enabled)
        or computelab_enabled
    ):
        base += web_search_system_prompt_multi_append()
    if deep_research_enabled:
        prefs = deep_research_prefs if isinstance(deep_research_prefs, dict) else {}
        rounds = int(prefs.get("max_search_rounds", 5))
        base += deep_research_system_prompt_append(rounds)
    return f"{base}\n\n現在日時（サーバー）: {now}"


def strip_reasoning_content_from_messages(messages, provider_id=None):
    from model_registry import provider_supports_reasoning_content

    if provider_supports_reasoning_content(provider_id):
        return messages
    stripped = []
    for m in messages:
        if m.get("role") == "assistant" and "reasoning_content" in m:
            stripped.append({k: v for k, v in m.items() if k != "reasoning_content"})
        else:
            stripped.append(m)
    return stripped


def apply_reasoning_english_to_messages(messages, reasoning_in_english=False):
    if not reasoning_in_english:
        return messages
    out = list(messages)
    for i, m in enumerate(out):
        if m.get("role") == "system":
            out[i] = {
                **m,
                "content": (m.get("content") or "") + REASONING_ENGLISH_SYSTEM_APPEND,
            }
            return out
    out.insert(0, {"role": "system", "content": REASONING_ENGLISH_SYSTEM_APPEND.strip()})
    return out


def _estimate_message_tokens(messages):
    """メッセージリストの概算トークン数を計算"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4  # 概算: 4文字 = 1トークン
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(part.get("text", "")) // 4
    return total


def _summarize_old_turns(messages, max_tokens=MAX_HISTORY_TOKENS):
    """古いターンを要約してトークン数を削減

    注意: ツール会話（tool ロールや tool_calls を含む assistant）が混在する場合は
    要約を行わない。要約すると OpenAI のメッセージ形式（tool は直前の
    assistant tool_calls と対になる）が壊れ、API 呼び出しが失敗するため。
    """
    if not messages or len(messages) < 4:
        return messages

    # ツール会話が含まれる場合は要約しない（形式を壊さないため）
    for m in messages:
        role = m.get("role")
        if role == "tool":
            return messages
        if role == "assistant" and m.get("tool_calls"):
            return messages

    total_tokens = _estimate_message_tokens(messages)
    if total_tokens <= max_tokens:
        return messages

    # システムメッセージは先頭のみに集約
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    # ターン境界を意識して直近のユーザーターンを保持
    # （1ターン = user で始まり、次に user が来るまで）
    user_indices = [i for i, m in enumerate(other_msgs) if m.get("role") == "user"]
    if len(user_indices) <= MAX_RECENT_TURNS:
        return messages

    keep_from = user_indices[-MAX_RECENT_TURNS]
    recent = other_msgs[keep_from:]
    old = other_msgs[:keep_from]

    if not old:
        return messages

    # 古いターンを要約（user/assistant の本文のみ抽出）
    old_lines = []
    for m in old:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        text = str(content)[:200].strip()
        if text:
            label = "ユーザー" if role == "user" else "AI"
            old_lines.append(f"{label}: {text}")

    if not old_lines:
        return messages

    summary = {
        "role": "system",
        "content": (
            "【過去の会話要約】\n"
            + "\n".join(old_lines)[:1200]
            + "\n（以降の回答ではこの要約を文脈として参照してください）"
        ),
    }

    # 要約は必ず先頭のシステムメッセージ群に追加し、本文の途中には挿入しない
    return system_msgs + [summary] + recent


def prepare_agent_messages(
    prepared,
    allow_web_search=True,
    provider_id=None,
    agent_profile="deepseek",
    location_hint=None,
    google_calendar_enabled=False,
    google_gmail_enabled=False,
    tasks_enabled=False,
    memory_enabled=False,
    memory_username=None,
    computelab_enabled=False,
    image_generation_enabled=False,
    user_questions_enabled=False,
    cost_performance_maximized=False,
    expression_extension_enabled=False,
    reasoning_in_english=False,
    deep_research_enabled=False,
    deep_research_prefs=None,
    intelligent_search_override_enabled=False,
    custom_agent=None,
):
    # 履歴を要約してトークン数を削減
    prepared = _summarize_old_turns(prepared)
    
    user_text = extract_user_text(prepared)
    system_content = agent_system_message(
        allow_web_search,
        agent_profile=agent_profile,
        google_calendar_enabled=google_calendar_enabled,
        google_gmail_enabled=google_gmail_enabled,
        tasks_enabled=tasks_enabled,
        memory_enabled=memory_enabled,
        memory_username=memory_username,
        computelab_enabled=computelab_enabled,
        image_generation_enabled=image_generation_enabled,
        user_questions_enabled=user_questions_enabled,
        cost_performance_maximized=cost_performance_maximized,
        expression_extension_enabled=expression_extension_enabled,
        user_text=user_text,
        deep_research_enabled=deep_research_enabled,
        deep_research_prefs=deep_research_prefs,
        intelligent_search_override_enabled=intelligent_search_override_enabled,
    )
    if location_hint:
        system_content += (
            f"\n\nユーザーのおおよその位置: {location_hint}"
            "（市区町村レベル。正確な住所は不明）"
        )
    if allow_web_search:
        urls = extract_urls_from_text(extract_user_text(prepared))
        if urls:
            lines = "\n".join(f"- {u}" for u in urls)
            system_content += (
                "\n\n【ユーザー指定URL】内容を答えるには web_fetch で取得する:\n"
                f"{lines}"
            )
    if messages_include_structured_document(prepared):
        system_content += build_structured_document_chat_system_append()
    elif messages_include_ocr_context(prepared):
        system_content += build_ocr_chat_system_append(prepared)
    if messages_include_pdf_context(prepared):
        system_content += build_pdf_chat_system_append()
    if custom_agent:
        from custom_agents_storage import build_custom_agent_system_append

        system_content += build_custom_agent_system_append(custom_agent)
    msgs = [
        {"role": "system", "content": system_content},
        *prepared,
    ]
    msgs = strip_reasoning_content_from_messages(msgs, provider_id)
    return apply_reasoning_english_to_messages(msgs, reasoning_in_english)


def parse_web_search_tool_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    reason = (data.get("reason") or "").strip()
    queries = data.get("queries") or []
    if isinstance(queries, str):
        queries = [queries]
    queries = [str(q).strip() for q in queries if str(q).strip()][:3]
    if not queries:
        return None
    return {"reason": reason, "queries": queries}


def parse_web_fetch_tool_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    url = (data.get("url") or "").strip()
    if not url or not is_fetchable_url(url):
        return None
    return {"url": url, "reason": (data.get("reason") or "").strip()}


_TOOL_URGENCY_RE = re.compile(
    # URL
    r"https?://[^\s]{4,}"
    # Time-sensitive with specific context
    r"|今日の(?:天気|気温|株価|為替|ニュース|予定)"
    r"|現在の(?:総理|大統領|首相|CEO|株価|為替|バージョン)"
    r"|最新の(?:ニュース|情報|バージョン|価格|リリース|アップデート)"
    r"|直近の(?:ニュース|情報|出来事|メール|投稿)"
    # Product/model number (e.g., RTL8127, RX7800XT, iPhone15, NB-RT-8127F)
    r"|[A-Z]{2,}[ -]?[A-Z]?[0-9]{2,}[A-Za-z]?"
    # Explicit search verbs
    r"|(?:調べて|検索して|探して|調査して|ググって)"
    # Technical/spec terms that imply lookup
    r"|(?:スペック|仕様|性能|ベンチマーク|RSS|マルチキュー|オフロード|データシート)"
    r"|(?:対応状況|サポート状況|設定方法|インストール方法)"
    # English
    r"|(?:what is|who is|how to|tell me about|look up|search for|find out about)",
    re.IGNORECASE,
)


def _detect_tool_urgency(user_text, allow_web_search=True):
    """ユーザークエリが明らかにWeb検索/フェッチを必要とするか判定。
    Trueの場合、初回モデル呼出で tool_choice="required" を使用する。"""
    if not allow_web_search:
        return False
    text = (user_text or "").strip()
    if not text or len(text) < 6:
        return False
    if _TOOL_URGENCY_RE.search(text):
        return True
    return False


def thinking_mode_active(disable_reasoning=False, provider_id=None):
    if disable_reasoning:
        return False
    from model_registry import provider_supports_thinking

    return provider_supports_thinking(provider_id)


def effective_disable_reasoning_for_tools(
    disable_reasoning=False, *, tools=None, provider_id=None
):
    if disable_reasoning:
        return True
    if tools and thinking_mode_active(False, provider_id):
        return True
    return False


def apply_disable_reasoning_kwargs(kwargs, disable_reasoning=False, provider_id=None):
    if not disable_reasoning:
        return kwargs
    from model_registry import provider_supports_thinking

    if not provider_supports_thinking(provider_id):
        return kwargs
    extra = dict(kwargs.get("extra_body") or {})
    extra["thinking"] = {"type": "disabled"}
    kwargs["extra_body"] = extra
    return kwargs


def _apply_model_completion_kwargs(kwargs, disable_reasoning=False, provider_id=None):
    apply_disable_reasoning_kwargs(kwargs, disable_reasoning, provider_id)
    from cost_performance import apply_cost_performance_kwargs

    apply_cost_performance_kwargs(kwargs, disable_reasoning, provider_id)
    return kwargs


def apply_tool_choice_kwargs(
    kwargs,
    *,
    tools=None,
    tool_choice=None,
    disable_reasoning=False,
    provider_id=None,
):
    """DeepSeek 等の Thinking モードでは tool_choice と併用できないため、ツール利用時は推論をオフにする。"""
    effective_disable = effective_disable_reasoning_for_tools(
        disable_reasoning, tools=tools, provider_id=provider_id
    )
    if tools:
        kwargs["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    elif tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    else:
        kwargs["tool_choice"] = "none"
    return effective_disable


def apply_stream_usage_kwargs(kwargs, provider_id=None):
    from model_registry import provider_supports_stream_usage

    if provider_supports_stream_usage(provider_id):
        kwargs["stream_options"] = {"include_usage": True}
    return kwargs


def format_chat_provider_error(exc, provider_id=None):
    text = str(exc).strip()
    lower = text.lower()
    if not text:
        return "チャット処理中に不明なエラーが発生しました。再試行してください。"

    context_signals = (
        "context length",
        "maximum context",
        "max context",
        "too many tokens",
        "token limit",
        "prompt is too long",
        "request too large",
        "入力が長すぎ",
        "コンテキスト",
    )
    if any(sig in lower for sig in context_signals):
        return (
            "入力（会話履歴・添付PDF/OCRテキストなど）が長すぎる可能性があります。"
            "新しいチャットを始めるか、添付を減らして再試行してください。"
        )

    if (
        "error code: 500" in lower
        or "internal server error" in lower
        or "internal_error" in lower
        or "'type': 'internal_error'" in lower
    ):
        from model_registry import PROVIDERS

        meta = PROVIDERS.get((provider_id or "").strip()) or {}
        label = (meta.get("label") or provider_id or "AI").strip()
        return (
            f"{label} 側で一時的なエラー（500）が発生しました。"
            "しばらく待って再試行するか、別のモデルをお試しください。"
        )

    if "error code: 429" in lower or "rate limit" in lower or "too many requests" in lower:
        return "リクエストが集中しています。しばらく待ってから再試行してください。"

    if (
        "error code: 401" in lower
        or "error code: 403" in lower
        or "invalid api key" in lower
        or "incorrect api key" in lower
        or "authentication" in lower
    ):
        return "APIキーが無効です。管理者に連絡してください。"

    if "thinking mode" in lower and "tool_choice" in lower:
        return (
            "推論（Thinking）モードとツール指定の組み合わせに問題がありました。"
            " 設定で推論をオフにするか、しばらくして再試行してください。"
        )

    if len(text) > 240:
        return text[:240] + "…"
    return text


def openai_tool_calls_list(tool_calls_map, allowed_names=None):
    allowed = set(allowed_names or AGENT_TOOL_NAMES)
    calls = []
    for idx in sorted(tool_calls_map.keys()):
        entry = tool_calls_map[idx]
        name = entry.get("name")
        if name not in allowed:
            continue
        calls.append(
            {
                "id": entry.get("id") or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": entry.get("arguments") or "{}",
                },
            }
        )
    return calls


def _extract_tool_calls(round_data, provider_id=None, allowed_names=None):
    return openai_tool_calls_list(round_data.get("tool_calls_map") or {}, allowed_names)


def _sse_fetch_event(event):
    public = {k: v for k, v in event.items() if not str(k).startswith("_")}
    return {"fetch": public}


def _apply_sampling_kwargs(kwargs, sampling):
    """OpenAI互換APIからのサンプリングパラメータを上流リクエストに適用"""
    if not sampling or not isinstance(sampling, dict):
        return
    mapping = {
        "temperature": "temperature",
        "top_p": "top_p",
        "max_tokens": "max_tokens",
        "max_completion_tokens": "max_completion_tokens",
        "presence_penalty": "presence_penalty",
        "frequency_penalty": "frequency_penalty",
        "seed": "seed",
        "stop": "stop",
        "user": "user",
    }
    for src, dst in mapping.items():
        val = sampling.get(src)
        if val is not None:
            kwargs[dst] = val
    if sampling.get("response_format"):
        try:
            kwargs["response_format"] = sampling["response_format"]
        except Exception:
            pass
    if sampling.get("stream_options"):
        try:
            kwargs["stream_options"] = sampling["stream_options"]
        except Exception:
            pass

    # 推論制御（TTFB 最適化）
    #   thinking: {budget_tokens: N} 指定 -> そのまま extra_body へ
    #   reasoning_effort: low/minimal/medium/high -> thinking budget にマッピング
    #   ※ thinking=false の場合は disable_reasoning 経由で
    #      apply_disable_reasoning_kwargs が "disabled" で上書きする
    thinking = sampling.get("thinking")
    reasoning_effort = sampling.get("reasoning_effort")
    if isinstance(thinking, dict):
        extra = dict(kwargs.get("extra_body") or {})
        extra["thinking"] = thinking
        kwargs["extra_body"] = extra
    elif reasoning_effort in ("low", "minimal", "medium", "high"):
        budget = {
            "minimal": 128,
            "low": 256,
            "medium": 2048,
            "high": 8192,
        }.get(reasoning_effort, 2048)
        extra = dict(kwargs.get("extra_body") or {})
        extra["thinking"] = {"type": "enabled", "budget_tokens": budget}
        kwargs["extra_body"] = extra


def stream_model_round(
    client,
    model,
    messages,
    tools=None,
    disable_reasoning=False,
    provider_id=None,
    tool_choice=None,
    sampling=None,
):
    kwargs = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    _apply_sampling_kwargs(kwargs, sampling)
    if tools:
        kwargs["tools"] = tools
        effective_disable = apply_tool_choice_kwargs(
            kwargs,
            tools=tools,
            tool_choice=tool_choice,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        )
    else:
        effective_disable = disable_reasoning
    _apply_model_completion_kwargs(kwargs, effective_disable, provider_id)
    apply_stream_usage_kwargs(kwargs, provider_id)

    stream = client.chat.completions.create(**kwargs)
    content_parts = []
    reasoning_parts = []
    tool_calls_map = {}
    sanitizer = StreamSanitizer()
    round_usage = empty_usage()

    for chunk in stream:
        if getattr(chunk, "usage", None):
            merge_usage(round_usage, usage_from_openai(chunk.usage))
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if delta:
            if not disable_reasoning:
                reasoning_piece = getattr(delta, "reasoning_content", None) or ""
                if reasoning_piece:
                    reasoning_parts.append(reasoning_piece)
                    yield ("reasoning", reasoning_piece)

            piece = getattr(delta, "content", None) or ""
            if piece:
                content_parts.append(piece)
                safe = sanitizer.feed(piece)
                if safe:
                    yield ("content", safe)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    delta_payload = {"index": idx, "type": "function"}
                    if tc.id:
                        tool_calls_map[idx]["id"] = tc.id
                        delta_payload["id"] = tc.id
                    fn = tc.function
                    if fn:
                        if fn.name:
                            tool_calls_map[idx]["name"] = fn.name
                            delta_payload["name"] = fn.name
                        if fn.arguments:
                            tool_calls_map[idx]["arguments"] += fn.arguments
                            delta_payload["arguments"] = fn.arguments
                    yield ("tool_call_delta", delta_payload)

        msg = getattr(choice, "message", None)
        if msg:
            if not disable_reasoning:
                msg_reasoning = getattr(msg, "reasoning_content", None)
                if msg_reasoning:
                    reasoning_parts = [msg_reasoning]

    tail = sanitizer.finalize()
    if tail:
        yield ("content", tail)

    yield (
        "end",
        {
            "content": sanitize_assistant_text("".join(content_parts)),
            "reasoning_content": "".join(reasoning_parts),
            "tool_calls_map": tool_calls_map,
            "sanitizer_frozen": sanitizer.frozen,
            "usage": round_usage,
        },
    )


def complete_model_round(
    client,
    model,
    messages,
    tools=None,
    disable_reasoning=False,
    provider_id=None,
    tool_choice=None,
    sampling=None,
):
    kwargs = {"model": model, "messages": messages, "stream": False}
    _apply_sampling_kwargs(kwargs, sampling)
    if tools:
        kwargs["tools"] = tools
        effective_disable = apply_tool_choice_kwargs(
            kwargs,
            tools=tools,
            tool_choice=tool_choice,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        )
    else:
        effective_disable = disable_reasoning
    _apply_model_completion_kwargs(kwargs, effective_disable, provider_id)
    response = client.chat.completions.create(**kwargs)
    msg = response.choices[0].message
    tool_calls_map = {}
    if msg.tool_calls:
        for idx, tc in enumerate(msg.tool_calls):
            tool_calls_map[idx] = {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments or "",
            }
    usage = usage_from_openai(getattr(response, "usage", None))
    return {
        "content": sanitize_assistant_text(msg.content or ""),
        "reasoning_content": getattr(msg, "reasoning_content", None) or "",
        "tool_calls_map": tool_calls_map,
        "usage": usage,
    }


def build_assistant_tool_message(round_data, tool_calls, provider_id=None):
    from model_registry import provider_supports_reasoning_content

    msg = {
        "role": "assistant",
        "content": (round_data.get("content") or "").strip() or None,
        "tool_calls": tool_calls,
    }
    if provider_supports_reasoning_content(provider_id):
        msg["reasoning_content"] = round_data.get("reasoning_content") or ""
    return msg


def append_tool_round_to_conversation(
    conversation, round_data, tool_calls, tool_contents_by_id, provider_id=None
):
    assistant_msg = build_assistant_tool_message(
        round_data, tool_calls, provider_id=provider_id
    )
    tool_messages = [
        {
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": tool_contents_by_id[tc["id"]],
        }
        for tc in tool_calls
    ]
    return strip_reasoning_content_from_messages(
        conversation + [assistant_msg, *tool_messages], provider_id
    )


REASONING_CARD_SKIP_RE = re.compile(
    r"検索の必要はない|検索は不要|検索不要|挨拶を返|普通に挨拶|"
    r"特に検索|greeting|no search needed|don't need search|"
    r"検索結果を確認|与えられた|各ソース|断言できない|確認できない|"
    r"Wikiも|Releasesページ|Tavily|スニペットだけでは|"
    r"Unknown tool|ツール一覧|定義されているはず|もう一度呼び出|"
    r"関数名が違う|なぜエラー|web_search.*使えない|IntelligentSearch|"
    r"web_searchを使|web_search を使|この情報は時期によって",
    re.IGNORECASE,
)

REASONING_SEARCH_HINTS = (
    "検索",
    "web_search",
    "web_fetch",
    "調べ",
    "調査",
    "クエリ",
    "サーチ",
    "search",
    "IntelligentSearch",
    "ページを取得",
    "URL",
)


def should_emit_reasoning_card(reasoning_text, round_data=None, emit_enabled=True):
    if not emit_enabled:
        return False
    text = (reasoning_text or "").strip()
    if not text:
        return False
    if round_data and openai_tool_calls_list(round_data.get("tool_calls_map") or {}):
        return True
    if len(text) < 56:
        return False
    if REASONING_CARD_SKIP_RE.search(text):
        return False
    if any(hint in text for hint in REASONING_SEARCH_HINTS):
        return True
    return len(text) >= 100


def _reasoning_buffer_text(state, round_data=None):
    parts = state.get("reasoning_buffer") or []
    if parts:
        return "".join(parts)
    if round_data:
        return (round_data.get("reasoning_content") or "").strip()
    rd = state.get("round_data")
    if rd:
        return (rd.get("reasoning_content") or "").strip()
    return ""


def _reasoning_unemitted_text(state, round_data=None):
    text = _reasoning_buffer_text(state, round_data)
    emitted_len = int(state.get("reasoning_emitted_len") or 0)
    if len(text) <= emitted_len:
        return ""
    return text[emitted_len:]


def _maybe_emit_reasoning_delta(state, sse_event, round_data=None):
    if state.get("reasoning_done_sent"):
        return
    text = _reasoning_buffer_text(state, round_data)
    if state.get("reasoning_card_started"):
        delta = _reasoning_unemitted_text(state, round_data)
        if delta:
            state["reasoning_emitted_len"] = len(text)
            yield sse_event({"reasoning": {"type": "delta", "text": delta}})
        return
    if should_emit_reasoning_card(
        text, round_data, state.get("emit_reasoning_cards", True)
    ):
        state["reasoning_card_started"] = True
        delta = _reasoning_unemitted_text(state, round_data)
        if delta:
            state["reasoning_emitted_len"] = len(text)
            yield sse_event({"reasoning": {"type": "delta", "text": delta}})


def _finish_reasoning_card(state, sse_event, round_data=None):
    if state.get("reasoning_done_sent"):
        return
    text = _reasoning_buffer_text(state, round_data)
    if state.get("reasoning_card_started"):
        delta = _reasoning_unemitted_text(state, round_data)
        if delta:
            state["reasoning_emitted_len"] = len(text)
            yield sse_event({"reasoning": {"type": "delta", "text": delta}})
        state["reasoning_done_sent"] = True
        yield sse_event({"reasoning": {"type": "done"}})
        return
    if should_emit_reasoning_card(
        text, round_data, state.get("emit_reasoning_cards", True)
    ):
        if text:
            yield sse_event({"reasoning": {"type": "delta", "text": text}})
        state["reasoning_done_sent"] = True
        yield sse_event({"reasoning": {"type": "done"}})
        return
    state["reasoning_done_sent"] = True


def _content_has_dsml_hallucination(text):
    t = text or ""
    if not t:
        return False
    return bool(
        re.search(
            r"DSML|｜｜invoke|function_calls\s*begin|</?\s*tool_call",
            t,
            re.IGNORECASE,
        )
    )


def _must_force_answer_recovery(round_data):
    if not round_data:
        return True
    if round_data.get("sanitizer_frozen"):
        return True
    return _content_has_dsml_hallucination(round_data.get("content") or "")


def needs_answer_recovery(round_data, user_text="", min_chars=100):
    if not round_data:
        return True
    text = (round_data.get("content") or "").strip()
    if _content_has_dsml_hallucination(text):
        return True
    if len(text) < min_chars:
        return True
    if round_data.get("sanitizer_frozen"):
        return True
    if re.search(
        r"より詳細な情報を取得します|該当ページを開いて|さらに検索します|"
        r"詳しく調べてみます|調べてみましょう",
        text,
    ):
        return True
    if re.search(
        r"検索結果(の範囲)?では|与えられた検索結果|各ソース（|Tavily要約|"
        r"断言できません|確認できません|現時点の検索結果だけでは",
        text,
    ):
        return True
    bracket_count = len(re.findall(r"\[\d+\]", text))
    if bracket_count >= 3:
        return True
    if infer_search_topic(user_text) == "news" and bracket_count >= 1:
        return True
    if bracket_count >= 1 and not re.search(r"https?://", text):
        return True
    return False


def _emit_round_events(kind, payload, sse_event, state):
    if kind == "reasoning":
        state["reasoning_streamed"] = True
        state.setdefault("reasoning_buffer", []).append(payload)
        yield from _maybe_emit_reasoning_delta(
            state, sse_event, round_data=state.get("round_data")
        )
        return
    if kind == "content":
        if not state.get("emit_content", True):
            state.setdefault("content_buffer", []).append(payload)
            return
        if state.get("reasoning_streamed") and not state.get("reasoning_done_sent"):
            yield from _finish_reasoning_card(
                state, sse_event, round_data=state.get("round_data")
            )
        yield sse_event({"content": payload})
        return
    if kind == "end":
        state["round_data"] = payload
        if payload:
            merge_usage(state["usage_out"], payload.get("usage"))
            extra = (payload.get("reasoning_content") or "").strip()
            if extra and not state.get("reasoning_buffer"):
                state["reasoning_buffer"] = [extra]
                state["reasoning_streamed"] = True
        if state.get("reasoning_streamed") and not state.get("reasoning_done_sent"):
            yield from _finish_reasoning_card(state, sse_event, round_data=payload)
        return


def stream_chat_completion(
    messages,
    api_key,
    model,
    make_client,
    sse_event,
    usage_out=None,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    reasoning_in_english=False,
    cost_performance_maximized=False,
):
    from cost_performance import cost_performance_token, reset_cost_performance_token

    cp_token = cost_performance_token(cost_performance_maximized)
    try:
        yield from _stream_chat_completion_body(
            messages=messages,
            api_key=api_key,
            model=model,
            make_client=make_client,
            sse_event=sse_event,
            usage_out=usage_out,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            reasoning_in_english=reasoning_in_english,
            cost_performance_maximized=cost_performance_maximized,
        )
    finally:
        reset_cost_performance_token(cp_token)


def _stream_chat_completion_body(
    *,
    messages,
    api_key,
    model,
    make_client,
    sse_event,
    usage_out,
    emit_reasoning_cards,
    disable_reasoning,
    provider_id,
    reasoning_in_english,
    cost_performance_maximized,
):
    usage_out = usage_out if usage_out is not None else empty_usage()
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    if isinstance(last_user, list):
        last_user = next(
            (p.get("text", "") for p in last_user if p.get("type") == "text"),
            "",
        )

    has_search = any(m.get("role") == "system" for m in messages)
    if not api_key:
        search_note = "（Web検索オン）" if has_search else ""
        demo = (
            f"デモモードです。OPENAI_API_KEY を .env に設定してください。{search_note}\n\n"
            f"あなたのメッセージ: 「{last_user}」"
        )
        for word in demo.split():
            yield sse_event({"content": word + " "})
            time.sleep(0.03)
        merge_usage(
            usage_out,
            estimate_turn_tokens(messages, demo, "", model),
        )
        yield sse_event({"done": True, "usage": usage_out})
        return

    client = make_client(api_key)
    chat_messages = apply_reasoning_english_to_messages(messages, reasoning_in_english)
    if cost_performance_maximized:
        from cost_performance import cost_performance_system_prompt_append

        append = cost_performance_system_prompt_append()
        updated = False
        for i, m in enumerate(chat_messages):
            if m.get("role") == "system":
                chat_messages[i] = {
                    **m,
                    "content": (m.get("content") or "") + append,
                }
                updated = True
                break
        if not updated:
            chat_messages.insert(0, {"role": "system", "content": append.strip()})
    kwargs = {
        "model": model,
        "messages": chat_messages,
        "stream": True,
    }
    effective_disable = apply_tool_choice_kwargs(
        kwargs,
        tools=None,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
    )
    _apply_model_completion_kwargs(kwargs, effective_disable, provider_id)
    apply_stream_usage_kwargs(kwargs, provider_id)
    stream = client.chat.completions.create(**kwargs)

    sanitizer = StreamSanitizer()
    reasoning_done_sent = False
    output_parts = []
    reasoning_parts = []
    reasoning_state = {
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "emit_reasoning_cards": emit_reasoning_cards,
    }

    for chunk in stream:
        if getattr(chunk, "usage", None):
            merge_usage(usage_out, usage_from_openai(chunk.usage))
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if not delta:
            continue
        if not disable_reasoning:
            reasoning_piece = getattr(delta, "reasoning_content", None) or ""
            if reasoning_piece:
                reasoning_parts.append(reasoning_piece)
                reasoning_state["reasoning_streamed"] = True
                reasoning_state["reasoning_buffer"].append(reasoning_piece)
                yield from _maybe_emit_reasoning_delta(reasoning_state, sse_event)

        piece = getattr(delta, "content", None) or ""
        if piece:
            if (
                not disable_reasoning
                and reasoning_state["reasoning_streamed"]
                and not reasoning_state["reasoning_done_sent"]
            ):
                yield from _finish_reasoning_card(reasoning_state, sse_event)
                reasoning_done_sent = reasoning_state["reasoning_done_sent"]
            output_parts.append(piece)
            safe = sanitizer.feed(piece)
            if safe:
                yield sse_event({"content": safe})

    tail = sanitizer.finalize()
    if tail:
        output_parts.append(tail)
        yield sse_event({"content": tail})

    if (
        not disable_reasoning
        and reasoning_state["reasoning_streamed"]
        and not reasoning_state["reasoning_done_sent"]
    ):
        yield from _finish_reasoning_card(reasoning_state, sse_event)

    if not usage_out.get("total_tokens"):
        merge_usage(
            usage_out,
            estimate_turn_tokens(
                messages,
                "".join(output_parts),
                "".join(reasoning_parts) if not disable_reasoning else "",
                model,
            ),
        )

    yield sse_event({"done": True, "usage": usage_out})


def stream_memory_tool_loop(
    client,
    model,
    messages,
    memory_username,
    initial_round_data,
    initial_tool_calls,
    sse_event,
    usage_out,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    emit_tool_trace=False,
):
    memory_tools = build_memory_tool_list()
    conversation = list(messages)
    round_data = initial_round_data
    tool_calls = initial_tool_calls
    rounds = 0

    while tool_calls and rounds < MAX_MEMORY_TOOL_ROUNDS:
        rounds += 1
        yield sse_event({"segment_end": True})
        mutation_flags = []

        def memory_runner(tc):
            context, mutated = execute_memory_tool(
                memory_username, tc["function"]["name"], tc["function"]["arguments"]
            )
            if mutated:
                mutation_flags.append(1)
            return context

        tool_contents_by_id, traces = run_tool_calls_parallel(
            tool_calls, memory_runner, max_workers=4, timeout=30
        )
        yield from _yield_tool_trace_events(sse_event, emit_tool_trace, traces)
        for _ in tool_calls:
            yield sse_event({"memory_tool_used": True})
        if mutation_flags:
            yield sse_event({"memory_updated": True})

        conversation = append_tool_round_to_conversation(
            conversation,
            round_data,
            tool_calls,
            tool_contents_by_id,
            provider_id=provider_id,
        )
        yield sse_event({"segment_start": True, "discard_previous": False})

        round_state = {
            "round_data": None,
            "reasoning_streamed": False,
            "reasoning_done_sent": False,
            "reasoning_card_started": False,
            "reasoning_emitted_len": 0,
            "reasoning_buffer": [],
            "usage_out": usage_out,
            "emit_reasoning_cards": emit_reasoning_cards,
        }
        for kind, payload in stream_model_round(
            client,
            model,
            conversation,
            memory_tools,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        ):
            yield from _emit_round_events(kind, payload, sse_event, round_state)
            if kind == "end":
                round_data = round_state["round_data"]

        if round_data is None:
            tool_calls = []
            break

        merge_usage(usage_out, round_data.get("usage") or {})
        tool_calls = openai_tool_calls_list(
            round_data["tool_calls_map"], MEMORY_TOOL_NAMES
        )

    if tool_calls:
        yield sse_event({"segment_start": True, "discard_previous": False})
        yield from _stream_followup_with_recovery(
            client,
            model,
            conversation,
            "",
            sse_event,
            usage_out,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            recovery_hint=(
                "これまでのメモリ操作結果だけを根拠に、ユーザーの質問へ日本語で答えてください。"
            ),
            allow_recovery=False,
        )


def _conversation_has_public_url(conversation):
    for msg in conversation:
        content = msg.get("content")
        if not isinstance(content, str):
            continue
        if (
            "http://" in content
            or "https://" in content
            or "suggestedPublicUrl" in content
        ):
            return True
    return False


def _user_wants_deploy_url(user_text):
    text = user_text or ""
    return any(
        key in text
        for key in ("URL", "url", "ポート", "デプロイ", "見て", "公開", "Flask", "flask")
    )


def _conversation_text_blob(conversation):
    parts = []
    for msg in conversation or []:
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content)
    return "\n".join(parts)


def _user_requests_long_computelab_setup(user_text, conversation=None):
    intent = setup_intent_text(user_text, conversation)
    if not intent.strip():
        return False
    if not (
        user_requests_computelab_operations(user_text, conversation)
        or re.search(r"computelab|マイクラ|minecraft|paper", intent, re.IGNORECASE)
    ):
        return False
    return bool(
        re.search(
            r"マイクラ|minecraft|paper|spigot|サーバー.*作|作って|セットアップ|"
            r"インストール|構築|導入|compose|docker|nginx|postgres|25565|screen|"
            r"viaversion|viabackward",
            intent,
            re.IGNORECASE,
        )
    )


def _computelab_setup_requirement_status(user_text, conversation):
    intent = setup_intent_text(user_text, conversation)
    evidence = tool_evidence_blob(conversation)
    return setup_requirement_pending(intent, evidence)


def _computelab_setup_seems_complete(user_text, conversation):
    if not _user_requests_long_computelab_setup(user_text, conversation):
        return True
    intent = setup_intent_text(user_text, conversation)
    return setup_verified_complete(intent, tool_evidence_blob(conversation))


def _last_assistant_content(conversation):
    for msg in reversed(conversation or []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return ""


def _extract_computelab_instance_id(conversation):
    blob = _conversation_text_blob(conversation)
    match = re.search(
        r"\b(clx[a-z0-9]{10,}|cmp[a-z0-9]{15,})\b", blob, re.IGNORECASE
    )
    return match.group(1) if match else None


def _build_computelab_setup_continue_nudge(user_text, conversation):
    pending = _computelab_setup_requirement_status(user_text, conversation)
    lines = [COMPUTELAB_SETUP_CONTINUE_NUDGE]
    instance_id = _extract_computelab_instance_id(conversation)
    if instance_id:
        lines.append(
            f"会話内の既存 instance_id={instance_id} を使い、"
            "computelab_get_instance → 未完了手順を exec / write_file で続行してください。"
        )
    if pending:
        lines.append("未完了の要件:")
        for item in pending:
            lines.append(f"- {item}")
    lines.append(
        "完了後、接続方法（IP/ポート/screen 再開コマンド）と実施済み手順を短くまとめてください。"
    )
    return "\n".join(lines)


def user_wants_code_explanation_only(user_text):
    text = (user_text or "").strip().lower()
    if not text:
        return False
    remote_signals = (
        "computelab",
        "インスタンス",
        "デプロイ",
        "deploy",
        "ポート開",
        "/data/",
        "リモート",
        "サーバー上",
        "サーバーに",
        "vm",
        "コンテナ",
        "公開url",
        "list_instances",
        "write_file",
    )
    if any(s in text for s in remote_signals):
        return False
    tutorial_signals = (
        "教えて",
        "教えて下さい",
        "教えてください",
        "コードを",
        "サンプル",
        "例を",
        "どう書",
        "書き方",
        "とは",
        "説明して",
        "紹介",
        "簡単な",
        "チュートリアル",
        "例示",
        "how to",
        "example",
    )
    return any(s in text for s in tutorial_signals)


def _messages_mention_computelab_work(messages):
    blob = _conversation_text_blob(messages).lower()
    if "computelab" in blob:
        return True
    if re.search(r"\b(clx[a-z0-9]{10,}|cmp[a-z0-9]{15,})\b", blob):
        return True
    if "papermc" in blob and ("instance" in blob or "computelab_" in blob):
        return True
    return False


def user_requests_computelab_operations(user_text, messages=None):
    text = (user_text or "").strip().lower()
    if not text:
        return False
    if user_wants_code_explanation_only(user_text):
        return False
    if re.search(r"継続|続き|続けて|続行|再開", text) and _messages_mention_computelab_work(
        messages
    ):
        return True
    explicit = (
        "computelab",
        "インスタンスを",
        "インスタンスの",
        "インスタンスに",
        "インスタンス上",
        "インスタンスへ",
        "vmを",
        "vmの",
        "コンテナを",
        "コンテナの",
    )
    if any(k in text for k in explicit):
        return True
    if "インスタンス" in text and any(
        v in text
        for v in ("作成", "削除", "起動", "停止", "再起動", "一覧", "確認", "見せ")
    ):
        return True
    ops = (
        "デプロイして",
        "デプロイし",
        "deploy ",
        "deployして",
        "ポート開",
        "ポートを開",
        "公開して",
        "再起動して",
        "起動して",
        "停止して",
        "削除して",
        "computelab_",
        "write_file",
        "list_instances",
        "execして",
        "/data/app",
        "リモートで",
        "サーバーに載",
        "サーバーにデ",
    )
    if any(k in text for k in ops):
        return True
    if any(k in text for k in ("配置", "アップロード", "書き込")) and any(
        k in text for k in ("インスタンス", "computelab", "/data", "リモート")
    ):
        return True
    return False


def _assistant_claims_computelab_work(content):
    text = content or ""
    if not text.strip():
        return False
    markers = (
        "デプロイしました",
        "デプロイ完了",
        "デプロイしてみ",
        "作成しました",
        "作成完了",
        "配置しました",
        "更新しました",
        "再起動しました",
        "ポート開放しました",
        "公開しました",
        "インスタンスに",
        "インスタンスへ",
        "インスタンス上に",
        "computelab_list",
        "computelab_write",
        "computelab_exec",
        "実際にデプロイ",
        "デプロイしてみます",
        "確認します",
        "既存ファイルを確認",
        "完成しました",
        "設定済み",
        "正常に動作",
        "ポート開放完了",
        "ダウンロードが完了",
        "起動しました",
    )
    return any(m in text for m in markers)


def _messages_include_search_context(conversation):
    for msg in conversation or []:
        if msg.get("role") != "tool":
            continue
        body = msg.get("content") or ""
        if "検索クエリ:" in body or "【検索ラウンド" in body:
            return True
    return False


def _format_search_tool_content(
    results, search_query, user_text, round_no, max_rounds, intelligent_search_override=False
):
    body = format_search_context(results, search_query, user_text)
    if max_rounds <= 1 and not intelligent_search_override:
        return body
    footer = (
        f"\n\n---\n"
        f"検索ラウンド {round_no}/{max_rounds} 完了。"
    )
    if intelligent_search_override:
        from intelligent_search_override import japanese_entrance_exam_nendos

        primary = japanese_entrance_exam_nendos()["primary_nendo"]
        footer += (
            " IntelligentSearchオーバーライド: 上位URL本文と関連リンクを自動取得済み。"
            "「（ページ本文）」「（関連ページ）」を最優先し、スニペットだけで判断しない。"
            f" 入試日程では {primary}年度 表記の可能性に注意。"
        )
    if round_no < max_rounds:
        footer += (
            " まだ不足があれば queries を変えて web_search を再度呼び出せます。"
            " 十分なら追加検索せず、最終回答のみを書いてください。"
        )
    else:
        footer += " これ以上 web_search は不要です。最終回答を書いてください。"
    return body + footer


def _yield_web_search_execution(
    tc,
    user_text,
    search_engines,
    sse_event,
    *,
    round_label="",
    computelab_active=False,
    emit_tool_trace=False,
    intelligent_search_override=False,
    llm_client=None,
    llm_model=None,
    provider_id=None,
):
    parsed = parse_web_search_tool_args(tc["function"]["arguments"])
    if not parsed:
        return None

    reason = parsed["reason"]
    queries = refine_search_queries(
        user_text,
        parsed["queries"],
        computelab_active=computelab_active,
        intelligent_search_override=intelligent_search_override,
    )
    if round_label:
        reason = f"{round_label} {reason}".strip()

    yield sse_event(
        {"search": {"type": "intent", "reason": reason, "queries": queries}}
    )

    search_results = []
    search_query = ", ".join(queries)
    search_started = time.perf_counter()
    for event in stream_web_search_for_queries(
        queries,
        user_text=user_text,
        search_engines=search_engines,
        computelab_active=computelab_active,
    ):
        if event["type"] == "done":
            search_results = event["results"]
            search_query = event.get("query") or search_query
        yield sse_event({"search": event})

    search_topic = infer_search_topic(user_text)
    search_limit, _ = search_limits_for_topic(search_topic)
    search_results = filter_search_results(
        search_results,
        user_text,
        limit=search_limit,
        queries=queries,
    )

    def _augment_fetched(results, active_queries):
        fetch_max, _ = plan_search_page_fetches(user_text, results)
        if intelligent_search_override:
            from intelligent_search_override import boost_search_page_fetch_plan

            fetch_max, _ = boost_search_page_fetch_plan(
                fetch_max, _FETCH_PAGE_EXTRACT_CHARS, _FETCH_PAGE_EXTRACT_CHARS
            )
        if (fetch_max > 0 or intelligent_search_override) and not computelab_active:
            return augment_results_with_fetched_pages(
                results,
                user_text=user_text,
                queries=active_queries,
                max_pages=fetch_max if fetch_max > 0 else None,
                search_override=intelligent_search_override,
                llm_client=llm_client if intelligent_search_override else None,
                llm_model=llm_model if intelligent_search_override else None,
                provider_id=provider_id if intelligent_search_override else None,
            )
        return results

    search_results = _augment_fetched(search_results, queries)

    tried_queries = list(queries)
    from intelligent_search_override import (
        admission_search_needs_retry,
        build_admission_retry_queries,
        wants_admission_exam_search,
    )
    from search_retry import build_search_retry_queries, search_needs_retry

    if (
        intelligent_search_override
        or wants_admission_exam_search(user_text)
        or search_needs_retry(search_results, user_text, queries)
    ):
        for _ in range(2):
            if not search_needs_retry(search_results, user_text, tried_queries):
                break
            if wants_admission_exam_search(user_text):
                retry_queries = build_admission_retry_queries(user_text, tried_queries)
            else:
                retry_queries = build_search_retry_queries(user_text, tried_queries)
            if not retry_queries:
                break
            tried_queries.extend(retry_queries)
            retry_results = []
            for event in stream_web_search_for_queries(
                retry_queries,
                user_text=user_text,
                search_engines=search_engines,
                computelab_active=computelab_active,
            ):
                if event["type"] == "done":
                    retry_results = event["results"]
                yield sse_event({"search": event})
            if not retry_results:
                break
            search_results = merge_search_result_lists(search_results, retry_results)
            search_results = filter_search_results(
                search_results,
                user_text,
                limit=search_limit,
                queries=tried_queries,
            )
            search_results = _augment_fetched(search_results, tried_queries)
            queries = tried_queries
            search_query = ", ".join(dict.fromkeys(tried_queries))

    search_ms = (time.perf_counter() - search_started) * 1000
    yield from _yield_tool_trace_events(
        sse_event,
        emit_tool_trace,
        [("web_search", search_ms, True, None)],
    )
    return {
        "results": search_results,
        "queries": tried_queries if tried_queries else queries,
        "search_query": search_query,
    }


def _stream_web_search_model_round(
    client,
    model,
    conversation,
    sse_event,
    usage_out,
    emit_reasoning_cards,
    disable_reasoning,
    provider_id,
    *,
    emit_content=True,
):
    web_tools = [WEB_SEARCH_TOOL, WEB_FETCH_TOOL]
    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
        "emit_content": emit_content,
    }
    for kind, payload in stream_model_round(
        client,
        model,
        conversation,
        web_tools,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)

    round_data = round_state["round_data"]
    tool_calls = openai_tool_calls_list(
        (round_data or {}).get("tool_calls_map") or {},
        allowed_names=WEB_TOOL_NAMES,
    )
    return round_data, tool_calls


def stream_web_search_tool_loop(
    client,
    model,
    messages,
    round_data,
    tool_calls,
    sse_event,
    usage_out,
    *,
    user_text,
    search_engines,
    agent_profile,
    emit_reasoning_cards,
    disable_reasoning,
    provider_id,
    computelab_active=False,
    allow_web_search=True,
    emit_tool_trace=False,
    deep_research_enabled=False,
    deep_research_prefs=None,
    intelligent_search_override=False,
):
    max_rounds = effective_max_web_search_rounds(
        user_text,
        computelab_active,
        deep_research_active=deep_research_enabled,
        deep_research_prefs=deep_research_prefs,
    )
    conversation = list(messages)
    all_results = []
    all_queries = []
    rounds = 0
    _sw_timing = __import__("logging").getLogger("chat_agent.timing")
    _sw_total = time.perf_counter()

    web_calls = [
        tc for tc in tool_calls if tc["function"]["name"] == "web_search"
    ]
    if not web_calls:
        yield sse_event({"done": True, "usage": usage_out})
        return

    while web_calls and rounds < max_rounds:
        rounds += 1
        _sw_timing.info("search_round=%d/%d total_ms=%.0f", rounds, max_rounds, (time.perf_counter() - _sw_total) * 1000)
        tool_contents = {}
        for tc in web_calls:
            label = f"[検索 {rounds}/{max_rounds}]" if max_rounds > 1 else ""
            batch = yield from _yield_web_search_execution(
                tc,
                user_text,
                search_engines,
                sse_event,
                round_label=label,
                computelab_active=computelab_active,
                emit_tool_trace=emit_tool_trace,
                intelligent_search_override=intelligent_search_override,
                llm_client=client,
                llm_model=model,
                provider_id=provider_id,
            )
            if not batch:
                continue
            all_results = merge_search_result_lists(
                all_results, batch["results"]
            )
            all_queries.extend(batch["queries"])
            combined_query = ", ".join(dict.fromkeys(all_queries))
            tool_contents[tc["id"]] = _format_search_tool_content(
                all_results,
                combined_query,
                user_text,
                rounds,
                max_rounds,
                intelligent_search_override=intelligent_search_override,
            )

        if not tool_contents:
            break

        conversation = append_tool_round_to_conversation(
            conversation,
            round_data,
            web_calls,
            tool_contents,
            provider_id=provider_id,
        )

        yield sse_event({"segment_start": True, "discard_previous": False})
        round_data, next_calls = yield from _stream_web_search_model_round(
            client,
            model,
            conversation,
            sse_event,
            usage_out,
            emit_reasoning_cards,
            disable_reasoning,
            provider_id,
            emit_content=False,
        )
        if round_data is None:
            break

        web_calls = [
            tc
            for tc in (next_calls or [])
            if tc["function"]["name"] == "web_search"
        ]
        fetch_calls = [
            tc
            for tc in (next_calls or [])
            if tc["function"]["name"] == "web_fetch"
        ]
        if fetch_calls and not web_calls:
            tc = fetch_calls[0]
            parsed = parse_web_fetch_tool_args(tc["function"]["arguments"])
            if parsed:
                page = None
                for event in stream_web_fetch(parsed["url"], reason=parsed["reason"]):
                    if event.get("type") == "done" and event.get("_page"):
                        page = event["_page"]
                    yield sse_event(_sse_fetch_event(event))
                context = format_fetch_context(
                    page or {"url": parsed["url"], "text": ""},
                    user_text=user_text,
                    query=parsed["reason"],
                )
                conversation = append_tool_round_to_conversation(
                    conversation,
                    round_data,
                    fetch_calls[:1],
                    {tc["id"]: context},
                    provider_id=provider_id,
                )
                round_data, next_calls = yield from _stream_web_search_model_round(
                    client,
                    model,
                    conversation,
                    sse_event,
                    usage_out,
                    emit_reasoning_cards,
                    disable_reasoning,
                    provider_id,
                    emit_content=False,
                )
                web_calls = [
                    tc
                    for tc in (next_calls or [])
                    if tc["function"]["name"] == "web_search"
                ]
            else:
                web_calls = []
        if not web_calls:
            break

    combined_query = ", ".join(dict.fromkeys(all_queries)) or user_text[:80]
    if all_results:
        final_context = format_search_context(all_results, combined_query, user_text)
    else:
        final_context = (
            f"検索クエリ: {combined_query}\n"
            "検索結果が取得できませんでした。"
            "学習データと推論に基づいて可能な範囲で回答してください。"
        )
    followup = strip_reasoning_content_from_messages(conversation, provider_id)
    followup[0] = {
        "role": "system",
        "content": build_web_search_system_message(
            final_context, user_text, agent_profile=agent_profile
        ),
    }
    followup.append({"role": "user", "content": WEB_SEARCH_FINAL_ANSWER_NUDGE})

    yield sse_event({"segment_start": True, "discard_previous": True})
    _sw_timing.info("search_final_answer rounds=%d total_ms=%.0f", rounds, (time.perf_counter() - _sw_total) * 1000)
    recovery_hint = _build_recovery_hint(user_text, agent_profile)
    recovery_hint += (
        f" これまで {rounds} 回の検索結果を統合して答えてください。"
        " 追加の web_search は不要です。"
    )
    yield from _stream_followup_with_recovery(
        client,
        model,
        followup,
        user_text,
        sse_event,
        usage_out,
        emit_reasoning_cards=False,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        agent_profile=agent_profile,
        recovery_hint=recovery_hint,
        search_results=all_results,
        allow_recovery=False,
    )


def _computelab_prefetch_queries(user_text):
    seed = []
    if re.search(r"paper|マイクラ|minecraft", user_text or "", re.IGNORECASE):
        seed.extend(
            [
                "PaperMC latest build download API",
                "ViaVersion ViaBackwards compatible Paper version Hangar",
                "Minecraft server Java 21 RAM requirements 10 players",
            ]
        )
    return refine_search_queries(user_text, seed, computelab_active=True)


def _yield_computelab_prefetch_search(
    user_text,
    search_engines,
    sse_event,
):
    queries = _computelab_prefetch_queries(user_text)
    if not queries:
        queries = [user_text[:120]]
    yield sse_event(
        {
            "search": {
                "type": "intent",
                "reason": "ComputeLab作業前に最新の手順・バージョンを調べます",
                "queries": queries,
            }
        }
    )
    search_results = []
    search_query = ", ".join(queries)
    for event in stream_web_search_for_queries(
        queries,
        user_text=user_text,
        search_engines=search_engines,
        computelab_active=True,
    ):
        if event["type"] == "done":
            search_results = event["results"]
            search_query = event.get("query") or search_query
        yield sse_event({"search": event})

    search_topic = infer_search_topic(user_text)
    search_limit, _ = search_limits_for_topic(search_topic)
    search_results = filter_search_results(
        search_results,
        user_text,
        limit=search_limit,
        queries=queries,
    )
    context = format_search_context(search_results, search_query, user_text)
    return search_results, (
        "【作業前Web調査（自動）】\n"
        f"{context}\n\n"
        "---\n"
        "上記を参考に ComputeLab 作業を進めてください。"
    )


def _should_force_computelab_tool_round(user_text, assistant_content):
    if not user_requests_computelab_operations(user_text):
        return False
    return _assistant_claims_computelab_work(assistant_content)


def _yield_tool_trace_events(sse_event, emit_tool_trace, traces):
    if not emit_tool_trace or not traces:
        return
    for name, duration_ms, ok, err in traces:
        yield sse_event(
            tool_trace_payload(name, duration_ms, ok=ok, error=err)
        )


def _run_computelab_tool_batch(computelab_username, tool_calls):
    from computelab_services import format_tool_result

    def runner(tc):
        return execute_computelab_tool(
            computelab_username,
            tc["function"]["name"],
            tc["function"]["arguments"],
        )

    try:
        return run_tool_calls_parallel(tool_calls, runner, max_workers=6, timeout=60)
    except Exception:
        tool_contents_by_id = {}
        traces = []
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            started = time.perf_counter()
            try:
                content = runner(tc)
                ok = True
                err = None
            except Exception as exc:
                content = format_tool_result(
                    None, f"ComputeLab ツール実行エラー: {exc}"
                )
                ok = False
                err = str(exc)
            duration_ms = (time.perf_counter() - started) * 1000
            tool_contents_by_id[tc["id"]] = content
            traces.append((tool_name, duration_ms, ok, err))
        return tool_contents_by_id, traces


def _stream_computelab_model_round(
    client,
    model,
    conversation,
    round_data,
    tool_calls,
    computelab_username,
    computelab_tools,
    sse_event,
    usage_out,
    emit_reasoning_cards,
    disable_reasoning,
    provider_id,
    *,
    run_tools_first=True,
    tool_choice=None,
    emit_tool_trace=False,
):
    if run_tools_first and tool_calls:
        yield sse_event({"segment_end": True})
        tool_contents_by_id, traces = _run_computelab_tool_batch(
            computelab_username, tool_calls
        )
        yield from _yield_tool_trace_events(sse_event, emit_tool_trace, traces)
        for _ in tool_calls:
            yield sse_event({"computelab_tool_used": True})
        conversation = append_tool_round_to_conversation(
            conversation,
            round_data,
            tool_calls,
            tool_contents_by_id,
            provider_id=provider_id,
        )

    yield sse_event({"segment_start": True, "discard_previous": False})
    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
    }
    for kind, payload in stream_model_round(
        client,
        model,
        conversation,
        computelab_tools,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        tool_choice=tool_choice,
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)
        if kind == "end":
            round_data = round_state["round_data"]

    if round_data is None:
        return conversation, None, []

    merge_usage(usage_out, round_data.get("usage") or {})
    next_tool_calls = openai_tool_calls_list(
        round_data["tool_calls_map"], COMPUTELAB_TOOL_NAMES
    )
    return conversation, round_data, next_tool_calls


def _stream_generate_image_tool_turn(
    client,
    model,
    messages,
    round_data,
    tc,
    tool_calls,
    sse_event,
    usage_out,
    *,
    image_generation_enabled,
    image_generation_config,
    providers_config,
    plan_key,
    image_generation_prefs,
    image_generation_username,
    image_generation_public_base_url,
    user_text,
    emit_reasoning_cards,
    disable_reasoning,
    provider_id,
    agent_profile,
):
    if not image_generation_enabled:
        yield sse_event({"error": "画像生成が無効です"})
        return False

    parsed = parse_generate_image_tool_args(tc["function"]["arguments"])
    if not parsed:
        yield sse_event({"error": "画像生成パラメータが不正です"})
        return False

    image_context = None
    for event in stream_image_generation_events(
        plan_key,
        image_generation_config,
        providers_config,
        tc["function"]["arguments"],
        user_prefs=image_generation_prefs,
        username=image_generation_username,
        public_base_url=image_generation_public_base_url,
    ):
        if event.get("type") == "done":
            image_context = event.get("_context")
        if event.get("type") == "error":
            yield sse_event(
                {"error": event.get("message") or "画像生成に失敗しました"}
            )
            return False
        public = {k: v for k, v in event.items() if not str(k).startswith("_")}
        yield sse_event({"image_generation": public})

    if not image_context:
        yield sse_event({"error": "画像生成に失敗しました"})
        return False

    assistant_msg = build_assistant_tool_message(
        round_data, tool_calls, provider_id=provider_id
    )
    tool_msg = {
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": image_context,
    }
    followup = strip_reasoning_content_from_messages(
        messages + [assistant_msg, tool_msg], provider_id
    )
    followup[0] = {
        "role": "system",
        "content": build_image_generation_followup_system(image_context, user_text),
    }
    yield sse_event({"segment_start": True})
    recovery_hint = (
        "generate_image は実行済みで、生成画像はチャットに表示されています。"
        "日本語で短く説明するだけにし、Markdown 画像記法やURLの再掲は禁止です。"
        "「生成しています」「完成です」など、未実行を示す表現は禁止です。"
        "追加の generate_image は禁止です。"
    )
    yield from _stream_followup_with_recovery(
        client,
        model,
        followup,
        user_text,
        sse_event,
        usage_out,
        emit_reasoning_cards=emit_reasoning_cards,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        agent_profile=agent_profile,
        recovery_hint=recovery_hint,
        allow_recovery=False,
    )
    return True


def stream_image_generation_force_loop(
    client,
    model,
    messages,
    initial_round_data,
    sse_event,
    usage_out,
    *,
    image_generation_enabled,
    image_generation_config,
    providers_config,
    plan_key,
    image_generation_prefs,
    image_generation_username,
    image_generation_public_base_url,
    user_text,
    emit_reasoning_cards,
    disable_reasoning,
    provider_id,
    agent_profile,
):
    yield sse_event({"segment_start": True, "discard_previous": True})

    conversation = strip_reasoning_content_from_messages(list(messages), provider_id)
    assistant_content = (initial_round_data.get("content") or "").strip()
    if assistant_content:
        conversation.append({"role": "assistant", "content": assistant_content})
    conversation.append(
        {"role": "user", "content": IMAGE_GENERATION_TOOL_REQUIRED_NUDGE}
    )

    image_tools = build_image_generation_tool_list()
    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
    }
    for kind, payload in stream_model_round(
        client,
        model,
        conversation,
        image_tools,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        tool_choice="required",
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)

    round_data = round_state["round_data"]
    if round_data is None:
        yield sse_event({"error": "画像生成ツールの呼び出しに失敗しました"})
        return

    tool_calls = openai_tool_calls_list(
        round_data.get("tool_calls_map") or {},
        allowed_names=IMAGE_GENERATION_TOOL_NAMES,
    )
    if not tool_calls:
        yield sse_event(
            {
                "error": (
                    "画像生成ツールが呼び出されませんでした。"
                    " もう一度お試しください。"
                )
            }
        )
        return

    pre_tool = (round_data.get("content") or "").strip()
    if pre_tool:
        yield sse_event({"segment_end": True})

    tc = tool_calls[0]
    yield from _stream_generate_image_tool_turn(
        client,
        model,
        messages,
        round_data,
        tc,
        tool_calls,
        sse_event,
        usage_out,
        image_generation_enabled=image_generation_enabled,
        image_generation_config=image_generation_config,
        providers_config=providers_config,
        plan_key=plan_key,
        image_generation_prefs=image_generation_prefs,
        image_generation_username=image_generation_username,
        image_generation_public_base_url=image_generation_public_base_url,
        user_text=user_text,
        emit_reasoning_cards=emit_reasoning_cards,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        agent_profile=agent_profile,
    )


def stream_computelab_tool_loop(
    client,
    model,
    messages,
    computelab_username,
    initial_round_data,
    initial_tool_calls,
    sse_event,
    usage_out,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    agent_profile="deepseek",
    user_text="",
    force_tools_after_hallucination=False,
    emit_tool_trace=False,
):
    computelab_tools = build_computelab_tool_list()
    conversation = list(messages)
    round_data = initial_round_data
    tool_calls = initial_tool_calls
    rounds = 0

    if force_tools_after_hallucination and not tool_calls:
        assistant_so_far = (round_data.get("content") or "").strip()
        conversation = strip_reasoning_content_from_messages(conversation, provider_id)
        if assistant_so_far:
            conversation = conversation + [
                {"role": "assistant", "content": assistant_so_far},
                {"role": "user", "content": COMPUTELAB_TOOL_REQUIRED_NUDGE},
            ]
        else:
            conversation = conversation + [
                {"role": "user", "content": COMPUTELAB_TOOL_REQUIRED_NUDGE},
            ]
        round_data = {"content": "", "reasoning_content": "", "tool_calls_map": {}}
        conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
            client,
            model,
            conversation,
            round_data,
            [],
            computelab_username,
            computelab_tools,
            sse_event,
            usage_out,
            emit_reasoning_cards,
            disable_reasoning,
            provider_id,
            emit_tool_trace=emit_tool_trace,
            run_tools_first=False,
            tool_choice="required",
        )
        if round_data is None:
            yield sse_event(
                {
                    "error": "ComputeLab: ツール呼び出しに失敗しました。もう一度お試しください。"
                }
            )
            return
        if not tool_calls:
            yield sse_event(
                {
                    "error": (
                        "ComputeLab ツールが呼び出されませんでした。"
                        " 設定で ComputeLab ツールが ON か確認し、短い指示で再試行してください。"
                    )
                }
            )
            return

    while tool_calls and rounds < MAX_COMPUTELAB_TOOL_ROUNDS:
        rounds += 1
        conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
            client,
            model,
            conversation,
            round_data,
            tool_calls,
            computelab_username,
            computelab_tools,
            sse_event,
            usage_out,
            emit_reasoning_cards,
            disable_reasoning,
            provider_id,
            emit_tool_trace=emit_tool_trace,
            run_tools_first=True,
        )
        if round_data is None:
            yield sse_event(
                {
                    "error": "ComputeLab: モデル応答がありませんでした。もう一度お試しください。"
                }
            )
            tool_calls = []
            break

    if (
        rounds > 0
        and not tool_calls
        and _user_requests_long_computelab_setup(user_text, conversation)
        and hallucinated_setup_completion(
            setup_intent_text(user_text, conversation),
            tool_evidence_blob(conversation),
            _last_assistant_content(conversation),
        )
    ):
        conversation = strip_reasoning_content_from_messages(
            conversation + [{"role": "user", "content": COMPUTELAB_VERIFY_NUDGE}],
            provider_id,
        )
        round_data = {"content": "", "reasoning_content": "", "tool_calls_map": {}}
        conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
            client,
            model,
            conversation,
            round_data,
            [],
            computelab_username,
            computelab_tools,
            sse_event,
            usage_out,
            emit_reasoning_cards,
            disable_reasoning,
            provider_id,
            emit_tool_trace=emit_tool_trace,
            run_tools_first=False,
            tool_choice="required",
        )
        if tool_calls:
            while tool_calls and rounds < MAX_COMPUTELAB_TOOL_ROUNDS:
                rounds += 1
                conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
                    client,
                    model,
                    conversation,
                    round_data,
                    tool_calls,
                    computelab_username,
                    computelab_tools,
                    sse_event,
                    usage_out,
                    emit_reasoning_cards,
                    disable_reasoning,
                    provider_id,
                    emit_tool_trace=emit_tool_trace,
                    run_tools_first=True,
                )
                if round_data is None:
                    tool_calls = []
                    break

    if tool_calls:
        overflow = 0
        while tool_calls and overflow < MAX_COMPUTELAB_COMPLETION_ROUNDS:
            overflow += 1
            conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
                client,
                model,
                conversation,
                round_data,
                tool_calls,
                computelab_username,
                computelab_tools,
                sse_event,
                usage_out,
                emit_reasoning_cards,
                disable_reasoning,
                provider_id,
                emit_tool_trace=emit_tool_trace,
                run_tools_first=True,
            )
            if round_data is None:
                break
            if _conversation_has_public_url(conversation):
                tool_calls = []
                break

    needs_completion = (
        rounds > 0
        and _user_wants_deploy_url(user_text)
        and not _conversation_has_public_url(conversation)
    )
    if needs_completion:
        conversation = strip_reasoning_content_from_messages(
            conversation
            + [{"role": "user", "content": COMPUTELAB_COMPLETION_NUDGE}],
            provider_id,
        )
        round_data = {"content": "", "reasoning_content": ""}
        tool_calls = []
        completion_rounds = 0
        while completion_rounds < MAX_COMPUTELAB_COMPLETION_ROUNDS:
            completion_rounds += 1
            conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
                client,
                model,
                conversation,
                round_data,
                tool_calls,
                computelab_username,
                computelab_tools,
                sse_event,
                usage_out,
                emit_reasoning_cards,
                disable_reasoning,
                provider_id,
                emit_tool_trace=emit_tool_trace,
                run_tools_first=bool(tool_calls),
            )
            if round_data is None:
                break
            if _conversation_has_public_url(conversation):
                break

    needs_setup_completion = (
        rounds > 0
        and not tool_calls
        and _user_requests_long_computelab_setup(user_text, conversation)
        and not _computelab_setup_seems_complete(user_text, conversation)
    )
    if needs_setup_completion:
        conversation = strip_reasoning_content_from_messages(
            conversation
            + [
                {
                    "role": "user",
                    "content": _build_computelab_setup_continue_nudge(
                        user_text, conversation
                    ),
                }
            ],
            provider_id,
        )
        round_data = {"content": "", "reasoning_content": ""}
        tool_calls = []
        setup_rounds = 0
        force_tools_once = True
        while setup_rounds < MAX_COMPUTELAB_COMPLETION_ROUNDS:
            setup_rounds += 1
            choice = "required" if force_tools_once and not tool_calls else None
            force_tools_once = False
            conversation, round_data, tool_calls = yield from _stream_computelab_model_round(
                client,
                model,
                conversation,
                round_data,
                tool_calls,
                computelab_username,
                computelab_tools,
                sse_event,
                usage_out,
                emit_reasoning_cards,
                disable_reasoning,
                provider_id,
                emit_tool_trace=emit_tool_trace,
                run_tools_first=bool(tool_calls),
                tool_choice=choice,
            )
            if round_data is None:
                break
            if _computelab_setup_seems_complete(user_text, conversation):
                tool_calls = []
                break
            if not tool_calls:
                continue
        if not _computelab_setup_seems_complete(user_text, conversation):
            yield sse_event(
                {
                    "error": (
                        "ComputeLab のセットアップが途中で止まりました。"
                        " チャットで「続きから完了して」と送ると再開できます。"
                        f" 未完了: {', '.join(_computelab_setup_requirement_status(user_text, conversation))}"
                    )
                }
            )

    if (
        rounds > 0
        and not tool_calls
        and _user_requests_long_computelab_setup(user_text, conversation)
        and _computelab_setup_seems_complete(user_text, conversation)
    ):
        conversation = strip_reasoning_content_from_messages(
            conversation
            + [
                {
                    "role": "user",
                    "content": (
                        "【システム】ツール結果でセットアップ要件は満たされています。"
                        " ツールは呼ばず、直近の computelab_* の JSON と exec の stdout だけを根拠に、"
                        "接続方法（get_instance の IP / add_port の URL・25565）、"
                        "screen 再開コマンド、OP、起動確認を箇条書きでまとめてください。"
                        "根拠のない IP・バージョン・URL は書かないでください。"
                    ),
                }
            ],
            provider_id,
        )
        yield sse_event({"segment_start": True})
        round_state = {
            "round_data": None,
            "reasoning_streamed": False,
            "reasoning_done_sent": False,
            "reasoning_card_started": False,
            "reasoning_emitted_len": 0,
            "reasoning_buffer": [],
            "usage_out": usage_out,
            "emit_reasoning_cards": emit_reasoning_cards,
        }
        for kind, payload in stream_model_round(
            client,
            model,
            conversation,
            None,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        ):
            yield from _emit_round_events(kind, payload, sse_event, round_state)

    if tool_calls:
        yield sse_event(
            {
                "error": (
                    "ComputeLab の操作が多すぎるため続行を打ち切りました。"
                    " 一覧で instance_id を確認し、短い指示で再試行してください。"
                )
            }
        )


def stream_resume_after_ask_user(
    pending,
    *,
    answers,
    dismissed,
    client,
    model,
    sse_event,
    usage_out=None,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    agent_profile="deepseek",
):
    usage_out = usage_out if usage_out is not None else empty_usage()
    messages = pending.get("messages") or []
    round_data = pending.get("round_data") or {}
    tool_call = pending.get("tool_call")
    questions = pending.get("questions") or []
    user_text = pending.get("user_text") or ""
    if not tool_call or not isinstance(tool_call, dict):
        yield sse_event({"error": "再開データが不正です"})
        yield sse_event({"done": True, "usage": usage_out})
        return
    tool_content = format_ask_user_tool_result(
        questions, answers, dismissed=bool(dismissed)
    )
    followup = append_tool_round_to_conversation(
        messages,
        round_data,
        [tool_call],
        {tool_call["id"]: tool_content},
        provider_id=provider_id,
    )
    yield sse_event({"segment_start": True, "discard_previous": False})
    yield from _stream_followup_with_recovery(
        client,
        model or pending.get("model") or "",
        followup,
        user_text,
        sse_event,
        usage_out,
        emit_reasoning_cards=emit_reasoning_cards,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        agent_profile=agent_profile,
        recovery_hint=(
            "上記のユーザー回答を踏まえ、元の質問に対して日本語で答えてください。"
            "再度 ask_user は使わないでください。"
        ),
        allow_recovery=True,
    )
    if not usage_out.get("total_tokens"):
        merge_usage(
            usage_out,
            estimate_turn_tokens(messages, "", "", model or pending.get("model") or ""),
        )
    yield sse_event({"done": True, "usage": usage_out})


def stream_agent_chat(
    prepared,
    api_key,
    model,
    make_client,
    sse_event,
    usage_out=None,
    allow_web_search=True,
    search_engines=None,
    location_hint=None,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    agent_profile="deepseek",
    chat_username=None,
    user_questions_enabled=False,
    google_username=None,
    google_calendar_enabled=False,
    google_gmail_enabled=False,
    tasks_enabled=False,
    tasks_username=None,
    memory_enabled=False,
    memory_username=None,
    computelab_enabled=False,
    computelab_username=None,
    image_generation_enabled=False,
    image_generation_config=None,
    providers_config=None,
    plan_key="free",
    image_generation_prefs=None,
    image_generation_username=None,
    image_generation_public_base_url="",
    reasoning_in_english=False,
    emit_tool_trace=False,
    deep_research_enabled=False,
    deep_research_prefs=None,
    intelligent_search_override=False,
    custom_agent=None,
    emit_full_info=False,
    cost_performance_maximized=False,
    expression_extension_enabled=False,
):
    from cost_performance import cost_performance_token, reset_cost_performance_token

    cp_token = cost_performance_token(cost_performance_maximized)
    _req_start = time.perf_counter()
    _req_ok = True
    _req_error = ""
    try:
        yield from _stream_agent_chat_body(
            prepared=prepared,
            api_key=api_key,
            model=model,
            make_client=make_client,
            sse_event=sse_event,
            usage_out=usage_out,
            allow_web_search=allow_web_search,
            search_engines=search_engines,
            location_hint=location_hint,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            agent_profile=agent_profile,
            chat_username=chat_username,
            user_questions_enabled=user_questions_enabled,
            cost_performance_maximized=cost_performance_maximized,
            google_username=google_username,
            google_calendar_enabled=google_calendar_enabled,
            google_gmail_enabled=google_gmail_enabled,
            tasks_enabled=tasks_enabled,
            tasks_username=tasks_username,
            memory_enabled=memory_enabled,
            memory_username=memory_username,
            computelab_enabled=computelab_enabled,
            computelab_username=computelab_username,
            image_generation_enabled=image_generation_enabled,
            image_generation_config=image_generation_config,
            providers_config=providers_config,
            plan_key=plan_key,
            image_generation_prefs=image_generation_prefs,
            image_generation_username=image_generation_username,
            image_generation_public_base_url=image_generation_public_base_url,
            reasoning_in_english=reasoning_in_english,
            emit_tool_trace=emit_tool_trace,
            deep_research_enabled=deep_research_enabled,
            deep_research_prefs=deep_research_prefs,
            intelligent_search_override=intelligent_search_override,
            custom_agent=custom_agent,
            emit_full_info=emit_full_info,
            expression_extension_enabled=expression_extension_enabled,
        )
    except Exception as exc:
        _req_ok = False
        _req_error = str(exc)
        raise
    finally:
        reset_cost_performance_token(cp_token)
        try:
            _req_ms = (time.perf_counter() - _req_start) * 1000
            _req_tokens = (usage_out or {}).get("total_tokens", 0) if usage_out else 0
            record_chat_request(
                model=model,
                provider=provider_id,
                duration_ms=_req_ms,
                tokens=_req_tokens,
                ok=_req_ok,
                error=_req_error,
            )
            if not _req_ok:
                record_error(context="stream_agent_chat", error=_req_error)
        except Exception:
            pass


def _stream_agent_chat_body(
    prepared,
    api_key,
    model,
    make_client,
    sse_event,
    usage_out=None,
    allow_web_search=True,
    search_engines=None,
    location_hint=None,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    agent_profile="deepseek",
    chat_username=None,
    user_questions_enabled=False,
    cost_performance_maximized=False,
    google_username=None,
    google_calendar_enabled=False,
    google_gmail_enabled=False,
    tasks_enabled=False,
    tasks_username=None,
    memory_enabled=False,
    memory_username=None,
    computelab_enabled=False,
    computelab_username=None,
    image_generation_enabled=False,
    image_generation_config=None,
    providers_config=None,
    plan_key="free",
    image_generation_prefs=None,
    image_generation_username=None,
    image_generation_public_base_url="",
    reasoning_in_english=False,
    emit_tool_trace=False,
    deep_research_enabled=False,
    deep_research_prefs=None,
    intelligent_search_override=False,
    custom_agent=None,
    emit_full_info=False,
    expression_extension_enabled=False,
):
    usage_out = usage_out if usage_out is not None else empty_usage()
    _timing = __import__("logging").getLogger("chat_agent.timing")
    _t_total = time.perf_counter()
    _t_step = _t_total
    def _lap(label):
        nonlocal _t_step
        now = time.perf_counter()
        elapsed = (now - _t_step) * 1000
        _t_step = now
        _timing.info("step=%s elapsed_ms=%.0f total_ms=%.0f", label, elapsed, (now - _t_total) * 1000)
        # メトリクス記録
        try:
            record_step(label, elapsed)
        except Exception:
            pass
        return now

    # A/Bテスト割り当て（応答文体のバリエーション）
    _ab_style = None
    try:
        _ab_style = assign_variant(chat_username or "anonymous", "response_style")
    except Exception:
        _ab_style = None

    if not api_key:
        user_text = extract_user_text(prepared)
        demo = (
            "デモモードです。OPENAI_API_KEY を .env に設定してください。\n\n"
            f"あなたのメッセージ: 「{user_text}」"
        )
        for word in demo.split():
            yield sse_event({"content": word + " "})
        merge_usage(
            usage_out,
            estimate_turn_tokens(prepared, demo, "", model),
        )
        yield sse_event({"done": True, "usage": usage_out})
        return

    client = make_client(api_key)
    user_text = extract_user_text(prepared)
    computelab_this_turn = computelab_enabled and user_requests_computelab_operations(
        user_text, prepared
    )
    messages = prepare_agent_messages(
        prepared,
        allow_web_search=allow_web_search,
        provider_id=provider_id,
        agent_profile=agent_profile,
        location_hint=location_hint,
        google_calendar_enabled=google_calendar_enabled,
        google_gmail_enabled=google_gmail_enabled,
        tasks_enabled=tasks_enabled,
        memory_enabled=memory_enabled,
        memory_username=memory_username,
        computelab_enabled=computelab_this_turn,
        image_generation_enabled=image_generation_enabled,
        user_questions_enabled=user_questions_enabled,
        cost_performance_maximized=cost_performance_maximized,
        expression_extension_enabled=expression_extension_enabled,
        reasoning_in_english=reasoning_in_english,
        deep_research_enabled=deep_research_enabled,
        deep_research_prefs=deep_research_prefs,
        intelligent_search_override_enabled=intelligent_search_override,
        custom_agent=custom_agent,
    )
    # A/Bテスト: 応答文体バリアントを適用
    if _ab_style:
        _style_append = {
            "concise": "\n\n【応答文体】簡潔さを最優先。冗長な説明は避け、要点だけを短く答える。",
            "bulleted": "\n\n【応答文体】箇条書きを多用して要点を整理する。長文段落は避ける。",
            "default": "",
        }.get(_ab_style, "")
        if _style_append:
            for _i, _m in enumerate(messages):
                if _m.get("role") == "system":
                    messages[_i] = {**_m, "content": (_m.get("content") or "") + _style_append}
                    break
    _lap("prepare_agent_messages")
    agent_tools = []
    if user_questions_enabled:
        agent_tools.extend(build_ask_user_tool_list())
    if allow_web_search:
        agent_tools.extend([WEB_SEARCH_TOOL, WEB_FETCH_TOOL])
    if image_generation_enabled:
        agent_tools.extend(build_image_generation_tool_list())
    agent_tools.extend(
        build_google_tool_list(google_calendar_enabled, google_gmail_enabled)
    )
    if tasks_enabled:
        agent_tools.extend(build_tasks_tool_list())
    if memory_enabled:
        agent_tools.extend(build_memory_tool_list())
    if computelab_this_turn:
        agent_tools.extend(build_computelab_tool_list())
    agent_tools = agent_tools or None
    allowed_tool_names = set(AGENT_TOOL_NAMES)
    if google_calendar_enabled or google_gmail_enabled:
        allowed_tool_names |= GOOGLE_TOOL_NAMES
    if tasks_enabled:
        allowed_tool_names |= TASKS_TOOL_NAMES
    if memory_enabled:
        allowed_tool_names |= MEMORY_TOOL_NAMES
    if computelab_this_turn:
        allowed_tool_names |= COMPUTELAB_TOOL_NAMES
    if image_generation_enabled:
        allowed_tool_names |= IMAGE_GENERATION_TOOL_NAMES
    if user_questions_enabled:
        allowed_tool_names |= ASK_USER_TOOL_NAMES

    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
    }
    if emit_full_info:
        from full_info_trace import (
            full_info_payload,
            model_request_payload,
            sanitize_messages_for_full_info,
        )

        yield sse_event(
            full_info_payload(
                "turn_start",
                messages=sanitize_messages_for_full_info(prepared),
            )
        )
        yield sse_event(
            model_request_payload(
                model,
                messages,
                tools=agent_tools,
                label="initial",
            )
        )
    # クエリが明らかにツールを必要とする場合、tool_choice="required" で初回呼出
    _force_tools = _detect_tool_urgency(user_text, allow_web_search)
    _lap("tools_built")
    for kind, payload in stream_model_round(
        client,
        model,
        messages,
        agent_tools,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        tool_choice="required" if _force_tools else None,
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)

    _lap("first_model_round")
    round_data = round_state["round_data"]
    if round_data is None:
        yield sse_event({"error": "モデルからの応答が取得できませんでした。再試行してください。"})
        yield sse_event({"done": True, "usage": usage_out})
        return

    tool_calls = openai_tool_calls_list(
        round_data["tool_calls_map"], allowed_tool_names
    )
    # ストリームで得たツール呼び出しが完結している場合のみ、
    # モデルの再呼び出し（complete_model_round_fallback）をスキップする。
    # 不完全（引数が途中で切れた等）な場合は品質維持のため従来どおり再実行する。
    _streamed_tool_calls_complete = bool(tool_calls) and all(
        (entry.get("name") or "").strip()
        and str(entry.get("arguments") or "").strip().endswith("}")
        for entry in (round_data.get("tool_calls_map") or {}).values()
        if entry.get("name") in allowed_tool_names
    )
    if (
        allow_web_search
        and tool_calls
        and not (round_data.get("reasoning_content") or "").strip()
        and (_force_tools or not _streamed_tool_calls_complete)
    ):
        streamed_content = round_data.get("content") or ""
        round_data = complete_model_round(
            client,
            model,
            messages,
            agent_tools,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        )
        merge_usage(usage_out, round_data.get("usage"))
        if streamed_content:
            round_data["content"] = streamed_content
        tool_calls = openai_tool_calls_list(
            round_data["tool_calls_map"], allowed_tool_names
        )
        if not disable_reasoning:
            reasoning_text = (round_data.get("reasoning_content") or "").strip()
            if reasoning_text and should_emit_reasoning_card(
                reasoning_text, round_data, emit_reasoning_cards
            ):
                yield sse_event({"reasoning": {"type": "delta", "text": reasoning_text}})
                yield sse_event({"reasoning": {"type": "done"}})
        _lap("complete_model_round_fallback")

    tool_calls = filter_tool_calls_for_web_access(
        tool_calls, allow_web_search, allow_image_generation=image_generation_enabled
    )
    if user_questions_enabled and any(
        tc.get("function", {}).get("name") == ASK_USER_TOOL_NAME for tc in tool_calls
    ):
        tool_calls = [
            tc
            for tc in tool_calls
            if tc.get("function", {}).get("name") == ASK_USER_TOOL_NAME
        ][:1]

    tool_retry_succeeded = False
    _lap("tool_filtering")

    if not tool_calls:
        if (
            computelab_this_turn
            and computelab_username
            and _should_force_computelab_tool_round(
                user_text, round_data.get("content") or ""
            )
        ):
            if (round_data.get("content") or "").strip():
                yield sse_event({"segment_end": True})
            yield from stream_computelab_tool_loop(
                client,
                model,
                messages,
                computelab_username,
                round_data,
                [],
                sse_event,
                usage_out,
                emit_reasoning_cards=emit_reasoning_cards,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
                agent_profile=agent_profile,
                user_text=user_text,
                force_tools_after_hallucination=True,
                emit_tool_trace=emit_tool_trace,
            )
            if not usage_out.get("total_tokens"):
                merge_usage(
                    usage_out,
                    estimate_turn_tokens(messages, "", "", model),
                )
            yield sse_event({"done": True, "usage": usage_out})
            return
        if (
            image_generation_enabled
            and user_wants_image_generation(user_text, messages)
        ):
            yield from stream_image_generation_force_loop(
                client,
                model,
                messages,
                round_data,
                sse_event,
                usage_out,
                image_generation_enabled=image_generation_enabled,
                image_generation_config=image_generation_config,
                providers_config=providers_config,
                plan_key=plan_key,
                image_generation_prefs=image_generation_prefs,
                image_generation_username=image_generation_username,
                image_generation_public_base_url=image_generation_public_base_url,
                user_text=user_text,
                emit_reasoning_cards=emit_reasoning_cards,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
                agent_profile=agent_profile,
            )
            if not usage_out.get("total_tokens"):
                merge_usage(
                    usage_out,
                    estimate_turn_tokens(messages, "", "", model),
                )
            yield sse_event({"done": True, "usage": usage_out})
            return

        # ── Tool intent retry: model declared it will use a tool but didn't.
        # Trigger for responses < 200 chars to catch longer preambles.
        _content_text = (round_data.get("content") or "").strip() if round_data else ""
        _TOOL_INTENT_RE = re.compile(
            r"(?:検索|調べ|確認|取得|一覧表示|呼び出|実行|送信|作成|追加|更新|削除|探し|見てみ|調査"
            r"|I will|let me|I'll|i will|let's|i'll)"
            r"(?:します|する|いたします|しよう|してみます|してみる|しますね|してみよう|いたそう|致します"
            r"|search|look ?up|check|find|look into|look at|research)",
            re.IGNORECASE,
        )
        if _content_text and len(_content_text) < 200 and _TOOL_INTENT_RE.search(_content_text):
            _lap("tool_intent_retry_enter")
            import logging as _logging
            _tool_log = _logging.getLogger("chat_agent.tool_recovery")
            _tool_log.warning(
                "Tool intent retry: content=%r len=%d",
                _content_text[:200],
                len(_content_text),
            )
            retry_hint = (
                "ツールを使ってください。会話文だけで説明するのは禁止です。"
                "ユーザーが特定の送信者・キーワード・話題について質問した場合、"
                "たとえ過去の会話にその情報が一部含まれていても、"
                "gmail_search や web_search で新たに検索してください。"
                "過去の検索結果をそのまま再利用せず、必ずツールを呼び出してから回答してください。"
            )
            retry_messages = list(messages) + [
                {"role": "user", "content": retry_hint}
            ]
            yield sse_event({"segment_start": True, "discard_previous": True})
            retry_round = None
            retry_state = {
                "round_data": None,
                "reasoning_streamed": False,
                "reasoning_done_sent": False,
                "reasoning_card_started": False,
                "reasoning_emitted_len": 0,
                "reasoning_buffer": [],
                "usage_out": usage_out,
                "emit_reasoning_cards": emit_reasoning_cards,
                "emit_content": True,
                "content_buffer": [],
            }
            effective_disable = apply_tool_choice_kwargs(
                {},
                tools=agent_tools,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
            )
            for kind, payload in stream_model_round(
                client,
                model,
                retry_messages,
                agent_tools,
                disable_reasoning=effective_disable,
                provider_id=provider_id,
            ):
                yield from _emit_round_events(kind, payload, sse_event, retry_state)
                if kind == "end":
                    retry_round = retry_state["round_data"]

            if retry_round:
                retry_tool_calls = openai_tool_calls_list(
                    retry_round.get("tool_calls_map") or {}, allowed_tool_names
                )
                if retry_tool_calls:
                    # Model emitted tool calls on retry — dispatch normally
                    tool_retry_succeeded = True
                    merged = dict(round_data)
                    merged.update(retry_round)
                    round_data = merged
                    tool_calls = retry_tool_calls
                    # Fall through to normal tool dispatch below
                else:
                    # Stage 2 retry: force tool_choice="required" as last resort
                    _lap("tool_intent_retry_stage2")
                    _tool_log.warning("Tool intent retry stage 2 (required)")
                    retry2_messages = list(messages) + [
                        {
                            "role": "user",
                            "content": (
                                "【重要】必ずツールを呼び出してください。"
                                "web_search または web_fetch を使って情報を取得してから回答してください。"
                                "ツールを呼び出さずに会話文だけで答えることは禁止です。"
                                "今すぐツールを実行してください。"
                            ),
                        }
                    ]
                    yield sse_event({"segment_start": True, "discard_previous": True})
                    retry2_state = {
                        "round_data": None,
                        "reasoning_streamed": False,
                        "reasoning_done_sent": False,
                        "reasoning_card_started": False,
                        "reasoning_emitted_len": 0,
                        "reasoning_buffer": [],
                        "usage_out": usage_out,
                        "emit_reasoning_cards": emit_reasoning_cards,
                        "emit_content": True,
                        "content_buffer": [],
                    }
                    retry2_round = None
                    for kind, payload in stream_model_round(
                        client,
                        model,
                        retry2_messages,
                        agent_tools,
                        disable_reasoning=effective_disable,
                        provider_id=provider_id,
                        tool_choice="required",
                    ):
                        yield from _emit_round_events(kind, payload, sse_event, retry2_state)
                        if kind == "end":
                            retry2_round = retry2_state["round_data"]

                    if retry2_round:
                        retry2_tool_calls = openai_tool_calls_list(
                            retry2_round.get("tool_calls_map") or {}, allowed_tool_names
                        )
                        if retry2_tool_calls:
                            tool_retry_succeeded = True
                            merged = dict(round_data)
                            merged.update(retry2_round)
                            round_data = merged
                            tool_calls = retry2_tool_calls
                        else:
                            for chunk in retry2_state.get("content_buffer") or []:
                                yield sse_event({"content": chunk})
                            if not usage_out.get("total_tokens"):
                                merge_usage(
                                    usage_out,
                                    estimate_turn_tokens(messages, "", "", model),
                                )
                            yield sse_event({"done": True, "usage": usage_out})
                            return
                    else:
                        if not usage_out.get("total_tokens"):
                            merge_usage(
                                usage_out,
                                estimate_turn_tokens(messages, "", "", model),
                            )
                        yield sse_event({"done": True, "usage": usage_out})
                        return
            else:
                if not usage_out.get("total_tokens"):
                    merge_usage(
                        usage_out,
                        estimate_turn_tokens(messages, "", "", model),
                    )
                yield sse_event({"done": True, "usage": usage_out})
                return

        if not tool_retry_succeeded:
            if _must_force_answer_recovery(round_data):
                yield sse_event({"segment_start": True, "discard_previous": True})
                yield from _stream_followup_with_recovery(
                    client,
                    model,
                    messages,
                    user_text,
                    sse_event,
                    usage_out,
                    emit_reasoning_cards=emit_reasoning_cards,
                    disable_reasoning=disable_reasoning,
                    provider_id=provider_id,
                    agent_profile=agent_profile,
                    recovery_hint=(
                        "DSML・XML・tool_calls 記法は本文に出力禁止。"
                        "ユーザーの質問への日本語の最終回答を完成させてください。"
                    ),
                    allow_recovery=True,
                )
                if not usage_out.get("total_tokens"):
                    merge_usage(
                        usage_out,
                        estimate_turn_tokens(
                            messages,
                            round_data.get("content") or "",
                            round_data.get("reasoning_content") or "",
                            model,
                        ),
                    )
                yield sse_event({"done": True, "usage": usage_out})
                return
            if not usage_out.get("total_tokens"):
                merge_usage(
                    usage_out,
                    estimate_turn_tokens(
                        messages,
                        round_data.get("content") or "",
                        round_data.get("reasoning_content") or "",
                        model,
                    ),
                )
            yield sse_event({"done": True, "usage": usage_out})
            return

    if not tool_calls:
        _lap("done_no_tools")
    else:
        _lap("tool_dispatch_enter")
    tc = tool_calls[0]
    tool_name = tc["function"]["name"]
    _lap(f"dispatch_{tool_name}")

    # Warn if multiple tool types are present (only first is dispatched)
    _tool_types = set(tc["function"]["name"] for tc in tool_calls)
    if len(_tool_types) > 1:
        import logging as _logging_mt
        _mt_log = _logging_mt.getLogger("chat_agent.multi_tool")
        _mt_log.warning(
            "Multiple tool types requested, only dispatching first: %s (all: %s)",
            tool_name,
            ", ".join(sorted(_tool_types)),
        )

    pre_tool_content = (round_data.get("content") or "").strip()
    if (
        pre_tool_content
        and tool_name not in GOOGLE_TOOL_NAMES
        and tool_name not in TASKS_TOOL_NAMES
        and tool_name not in MEMORY_TOOL_NAMES
        and tool_name not in COMPUTELAB_TOOL_NAMES
        and tool_name not in ASK_USER_TOOL_NAMES
    ):
        yield sse_event({"segment_end": True})

    if tool_name in ASK_USER_TOOL_NAMES:
        if not user_questions_enabled:
            yield sse_event({"error": "ユーザーへの質問は無効です"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        if not chat_username:
            yield sse_event({"error": "ユーザーへの質問を開始できません"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        parsed = parse_ask_user_tool_args(tc["function"].get("arguments"))
        if not parsed.get("questions"):
            yield sse_event({"error": "質問内容が不正です"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        if pre_tool_content:
            yield sse_event({"segment_end": True})
        from user_question_pending import create_user_question_pending

        pending_token = create_user_question_pending(
            chat_username,
            {
                "messages": messages,
                "round_data": round_data,
                "tool_call": tc,
                "questions": parsed["questions"],
                "intro": parsed.get("intro") or "",
                "user_text": user_text,
                "model": model,
                "provider_id": provider_id,
                "agent_profile": agent_profile,
                "disable_reasoning": disable_reasoning,
                "emit_reasoning_cards": emit_reasoning_cards,
            },
        )
        yield sse_event(
            {
                "ask_user": {
                    "token": pending_token,
                    "intro": parsed.get("intro") or "",
                    "questions": parsed["questions"],
                },
                "paused_for_user": True,
                "done": True,
                "usage": usage_out,
            }
        )
        return

    if tool_name in TASKS_TOOL_NAMES:
        if not tasks_enabled or not tasks_username:
            yield sse_event({"error": "TASKS が無効です"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        batch = [
            tc for tc in tool_calls if tc["function"]["name"] in TASKS_TOOL_NAMES
        ]
        mutation_flags = []

        def tasks_runner(ttc):
            context, mutated = execute_tasks_tool(
                tasks_username, ttc["function"]["name"], ttc["function"]["arguments"]
            )
            if mutated:
                mutation_flags.append(1)
            return context

        tool_contents_by_id, traces = run_tool_calls_parallel(
            batch, tasks_runner, max_workers=4, timeout=30
        )
        yield from _yield_tool_trace_events(sse_event, emit_tool_trace, traces)
        for _ in batch:
            yield sse_event({"tasks_tool_used": True})
        if mutation_flags:
            yield sse_event({"tasks_updated": True})
        followup = append_tool_round_to_conversation(
            messages,
            round_data,
            batch,
            tool_contents_by_id,
            provider_id=provider_id,
        )
        recovery_hint = (
            "上記のTASKS操作結果だけを根拠に、ユーザーの質問へ日本語で答えてください。"
            "追加の同種ツール呼び出しの宣言は禁止です。"
        )
        yield sse_event({"segment_start": True, "discard_previous": False})
        yield from _stream_followup_with_recovery(
            client,
            model,
            followup,
            user_text,
            sse_event,
            usage_out,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            agent_profile=agent_profile,
            recovery_hint=recovery_hint,
            allow_recovery=False,
        )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return

    if tool_name in MEMORY_TOOL_NAMES:
        if not memory_enabled or not memory_username:
            yield sse_event({"error": "メモリが無効です"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        yield from stream_memory_tool_loop(
            client,
            model,
            messages,
            memory_username,
            round_data,
            tool_calls,
            sse_event,
            usage_out,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            emit_tool_trace=emit_tool_trace,
        )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return

    if tool_name in COMPUTELAB_TOOL_NAMES:
        if not computelab_this_turn or not computelab_username:
            yield sse_event({"error": "ComputeLab連携が無効です"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        if pre_tool_content:
            yield sse_event({"segment_end": True})
        computelab_messages = list(messages)
        if (
            allow_web_search
            and user_needs_multi_search(user_text, computelab_active=True)
            and not _messages_include_search_context(computelab_messages)
        ):
            _, prefetch_note = yield from _yield_computelab_prefetch_search(
                user_text,
                search_engines,
                sse_event,
            )
            if prefetch_note:
                computelab_messages = computelab_messages + [
                    {"role": "user", "content": prefetch_note},
                ]
        yield from stream_computelab_tool_loop(
            client,
            model,
            computelab_messages,
            computelab_username,
            round_data,
            tool_calls,
            sse_event,
            usage_out,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            agent_profile=agent_profile,
            user_text=user_text,
            emit_tool_trace=emit_tool_trace,
        )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return

    if tool_name in GOOGLE_TOOL_NAMES:
        if not google_username:
            yield sse_event({"error": "Google連携が無効です"})
            yield sse_event({"done": True, "usage": usage_out})
            return
        batch = [
            tc for tc in tool_calls if tc["function"]["name"] in GOOGLE_TOOL_NAMES
        ]

        def google_runner(gtc):
            return execute_google_tool(
                google_username, gtc["function"]["name"], gtc["function"]["arguments"]
            )

        tool_contents_by_id, traces = run_tool_calls_parallel(
            batch, google_runner, max_workers=4, timeout=30
        )
        yield from _yield_tool_trace_events(sse_event, emit_tool_trace, traces)
        followup = append_tool_round_to_conversation(
            messages,
            round_data,
            batch,
            tool_contents_by_id,
            provider_id=provider_id,
        )

        # Build google tools for follow-up rounds (e.g. gmail_list → gmail_get)
        google_followup_tools = build_google_tool_list(google_calendar_enabled, google_gmail_enabled)
        google_followup_tools = google_followup_tools or None

        # Allow up to 2 rounds of follow-up Google tool calls (e.g. gmail_list → gmail_get)
        google_rounds = 0
        google_max_rounds = 3
        while google_rounds < google_max_rounds:
            google_rounds += 1
            is_last_round = google_rounds >= google_max_rounds

            if is_last_round:
                recovery_hint = (
                    "上記のGoogle連携結果だけを根拠に、ユーザーの質問へ日本語で答えてください。"
                    "追加のツール呼び出しの宣言は禁止です。"
                )
                allow_rec = False
                followup_tools = None
            else:
                recovery_hint = (
                    "上記のGoogle連携結果を確認し、必要なら gmail_get などで詳細を取得してください。"
                    "十分な情報が揃ったら日本語で回答してください。"
                )
                allow_rec = True
                followup_tools = google_followup_tools

            yield sse_event({"segment_start": True, "discard_previous": False})
            last_round = None
            round_state = {
                "round_data": None,
                "reasoning_streamed": False,
                "reasoning_done_sent": False,
                "reasoning_card_started": False,
                "reasoning_emitted_len": 0,
                "reasoning_buffer": [],
                "usage_out": usage_out,
                "emit_reasoning_cards": emit_reasoning_cards,
                "emit_content": not allow_rec,
                "content_buffer": [],
            }
            for kind, payload in stream_model_round(
                client,
                model,
                followup,
                followup_tools,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
            ):
                yield from _emit_round_events(kind, payload, sse_event, round_state)
                if kind == "end":
                    last_round = round_state["round_data"]

            if not last_round:
                break

            # Check if model wants more Google tool calls
            new_tool_calls = _extract_tool_calls(
                last_round, provider_id=provider_id, allowed_names=GOOGLE_TOOL_NAMES
            )
            google_tool_calls = [
                tc for tc in new_tool_calls
                if (tc.get("function", {}).get("name") or "") in GOOGLE_TOOL_NAMES
            ]
            if not google_tool_calls:
                # Flush buffered content
                for chunk in round_state.get("content_buffer") or []:
                    yield sse_event({"content": chunk})
                break

            # Execute the follow-up Google tools
            def google_runner2(gtc):
                return execute_google_tool(
                    google_username, gtc["function"]["name"], gtc["function"]["arguments"]
                )

            more_contents, more_traces = run_tool_calls_parallel(
                google_tool_calls, google_runner2, max_workers=4, timeout=30
            )
            yield from _yield_tool_trace_events(sse_event, emit_tool_trace, more_traces)
            followup = append_tool_round_to_conversation(
                followup,
                last_round,
                google_tool_calls,
                more_contents,
                provider_id=provider_id,
            )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return

    if tool_name in IMAGE_GENERATION_TOOL_NAMES:
        yield from _stream_generate_image_tool_turn(
            client,
            model,
            messages,
            round_data,
            tc,
            tool_calls,
            sse_event,
            usage_out,
            image_generation_enabled=image_generation_enabled,
            image_generation_config=image_generation_config,
            providers_config=providers_config,
            plan_key=plan_key,
            image_generation_prefs=image_generation_prefs,
            image_generation_username=image_generation_username,
            image_generation_public_base_url=image_generation_public_base_url,
            user_text=user_text,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            agent_profile=agent_profile,
        )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return

    search_results = None
    if tool_name == "web_fetch":
        parsed = parse_web_fetch_tool_args(tc["function"]["arguments"])
        if not parsed:
            yield sse_event({"done": True})
            return

        reason = parsed["reason"]
        url = parsed["url"]
        page = None
        for event in stream_web_fetch(url, reason=reason):
            if event.get("type") == "done" and event.get("_page"):
                page = event["_page"]
            yield sse_event(_sse_fetch_event(event))

        context = format_fetch_context(
            page or {"url": url, "text": ""},
            user_text=user_text,
            query=reason,
        )
        assistant_msg = build_assistant_tool_message(
            round_data, tool_calls, provider_id=provider_id
        )
        tool_msg = {
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": context,
        }
        followup = strip_reasoning_content_from_messages(
            messages + [assistant_msg, tool_msg], provider_id
        )
        followup[0] = {
            "role": "system",
            "content": build_web_fetch_system_message(
                context, user_text, agent_profile=agent_profile
            ),
        }
        yield sse_event({"segment_start": True})
        recovery_hint = (
            "上記の取得ページ本文だけを根拠に、質問への回答を日本語で完成させてください。"
            "追加の web_fetch / web_search の宣言は禁止です。"
        )
        yield from _stream_followup_with_recovery(
            client,
            model,
            followup,
            user_text,
            sse_event,
            usage_out,
            emit_reasoning_cards=False,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            agent_profile=agent_profile,
            recovery_hint=recovery_hint,
            allow_recovery=False,
        )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return
    else:
        yield from stream_web_search_tool_loop(
            client,
            model,
            messages,
            round_data,
            tool_calls,
            sse_event,
            usage_out,
            user_text=user_text,
            search_engines=search_engines,
            agent_profile=agent_profile,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            computelab_active=computelab_this_turn,
            allow_web_search=allow_web_search,
            emit_tool_trace=emit_tool_trace,
            deep_research_enabled=deep_research_enabled,
            deep_research_prefs=deep_research_prefs,
            intelligent_search_override=intelligent_search_override,
        )
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(messages, "", "", model),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return


def _build_recovery_hint(user_text, agent_profile="deepseek"):
    if is_deepseek_agent_profile(agent_profile):
        recovery_hint = (
            "上記のWeb検索結果だけを根拠に、質問への回答を日本語で完成させてください。"
            "追加検索・ツール・ページ閲覧の宣言は禁止です。"
        )
        if infer_search_topic(user_text) == "llm_ranking":
            recovery_hint += (
                "ローカル実行可能なオープンウェイトLLMのランキング表（順位|モデル|根拠|情報の日付）を必ず提示。"
                "スニペットのモデル名をすべて使う。不確実なら参考候補を別枠で補足。"
            )
        elif infer_search_topic(user_text) == "software_setup":
            recovery_hint += (
                "冒頭で質問に直接答える（起動だけでマルチバージョン有効か、設定が必要か）。"
                "README・Wiki・ページ本文の記述を優先し、確認手順を箇条書きで示す。"
            )
        elif infer_search_topic(user_text) == "news":
            recovery_hint += (
                "各ニュースに Markdown リンクの出典URLを必ず付ける。"
                "[1][2] の番号脚注は禁止。末尾に「### 参考リンク」の箇条書きを付ける。"
            )
        elif infer_search_topic(user_text) == "service_status":
            recovery_hint += (
                "公式ステータス API の進行中インシデントを最優先。"
                "Investigating / Identified がある場合は「全サービス正常」と書かない。"
            )
        else:
            recovery_hint += "ランキング形式なら順位とモデル名を明示してください。"
        return recovery_hint

    recovery_hint = (
        "上記のWeb検索結果を根拠に、質問への回答を日本語で完成させてください。"
        "冒頭で質問に直接答える。[1][2] 形式の出典や「検索結果の範囲では」などのメタ前置きは禁止。"
        "参考は末尾に1行程度。追加検索・ツールの宣言は禁止。"
    )
    topic = infer_search_topic(user_text)
    if topic == "llm_ranking":
        recovery_hint += "ランキングなら簡潔な表か箇条書きで順位とモデル名を示してください。"
    elif topic == "software_setup":
        recovery_hint += (
            "マルチバージョン・設定の質問なら、起動手順と nukkit.yml 等の確認ポイントを具体的に書く。"
        )
    elif topic == "news":
        recovery_hint += (
            "各ニュース項目に Markdown リンクのURLを付ける。[1][2] 番号脚注は禁止。"
            "末尾に「### 参考リンク」を付ける。"
        )
    elif topic == "service_status":
        recovery_hint += (
            "公式ステータスの進行中インシデントを優先。障害調査中は「正常」と書かない。"
        )
    return recovery_hint


def _stream_followup_with_recovery(
    client,
    model,
    followup,
    user_text,
    sse_event,
    usage_out,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    agent_profile="deepseek",
    recovery_hint=None,
    allow_recovery=True,
    search_results=None,
):
    follow_round = None
    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
        "emit_content": not allow_recovery,
        "content_buffer": [],
    }
    for kind, payload in stream_model_round(
        client,
        model,
        followup,
        None,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)
        if kind == "end":
            follow_round = round_state["round_data"]

    follow_round, citation_events = _apply_search_citation_fix(
        follow_round, search_results
    )

    force_recovery = _must_force_answer_recovery(follow_round)
    effective_allow_recovery = allow_recovery or force_recovery
    if not effective_allow_recovery or not needs_answer_recovery(
        follow_round, user_text
    ):
        if citation_events:
            for payload in citation_events:
                yield sse_event(payload)
        else:
            for chunk in round_state.get("content_buffer") or []:
                yield sse_event({"content": chunk})
        return follow_round

    recovery = list(followup)
    hint = recovery_hint or _build_recovery_hint(user_text, agent_profile)
    if force_recovery and not allow_recovery:
        hint += (
            "\n\n【重要】DSML・XML・tool_calls 記法は本文に出力禁止。"
            "ツール呼び出し宣言なしで、検索結果に基づく日本語の最終回答のみ完成させてください。"
        )
    recovery.append({"role": "user", "content": hint})
    yield sse_event({"segment_start": True, "discard_previous": True})
    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
    }
    for kind, payload in stream_model_round(
        client,
        model,
        recovery,
        None,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)
        if kind == "end":
            follow_round = round_state["round_data"]
    if follow_round is not None:
        follow_round, citation_events = _apply_search_citation_fix(
            follow_round, search_results
        )
    else:
        citation_events = []
    for payload in citation_events:
        yield sse_event(payload)
    return follow_round


def _apply_search_citation_fix(follow_round, search_results):
    if not search_results or not follow_round:
        return follow_round, []
    original = (follow_round.get("content") or "").strip()
    if not original:
        return follow_round, []
    from model_sanitize import improve_readability

    fixed = improve_readability(
        fix_search_answer_citations(original, search_results)
    )
    if not fixed or fixed == original:
        return follow_round, []
    updated = dict(follow_round)
    updated["content"] = fixed
    events = [{"content_replace": fixed}]
    return updated, events
