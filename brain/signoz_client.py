"""The brain's only read path: the SigNoz MCP server, spoken over streamable HTTP.

Every number the brain reports comes from one of these bounded queries (see skill.md) —
the investigation is a fixed playbook over MCP tools, never freeform: the brain cannot
hallucinate an RCA because it cannot ask an unbounded question.
"""
import json
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

import truststore

truststore.inject_into_ssl()
import requests

BASE = os.getenv("SIGNOZ_BASE_URL", "https://signoz.apteancloud.dev").rstrip("/")
MCP_URL = f"{BASE}/mcp"
HEADERS = {"SIGNOZ-API-KEY": os.getenv("SIGNOZ_API_KEY", ""),
           "Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}

_lock = threading.Lock()
_session_id: str | None = None


def _parse(resp):
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise RuntimeError(f"no data line in SSE response: {resp.text[:200]}")
    return resp.json()


def _post(payload, session_id=None):
    headers = dict(HEADERS)
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return requests.post(MCP_URL, headers=headers, json=payload, timeout=60)


def _ensure_session() -> str | None:
    global _session_id
    with _lock:
        if _session_id is None:
            resp = _post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "homeostat-brain", "version": "1.0"}}})
            _session_id = resp.headers.get("Mcp-Session-Id") or None
            _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, _session_id)
        return _session_id


def call_tool(name: str, arguments: dict) -> dict:
    global _session_id
    sid = _ensure_session()
    resp = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": name, "arguments": arguments}}, sid)
    if resp.status_code == 404:  # session expired — reinitialize once
        with _lock:
            _session_id = None
        sid = _ensure_session()
        resp = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": name, "arguments": arguments}}, sid)
    resp.raise_for_status()
    out = _parse(resp)
    result = out.get("result", {})
    if result.get("isError"):
        raise RuntimeError(f"MCP tool {name} errored: {json.dumps(result)[:300]}")
    return json.loads(result["content"][0]["text"])


# ---- bounded query helpers (the whole read surface the brain is allowed) ----

SVC = "service.name = 'claimpilot'"


def _builder_ts(queries, start_ms, end_ms, ctx):
    payload = call_tool("signoz_execute_builder_query", {
        "searchContext": ctx,
        "query": {"schemaVersion": "v1", "start": start_ms, "end": end_ms,
                  "requestType": "time_series",
                  "compositeQuery": {"queries": queries}, "formatOptions": {}, "variables": {}},
    })
    # response nesting: {status, data: {type, meta, data: {results: [...]}}}
    return payload.get("data", {}).get("data", {})


def _mq(name, metric, time_agg, space_agg, filt=SVC, group_by=None, disabled=False):
    agg = {"metricName": metric, "spaceAggregation": space_agg}
    if time_agg:
        agg["timeAggregation"] = time_agg
    spec = {"name": name, "signal": "metrics", "stepInterval": 60, "disabled": disabled,
            "aggregations": [agg], "filter": {"expression": filt},
            "limit": 10000 if disabled else 100,
            "order": [{"key": {"name": "__result"}, "direction": "desc"}]}
    if group_by:
        spec["groupBy"] = [{"name": g, "fieldContext": "attribute", "fieldDataType": "string"}
                           for g in group_by]
    return {"type": "builder_query", "spec": spec}


def _formula(expr):
    return {"type": "builder_formula", "spec": {"name": "F1", "expression": expr, "limit": 100,
            "order": [{"key": {"name": "__result"}, "direction": "desc"}]}}


def _series_avgs(data, query_name="F1", label_key=None):
    """Collapse time_series results to {label_value: avg} (or {'_': avg} when ungrouped)."""
    out = {}
    for result in data.get("results", []):
        if result.get("queryName") != query_name:
            continue
        for agg in result.get("aggregations", []):
            for series in agg.get("series", []) or []:
                key = "_"
                for lbl in series.get("labels", []) or []:
                    if not label_key or lbl.get("key", {}).get("name") == label_key:
                        key = lbl.get("value", "_")
                values = [v["value"] for v in series.get("values", []) if v.get("value") is not None]
                if values:
                    out[key] = sum(values) / len(values)
    return out


def avg_score_by(label_key: str, start_ms: int, end_ms: int) -> dict:
    """Average faithfulness score grouped by a bounded label (prompt.version or model)."""
    data = _builder_ts(
        [_mq("A", "gen_ai.evaluation.score.sum", "rate", "sum", group_by=[label_key], disabled=True),
         _mq("B", "gen_ai.evaluation.score.count", "rate", "sum", group_by=[label_key], disabled=True),
         _formula("A/B")],
        start_ms, end_ms, f"homeostat brain investigation: avg faithfulness by {label_key}")
    return _series_avgs(data, "F1", label_key)


def grounded_ratio(start_ms: int, end_ms: int) -> float | None:
    data = _builder_ts(
        [_mq("A", "gen_ai.evaluation.verdicts", "rate", "sum", filt=SVC + " AND label = 'grounded'", disabled=True),
         _mq("B", "gen_ai.evaluation.verdicts", "rate", "sum", disabled=True),
         _formula("A/B")],
        start_ms, end_ms, "homeostat brain: grounded-verdict ratio (SLO SLI)")
    return _series_avgs(data, "F1").get("_")


def claim_error_rate(start_ms: int, end_ms: int) -> float | None:
    data = _builder_ts(
        [_mq("A", "claimpilot.claims.processed", "increase", "sum",
             filt=SVC + " AND outcome = 'error'", disabled=True),
         _mq("B", "claimpilot.claims.processed", "increase", "sum", disabled=True),
         _formula("A/B")],
        start_ms, end_ms, "homeostat brain: claim error rate (traditional signal check)")
    return _series_avgs(data, "F1").get("_")


def p99_latency_s(start_ms: int, end_ms: int) -> float | None:
    data = _builder_ts(
        [_mq("A", "gen_ai.client.operation.duration.bucket", None, "p99")],
        start_ms, end_ms, "homeostat brain: p99 LLM latency (traditional signal check)")
    return _series_avgs(data, "A").get("_")
