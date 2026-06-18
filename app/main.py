from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.advisor import AdvisorEngine
from app.models import ChatRequest, ChatResponse, RuntimeStatus, ServicePackSummary


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


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
    return advisor.answer(request)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
