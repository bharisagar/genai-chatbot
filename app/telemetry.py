import hashlib
import json
import math
import os
import sqlite3
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.models import ChatRequest, ChatResponse


METRIC_NAMESPACE = "AIOpsLens/Chatbot"
APPLICATION_NAME = os.getenv("APPLICATION_NAME", "aiops-lens-advisor")
SLO_SUCCESS_TARGET = float(os.getenv("SLO_SUCCESS_TARGET", "0.99"))
SLO_LATENCY_P95_TARGET_MS = float(os.getenv("SLO_LATENCY_P95_TARGET_MS", "1000"))
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "telemetry_events.db"
TELEMETRY_BACKEND = os.getenv("TELEMETRY_BACKEND", "sqlite").lower()
TELEMETRY_TABLE_NAME = os.getenv("TELEMETRY_TABLE_NAME", "")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


class TelemetryStore:
    def __init__(self, max_events: int = 200, db_path: Path | None = None) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self.db_path = db_path or Path(os.getenv("TELEMETRY_DB_PATH", str(DEFAULT_DB_PATH)))
        if TELEMETRY_BACKEND != "dynamodb":
            self._init_db()

    def record_success(
        self,
        request_id: str,
        request: ChatRequest,
        response: ChatResponse,
        latency_ms: float,
    ) -> None:
        event = self._base_event(request_id, request, latency_ms)
        event.update(
            {
                "success": True,
                "error_type": None,
                "service_id": response.service_id,
                "service_name": response.service_name,
                "intent": response.intent,
                "response_source": response.response_source,
                "confidence": response.confidence,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
                "estimated_cost_usd": response.estimated_cost_usd,
                "fallback_used": response.response_source == "service_pack"
                and bool(response.bedrock_error),
                "explainability": response.explainability,
                "governance": response.governance,
                "actions_count": len(response.actions),
                "references_count": len(response.references),
            }
        )
        self._emit(event)

    def record_error(
        self,
        request_id: str,
        request: ChatRequest,
        latency_ms: float,
        error: Exception,
    ) -> None:
        event = self._base_event(request_id, request, latency_ms)
        event.update(
            {
                "success": False,
                "error_type": type(error).__name__,
                "service_id": request.service_id or "unknown",
                "service_name": "Unknown",
                "intent": "unknown",
                "response_source": "error",
                "confidence": 0.0,
                "input_tokens": estimate_tokens(request.message),
                "output_tokens": 0,
                "total_tokens": estimate_tokens(request.message),
                "estimated_cost_usd": 0.0,
                "fallback_used": False,
                "explainability": {
                    "action_taken": "Request failed before an advisor response was completed.",
                    "error": str(error),
                },
                "governance": {
                    "allowed": False,
                    "policy_action": "error",
                    "severity": "critical",
                    "risk_score": 0.0,
                    "categories": ["runtime_error"],
                    "findings": [],
                },
                "actions_count": 0,
                "references_count": 0,
            }
        )
        self._emit(event)

    def recent(
        self,
        limit: int = 50,
        service_id: str | None = None,
        days: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self.events.maxlen or 200))
        return self._filter_events(service_id, days)[-limit:]

    def summary(self, service_id: str | None = None, days: int | None = None) -> dict[str, Any]:
        events = self._filter_events(service_id, days)
        request_count = len(events)
        success_count = sum(1 for event in events if event["success"])
        error_count = request_count - success_count
        total_tokens = sum(int(event.get("total_tokens", 0)) for event in events)
        total_cost = sum(float(event.get("estimated_cost_usd", 0.0)) for event in events)
        fallback_count = sum(1 for event in events if event.get("fallback_used"))
        low_confidence_count = sum(1 for event in events if float(event.get("confidence", 0.0)) < 0.8)
        governance_blocked_count = sum(1 for event in events if governance_action(event) == "block")
        prompt_injection_count = sum(1 for event in events if has_governance_category(event, "prompt_injection"))
        pii_detection_count = sum(1 for event in events if has_governance_category(event, "pii"))
        secret_detection_count = sum(1 for event in events if has_governance_category(event, "secret"))
        risk_scores = [float(event.get("governance", {}).get("risk_score", 0.0)) for event in events]
        avg_governance_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0
        latencies = [float(event.get("latency_ms", 0.0)) for event in events]
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        p50_latency = percentile(latencies, 50)
        p95_latency = percentile(latencies, 95)
        p99_latency = percentile(latencies, 99)
        success_rate = round(success_count / request_count, 4) if request_count else 0.0
        error_rate = (error_count / request_count) if request_count else 0.0
        error_budget_remaining = error_budget(SLO_SUCCESS_TARGET, error_rate)
        slo_status = slo_state(success_rate, p95_latency)

        by_service: dict[str, int] = {}
        by_intent: dict[str, int] = {}
        trace_count = 0
        source_attribution_count = 0
        for event in events:
            by_service[event["service_id"]] = by_service.get(event["service_id"], 0) + 1
            by_intent[event["intent"]] = by_intent.get(event["intent"], 0) + 1
            explainability = event.get("explainability", {})
            if explainability.get("selected_service_reason") and explainability.get("selected_intent_reason"):
                trace_count += 1
            if int(event.get("references_count", 0)) > 0:
                source_attribution_count += 1

        pillar_summary = build_pillar_summary(
            request_count=request_count,
            success_rate=success_rate,
            error_count=error_count,
            avg_latency=avg_latency,
            p95_latency=p95_latency,
            total_tokens=total_tokens,
            total_cost=total_cost,
            fallback_count=fallback_count,
            low_confidence_count=low_confidence_count,
            trace_count=trace_count,
            source_attribution_count=source_attribution_count,
            governance_blocked_count=governance_blocked_count,
            prompt_injection_count=prompt_injection_count,
            pii_detection_count=pii_detection_count,
            secret_detection_count=secret_detection_count,
            avg_governance_risk=avg_governance_risk,
            error_budget_remaining=error_budget_remaining,
        )

        return {
            "service_id": service_id,
            "window_days": days,
            "request_count": request_count,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "latency_p50_ms": p50_latency,
            "latency_p95_ms": p95_latency,
            "latency_p99_ms": p99_latency,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 8),
            "fallback_count": fallback_count,
            "low_confidence_count": low_confidence_count,
            "governance_blocked_count": governance_blocked_count,
            "prompt_injection_count": prompt_injection_count,
            "pii_detection_count": pii_detection_count,
            "secret_detection_count": secret_detection_count,
            "avg_governance_risk": avg_governance_risk,
            "slo": {
                "status": slo_status,
                "success_target": SLO_SUCCESS_TARGET,
                "latency_p95_target_ms": SLO_LATENCY_P95_TARGET_MS,
                "error_budget_remaining": error_budget_remaining,
            },
            "by_service": by_service,
            "by_intent": by_intent,
            "pillars": pillar_summary,
        }

    def daily(self, service_id: str | None = None, days: int = 7) -> list[dict[str, Any]]:
        days = max(1, min(days, 30))
        today = datetime.now().date()
        buckets: dict[str, dict[str, Any]] = {}
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            buckets[key] = {
                "date": key,
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "governance_blocked_count": 0,
                "prompt_injection_count": 0,
                "pii_detection_count": 0,
                "secret_detection_count": 0,
                "_latencies": [],
            }

        for event in self._filter_events(service_id, days):
            day = datetime.fromtimestamp(event["timestamp_epoch_ms"] / 1000).date().isoformat()
            if day not in buckets:
                continue
            bucket = buckets[day]
            bucket["request_count"] += 1
            bucket["success_count"] += 1 if event["success"] else 0
            bucket["error_count"] += 0 if event["success"] else 1
            bucket["total_tokens"] += int(event.get("total_tokens", 0))
            bucket["estimated_cost_usd"] += float(event.get("estimated_cost_usd", 0.0))
            bucket["governance_blocked_count"] += 1 if governance_action(event) == "block" else 0
            bucket["prompt_injection_count"] += 1 if has_governance_category(event, "prompt_injection") else 0
            bucket["pii_detection_count"] += 1 if has_governance_category(event, "pii") else 0
            bucket["secret_detection_count"] += 1 if has_governance_category(event, "secret") else 0
            bucket["_latencies"].append(float(event.get("latency_ms", 0.0)))

        results = []
        for bucket in buckets.values():
            latencies = bucket.pop("_latencies")
            bucket["avg_latency_ms"] = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            bucket["latency_p95_ms"] = percentile(latencies, 95)
            bucket["estimated_cost_usd"] = round(bucket["estimated_cost_usd"], 8)
            results.append(bucket)
        return results

    def alerts(self, service_id: str | None = None, days: int | None = 7) -> list[dict[str, Any]]:
        summary = self.summary(service_id, days)
        alerts: list[dict[str, Any]] = []
        if summary["request_count"] == 0:
            return [
                {
                    "severity": "info",
                    "title": "No telemetry captured",
                    "detail": "No requests match the selected service and time window.",
                }
            ]
        if summary["error_count"] > 0:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Request errors detected",
                    "detail": f"{summary['error_count']} failed requests in the selected window.",
                }
            )
        if summary["success_rate"] < SLO_SUCCESS_TARGET:
            alerts.append(
                {
                    "severity": "warning",
                    "title": "Success SLO at risk",
                    "detail": f"Success rate is {round(summary['success_rate'] * 100, 2)}%, below the {round(SLO_SUCCESS_TARGET * 100, 2)}% target.",
                }
            )
        if summary["latency_p95_ms"] > SLO_LATENCY_P95_TARGET_MS:
            alerts.append(
                {
                    "severity": "warning",
                    "title": "Latency SLO at risk",
                    "detail": f"p95 latency is {summary['latency_p95_ms']} ms, above the {SLO_LATENCY_P95_TARGET_MS} ms target.",
                }
            )
        if summary["low_confidence_count"] > 0:
            alerts.append(
                {
                    "severity": "notice",
                    "title": "Low-confidence responses",
                    "detail": f"{summary['low_confidence_count']} responses were below the confidence threshold.",
                }
            )
        if summary["governance_blocked_count"] > 0:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Governance blocked requests",
                    "detail": f"{summary['governance_blocked_count']} requests were blocked before advisor or model execution.",
                }
            )
        if summary["prompt_injection_count"] > 0:
            alerts.append(
                {
                    "severity": "warning",
                    "title": "Prompt injection attempts",
                    "detail": f"{summary['prompt_injection_count']} prompts matched instruction-override or prompt-disclosure signals.",
                }
            )
        if summary["secret_detection_count"] > 0 or summary["pii_detection_count"] > 0:
            alerts.append(
                {
                    "severity": "warning",
                    "title": "Sensitive data detected",
                    "detail": (
                        f"{summary['secret_detection_count']} secret signals and "
                        f"{summary['pii_detection_count']} PII signals were detected."
                    ),
                }
            )
        if not alerts:
            alerts.append(
                {
                    "severity": "healthy",
                    "title": "Telemetry healthy",
                    "detail": "No SLO, latency, confidence, or error alerts in this window.",
                }
            )
        return alerts

    def get_event(self, request_id: str) -> dict[str, Any] | None:
        for event in self._load_events_from_db():
            if event.get("request_id") == request_id:
                return event
        for event in self.events:
            if event.get("request_id") == request_id:
                return event
        return None

    def _base_event(self, request_id: str, request: ChatRequest, latency_ms: float) -> dict[str, Any]:
        return {
            "event_type": "chatbot_observability",
            "application": APPLICATION_NAME,
            "request_id": request_id,
            "timestamp_epoch_ms": int(time.time() * 1000),
            "latency_ms": round(latency_ms, 2),
            "message_hash": hashlib.sha256(request.message.encode("utf-8")).hexdigest()[:16],
            "message_length": len(request.message),
            "requested_service_id": request.service_id,
            "requested_bedrock": request.use_bedrock,
        }

    def _filter_events(
        self,
        service_id: str | None = None,
        days: int | None = None,
    ) -> list[dict[str, Any]]:
        events = self._load_events_from_db()
        if not events:
            events = list(self.events)
        if days:
            cutoff_ms = int((time.time() - (max(1, min(days, 90)) * 86400)) * 1000)
            events = [event for event in events if int(event.get("timestamp_epoch_ms", 0)) >= cutoff_ms]
        if not service_id:
            return events
        return [event for event in events if event.get("service_id") == service_id]

    def _emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self._persist_event(event)
        print(json.dumps(self._to_emf(event), separators=(",", ":")), flush=True)

    def _init_db(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_events (
                        request_id TEXT PRIMARY KEY,
                        timestamp_epoch_ms INTEGER NOT NULL,
                        service_id TEXT NOT NULL,
                        intent TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        event_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_telemetry_service_time ON telemetry_events(service_id, timestamp_epoch_ms)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_telemetry_time ON telemetry_events(timestamp_epoch_ms)"
                )
        except sqlite3.Error:
            pass

    def _persist_event(self, event: dict[str, Any]) -> None:
        if TELEMETRY_BACKEND == "dynamodb" and TELEMETRY_TABLE_NAME:
            self._persist_event_to_dynamodb(event)
            return

        try:
            with sqlite3.connect(self.db_path) as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO telemetry_events
                    (request_id, timestamp_epoch_ms, service_id, intent, success, event_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["request_id"],
                        int(event["timestamp_epoch_ms"]),
                        event["service_id"],
                        event["intent"],
                        1 if event["success"] else 0,
                        json.dumps(event, separators=(",", ":")),
                    ),
                )
        except sqlite3.Error:
            pass

    def _load_events_from_db(self) -> list[dict[str, Any]]:
        if TELEMETRY_BACKEND == "dynamodb" and TELEMETRY_TABLE_NAME:
            return self._load_events_from_dynamodb()

        try:
            with sqlite3.connect(self.db_path) as connection:
                rows = connection.execute(
                    "SELECT event_json FROM telemetry_events ORDER BY timestamp_epoch_ms ASC"
                ).fetchall()
            return [json.loads(row[0]) for row in rows]
        except (sqlite3.Error, json.JSONDecodeError):
            return []

    def _persist_event_to_dynamodb(self, event: dict[str, Any]) -> None:
        try:
            import boto3

            table = boto3.resource("dynamodb").Table(TELEMETRY_TABLE_NAME)
            table.put_item(
                Item={
                    "request_id": event["request_id"],
                    "timestamp_epoch_ms": int(event["timestamp_epoch_ms"]),
                    "service_id": event["service_id"],
                    "intent": event["intent"],
                    "success": bool(event["success"]),
                    "event_json": json.dumps(event, separators=(",", ":")),
                }
            )
        except Exception:
            pass

    def _load_events_from_dynamodb(self) -> list[dict[str, Any]]:
        try:
            import boto3

            table = boto3.resource("dynamodb").Table(TELEMETRY_TABLE_NAME)
            response = table.scan(ProjectionExpression="event_json")
            rows = response.get("Items", [])
            while "LastEvaluatedKey" in response:
                response = table.scan(
                    ProjectionExpression="event_json",
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                rows.extend(response.get("Items", []))
            events = [json.loads(row["event_json"]) for row in rows]
            return sorted(events, key=lambda event: int(event.get("timestamp_epoch_ms", 0)))
        except Exception:
            return []

    def _to_emf(self, event: dict[str, Any]) -> dict[str, Any]:
        success_count = 1 if event["success"] else 0
        error_count = 0 if event["success"] else 1
        fallback_count = 1 if event.get("fallback_used") else 0
        low_confidence_count = 1 if float(event.get("confidence", 0.0)) < 0.8 else 0
        governance = event.get("governance", {})
        governance_blocked_count = 1 if governance.get("policy_action") == "block" else 0
        prompt_injection_count = 1 if "prompt_injection" in governance.get("categories", []) else 0
        pii_detection_count = 1 if "pii" in governance.get("categories", []) else 0
        secret_detection_count = 1 if "secret" in governance.get("categories", []) else 0

        return {
            "_aws": {
                "Timestamp": event["timestamp_epoch_ms"],
                "CloudWatchMetrics": [
                    {
                        "Namespace": METRIC_NAMESPACE,
                        "Dimensions": [
                            ["Application"],
                            ["Application", "ServiceId"],
                            ["Application", "Intent"],
                            ["Application", "ServiceId", "Intent", "ResponseSource"],
                        ],
                        "Metrics": [
                            {"Name": "RequestCount", "Unit": "Count"},
                            {"Name": "SuccessCount", "Unit": "Count"},
                            {"Name": "ErrorCount", "Unit": "Count"},
                            {"Name": "LatencyMs", "Unit": "Milliseconds"},
                            {"Name": "InputTokens", "Unit": "Count"},
                            {"Name": "OutputTokens", "Unit": "Count"},
                            {"Name": "TotalTokens", "Unit": "Count"},
                            {"Name": "EstimatedCostUsd", "Unit": "None"},
                            {"Name": "FallbackCount", "Unit": "Count"},
                            {"Name": "LowConfidenceCount", "Unit": "Count"},
                            {"Name": "GovernanceBlockedCount", "Unit": "Count"},
                            {"Name": "PromptInjectionCount", "Unit": "Count"},
                            {"Name": "PiiDetectionCount", "Unit": "Count"},
                            {"Name": "SecretDetectionCount", "Unit": "Count"},
                            {"Name": "GovernanceRiskScore", "Unit": "None"},
                        ],
                    }
                ],
            },
            "EventType": event["event_type"],
            "Application": event["application"],
            "RequestId": event["request_id"],
            "ServiceId": event["service_id"],
            "ServiceName": event["service_name"],
            "Intent": event["intent"],
            "ResponseSource": event["response_source"],
            "RequestCount": 1,
            "SuccessCount": success_count,
            "ErrorCount": error_count,
            "LatencyMs": event["latency_ms"],
            "InputTokens": event["input_tokens"],
            "OutputTokens": event["output_tokens"],
            "TotalTokens": event["total_tokens"],
            "EstimatedCostUsd": event["estimated_cost_usd"],
            "FallbackCount": fallback_count,
            "LowConfidenceCount": low_confidence_count,
            "GovernanceBlockedCount": governance_blocked_count,
            "PromptInjectionCount": prompt_injection_count,
            "PiiDetectionCount": pii_detection_count,
            "SecretDetectionCount": secret_detection_count,
            "GovernanceRiskScore": governance.get("risk_score", 0.0),
            "Confidence": event["confidence"],
            "ErrorType": event["error_type"],
            "MessageHash": event["message_hash"],
            "MessageLength": event["message_length"],
            "Explainability": event["explainability"],
            "Governance": governance,
        }


telemetry_store = TelemetryStore()


def percentile(values: list[float], target: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (target / 100) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(ordered[int(rank)], 2)
    weighted = ordered[low] + (ordered[high] - ordered[low]) * (rank - low)
    return round(weighted, 2)


def error_budget(success_target: float, error_rate: float) -> float:
    allowed_error_rate = max(0.0001, 1 - success_target)
    remaining = 1 - (error_rate / allowed_error_rate)
    return round(max(0.0, min(1.0, remaining)), 4)


def slo_state(success_rate: float, latency_p95_ms: float) -> str:
    if success_rate == 0 and latency_p95_ms == 0:
        return "no_data"
    if success_rate < SLO_SUCCESS_TARGET or latency_p95_ms > SLO_LATENCY_P95_TARGET_MS:
        return "at_risk"
    return "healthy"


def governance_action(event: dict[str, Any]) -> str:
    governance = event.get("governance", {})
    if not isinstance(governance, dict):
        return "unknown"
    return str(governance.get("policy_action", "allow"))


def has_governance_category(event: dict[str, Any], category: str) -> bool:
    governance = event.get("governance", {})
    if not isinstance(governance, dict):
        return False
    categories = governance.get("categories", [])
    return isinstance(categories, list) and category in categories


def build_pillar_summary(
    *,
    request_count: int,
    success_rate: float,
    error_count: int,
    avg_latency: float,
    p95_latency: float,
    total_tokens: int,
    total_cost: float,
    fallback_count: int,
    low_confidence_count: int,
    trace_count: int,
    source_attribution_count: int,
    governance_blocked_count: int,
    prompt_injection_count: int,
    pii_detection_count: int,
    secret_detection_count: int,
    avg_governance_risk: float,
    error_budget_remaining: float,
) -> list[dict[str, Any]]:
    success_pct = percent_value(success_rate)
    error_rate_pct = percent_value(error_count / request_count if request_count else 0.0)
    trace_pct = percent_value(trace_count / request_count if request_count else 0.0)
    attribution_pct = percent_value(source_attribution_count / request_count if request_count else 0.0)
    low_confidence_rate = low_confidence_count / request_count if request_count else 0.0
    hallucination_proxy_pct = percent_value(low_confidence_rate)
    accuracy_proxy_pct = percent_value(max(0.0, 1 - low_confidence_rate))
    blocked_rate_pct = percent_value(governance_blocked_count / request_count if request_count else 0.0)
    safe_prompt_pct = percent_value(max(0.0, 1 - avg_governance_risk))
    validation_score = percent_value(
        (success_rate + max(0.0, 1 - low_confidence_rate) + error_budget_remaining) / 3
        if request_count
        else 0.0
    )

    return [
        {
            "id": "observability",
            "name": "Observability",
            "outcome": "Complete visibility into agent behavior and system performance.",
            "score": success_pct,
            "status": pillar_status(success_pct),
            "metrics": [
                metric_item("Request volume", request_count, "count"),
                metric_item("Agent success rate", success_pct, "percent"),
                metric_item("Tool invocation success", success_pct, "percent"),
                metric_item("End-to-end latency", avg_latency, "ms"),
                metric_item("p95 latency", p95_latency, "ms"),
                metric_item("Token usage", total_tokens, "count"),
                metric_item("Cost per request", total_cost / request_count if request_count else 0.0, "usd"),
                metric_item("Error rate", error_rate_pct, "percent"),
                metric_item("Escalation rate", blocked_rate_pct, "percent"),
            ],
        },
        {
            "id": "explainability",
            "name": "Explainability",
            "outcome": "Explain why the agent selected a service, intent, and action.",
            "score": trace_pct,
            "status": pillar_status(trace_pct),
            "metrics": [
                metric_item("Reasoning trace availability", trace_pct, "percent"),
                metric_item("Decision path coverage", trace_pct, "percent"),
                metric_item("Source attribution rate", attribution_pct, "percent"),
                metric_item("Citation coverage", attribution_pct, "percent"),
                metric_item("Tool selection rationale", trace_pct, "percent"),
                metric_item("Human override reasons", governance_blocked_count, "count"),
            ],
        },
        {
            "id": "quality",
            "name": "Quality",
            "outcome": "Ensure responses are accurate, relevant, and consistent.",
            "score": accuracy_proxy_pct,
            "status": pillar_status(accuracy_proxy_pct),
            "metrics": [
                metric_item("Accuracy score", accuracy_proxy_pct, "percent"),
                metric_item("Groundedness score", attribution_pct, "percent"),
                metric_item("Faithfulness score", accuracy_proxy_pct, "percent"),
                metric_item("Relevance score", accuracy_proxy_pct, "percent"),
                metric_item("Hallucination rate", hallucination_proxy_pct, "percent"),
                metric_item("Task completion rate", success_pct, "percent"),
                metric_item("User satisfaction score", accuracy_proxy_pct, "percent"),
            ],
        },
        {
            "id": "ethics_safety",
            "name": "Ethics & Safety",
            "outcome": "Ensure safe, fair, and responsible AI behavior.",
            "score": safe_prompt_pct,
            "status": pillar_status(safe_prompt_pct),
            "metrics": [
                metric_item("Toxicity rate", 0, "count"),
                metric_item("Prompt injection attempts", prompt_injection_count, "count"),
                metric_item("PII detection events", pii_detection_count, "count"),
                metric_item("Secret detection events", secret_detection_count, "count"),
                metric_item("Policy violations", governance_blocked_count, "count"),
                metric_item("Unauthorized tool access attempts", governance_blocked_count, "count"),
                metric_item("Human escalation rate", blocked_rate_pct, "percent"),
            ],
        },
        {
            "id": "continuous_validation",
            "name": "Continuous Validation",
            "outcome": "Continuously validate and improve agent behavior over time.",
            "score": validation_score,
            "status": pillar_status(validation_score),
            "metrics": [
                metric_item("Model drift score", 0, "count"),
                metric_item("Evaluation benchmark score", validation_score, "percent"),
                metric_item("Regression test signal", percent_value(error_budget_remaining), "percent"),
                metric_item("Prompt performance trend", p95_latency, "ms"),
                metric_item("Agent evaluation score", validation_score, "percent"),
                metric_item("Feedback loop effectiveness", success_pct, "percent"),
                metric_item("Fallback count", fallback_count, "count"),
            ],
        },
    ]


def metric_item(label: str, value: float | int, unit: str) -> dict[str, Any]:
    return {"label": label, "value": round(value, 4) if isinstance(value, float) else value, "unit": unit}


def percent_value(value: float) -> float:
    return round(max(0.0, min(1.0, value)) * 100, 2)


def pillar_status(score: float) -> str:
    if score >= 90:
        return "healthy"
    if score >= 70:
        return "watch"
    if score > 0:
        return "risk"
    return "no_data"
