import json
import re
import uuid

ASK_USER_TOOL_NAME = "ask_user"
ASK_USER_TOOL_NAMES = frozenset({ASK_USER_TOOL_NAME})

ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": ASK_USER_TOOL_NAME,
        "description": (
            "回答前にユーザーへ確認したい点があるときだけ使う。"
            "曖昧さや不足情報があり、推測で答えると無駄・誤答になる場合に限る。"
            "質問は必要最小限（できれば1件、多くても3件）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "ユーザーへの質問リスト",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "prompt": {
                                "type": "string",
                                "description": "質問文（ユーザーに表示）",
                            },
                            "choices": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "選択肢（2〜5個推奨）",
                            },
                            "allow_custom": {
                                "type": "boolean",
                                "description": "自由入力を許可するか（既定: true）",
                            },
                        },
                        "required": ["prompt"],
                    },
                    "minItems": 1,
                    "maxItems": 5,
                },
                "intro": {
                    "type": "string",
                    "description": "モーダル上部に短く表示する補足（任意）",
                },
            },
            "required": ["questions"],
        },
    },
}


def build_ask_user_tool_list():
    return [ASK_USER_TOOL]


def ask_user_system_prompt_append():
    return (
        "\n\n## ユーザーへの質問（ask_user）\n"
        "不明点があり、推測で答えると無駄・誤答になるときだけ ask_user を使う。\n"
        "- 挨拶・明確な依頼・一般論で足りる質問には使わない\n"
        "- 質問数は必要最小限（1件が理想、多くても3件）\n"
        "- 各質問に2〜4個の選択肢を付け、allow_custom は true にする\n"
        "- ツール呼び出し後はユーザーの回答を待ち、回答前に長文を書かない\n"
    )


def _slug_id(text, index):
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower())[:24].strip("-")
    return base or f"q{index + 1}"


def normalize_ask_user_questions(raw_questions):
    if not isinstance(raw_questions, list):
        return []
    out = []
    seen_ids = set()
    for index, item in enumerate(raw_questions[:5]):
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        qid = str(item.get("id") or "").strip() or _slug_id(prompt, index)
        if qid in seen_ids:
            qid = f"{qid}-{index + 1}"
        seen_ids.add(qid)
        choices = []
        for choice in item.get("choices") or []:
            text = str(choice or "").strip()
            if text and text not in choices:
                choices.append(text)
        allow_custom = item.get("allow_custom")
        if allow_custom is None:
            allow_custom = True
        out.append(
            {
                "id": qid,
                "prompt": prompt,
                "choices": choices[:6],
                "allow_custom": bool(allow_custom),
            }
        )
        if len(out) >= 3:
            break
    return out


def parse_ask_user_tool_args(raw_arguments):
    if isinstance(raw_arguments, dict):
        data = raw_arguments
    else:
        try:
            data = json.loads(raw_arguments or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
    questions = normalize_ask_user_questions(data.get("questions"))
    intro = str(data.get("intro") or "").strip()
    return {"questions": questions, "intro": intro}


def format_ask_user_tool_result(questions, answers, *, dismissed=False):
    if dismissed:
        return (
            "ユーザーは質問モーダルを閉じました。回答はありません。"
            "利用可能な情報だけで続行してください。"
        )
    lines = ["ユーザー回答:"]
    answer_map = {}
    if isinstance(answers, list):
        for item in answers:
            if not isinstance(item, dict):
                continue
            qid = str(item.get("id") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if qid and answer:
                answer_map[qid] = answer
    for question in questions or []:
        qid = question.get("id") or ""
        prompt = question.get("prompt") or ""
        answer = answer_map.get(qid, "").strip()
        if not answer:
            answer = "（未回答）"
        lines.append(f"Q. {prompt}")
        lines.append(f"A. {answer}")
    if len(lines) == 1:
        return "ユーザーからの回答はありませんでした。利用可能な情報だけで続行してください。"
    return "\n".join(lines)


def new_ask_user_request_id():
    return uuid.uuid4().hex
