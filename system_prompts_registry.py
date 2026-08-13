"""Catalog of built-in system prompts for admin inspection."""

from __future__ import annotations


def _entry(
    entry_id,
    name,
    category,
    source,
    symbol,
    content,
    *,
    dynamic=False,
    condition="",
):
    text = content or ""
    return {
        "id": entry_id,
        "name": name,
        "category": category,
        "source": source,
        "symbol": symbol,
        "dynamic": bool(dynamic),
        "condition": condition,
        "content": text,
        "char_count": len(text),
        "line_count": text.count("\n") + (1 if text else 0),
    }


def list_system_prompts():
    from chat_agent import (
        AGENT_SYSTEM_PROMPT,
        AGENT_SYSTEM_PROMPT_NO_SEARCH,
        AGENT_SYSTEM_PROMPT_NO_SEARCH_STANDARD,
        AGENT_SYSTEM_PROMPT_STANDARD,
    )
    from computelab_agent_tools import computelab_system_prompt_append
    from cost_performance import cost_performance_system_prompt_append
    from custom_agents_storage import build_custom_agent_system_append
    from deep_research import deep_research_system_prompt_append
    from expert_agent_tools import expert_system_prompt_append
    from expert_chat_agent import EXPERT_BASE_PROMPT, build_expert_creation_system_message
    from expert_crawler import _DEFAULT_SYSTEM_PROMPT
    from google_agent_tools import google_system_prompt_append
    from image_generation_agent_tools import (
        build_image_generation_followup_system,
        image_generation_system_prompt_append,
    )
    from image_ocr import OCR_CHAT_SYSTEM_APPEND, OCR_SYSTEM_PROMPT
    from memory_agent_tools import memory_system_prompt_append
    from pdf_extract import PDF_CHAT_SYSTEM_APPEND
    from project_chat_agent import MODE_PROMPTS, PROJECT_BASE_PROMPT
    from tasks_agent_tools import tasks_system_prompt_append
    from user_question_agent_tools import ask_user_system_prompt_append
    from web_fetch import build_web_fetch_system_message
    from web_search import (
        build_web_search_system_message,
        web_search_system_prompt_multi_append,
    )

    prompts = [
        _entry(
            "agent_deepseek_search",
            "チャットエージェント（DeepSeek・検索あり）",
            "チャット",
            "chat_agent.py",
            "AGENT_SYSTEM_PROMPT",
            AGENT_SYSTEM_PROMPT,
            condition="agent_profile=deepseek, Web検索または連携ツール有効",
        ),
        _entry(
            "agent_deepseek_no_search",
            "チャットエージェント（DeepSeek・検索なし）",
            "チャット",
            "chat_agent.py",
            "AGENT_SYSTEM_PROMPT_NO_SEARCH",
            AGENT_SYSTEM_PROMPT_NO_SEARCH,
            condition="agent_profile=deepseek, Web検索・連携ツールなし",
        ),
        _entry(
            "agent_standard_search",
            "チャットエージェント（標準・検索あり）",
            "チャット",
            "chat_agent.py",
            "AGENT_SYSTEM_PROMPT_STANDARD",
            AGENT_SYSTEM_PROMPT_STANDARD,
            condition="agent_profile≠deepseek, Web検索または連携ツール有効",
        ),
        _entry(
            "agent_standard_no_search",
            "チャットエージェント（標準・検索なし）",
            "チャット",
            "chat_agent.py",
            "AGENT_SYSTEM_PROMPT_NO_SEARCH_STANDARD",
            AGENT_SYSTEM_PROMPT_NO_SEARCH_STANDARD,
            condition="agent_profile≠deepseek, Web検索・連携ツールなし",
        ),
        _entry(
            "agent_integrations_only",
            "連携ツールのみ（Web検索無効時の追記）",
            "チャット追記",
            "chat_agent.py",
            "agent_system_message",
            "\n\n【制限】web_search と web_fetch は無効です。"
            "Google・TASKS・メモリ・ComputeLab など、下記の連携ツールのみ使用してください。",
            dynamic=True,
            condition="allow_web_search=False かつ連携ツール有効",
        ),
        _entry(
            "agent_computelab_priority",
            "ComputeLab 優先（追記）",
            "チャット追記",
            "chat_agent.py",
            "agent_system_message",
            "\n\n【ComputeLab 優先】\n"
            "ユーザーが ComputeLab / computelab での作業を依頼しているとき、"
            "外部VPSの調査に流れず computelab_catalog から着手する。"
            "web_search は Paper・Via 等のバージョン情報に限定する。"
            "詳細は docs/COMPUTELAB.md（リポジトリ内）を参照。\n",
            dynamic=True,
            condition="computelab_enabled=True",
        ),
        _entry(
            "agent_location_hint",
            "位置情報ヒント（追記）",
            "チャット追記",
            "chat_agent.py",
            "prepare_agent_messages",
            "\n\nユーザーのおおよその位置: {location_hint}"
            "（市区町村レベル。正確な住所は不明）",
            dynamic=True,
            condition="location_hint が指定されたとき",
        ),
        _entry(
            "agent_user_urls",
            "ユーザー指定URL（追記）",
            "チャット追記",
            "chat_agent.py",
            "prepare_agent_messages",
            "\n\n【ユーザー指定URL】内容を答えるには web_fetch で取得する:\n"
            "- https://example.com/page",
            dynamic=True,
            condition="ユーザーメッセージに URL が含まれるとき",
        ),
        _entry(
            "agent_datetime",
            "現在日時（追記）",
            "チャット追記",
            "chat_agent.py",
            "agent_system_message",
            "\n\n現在日時（サーバー）: {YYYY-MM-DD HH:MM}",
            dynamic=True,
            condition="毎リクエストでサーバー日時を付与",
        ),
        _entry(
            "append_google_calendar",
            "Googleカレンダー連携",
            "チャット追記",
            "google_agent_tools.py",
            "google_system_prompt_append",
            google_system_prompt_append(calendar_enabled=True, gmail_enabled=False),
            dynamic=True,
            condition="google_calendar_enabled=True",
        ),
        _entry(
            "append_google_gmail",
            "Gmail連携",
            "チャット追記",
            "google_agent_tools.py",
            "google_system_prompt_append",
            google_system_prompt_append(calendar_enabled=False, gmail_enabled=True),
            dynamic=True,
            condition="google_gmail_enabled=True",
        ),
        _entry(
            "append_tasks",
            "TASKSホワイトボード",
            "チャット追記",
            "tasks_agent_tools.py",
            "tasks_system_prompt_append",
            tasks_system_prompt_append(),
            dynamic=True,
            condition="tasks_enabled=True",
        ),
        _entry(
            "append_memory",
            "メモリ（試験）",
            "チャット追記",
            "memory_agent_tools.py",
            "memory_system_prompt_append",
            memory_system_prompt_append(),
            dynamic=True,
            condition="memory_enabled=True（ユーザー別の保存済みメモリも動的に付与）",
        ),
        _entry(
            "append_computelab",
            "ComputeLab連携",
            "チャット追記",
            "computelab_agent_tools.py",
            "computelab_system_prompt_append",
            computelab_system_prompt_append(),
            dynamic=True,
            condition="computelab_enabled=True",
        ),
        _entry(
            "append_image_generation",
            "画像生成",
            "チャット追記",
            "image_generation_agent_tools.py",
            "image_generation_system_prompt_append",
            image_generation_system_prompt_append(),
            dynamic=True,
            condition="image_generation_enabled=True",
        ),
        _entry(
            "append_ask_user",
            "ユーザーへの質問",
            "チャット追記",
            "user_question_agent_tools.py",
            "ask_user_system_prompt_append",
            ask_user_system_prompt_append(),
            dynamic=True,
            condition="user_questions_enabled=True",
        ),
        _entry(
            "append_cost_performance",
            "コストパフォーマンス最大化",
            "チャット追記",
            "cost_performance.py",
            "cost_performance_system_prompt_append",
            cost_performance_system_prompt_append(),
            dynamic=True,
            condition="cost_performance_maximized=True",
        ),
        _entry(
            "append_web_search_multi",
            "複数回Web検索",
            "チャット追記",
            "web_search.py",
            "web_search_system_prompt_multi_append",
            web_search_system_prompt_multi_append(),
            dynamic=True,
            condition="Web検索有効かつ複数検索が必要な文脈",
        ),
        _entry(
            "append_deep_research",
            "DeepResearch",
            "チャット追記",
            "deep_research.py",
            "deep_research_system_prompt_append",
            deep_research_system_prompt_append(5),
            dynamic=True,
            condition="deep_research_enabled=True（max_search_rounds は設定依存）",
        ),
        _entry(
            "append_ocr",
            "添付画像（OCR）",
            "チャット追記",
            "image_ocr.py",
            "OCR_CHAT_SYSTEM_APPEND",
            OCR_CHAT_SYSTEM_APPEND,
            dynamic=True,
            condition="メッセージに OCR 抽出テキストが含まれるとき",
        ),
        _entry(
            "append_pdf",
            "添付PDF",
            "チャット追記",
            "pdf_extract.py",
            "PDF_CHAT_SYSTEM_APPEND",
            PDF_CHAT_SYSTEM_APPEND,
            dynamic=True,
            condition="メッセージに PDF 抽出テキストが含まれるとき",
        ),
        _entry(
            "append_custom_agent",
            "カスタムエージェント",
            "チャット追記",
            "custom_agents_storage.py",
            "build_custom_agent_system_append",
            build_custom_agent_system_append(
                {
                    "name": "サンプルエージェント",
                    "description": "管理者向けプレビュー用のサンプルです。",
                    "instructions": "簡潔で丁寧に答えてください。",
                    "knowledge_items": [],
                }
            ),
            dynamic=True,
            condition="カスタムエージェント選択時（実際の内容はエージェント定義に依存）",
        ),
        _entry(
            "round_web_search_deepseek",
            "Web検索ラウンド（DeepSeek）",
            "ツールラウンド",
            "web_search.py",
            "build_web_search_system_message",
            build_web_search_system_message(
                "（Web検索結果サンプル）\n"
                "- example.com | ページタイトル | スニペット本文…",
                user_text="",
                agent_profile="deepseek",
            ),
            dynamic=True,
            condition="web_search ツール実行後の follow-up ラウンド",
        ),
        _entry(
            "round_web_search_standard",
            "Web検索ラウンド（標準）",
            "ツールラウンド",
            "web_search.py",
            "build_web_search_system_message",
            build_web_search_system_message(
                "（Web検索結果サンプル）\n"
                "- example.com | ページタイトル | スニペット本文…",
                user_text="",
                agent_profile="standard",
            ),
            dynamic=True,
            condition="web_search ツール実行後（非 DeepSeek プロファイル）",
        ),
        _entry(
            "round_web_fetch",
            "Webページ取得ラウンド",
            "ツールラウンド",
            "web_fetch.py",
            "build_web_fetch_system_message",
            build_web_fetch_system_message(
                "（取得ページ本文サンプル）\n# タイトル\n本文テキスト…",
                user_text="",
                agent_profile="deepseek",
            ),
            dynamic=True,
            condition="web_fetch ツール実行後の follow-up ラウンド",
        ),
        _entry(
            "round_image_generation",
            "画像生成フォローアップ",
            "ツールラウンド",
            "image_generation_agent_tools.py",
            "build_image_generation_followup_system",
            build_image_generation_followup_system(
                "画像生成が完了しました（モデル: FLUX 2.0）。\n"
                "プロンプト: sample prompt\n"
                "画像URL: https://example.com/image.png",
                user_text="",
            ),
            dynamic=True,
            condition="generate_image ツール実行後",
        ),
        _entry(
            "project_base",
            "プロジェクト（共通）",
            "プロジェクト",
            "project_chat_agent.py",
            "PROJECT_BASE_PROMPT",
            PROJECT_BASE_PROMPT,
        ),
        *[
            _entry(
                f"project_mode_{mode}",
                f"プロジェクト・{mode}",
                "プロジェクト",
                "project_chat_agent.py",
                f"MODE_PROMPTS[{mode!r}]",
                text,
                condition=f"mode={mode}",
            )
            for mode, text in MODE_PROMPTS.items()
        ],
        _entry(
            "expert_base",
            "Expert（共通）",
            "Expert",
            "expert_chat_agent.py",
            "EXPERT_BASE_PROMPT",
            EXPERT_BASE_PROMPT,
        ),
        _entry(
            "expert_tools_chat",
            "Expertツール追記（チャット）",
            "Expert",
            "expert_agent_tools.py",
            "expert_system_prompt_append",
            expert_system_prompt_append(creation_mode="chat"),
            dynamic=True,
            condition="creation_mode=chat",
        ),
        _entry(
            "expert_tools_crawl",
            "Expertツール追記（クロール）",
            "Expert",
            "expert_agent_tools.py",
            "expert_system_prompt_append",
            expert_system_prompt_append(creation_mode="crawl"),
            dynamic=True,
            condition="creation_mode=crawl",
        ),
        _entry(
            "expert_creation_sample",
            "Expert作成（組み立て例）",
            "Expert",
            "expert_chat_agent.py",
            "build_expert_creation_system_message",
            build_expert_creation_system_message(
                {
                    "id": "sample-expert-id",
                    "name": "サンプル専門家",
                    "description": "管理者向けプレビュー",
                    "instructions": "専門分野に沿って回答する",
                },
                creation_mode="chat",
                username=None,
                expert_id="sample-expert-id",
            ),
            dynamic=True,
            condition="Expert セッション（専門家定義・知識ベースは動的）",
        ),
        _entry(
            "ocr_api",
            "OCR API（画像文字抽出）",
            "OCR / PDF",
            "image_ocr.py",
            "OCR_SYSTEM_PROMPT",
            OCR_SYSTEM_PROMPT,
            condition="画像 OCR 専用 API 呼び出し",
        ),
        _entry(
            "crawler_summarize",
            "Expertクローラー要約",
            "Expert",
            "expert_crawler.py",
            "_DEFAULT_SYSTEM_PROMPT",
            _DEFAULT_SYSTEM_PROMPT,
            condition="expert_crawl_site によるページ要約",
        ),
    ]

    categories = []
    seen = set()
    for item in prompts:
        cat = item["category"]
        if cat not in seen:
            seen.add(cat)
            categories.append(cat)

    return {
        "prompts": prompts,
        "categories": categories,
        "total": len(prompts),
    }
