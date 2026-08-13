#!/usr/bin/env python
"""
sandbox.py - AI対話フロー検証ツール
chat_agent.py の全ツールシステムを数ターンにわたって監視・評価する。
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime

# --- Environment setup ---
os.environ.setdefault("FLASK_PORT", "15002")
os.environ.setdefault("FRONTEND_BASE_URL", "http://127.0.0.1:5000")
os.environ.setdefault("API_PORTAL_BASE_URL", "http://127.0.0.1:5001")
os.environ.setdefault("API_INTERNAL_URL", "http://127.0.0.1:5002")

# UTF-8出力を強制
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

# Enable timing logs
import logging
logging.getLogger("chat_agent.timing").setLevel(logging.INFO)
_timing_handler = logging.StreamHandler(sys.stdout)
_timing_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S"))
logging.getLogger("chat_agent.timing").addHandler(_timing_handler)
logging.getLogger("chat_agent.timing").propagate = False

# --- Flask app context ---
from app import app as flask_app
app_ctx = flask_app.app_context()
app_ctx.push()

# --- Imports ---
from app import load_system_config, load_users
from chat_agent import (
    _stream_agent_chat_body,
    empty_usage,
)
from model_registry import (
    resolve_chat_model,
    normalize_model_entry,
    make_openai_client_for_provider,
)


# ============================================================
# 設定
# ============================================================
config = load_system_config()
models_cfg = config.get("models") or {}
MODEL_ID = list(models_cfg.keys())[0] if models_cfg else "deepseek-v4-flash"

resolved = resolve_chat_model(MODEL_ID, config)
PROVIDER_ID = resolved["provider"]
API_MODEL = resolved["api_model"]
AGENT_PROFILE = resolved["agent_profile"]
CATALOG_MODEL_ENTRY = models_cfg.get(MODEL_ID) or normalize_model_entry(MODEL_ID, {})

# クライアント生成
client, api_key = make_openai_client_for_provider(PROVIDER_ID, config.get("providers"))

# make_client callable
def _make_client(key):
    from app import make_openai_client
    return make_openai_client(key)

print(f"=== NEXGATE AI Sandbox ===")
print(f"Model: {API_MODEL} (provider={PROVIDER_ID}, profile={AGENT_PROFILE})")
print(f"API Key: {'***' + api_key[-4:] if api_key else 'NOT SET'}")
if not api_key:
    print("ERROR: API key not found. Set OPENAI_API_KEY in .env or environment.")
    sys.exit(1)
print()


# ============================================================
# テストシナリオ（多様なシチュエーション）
# ============================================================
TEST_SCENARIOS = [
    # ── 基本対話 ──
    {
        "name": "T01: 挨拶（ツール不要）",
        "messages": [{"role": "user", "content": "こんにちは"}],
        "expect": "ツールなしで自然な応答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T02: 感謝（ツール不要）",
        "messages": [{"role": "user", "content": "ありがとう！助かった"}],
        "expect": "ツールなしで自然な応答",
        "tools_enabled": {"web_search": True},
    },
    # ── 検索が必要な質問 ──
    {
        "name": "T03: 現在の役職者",
        "messages": [{"role": "user", "content": "今の日本の総理大臣は誰？"}],
        "expect": "web_search 呼出",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T04: 天気",
        "messages": [{"role": "user", "content": "今日の東京の天気は？"}],
        "expect": "web_search 呼出",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T05: 株価",
        "messages": [{"role": "user", "content": "日経平均株価の現在値を教えて"}],
        "expect": "web_search 呼出",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T06: 製品スペック",
        "messages": [{"role": "user", "content": "NB-RT-8127F-S Realtek RTL8127 について調べて"}],
        "expect": "web_search 呼出",
        "tools_enabled": {"web_search": True},
    },
    # ── 検索不要な質問 ──
    {
        "name": "T07: 数学",
        "messages": [{"role": "user", "content": "微分方程式 dy/dx = x^2 を解いて"}],
        "expect": "ツールなしで回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T08: プログラミング",
        "messages": [{"role": "user", "content": "Pythonでリストを逆順にする方法を教えて"}],
        "expect": "ツールなしで回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T09: 翻訳",
        "messages": [{"role": "user", "content": "「こんにちは」を英語に翻訳して"}],
        "expect": "ツールなしで回答",
        "tools_enabled": {"web_search": True},
    },
    # ── URL指定 ──
    {
        "name": "T10: URL要約",
        "messages": [{"role": "user", "content": "https://www.python.org の内容を要約して"}],
        "expect": "web_fetch 呼出",
        "tools_enabled": {"web_search": True},
    },
    # ── マルチターン ──
    {
        "name": "T11: 文脈維持",
        "messages": [
            {"role": "user", "content": "こんにちは"},
            {"role": "assistant", "content": "こんにちは！何かお手伝いします。"},
            {"role": "user", "content": "さっきの質問覚えてる？"},
        ],
        "expect": "文脈を踏まえた応答",
        "tools_enabled": {"web_search": False},
    },
    # ── ツール無効時 ──
    {
        "name": "T12: 検索無効時の質問",
        "messages": [{"role": "user", "content": "最新のAIニュースを教えて"}],
        "expect": "ツールなしで回答（検索不可を説明）",
        "tools_enabled": {"web_search": False},
    },
    # ── エッジケース ──
    {
        "name": "T13: 曖昧な質問",
        "messages": [{"role": "user", "content": "それってどういう意味？"}],
        "expect": "文脈なしで丁寧に確認",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T14: 長文質問",
        "messages": [{"role": "user", "content": "以下の文章を要約してください。\n\n" + "これはテスト用の長文です。" * 50}],
        "expect": "要約を返す",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T15: コード生成",
        "messages": [{"role": "user", "content": "Pythonでフィボナッチ数列を生成する関数を書いて"}],
        "expect": "コードブロックで回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T16: 表形式の質問",
        "messages": [{"role": "user", "content": "主要なプログラミング言語の特徴を表で比較して"}],
        "expect": "表形式で回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T17: 数式を含む質問",
        "messages": [{"role": "user", "content": "オイラーの公式 $e^{i\\pi} + 1 = 0$ について説明して"}],
        "expect": "数式を含む回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T18: 複数質問",
        "messages": [{"role": "user", "content": "PythonとJavaScriptの違いは？あと、どっちが初心者向け？"}],
        "expect": "両方の質問に回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T19: 否定形の質問",
        "messages": [{"role": "user", "content": "Pythonは遅くないですか？"}],
        "expect": "バランスの取れた回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T20: 比較質問",
        "messages": [{"role": "user", "content": "ReactとVue.js、どちらが良いですか？"}],
        "expect": "比較検討した回答",
        "tools_enabled": {"web_search": True},
    },
    # ── 長期マルチターン（実際のユーザー行動を想定） ──
    {
        "name": "T21: 長期会話 - 技術相談の流れ",
        "messages": [
            {"role": "user", "content": "PythonでWebアプリを作りたい"},
            {"role": "assistant", "content": "FlaskやDjangoがおすすめです。どのようなアプリですか？"},
            {"role": "user", "content": "タスク管理アプリです"},
            {"role": "assistant", "content": "Flaskが軽量でおすすめです。データベースはSQLiteから始められます。"},
            {"role": "user", "content": "ユーザー認証も必要です"},
            {"role": "assistant", "content": "Flask-Loginを使うと簡単です。パスワードハッシュ化も忘れずに。"},
            {"role": "user", "content": "デプロイはどうすれば？"},
        ],
        "expect": "文脈を踏まえたデプロイ方法の提案",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T22: 長期会話 - 学習サポート",
        "messages": [
            {"role": "user", "content": "機械学習を勉強したい"},
            {"role": "assistant", "content": "まずPythonの基礎から始めましょう。NumPyとPandasを覚えると良いです。"},
            {"role": "user", "content": "NumPyって何？"},
            {"role": "assistant", "content": "数値計算ライブラリです。配列操作が高速です。"},
            {"role": "user", "content": "Pandasは？"},
            {"role": "assistant", "content": "データ分析ライブラリです。表形式データを扱いやすいです。"},
            {"role": "user", "content": "次は何を勉強すればいい？"},
        ],
        "expect": "学習ロードマップの提案",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T23: 長期会話 - トラブルシューティング",
        "messages": [
            {"role": "user", "content": "Pythonでエラーが出ました"},
            {"role": "assistant", "content": "どのようなエラーですか？メッセージを教えてください。"},
            {"role": "user", "content": "ModuleNotFoundError: No module named 'requests'"},
            {"role": "assistant", "content": "requestsモジュールがインストールされていません。pip install requests を実行してください。"},
            {"role": "user", "content": "インストールしましたがまだエラーです"},
            {"role": "assistant", "content": "仮想環境が有効になっているか確認してください。which python でパスを確認できます。"},
            {"role": "user", "content": "仮想環境を有効にしたら解決しました！"},
        ],
        "expect": "問題解決の確認と次のステップ",
        "tools_enabled": {"web_search": False},
    },
    {
        "name": "T24: 長期会話 - 創作支援",
        "messages": [
            {"role": "user", "content": "小説を書きたい"},
            {"role": "assistant", "content": "どのようなジャンルですか？SF、ファンタジー、ミステリーなど。"},
            {"role": "user", "content": "SFです。宇宙船が舞台です"},
            {"role": "assistant", "content": "宇宙船内の閉鎖空間での人間ドラマですね。キャラクター設定から始めましょう。"},
            {"role": "user", "content": "主人公はエンジニアです"},
            {"role": "assistant", "content": "技術的な問題に直面するエンジニアの視点は面白いですね。どのような問題が起こりますか？"},
            {"role": "user", "content": "生命維持装置の故障です"},
        ],
        "expect": "物語の展開提案",
        "tools_enabled": {"web_search": False},
    },
    {
        "name": "T25: 長期会話 - 調べ物の深掘り",
        "messages": [
            {"role": "user", "content": "量子コンピュータについて教えて"},
            {"role": "assistant", "content": "量子ビットを使った次世代コンピュータです。従来のビットと異なり、0と1の重ね合わせ状態を利用します。"},
            {"role": "user", "content": "具体的にどんな計算が速いの？"},
            {"role": "assistant", "content": "因数分解や最適化問題が得意です。Shorのアルゴリズムが有名です。"},
            {"role": "user", "content": "実用化はいつ頃？"},
        ],
        "expect": "最新動向の検索と回答",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T26: 長期会話 - 複数話題の切り替え",
        "messages": [
            {"role": "user", "content": "今日の天気は？"},
            {"role": "assistant", "content": "東京は晴れです。最高気温は32度です。"},
            {"role": "user", "content": "ありがとう。ところで、Pythonのリストについて教えて"},
            {"role": "assistant", "content": "リストは順序付きの変更可能なコレクションです。append()で要素を追加できます。"},
            {"role": "user", "content": "辞書との違いは？"},
            {"role": "assistant", "content": "辞書はキーと値のペアです。リストはインデックスでアクセス、辞書はキーでアクセスします。"},
            {"role": "user", "content": "明日の天気も教えて"},
        ],
        "expect": "話題切り替え後も正しく検索",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T27: 長期会話 - 段階的な詳細化",
        "messages": [
            {"role": "user", "content": "Web開発を学びたい"},
            {"role": "assistant", "content": "HTML/CSS/JavaScriptの基礎から始めましょう。"},
            {"role": "user", "content": "HTMLは分かります"},
            {"role": "assistant", "content": "ではCSSのレイアウトから。FlexboxとGridが重要です。"},
            {"role": "user", "content": "Flexboxとは？"},
            {"role": "assistant", "content": "1次元のレイアウトシステムです。要素を横並びや縦並びに柔軟に配置できます。"},
            {"role": "user", "content": "Gridとの違いは？"},
            {"role": "assistant", "content": "Gridは2次元（行と列）のレイアウトです。Flexboxは1次元です。"},
            {"role": "user", "content": "実際にコードを書いてみたい"},
        ],
        "expect": "実践的なコード例の提供",
        "tools_enabled": {"web_search": False},
    },
    {
        "name": "T28: 長期会話 - 意見の変化",
        "messages": [
            {"role": "user", "content": "Reactを学ぶべきか迷ってる"},
            {"role": "assistant", "content": "Reactは人気があり求人数も多いです。Vue.jsも検討してみては？"},
            {"role": "user", "content": "Vue.jsの方が簡単そう"},
            {"role": "assistant", "content": "確かにVue.jsは学習曲線が緩やかです。小規模プロジェクトから始めやすいです。"},
            {"role": "user", "content": "でもReactの方が将来性がある？"},
            {"role": "assistant", "content": "Reactのエコシステムは大きく、長期的なキャリアには有利です。"},
            {"role": "user", "content": "やっぱりReactにします"},
        ],
        "expect": "意見の変化を受け入れた上での助言",
        "tools_enabled": {"web_search": False},
    },
    {
        "name": "T29: 長期会話 - 複雑な技術的議論",
        "messages": [
            {"role": "user", "content": "マイクロサービスとモノリス、どちらが良い？"},
            {"role": "assistant", "content": "規模によります。小規模ならモノリス、大規模ならマイクロサービスが適しています。"},
            {"role": "user", "content": "うちは中規模です"},
            {"role": "assistant", "content": "中規模ならモジュラーモノリスがおすすめです。段階的にマイクロサービスに移行できます。"},
            {"role": "user", "content": "データベースは共有すべき？"},
            {"role": "assistant", "content": "マイクロサービスでは各サービスが独自のDBを持つべきです。共有DBは結合度を高めます。"},
            {"role": "user", "content": "トランザクションはどうする？"},
        ],
        "expect": "分散トランザクションの説明",
        "tools_enabled": {"web_search": True},
    },
    {
        "name": "T30: 長期会話 - 感情的なやり取り",
        "messages": [
            {"role": "user", "content": "プログラミングが難しくて挫折しそう"},
            {"role": "assistant", "content": "誰でも最初は難しく感じます。小さな成功体験を積み重ねましょう。"},
            {"role": "user", "content": "何から始めればいい？"},
            {"role": "assistant", "content": "簡単な計算機アプリから始めるのはどうでしょう。足し算・引き算だけのものです。"},
            {"role": "user", "content": "できた！"},
            {"role": "assistant", "content": "素晴らしい！次は掛け算・割り算を追加してみましょう。"},
            {"role": "user", "content": "もっと複雑なものに挑戦したい"},
        ],
        "expect": "励ましと次のステップ提案",
        "tools_enabled": {"web_search": False},
    },
    # ── 履歴要約機能の検証 ──
    {
        "name": "T31: 履歴要約 - 長い会話の継続",
        "messages": [
            # 20ターンの長い会話履歴をシミュレート
            *[{"role": "user", "content": f"質問{i}: Pythonについて教えて"} for i in range(1, 11)],
            *[{"role": "assistant", "content": f"回答{i}: Pythonは汎用プログラミング言語です。"} for i in range(1, 11)],
            {"role": "user", "content": "これまでの話を踏まえて、Pythonの最大の特徴は？"},
        ],
        "expect": "要約された履歴を踏まえた回答",
        "tools_enabled": {"web_search": False},
    },
    {
        "name": "T32: 履歴要約 - トークン削減の確認",
        "messages": [
            # 非常に長い会話履歴
            *[{"role": "user", "content": f"長い質問{i}: " + "あ" * 500} for i in range(1, 6)],
            *[{"role": "assistant", "content": f"長い回答{i}: " + "い" * 500} for i in range(1, 6)],
            {"role": "user", "content": "要約されましたか？"},
        ],
        "expect": "履歴が要約されてトークン数が削減されている",
        "tools_enabled": {"web_search": False},
    },
]


# ============================================================
# 監視・評価エンジン
# ============================================================
class TurnMonitor:
    """1ターンの実行を監視し、イベントを収集する"""

    def __init__(self, scenario_name):
        self.name = scenario_name
        self.events = []
        self.content_parts = []
        self.reasoning_parts = []
        self.tool_calls_made = []
        self.errors = []
        self.warnings = []
        self.started_at = None
        self.ended_at = None
        self.done_received = False
        self.total_tokens = None
        self.usage_history = []

    def sse_event(self, payload):
        if not isinstance(payload, dict):
            return payload
        self.events.append(payload)

        if payload.get("content"):
            self.content_parts.append(payload["content"])
        if payload.get("reasoning") and isinstance(payload["reasoning"], dict):
            if payload["reasoning"].get("type") == "delta":
                self.reasoning_parts.append(payload["reasoning"].get("text", ""))
        if payload.get("search"):
            search = payload["search"]
            if search.get("type") == "intent":
                self.tool_calls_made.append({
                    "tool": "web_search",
                    "reason": search.get("reason", ""),
                    "queries": search.get("queries", []),
                })
        if payload.get("fetch"):
            self.tool_calls_made.append({
                "tool": "web_fetch",
                "event": {k: v for k, v in payload["fetch"].items() if k != "_page"},
            })
        if payload.get("tool_trace"):
            tt = payload["tool_trace"]
            self.tool_calls_made.append({
                "tool": tt.get("name", "unknown"),
                "label": tt.get("label", ""),
                "duration_ms": tt.get("duration_ms", 0),
                "ok": tt.get("ok", True),
                "error": tt.get("error"),
            })
        if payload.get("error"):
            self.errors.append(payload["error"])
        if payload.get("done"):
            self.done_received = True
            if payload.get("usage"):
                self.total_tokens = payload["usage"].get("total_tokens", 0)
        if payload.get("usage"):
            self.usage_history.append(payload["usage"])

        return payload

    def start(self):
        self.started_at = time.perf_counter()

    def end(self):
        self.ended_at = time.perf_counter()

    @property
    def elapsed_ms(self):
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at) * 1000
        return 0

    @property
    def full_content(self):
        return "".join(self.content_parts)

    @property
    def full_reasoning(self):
        return "".join(self.reasoning_parts)

    def summary(self):
        lines = []
        lines.append(f"  ⏱  elapsed: {self.elapsed_ms:.0f}ms")
        lines.append(f"  📝 content: {len(self.full_content)} chars")
        if self.full_reasoning:
            lines.append(f"  🧠 reasoning: {len(self.full_reasoning)} chars")
        lines.append(f"  🔧 tool_calls: {len(self.tool_calls_made)}")
        for tc in self.tool_calls_made:
            label = tc.get("label") or tc.get("tool") or "?"
            dur = tc.get("duration_ms", 0)
            ok = "✅" if tc.get("ok", True) else "❌"
            extra = ""
            if tc.get("queries"):
                extra = f" queries={tc['queries']}"
            if tc.get("reason"):
                extra += f" reason={tc['reason'][:60]}"
            if tc.get("error"):
                extra += f" error={tc['error']}"
            lines.append(f"     {ok} {label} ({dur:.0f}ms){extra}")
        lines.append(f"  ✅ done: {self.done_received}")
        if self.total_tokens:
            lines.append(f"  🔢 tokens: {self.total_tokens}")
        if self.errors:
            lines.append(f"  ❌ errors: {len(self.errors)}")
            for e in self.errors:
                lines.append(f"     - {str(e)[:120]}")
        return "\n".join(lines)


# ============================================================
# 実行エンジン
# ============================================================
def run_turn(scenario, turn_index, previous_messages=None):
    """
    1ターンのチャットを実行する。
    scenario: テストシナリオ定義
    turn_index: ターン番号
    previous_messages: 前のターンまでの会話履歴（マルチターン用）
    """
    monitor = TurnMonitor(scenario["name"])
    monitor.start()

    # メッセージ準備
    if previous_messages:
        messages = list(previous_messages) + list(scenario.get("messages", []))
    else:
        messages = list(scenario.get("messages", []))

    # ツール設定
    tool_overrides = scenario.get("tools_enabled", {})
    search_allowed = tool_overrides.get("web_search", True)

    # prepared メッセージ（実際の前処理を模倣）
    prepared = list(messages)

    # ユーザー情報（簡易モック）
    chat_user = {"display_name": "sandbox_user"}

    print(f"\n{'='*60}")
    print(f"[Turn {turn_index}] {scenario['name']}")
    print(f"  期待動作: {scenario['expect']}")
    print(f"  messages: {len(prepared)}件, search_allowed={search_allowed}")
    print(f"{'='*60}")

    usage_out = empty_usage()

    try:
        gen = _stream_agent_chat_body(
            prepared=prepared,
            api_key=api_key,
            model=API_MODEL,
            make_client=_make_client,
            sse_event=monitor.sse_event,
            usage_out=usage_out,
            allow_web_search=search_allowed,
            search_engines={"tavily": True, "serper": False, "ddg": True},
            location_hint=None,
            emit_reasoning_cards=True,
            disable_reasoning=False,
            provider_id=PROVIDER_ID,
            agent_profile=AGENT_PROFILE,
            chat_username="sandbox_user",
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
            emit_tool_trace=True,
            deep_research_enabled=False,
            deep_research_prefs=None,
            intelligent_search_override=False,
            custom_agent=None,
            emit_full_info=False,
            cost_performance_maximized=False,
            expression_extension_enabled=False,
        )

        for _ in gen:
            pass  # monitor.sse_event captures everything

    except Exception as exc:
        monitor.errors.append(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()

    monitor.end()

    # 評価
    print(f"\n--- Monitor Summary ---")
    print(monitor.summary())

    # 自動評価
    evaluations = []
    content = monitor.full_content.strip()

    if not content:
        evaluations.append(("❌", "応答テキストが空"))
    elif len(content) < 5:
        evaluations.append(("⚠️", f"応答が極端に短い ({len(content)} chars)"))
    else:
        evaluations.append(("✅", f"応答あり ({len(content)} chars)"))

    if not monitor.done_received:
        evaluations.append(("❌", "done イベント未受信（生成が途中停止）"))

    if monitor.errors:
        for e in monitor.errors:
            evaluations.append(("❌", f"エラー: {str(e)[:100]}"))

    # 期待動作との照合
    expected = scenario.get("expect", "")
    if "web_search" in expected.lower() or "検索" in expected:
        has_search = any(
            tc.get("tool") == "web_search" for tc in monitor.tool_calls_made
        )
        if has_search:
            evaluations.append(("✅", "web_search 呼出し成功"))
        else:
            evaluations.append(("⚠️", "web_search が呼ばれなかった（モデルが検索不要と判断した可能性）"))

    if "web_fetch" in expected.lower():
        has_fetch = any(
            tc.get("tool") == "web_fetch" for tc in monitor.tool_calls_made
        )
        if has_fetch:
            evaluations.append(("✅", "web_fetch 呼出し成功"))
        else:
            evaluations.append(("⚠️", "web_fetch が呼ばれなかった"))

    if "ツール呼び出しなし" in expected or "ツールなし" in expected:
        if not monitor.tool_calls_made:
            evaluations.append(("✅", "期待通りツール呼出しなし"))
        else:
            evaluations.append(("⚠️", "ツールが呼ばれた（不要なはず）"))

    print(f"\n--- 自動評価 ---")
    for mark, msg in evaluations:
        print(f"  {mark} {msg}")

    # 会話履歴を構築して返す
    new_messages = list(prepared)
    if content:
        new_messages.append({"role": "assistant", "content": content})

    return {
        "monitor": monitor,
        "messages": new_messages,
        "evaluations": evaluations,
        "content": content,
    }


# ============================================================
# メイン実行
# ============================================================
def main():
    print("=== シナリオ実行開始 ===\n")

    accumulated_messages = None
    results = []

    for i, scenario in enumerate(TEST_SCENARIOS):
        result = run_turn(scenario, i + 1, previous_messages=accumulated_messages)
        results.append(result)

        # 結果を会話履歴に蓄積（マルチターンテスト用）
        if scenario.get("tools_enabled", {}).get("web_search", True):
            # 検索有効ターンは履歴に含める（コンテキスト汚染を避けるため全ターン含める）
            pass
        accumulated_messages = result["messages"]

        # ターン間の間隔（API制限対策）
        if i < len(TEST_SCENARIOS) - 1:
            time.sleep(1)

    # ============================================================
    # 総合評価レポート
    # ============================================================
    print(f"\n\n{'='*60}")
    print("=== 総合評価レポート ===")
    print(f"{'='*60}")

    total_ok = 0
    total_warn = 0
    total_err = 0

    for i, result in enumerate(results):
        m = result["monitor"]
        print(f"\n[Turn {i+1}] {m.name}")
        print(f"  経過時間: {m.elapsed_ms:.0f}ms")
        print(f"  応答: {len(m.full_content)} chars")
        if m.full_content:
            preview = m.full_content[:150].replace('\n', '\\n')
            print(f"  プレビュー: {preview}...")
        print(f"  ツール呼出: {len(m.tool_calls_made)}回")
        print(f"  エラー: {len(m.errors)}件")
        print(f"  done受信: {m.done_received}")

        for mark, msg in result["evaluations"]:
            if mark == "✅":
                total_ok += 1
            elif mark == "⚠️":
                total_warn += 1
            elif mark == "❌":
                total_err += 1

    print(f"\n--- 集計 ---")
    print(f"  ✅ 合格: {total_ok}")
    print(f"  ⚠️ 警告: {total_warn}")
    print(f"  ❌ 不合格: {total_err}")

    # 設計へのフィードバック
    print(f"\n--- 再設計へのフィードバック ---")
    issues_found = []

    for i, result in enumerate(results):
        m = result["monitor"]
        # round_data=None チェック
        if not m.done_received and not m.errors:
            issues_found.append(
                f"Turn {i+1}: done未受信 → round_data=None のパスを通った可能性"
            )
        # ツール意図リトライのチェック
        if "検索します" in m.full_content[:200] and not any(
            tc.get("tool") == "web_search" for tc in m.tool_calls_made
        ):
            issues_found.append(
                f"Turn {i+1}: 検索宣言ありだがweb_search未実行 → Tool Intent Retry が機能したか確認"
            )
        # 空応答チェック
        if not m.full_content.strip():
            issues_found.append(
                f"Turn {i+1}: 応答が空 → round_data=None パスの可能性"
            )

    if issues_found:
        for issue in issues_found:
            print(f"  🔍 {issue}")
    else:
        print("  ✅ 特に問題は検出されませんでした")

    print(f"\n=== 完了 ===")

    # クリーンアップ
    app_ctx.pop()


if __name__ == "__main__":
    main()
