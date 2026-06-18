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
    bedrock_error: str | None = None
    confidence: float
    actions: list[str]
    dashboard_sections: list[str]
    alarms: list[str]
    references: list[Reference]
