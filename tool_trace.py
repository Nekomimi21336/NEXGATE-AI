import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def tool_display_name(tool_name):
    name = (tool_name or "").strip()
    if name.startswith("computelab_"):
        return name.replace("computelab_", "CL:", 1)
    return name


def tool_trace_payload(tool_name, duration_ms, *, ok=True, error=None):
    return {
        "tool_trace": {
            "name": tool_name,
            "label": tool_display_name(tool_name),
            "duration_ms": round(float(duration_ms), 1),
            "ok": bool(ok),
            "error": (str(error)[:240] if error else None),
        }
    }


def tool_result_ok(content):
    try:
        data = json.loads(content or "{}")
    except json.JSONDecodeError:
        return True
    if isinstance(data, dict) and "ok" in data:
        return data.get("ok") is True
    return True


def tool_result_error(content):
    try:
        data = json.loads(content or "{}")
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("ok") is False:
        return data.get("error") or "error"
    return None


def run_tool_calls_parallel(tool_calls, runner, *, max_workers=6, timeout=None):
    """
    runner(tc) -> content string.
    Returns (contents_by_id, traces) where traces are dicts for tool_trace_payload.
    If timeout is set, individual tool calls that exceed it will be cancelled and
    return an error result.
    """
    if not tool_calls:
        return {}, []

    workers = min(max_workers, max(1, len(tool_calls)))

    def run_one(tc):
        name = tc["function"]["name"]
        started = time.perf_counter()
        try:
            content = runner(tc)
        except Exception as exc:
            content = json.dumps(
                {"ok": False, "error": str(exc)}, ensure_ascii=False
            )
        duration_ms = (time.perf_counter() - started) * 1000
        ok = tool_result_ok(content)
        err = None if ok else tool_result_error(content)
        return tc["id"], content, name, duration_ms, ok, err

    contents_by_id = {}
    traces = []

    if len(tool_calls) == 1:
        tid, content, name, ms, ok, err = run_one(tool_calls[0])
        contents_by_id[tid] = content
        traces.append((name, ms, ok, err))
        return contents_by_id, traces

    trace_by_id = {}
    timed_out = False
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(run_one, tc): tc for tc in tool_calls}
        try:
            for fut in as_completed(futures, timeout=timeout):
                tid, content, name, ms, ok, err = fut.result()
                contents_by_id[tid] = content
                trace_by_id[tid] = (name, ms, ok, err)
        except TimeoutError:
            # タイムアウト: 未完了のフューチャーをキャンセルし、エラー結果で補完
            timed_out = True
            for fut, tc in futures.items():
                if fut.cancelled() or fut.done():
                    continue
                fut.cancel()
                tid = tc["id"]
                name = tc["function"]["name"]
                contents_by_id[tid] = json.dumps(
                    {"ok": False, "error": "timeout"}, ensure_ascii=False
                )
                trace_by_id[tid] = (name, 0.0, False, "timeout")
    finally:
        # wait=False: ハングしたタスクの完了を待たずに返る
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            try:
                pool.shutdown(wait=False)
            except Exception:
                pass

    traces = [trace_by_id[tc["id"]] for tc in tool_calls if tc["id"] in trace_by_id]
    if timed_out and not traces:
        # 全件タイムアウト時のフォールバック
        traces = [
            (tc["function"]["name"], 0.0, False, "timeout")
            for tc in tool_calls
        ]
    return contents_by_id, traces
