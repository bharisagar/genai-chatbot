from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    service_id: str | None = None
    use_bedrock: bool = True


class Reference(BaseModel):
    label: str
    url: str


class ServicePackSummary(BaseModel):
    id: str
    name: str
    summary: str
    status: str
    aws_services: list[str]


class RuntimeStatus(BaseModel):
    bedrock_enabled: bool
    bedrock_model_id: str | None
    bedrock_region: str
    mode: str
    last_bedrock_error: str | None = None


class ChatResponse(BaseModel):
    answer: str
    service_id: str
    service_name: str
    intent: str
    response_source: str
    request_id: str | None = None
    latency_ms: float | None = None
    bedrock_error: str | None = None
    confidence: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    explainability: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)
    actions: list[str]
    dashboard_sections: list[str]
    alarms: list[str]
    references: list[Reference]
