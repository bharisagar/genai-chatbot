import hashlib
import json
import math
import os
import time
from collections import deque
from typing import Any

from app.models import ChatRequest, ChatResponse


METRIC_NAMESPACE = "AIOpsLens/Chatbot"
APPLICATION_NAME = os.getenv("APPLICATION_NAME", "aiops-lens-advisor")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


class TelemetryStore:
    def __init__(self, max_events: int = 200) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)

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
                "actions_count": 0,
                "references_count": 0,
            }
        )
        self._emit(event)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self.events.maxlen or 200))
        return list(self.events)[-limit:]

    def summary(self) -> dict[str, Any]:
        events = list(self.events)
        request_count = len(events)
        success_count = sum(1 for event in events if event["success"])
        error_count = request_count - success_count
        total_tokens = sum(int(event.get("total_tokens", 0)) for event in events)
        total_cost = sum(float(event.get("estimated_cost_usd", 0.0)) for event in events)
        latencies = [float(event.get("latency_ms", 0.0)) for event in events]
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

        by_service: dict[str, int] = {}
        by_intent: dict[str, int] = {}
        for event in events:
            by_service[event["service_id"]] = by_service.get(event["service_id"], 0) + 1
            by_intent[event["intent"]] = by_intent.get(event["intent"], 0) + 1

        return {
            "request_count": request_count,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": round(success_count / request_count, 4) if request_count else 0.0,
            "avg_latency_ms": avg_latency,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 8),
            "by_service": by_service,
            "by_intent": by_intent,
        }

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

    def _emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        print(json.dumps(self._to_emf(event), separators=(",", ":")), flush=True)

    def _to_emf(self, event: dict[str, Any]) -> dict[str, Any]:
        success_count = 1 if event["success"] else 0
        error_count = 0 if event["success"] else 1
        fallback_count = 1 if event.get("fallback_used") else 0
        low_confidence_count = 1 if float(event.get("confidence", 0.0)) < 0.8 else 0

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
            "Confidence": event["confidence"],
            "ErrorType": event["error_type"],
            "MessageHash": event["message_hash"],
            "MessageLength": event["message_length"],
            "Explainability": event["explainability"],
        }


telemetry_store = TelemetryStore()
