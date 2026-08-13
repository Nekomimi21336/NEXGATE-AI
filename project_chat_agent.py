from datetime import datetime

from chat_agent import stream_chat_completion

PROJECT_CHAT_MODES = frozenset({"agent", "multitask", "chat", "plan", "ask"})

PROJECT_BASE_PROMPT = """あなたは NEXGATE AI プロジェクトスペース専用のアシスタントです。
通常のチャット画面とは別系統のワークスペースで動作します。

共通ルール:
- プロジェクト名・説明・これまでの会話を文脈として最優先する
- このワークスペースでは Web 検索、外部ツール、メモリ、TASKS、Google 連携は使わない
- 推測でプロジェクト外の前提を足さない
- ユーザーが使う言語で回答する（通常は日本語）
- 読みやすい段落と箇条書きを適宜使う
- DSML や XML 風の tool_calls 記法を本文に出力しない"""

MODE_PROMPTS = {
    "agent": """【モード: Agent】
自律的にプロジェクトを前に進めるパートナーとして振る舞う。
- 目的の再確認、次のアクション、実行ステップ、判断ポイントを提案する
- 必要なら短期プランと中長期の分岐を示す
- 会話だけで終わらず、前に進むための具体案を出す""",
    "multitask": """【モード: MultiTask】
複数の論点・タスク・並行作業を整理して扱う。
- タスクごとに見出しや番号で区切る
- 優先度、依存関係、並行可能な作業を明示する
- 一度に扱う項目が多いときは整理してから回答する""",
    "chat": """【モード: Chat】
自然な会話形式で、簡潔かつ有用に答える。
- 必要以上に構造化しすぎない
- 雑談や短い質問には短く返す
- 深掘りが必要なときだけ詳述する""",
    "plan": """【モード: Plan】
計画立案に特化して回答する。
- 目標、前提、マイルストーン、依存関係、リスク、次の一手を整理する
- 実行前に計画を固めることに集中する
- 実装や詳細作業より、計画の骨子と順序を優先する""",
    "ask": """【モード: Ask】
質問への直接回答に特化する。
- 端的で正確な答えを優先する
- 不要な提案や長い前置きを避ける
- 不明点は短く確認し、確かな範囲だけ答える""",
}


def normalize_project_mode(mode):
    normalized = (mode or "chat").strip().lower()
    return normalized if normalized in PROJECT_CHAT_MODES else "chat"


def build_project_system_message(project, mode="chat"):
    name = (project.get("name") or "").strip() or "Untitled"
    description = (project.get("description") or "").strip()
    mode_key = normalize_project_mode(mode)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    parts = [
        PROJECT_BASE_PROMPT,
        MODE_PROMPTS[mode_key],
        f"プロジェクト名: {name}",
    ]
    if description:
        parts.append(f"プロジェクト説明: {description}")

    settings = project.get("settings") if isinstance(project.get("settings"), dict) else {}
    status = (settings.get("status") or "active").strip().lower()
    if status == "paused":
        parts.append("【プロジェクト状態】一時停止中。新しい作業提案は控えめにし、既存文脈の整理に集中する。")
    elif status == "archived":
        parts.append("【プロジェクト状態】アーカイブ済み。参照と要約を優先し、新規タスクの開始は避ける。")

    scope = (settings.get("scope") or "").strip()
    if scope:
        parts.append(f"プロジェクトスコープ: {scope}")

    custom = (settings.get("custom_instructions") or "").strip()
    if custom:
        parts.append(f"追加指示:\n{custom}")

    tools = settings.get("tools") if isinstance(settings.get("tools"), dict) else {}
    enabled_tools = [key for key, on in tools.items() if on]
    if enabled_tools:
        parts.append(
            "プロジェクトで有効化されたツール設定: "
            + ", ".join(enabled_tools)
            + "（アカウント側でも有効な場合のみ将来利用可能）"
        )

    parts.append(f"現在日時（サーバー）: {now}")
    return "\n\n".join(parts)


def prepare_project_chat_messages(project, mode="chat"):
    system = {
        "role": "system",
        "content": build_project_system_message(project, mode),
    }
    history = []
    for item in project.get("messages") or []:
        role = (item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        history.append({"role": role, "content": content})
    return [system, *history]


def stream_project_chat(
    project,
    mode,
    api_key,
    model,
    make_client,
    sse_event,
    usage_out=None,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    reasoning_in_english=False,
    filter_messages_fn=None,
):
    messages = prepare_project_chat_messages(project, mode)
    if filter_messages_fn:
        messages = filter_messages_fn(messages, provider_id=provider_id)
    yield from stream_chat_completion(
        messages,
        api_key=api_key,
        model=model,
        make_client=make_client,
        sse_event=sse_event,
        usage_out=usage_out,
        emit_reasoning_cards=emit_reasoning_cards,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        reasoning_in_english=reasoning_in_english,
    )
