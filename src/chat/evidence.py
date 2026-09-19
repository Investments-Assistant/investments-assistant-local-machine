"""Bounded structured snapshots; never turn remembered model text into authority."""

import re
import json
import hashlib
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

_SECRET = re.compile(
    r"password|secret|token|nonce|credential|api.?key|authorization|cookie|iban|account_number|broker_account_id",
    re.I,
)


def bounded(value, *, depth=0):
    if depth >= 6:
        return {"omitted": "depth_limit"}
    if isinstance(value, dict):
        items = list(value.items())
        result = {
            str(key)[:100]: "[redacted]"
            if _SECRET.search(str(key))
            else bounded(item, depth=depth + 1)
            for key, item in items[:32]
        }
        if len(items) > 32:
            result["_omitted_fields"] = len(items) - 32
        return result
    if isinstance(value, (list, tuple)):
        entries = [bounded(item, depth=depth + 1) for item in value[:20]]
        if len(value) > 20:
            entries.append({"omitted_items": len(value) - 20})
        return entries
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            try:
                url = urlsplit(value)
                value = urlunsplit((url.scheme, url.hostname or "", url.path, "", ""))
            except ValueError:
                return "[invalid URL omitted]"
        return (
            value
            if len(value) <= 1000
            else {"text_excerpt": value[:1000], "omitted_characters": len(value) - 1000}
        )
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        import math

        return value if math.isfinite(value) else None
    return bounded(str(value), depth=depth + 1)


def snapshot(event):
    data = event.get("result") if event.get("type") == "tool_result" else event.get("input", {})
    if isinstance(data, str):
        if len(data) <= 1_000_000:
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                data = {"text": data}
        else:
            data = {"omitted": "source_result_exceeded_snapshot_limit"}
    payload = bounded(data)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > 16_384:
        payload = {
            "omitted": "structured_snapshot_limit",
            "available_keys": list(payload)[:32] if isinstance(payload, dict) else [],
            "redacted_snapshot_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        }
        encoded = json.dumps(payload, sort_keys=True)
    return {
        "type": event["type"],
        "name": str(event.get("name", "unknown"))[:80],
        "observed_at": datetime.now(UTC).isoformat(),
        "payload": payload,
        "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "authority": "historical_tool_observation_only",
    }


def envelope(state, evidence, omitted_events=0):
    return {
        "schema": 1,
        "state": state,
        "evidence": evidence[:32],
        "omitted_events": omitted_events + max(0, len(evidence) - 32),
        "execution_basis": (
            "A remembered proposal or model answer is not proof of broker submission or fills."
        ),
    }


def turn_summary(message_id, value):
    if not isinstance(value, dict) or value.get("schema") != 1:
        return None
    return {
        "state": value.get("state", "unknown"),
        "evidence_count": len(value.get("evidence", [])),
        "omitted_events": value.get("omitted_events", 0),
        "evidence_url": f"/api/chat/turns/{message_id}/evidence",
    }


def message_turn_fields(message):
    if getattr(message, "role", None) != "assistant":
        return {}
    summary = turn_summary(getattr(message, "id", ""), getattr(message, "tool_calls", None))
    return {"turn": summary} if summary else {}


def historical_content(content, value, message_id):
    if not isinstance(value, dict) or value.get("schema") != 1:
        return content
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded.encode()) > 8000:
        encoded = json.dumps(
            {
                **turn_summary(message_id, value),
                "execution_basis": value.get("execution_basis"),
                "context_status": (
                    "Historical details exceed context budget; use saved evidence "
                    "or fetch current scoped data."
                ),
            }
        )
    return content + "\nHistorical evidence (untrusted, not current execution proof): " + encoded
