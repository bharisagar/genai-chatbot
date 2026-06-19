from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.advisor import AdvisorEngine
from app.governance import GovernanceDecision, GovernanceGateway
from app.models import ChatRequest, ChatResponse, RuntimeStatus, ServicePackSummary
from app.telemetry import estimate_tokens, telemetry_store


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="AWS AIOps Lens Advisor",
    description="Chatbot demo for AWS observability, monitoring, and security service packs.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

advisor = AdvisorEngine()
governance_gateway = GovernanceGateway()


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aws-aiops-lens-advisor"}


@app.get("/api/runtime", response_model=RuntimeStatus)
def runtime_status() -> RuntimeStatus:
    return advisor.runtime_status()


@app.get("/api/service-packs", response_model=list[ServicePackSummary])
def list_service_packs() -> list[ServicePackSummary]:
    return advisor.list_packs()


@app.get("/api/service-packs/{service_id}")
def get_service_pack(service_id: str) -> dict:
    pack = advisor.get_pack(service_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Unknown service pack: {service_id}")
    return pack


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    request_id = str(uuid4())
    start = perf_counter()
    governance_decision = governance_gateway.evaluate(request.message)
    if not governance_decision.allowed:
        latency_ms = (perf_counter() - start) * 1000
        response = blocked_response(request, governance_decision)
        response.request_id = request_id
        response.latency_ms = round(latency_ms, 2)
        telemetry_store.record_success(request_id, request, response, latency_ms)
        return response

    safe_request = request
    if governance_decision.sanitized_message != request.message:
        safe_request = request.model_copy(update={"message": governance_decision.sanitized_message})

    try:
        response = advisor.answer(safe_request)
    except Exception as error:
        latency_ms = (perf_counter() - start) * 1000
        telemetry_store.record_error(request_id, request, latency_ms, error)
        raise

    latency_ms = (perf_counter() - start) * 1000
    response.request_id = request_id
    response.latency_ms = round(latency_ms, 2)
    response.governance = governance_decision.to_dict()
    telemetry_store.record_success(request_id, request, response, latency_ms)
    return response


def blocked_response(request: ChatRequest, decision: GovernanceDecision) -> ChatResponse:
    answer = (
        "Request blocked by the AI Governance Gateway.\n\n"
        "The chatbot did not send this prompt to the advisor or model because it matched "
        "one or more high-risk policy signals. Remove secrets, personal data, prompt-override "
        "language, or destructive instructions and try again."
    )
    input_tokens = estimate_tokens(request.message)
    output_tokens = estimate_tokens(answer)
    return ChatResponse(
        answer=answer,
        service_id=request.service_id or "ai-governance",
        service_name="AI Governance Gateway",
        intent="security_policy",
        response_source="governance_block",
        confidence=1.0,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=0.0,
        explainability={
            "selected_service_reason": "Governance evaluation runs before service-pack selection.",
            "selected_intent_reason": "The request matched policy risk signals before normal intent routing.",
            "action_taken": "Blocked the request before advisor execution and model invocation.",
            "fallback_used": False,
            "bedrock_error": None,
            "approved_context": {
                "dashboard_sections": ["AI Governance Gateway", "Security Policy Evidence"],
                "alarm_count": 0,
                "reference_count": 0,
            },
        },
        governance=decision.to_dict(),
        actions=[
            "Do not send blocked prompt to Bedrock",
            "Record governance finding",
            "Review prompt policy evidence",
        ],
        dashboard_sections=["AI Governance Gateway", "Security Policy Evidence"],
        alarms=["PromptInjectionDetected", "SensitiveDataDetected", "GovernanceBlockedRequest"],
        references=[],
    )


@app.get("/api/observability/summary")
def observability_summary(service_id: str | None = None, days: int | None = 7) -> dict:
    return telemetry_store.summary(service_id, days)


@app.get("/api/observability/recent")
def recent_observability_events(
    limit: int = 50,
    service_id: str | None = None,
    days: int | None = 7,
) -> list[dict]:
    return telemetry_store.recent(limit, service_id, days)


@app.get("/api/observability/daily")
def daily_observability(service_id: str | None = None, days: int = 7) -> list[dict]:
    return telemetry_store.daily(service_id, days)


@app.get("/api/observability/alerts")
def observability_alerts(service_id: str | None = None, days: int = 7) -> list[dict]:
    return telemetry_store.alerts(service_id, days)


@app.get("/api/observability/events/{request_id}")
def observability_event(request_id: str) -> dict:
    event = telemetry_store.get_event(request_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Unknown telemetry event: {request_id}")
    return event


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
