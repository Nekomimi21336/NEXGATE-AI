import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

DEFAULT_API_URL = "https://api.nexgate.space/v1/chat/completions"
DEFAULT_MODEL = "nexgate-base"

SYSTEM_PROMPT = """あなたは日本の教科書・問題集のOCR結果を整理するアシスタントです。
ノイズの多いOCRテキストから、実際の問題の構造を復元してください。
推測で問題を作り足さず、テキストから読み取れる内容だけを構造化してください。
必ず有効なJSONのみを返してください。説明文やMarkdownは不要です。"""

USER_PROMPT_TEMPLATE = """以下は教科書・問題集ページの内容です（画像OCR、PDFテキスト抽出、埋め込み画像OCRのいずれかまたは組み合わせ）。
誤認識を文脈から補正し、ページの内容を構造化してください。

## OCR生テキスト
{ocr_text}

## 行番号付きOCR（参考）
{numbered_lines}

## 出力JSONスキーマ
{{
  "title": "ページタイトル",
  "summary": "このページの要約（2〜4文）",
  "sections": [
    {{
      "id": "1",
      "title": "セクション見出し",
      "topic": "セクションの説明",
      "questions": [
        {{
          "number": 1,
          "type": "matching | matching_description | ordering | multiple_choice | short_answer | fill_in_blank | other",
          "prompt": "設問文",
          "instruction": "選べ / 並べかえよ など",
          "options": ["選択肢や部品名"],
          "choices": [
            {{"label": "a", "text": "選択肢の説明"}}
          ],
          "steps": ["並べ替え用の文"],
          "blanks": ["空欄の説明があれば"],
          "answer_format": "選択 / 並べ替え / 記述 など"
        }}
      ]
    }}
  ]
}}

ルール:
- ページ内の見出し・設問構造に従って sections を分ける
- type は内容に最も近いものを選ぶ
- OCRの誤字は文脈から補正してよい
- 推測で問題を作り足さない
"""


def get_api_token(explicit_token: str | None = None) -> str:
    token = explicit_token or os.environ.get("NEXGATE_API_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "APIトークンが未設定です。環境変数 NEXGATE_API_TOKEN または --api-token を指定してください。"
        )
    return token


def build_numbered_lines(ocr_items: list[dict[str, Any]] | None) -> str:
    if not ocr_items:
        return ""
    lines: list[str] = []
    for item in ocr_items:
        if item.get("in_page") is False:
            continue
        index = item.get("index", "?")
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(f"[{index}] {text}")
    return "\n".join(lines)


def clean_json_text(text: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", text)


def extract_json_content(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("{"):
        return json.loads(clean_json_text(stripped))

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        return json.loads(clean_json_text(fenced.group(1)))

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(clean_json_text(stripped[start : end + 1]))

    raise ValueError("AIレスポンスからJSONを抽出できませんでした。")


def chat_completion(
    messages: list[dict[str, Any]],
    api_token: str,
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    temperature: float = 0.1,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"APIエラー ({error.code}): {detail}") from error

    return body["choices"][0]["message"]["content"]


def structure_worksheet(
    ocr_text: str,
    ocr_items: list[dict[str, Any]] | None = None,
    api_token: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    token = get_api_token(api_token)
    selected_model = model or os.environ.get("NEXGATE_MODEL", DEFAULT_MODEL)
    numbered_lines = build_numbered_lines(ocr_items)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        ocr_text=ocr_text.strip(),
        numbered_lines=numbered_lines.strip() or "(なし)",
    )

    content = chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        api_token=token,
        model=selected_model,
    )
    structured = extract_json_content(content)
    structured["source"] = {
        "model": selected_model,
        "ocr_line_count": len([line for line in ocr_text.splitlines() if line.strip()]),
    }
    return structured


def structure_worksheet_with_openai(
    client: Any,
    model: str,
    ocr_text: str,
    ocr_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    numbered_lines = build_numbered_lines(ocr_items)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        ocr_text=ocr_text.strip(),
        numbered_lines=numbered_lines.strip() or "(なし)",
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    structured = extract_json_content(content)
    structured["source"] = {
        "model": model,
        "ocr_line_count": len([line for line in ocr_text.splitlines() if line.strip()]),
    }
    return structured


def structured_to_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    title = data.get("title", "無題")
    lines.append(f"# {title}")
    lines.append("")

    summary = data.get("summary")
    if summary:
        lines.append(summary)
        lines.append("")

    for section in data.get("sections", []):
        section_title = section.get("title", "")
        lines.append(f"## {section_title}")
        topic = section.get("topic")
        if topic:
            lines.append(topic)
            lines.append("")

        for question in section.get("questions", []):
            number = question.get("number", "")
            prompt = question.get("prompt", "")
            qtype = question.get("type", "")
            header = f"### 問{number}" if number != "" else "### 設問"
            if qtype:
                header += f" ({qtype})"
            lines.append(header)
            if prompt:
                lines.append(prompt)

            instruction = question.get("instruction")
            if instruction:
                lines.append(f"- {instruction}")

            options = question.get("options") or []
            if options:
                lines.append("")
                lines.append("選択肢:")
                for option in options:
                    lines.append(f"- {option}")

            choices = question.get("choices") or []
            if choices:
                lines.append("")
                lines.append("選択肢:")
                for choice in choices:
                    label = choice.get("label", "")
                    text = choice.get("text", "")
                    prefix = f"({label}) " if label else ""
                    lines.append(f"- {prefix}{text}")

            steps = question.get("steps") or []
            if steps:
                lines.append("")
                lines.append("並べ替え候補:")
                for index, step in enumerate(steps, start=1):
                    lines.append(f"{index}. {step}")

            answer_format = question.get("answer_format")
            if answer_format:
                lines.append(f"- 解答形式: {answer_format}")

            lines.append("")

    return "\n".join(lines).strip() + "\n"
