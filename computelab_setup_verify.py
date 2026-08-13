import json
import re


def setup_intent_text(user_text, conversation):
    parts = []
    if user_text and str(user_text).strip():
        parts.append(str(user_text))
    for msg in conversation or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content)
    return "\n".join(parts)


def tool_evidence_blob(conversation):
    parts = []
    for msg in conversation or []:
        if msg.get("role") != "tool":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content)
    return "\n".join(parts)


def _iter_tool_json_objects(blob):
    for match in re.finditer(r"\{", blob or ""):
        start = match.start()
        depth = 0
        for i in range(start, len(blob)):
            if blob[i] == "{":
                depth += 1
            elif blob[i] == "}":
                depth -= 1
                if depth == 0:
                    chunk = blob[start : i + 1]
                    try:
                        yield json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
                    break


def _stdout_from_exec_evidence(blob):
    out = []
    for data in _iter_tool_json_objects(blob):
        if data.get("ok") and data.get("stdout"):
            out.append(str(data["stdout"]))
        if data.get("ok") and data.get("content") and isinstance(data.get("content"), str):
            out.append(str(data["content"]))
    return "\n".join(out).lower()


def _has_add_port_25565(blob):
    for data in _iter_tool_json_objects(blob):
        if data.get("ok") is not True:
            continue
        port = data.get("containerPort") or data.get("container_port")
        if port is not None and int(port) == 25565:
            return True
    return False


def setup_requirement_pending(intent_text, evidence_blob):
    text = intent_text or ""
    blob = evidence_blob or ""
    blob_lower = blob.lower()
    exec_out = _stdout_from_exec_evidence(blob)
    combined_exec = f"{blob_lower}\n{exec_out}"
    pending = []

    if re.search(r"paper|マイクラ|minecraft", text, re.IGNORECASE):
        has_jar = bool(
            re.search(r"paper-[\d.]+\.jar|paper\.jar", combined_exec)
            or re.search(r'"name"\s*:\s*"paper[^"]*\.jar"', blob_lower)
        )
        if not has_jar:
            pending.append("PaperMC 本体のダウンロード・配置（exec の ls/wget 出力で paper-*.jar を確認）")

    if re.search(r"viaversion|viabackward|マルチバージョン|複数バージョン", text, re.IGNORECASE):
        has_via_jar = bool(
            re.search(
                r"viaversion[-\d.]*\.jar|viabackwards?[-\d.]*\.jar",
                combined_exec,
                re.IGNORECASE,
            )
        )
        if not has_via_jar:
            pending.append("ViaVersion / ViaBackwards（plugins 内の .jar を exec で確認）")

    if re.search(r"screen", text, re.IGNORECASE):
        has_screen = bool(
            re.search(
                r"screen\s+(-dm|-dms|-S)|there is a screen|detached|screen -ls",
                combined_exec,
            )
        )
        if not has_screen:
            pending.append("screen での起動（screen -ls または起動コマンドの exec 出力）")

    op_match = re.search(r'\bop\s+["\']?([^\s"\']+)', text, re.IGNORECASE)
    if op_match or "op権限" in text or re.search(r"\bOP\b", text):
        op_name = (op_match.group(1) if op_match else "").lower()
        if op_name:
            in_ops = op_name in combined_exec or f'"{op_name}"' in blob_lower
            if not in_ops:
                pending.append(f"OP 付与（ops.json または exec で {op_match.group(1)} を確認）")
        elif "ops.json" not in blob_lower:
            pending.append("OP 付与（ops.json の read_file または exec）")

    if re.search(r"ポート|port|開放", text, re.IGNORECASE):
        port_ok = _has_add_port_25565(blob) or bool(
            re.search(r"publictcpendpoint|publichostip.*25565|hostport", blob_lower)
            and "25565" in blob_lower
        )
        if not port_ok:
            pending.append(
                "ポート開放（computelab_add_port の ok:true・containerPort 25565・publicTcpEndpoint）"
            )

    return pending


def setup_verified_complete(intent_text, evidence_blob):
    return len(setup_requirement_pending(intent_text, evidence_blob)) == 0


_ASSISTANT_FINISH_MARKERS = (
    "完成しました",
    "完成です",
    "設定済み",
    "正常に動作",
    "起動しました",
    "導入完了",
    "ダウンロードが完了",
    "ポート開放完了",
    "op ",
    "OP ",
    "listen して",
    "接続情報",
    "マインクラフトサーバー、",
)


def assistant_claims_setup_finished(content):
    text = content or ""
    if not text.strip():
        return False
    return any(marker.lower() in text.lower() for marker in _ASSISTANT_FINISH_MARKERS)


def hallucinated_setup_completion(intent_text, evidence_blob, assistant_content):
    if not re.search(
        r"paper|マイクラ|minecraft|viaversion|25565|screen",
        intent_text or "",
        re.IGNORECASE,
    ):
        return False
    if setup_verified_complete(intent_text, evidence_blob):
        return False
    if not assistant_claims_setup_finished(assistant_content):
        return False
    return True
