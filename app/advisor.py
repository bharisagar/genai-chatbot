import json
from pathlib import Path
from typing import Any

from app.bedrock_client import BedrockAdvisor
from app.models import ChatRequest, ChatResponse, Reference, ServicePackSummary


DATA_DIR = Path(__file__).resolve().parent / "data" / "service_packs"


class AdvisorEngine:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.packs = self._load_packs()
        self.bedrock = BedrockAdvisor()

    def _load_packs(self) -> dict[str, dict[str, Any]]:
        packs: dict[str, dict[str, Any]] = {}
        for path in sorted(self.data_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                pack = json.load(handle)
            packs[pack["id"]] = pack
        return packs

    def list_packs(self) -> list[ServicePackSummary]:
        return [
            ServicePackSummary(
                id=pack["id"],
                name=pack["name"],
                summary=pack["summary"],
                status=pack.get("status", "draft"),
                aws_services=pack["aws_services"],
            )
            for pack in self.packs.values()
        ]

    def get_pack(self, service_id: str) -> dict[str, Any] | None:
        return self.packs.get(service_id)

    def answer(self, request: ChatRequest) -> ChatResponse:
        service_id = request.service_id or self._classify_service(request.message)
        pack = self.packs.get(service_id) or self.packs["ecs-fargate"]

        deterministic_answer = self._build_answer(request.message, pack)
        bedrock_answer = self._maybe_generate_with_bedrock(request, pack)
        answer = bedrock_answer or deterministic_answer

        return ChatResponse(
            answer=answer,
            service_id=pack["id"],
            service_name=pack["name"],
            confidence=0.92 if pack["id"] == service_id else 0.72,
            actions=pack["adoption_plan"][:5],
            dashboard_sections=[section["name"] for section in pack["dashboard"]["sections"]],
            alarms=[alarm["name"] for alarm in pack["alarms"]],
            references=[Reference(**reference) for reference in pack["references"]],
        )

    def _classify_service(self, message: str) -> str:
        normalized = message.lower()
        best_id = "ecs-fargate"
        best_score = 0
        for pack_id, pack in self.packs.items():
            keywords = pack.get("keywords", [])
            score = sum(1 for keyword in keywords if keyword.lower() in normalized)
            if score > best_score:
                best_score = score
                best_id = pack_id
        return best_id

    def _maybe_generate_with_bedrock(self, request: ChatRequest, pack: dict[str, Any]) -> str | None:
        if not request.use_bedrock:
            return None

        system_prompt = (
            "You are an AWS production observability architect. "
            "Answer concisely using only approved service-pack context. "
            "Map recommendations to monitoring, observability, security, and adoption outcomes."
        )
        return self.bedrock.generate(system_prompt, request.message, pack)

    def _build_answer(self, message: str, pack: dict[str, Any]) -> str:
        question = message.strip()
        dashboard_lines = "\n".join(
            f"- {section['name']}: {section['purpose']}" for section in pack["dashboard"]["sections"]
        )
        alarm_lines = "\n".join(
            f"- {alarm['name']}: {alarm['condition']} -> {alarm['action']}" for alarm in pack["alarms"]
        )
        controls = "\n".join(
            f"- {control['name']}: {control['evidence']}" for control in pack["security_controls"]
        )
        logs = "\n".join(
            f"- {query['name']}: {query['intent']}" for query in pack["log_queries"]
        )
        adoption = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(pack["adoption_plan"]))

        return (
            f"Recommended AWS production approach for {pack['name']}\n\n"
            f"Question understood: {question}\n\n"
            f"Use the {pack['name']} service pack as a reusable organization standard. "
            "The chatbot should explain the pattern, then hand back approved dashboard sections, "
            "alarms, security controls, and adoption steps that a platform team can implement.\n\n"
            "Production dashboard sections\n"
            f"{dashboard_lines}\n\n"
            "Core alarms\n"
            f"{alarm_lines}\n\n"
            "CloudWatch Logs Insights starter queries\n"
            f"{logs}\n\n"
            "Security and governance evidence\n"
            f"{controls}\n\n"
            "Adoption plan\n"
            f"{adoption}\n\n"
            "Implementation output for this repo\n"
            "- Chatbot UI served by the same container.\n"
            "- FastAPI advisor API with deterministic service-pack response.\n"
            "- Optional Amazon Bedrock generation when environment variables are enabled.\n"
            "- Terraform starter for ECS/Fargate, ALB, CloudWatch dashboard, logs, and alarms.\n"
        )

