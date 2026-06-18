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


class ChatResponse(BaseModel):
    answer: str
    service_id: str
    service_name: str
    intent: str
    confidence: float
    actions: list[str]
    dashboard_sections: list[str]
    alarms: list[str]
    references: list[Reference]
