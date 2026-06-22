import json
import os
from pathlib import Path
from typing import Any

from app.bedrock_client import BedrockAdvisor
from app.models import ChatRequest, ChatResponse, Reference, RuntimeStatus, ServicePackSummary
from app.telemetry import estimate_tokens


DATA_DIR = Path(__file__).resolve().parent / "data" / "service_packs"
DEFAULT_ACTIVE_SERVICE_IDS = {
    "api-gateway",
    "bedrock",
    "ecs-fargate",
    "lambda",
    "load-balancer",
    "s3",
    "vpc",
}


class AdvisorEngine:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.packs = self._load_packs()
        self.active_service_ids = self._active_service_ids()
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
            if pack["id"] in self.active_service_ids
        ]

    def get_pack(self, service_id: str) -> dict[str, Any] | None:
        if service_id not in self.active_service_ids:
            return None
        return self.packs.get(service_id)

    def runtime_status(self) -> RuntimeStatus:
        status = self.bedrock.status()
        bedrock_enabled = bool(status["enabled"])
        return RuntimeStatus(
            bedrock_enabled=bedrock_enabled,
            bedrock_model_id=status["model_id"],
            bedrock_region=str(status["region"]),
            mode="bedrock_grounded" if bedrock_enabled else "service_pack",
            last_bedrock_error=status["last_error"],
        )

    def answer(self, request: ChatRequest) -> ChatResponse:
        service_id, service_reason = self._resolve_service(request)
        pack = self.packs.get(service_id) or self.packs["ecs-fargate"]
        intent, intent_reason = self._classify_intent_with_reason(request.message)

        deterministic_answer = self._build_answer(request.message, pack, intent)
        bedrock_answer, bedrock_error, input_tokens, output_tokens = self._maybe_generate_with_bedrock(
            request, pack, intent, deterministic_answer
        )
        answer = bedrock_answer or deterministic_answer
        response_source = "bedrock_grounded" if bedrock_answer else "service_pack"
        input_tokens = input_tokens or estimate_tokens(request.message)
        output_tokens = output_tokens or estimate_tokens(answer)
        total_tokens = input_tokens + output_tokens
        estimated_cost_usd = self._estimate_cost_usd(input_tokens, output_tokens, response_source)
        fallback_used = response_source == "service_pack" and bool(bedrock_error)

        return ChatResponse(
            answer=answer,
            service_id=pack["id"],
            service_name=pack["name"],
            intent=intent,
            response_source=response_source,
            bedrock_error=bedrock_error,
            confidence=0.92 if pack["id"] == service_id else 0.72,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            explainability={
                "selected_service_reason": service_reason,
                "selected_intent_reason": intent_reason,
                "action_taken": (
                    f"Returned {intent.replace('_', ' ')} guidance from the "
                    f"{pack['name']} service pack."
                ),
                "fallback_used": fallback_used,
                "bedrock_error": bedrock_error,
                "approved_context": {
                    "dashboard_sections": [section["name"] for section in pack["dashboard"]["sections"]],
                    "alarm_count": len(pack["alarms"]),
                    "reference_count": len(pack["references"]),
                },
            },
            actions=self._actions_for_intent(pack, intent),
            dashboard_sections=[section["name"] for section in pack["dashboard"]["sections"]],
            alarms=[alarm["name"] for alarm in pack["alarms"]],
            references=[Reference(**reference) for reference in pack["references"]],
        )

    def _resolve_service(self, request: ChatRequest) -> tuple[str, str]:
        if request.service_id:
            if request.service_id in self.active_service_ids and request.service_id in self.packs:
                return request.service_id, f"User selected the {request.service_id} service pack."
            return (
                "ecs-fargate",
                f"User selected unknown service pack '{request.service_id}', so the ECS Fargate default was used.",
            )
        return self._classify_service_with_reason(request.message)

    def _classify_service(self, message: str) -> str:
        service_id, _reason = self._classify_service_with_reason(message)
        return service_id

    def _classify_service_with_reason(self, message: str) -> tuple[str, str]:
        normalized = message.lower()
        best_id = "ecs-fargate"
        best_score = 0
        best_matches: list[str] = []
        for pack_id, pack in self.packs.items():
            if pack_id not in self.active_service_ids:
                continue
            keywords = pack.get("keywords", [])
            matches = [keyword for keyword in keywords if keyword.lower() in normalized]
            score = sum(len(keyword) for keyword in matches)
            if score > best_score:
                best_score = score
                best_id = pack_id
                best_matches = matches
        if best_matches:
            return best_id, f"Matched service keywords: {', '.join(best_matches[:5])}."
        return best_id, "No specific service keyword matched, so the ECS Fargate default was used."

    def _classify_intent(self, message: str) -> str:
        intent, _reason = self._classify_intent_with_reason(message)
        return intent

    def _classify_intent_with_reason(self, message: str) -> tuple[str, str]:
        normalized = message.lower()
        intent_keywords = {
            "dashboard_alarms": [
                "alarm",
                "alarms",
                "dashboard",
                "widget",
                "cloudwatch dashboard",
                "threshold",
            ],
            "security_evidence": [
                "security",
                "evidence",
                "compliance",
                "audit",
                "guardduty",
                "security hub",
                "config",
                "iam",
                "vulnerability",
            ],
            "logs_troubleshooting": [
                "log",
                "logs",
                "query",
                "troubleshoot",
                "investigate",
                "debug",
                "latency",
                "error",
                "errors",
                "failure",
                "slow",
                "unhealthy",
                "denied",
                "reject",
                "drift",
            ],
            "adoption_plan": [
                "adopt",
                "adoption",
                "rollout",
                "organization",
                "implement",
                "roadmap",
                "plan",
                "standard",
            ],
            "cost_efficiency": [
                "cost",
                "price",
                "rightsizing",
                "idle",
                "efficiency",
                "optimize",
                "token",
                "tokens",
                "usage",
            ],
        }

        for intent, keywords in intent_keywords.items():
            matches = [keyword for keyword in keywords if keyword in normalized]
            if matches:
                return intent, f"Matched intent keywords: {', '.join(matches[:5])}."
        return "monitoring_overview", "No specific intent keyword matched, so monitoring overview was used."

    def _active_service_ids(self) -> set[str]:
        configured = os.getenv("ACTIVE_SERVICE_PACK_IDS", "")
        if not configured.strip():
            return set(DEFAULT_ACTIVE_SERVICE_IDS)
        requested = {service_id.strip() for service_id in configured.split(",") if service_id.strip()}
        return requested & set(self.packs.keys())

    def _maybe_generate_with_bedrock(
        self, request: ChatRequest, pack: dict[str, Any], intent: str, deterministic_answer: str
    ) -> tuple[str | None, str | None, int, int]:
        if not request.use_bedrock:
            return None, None, 0, 0

        system_prompt = (
            "You are an AWS production observability architect. "
            "Answer concisely using only approved service-pack context. "
            f"The detected user intent is {intent}. "
            "Give a focused answer for that intent and avoid returning every available section. "
            "Do not invent AWS services, metric names, alarm names, IAM actions, or dashboard sections. "
            "If the approved context is insufficient, say what is missing."
        )
        grounded_context = {
            "service_id": pack["id"],
            "service_name": pack["name"],
            "intent": intent,
            "approved_services": pack["aws_services"],
            "trusted_ai_pillars": pack["trusted_ai_pillars"],
            "metrics": pack["metrics"],
            "dashboard": pack["dashboard"],
            "alarms": pack["alarms"],
            "security_controls": pack["security_controls"],
            "log_queries": pack["log_queries"],
            "adoption_plan": pack["adoption_plan"],
            "approved_draft_answer": deterministic_answer,
        }
        result = self.bedrock.generate(system_prompt, request.message, grounded_context)
        return result.text, result.error, result.input_tokens, result.output_tokens

    def _estimate_cost_usd(self, input_tokens: int, output_tokens: int, response_source: str) -> float:
        if response_source != "bedrock_grounded":
            return 0.0
        input_price_per_1k = float(os.getenv("BEDROCK_INPUT_PRICE_PER_1K", "0"))
        output_price_per_1k = float(os.getenv("BEDROCK_OUTPUT_PRICE_PER_1K", "0"))
        return round(
            ((input_tokens / 1000) * input_price_per_1k)
            + ((output_tokens / 1000) * output_price_per_1k),
            8,
        )

    def _build_answer(self, message: str, pack: dict[str, Any], intent: str) -> str:
        builders = {
            "dashboard_alarms": self._build_dashboard_alarm_answer,
            "security_evidence": self._build_security_answer,
            "logs_troubleshooting": self._build_logs_troubleshooting_answer,
            "adoption_plan": self._build_adoption_answer,
            "cost_efficiency": self._build_cost_answer,
            "monitoring_overview": self._build_monitoring_overview_answer,
        }
        return builders.get(intent, self._build_monitoring_overview_answer)(message, pack)

    def _build_monitoring_overview_answer(self, message: str, pack: dict[str, Any]) -> str:
        question = message.strip()
        primary_metrics = "\n".join(
            f"- {metric['name']} ({metric['namespace']}): {metric['why']}"
            for metric in pack["metrics"][:6]
        )
        pillars = "\n".join(
            f"- {pillar['name']}: {pillar['outcome']}"
            for pillar in pack["trusted_ai_pillars"]
        )

        return (
            f"{pack['name']} monitoring overview\n\n"
            f"Question understood: {question}\n\n"
            "Use this service pack as the organization baseline for ECS/Fargate workloads. "
            "The core pattern is CloudWatch metrics plus Container Insights, ALB health, "
            "application logs, traces, and security posture signals.\n\n"
            "Primary production signals\n"
            f"{primary_metrics}\n\n"
            "AIOps lens mapping\n"
            f"{pillars}\n\n"
            "Minimum implementation\n"
            "- Enable ECS Container Insights on the cluster.\n"
            "- Send application logs to CloudWatch Logs.\n"
            "- Put the service behind an ALB with target health checks.\n"
            "- Add CPU, memory, ALB 5xx, target health, and task-count alarms.\n"
            "- Add tracing with AWS X-Ray or OpenTelemetry for request-path visibility.\n"
        )

    def _build_dashboard_alarm_answer(self, message: str, pack: dict[str, Any]) -> str:
        dashboard_lines = "\n".join(
            f"- {section['name']}: {section['purpose']}" for section in pack["dashboard"]["sections"]
        )
        alarm_lines = "\n".join(
            f"- {alarm['name']}: {alarm['condition']} -> {alarm['action']}" for alarm in pack["alarms"]
        )

        return (
            f"{pack['name']} dashboard and alarms\n\n"
            "CloudWatch dashboard sections\n"
            f"{dashboard_lines}\n\n"
            "Production alarms\n"
            f"{alarm_lines}\n\n"
            "Recommended demo story\n"
            "- Show service health first: availability, current state, and recent changes.\n"
            "- Show customer impact next: request volume, latency, error rate, and saturation.\n"
            "- Show investigation depth: logs, traces, events, and dependency signals.\n"
            "- Close with evidence: alarms exist, logs exist, dashboard exists, and security checks are visible.\n"
        )

    def _build_security_answer(self, message: str, pack: dict[str, Any]) -> str:
        controls = "\n".join(
            f"- {control['name']}: {control['evidence']}" for control in pack["security_controls"]
        )

        return (
            f"{pack['name']} security evidence\n\n"
            "Security controls to prove production readiness\n"
            f"{controls}\n\n"
            "AWS services to connect\n"
            "- AWS Security Hub for centralized findings.\n"
            "- AWS Config for configuration compliance and drift.\n"
            "- Amazon GuardDuty for runtime threat findings.\n"
            "- AWS CloudTrail for deployment and API audit history.\n\n"
            "Evidence the security team should review\n"
            "- IAM policies, resource policies, and service-linked roles.\n"
            "- Network path, public exposure, encryption, and logging configuration.\n"
            "- CloudTrail events for configuration and deployment changes.\n"
            "- Security Hub and Config findings for the workload and its dependencies.\n"
            "- Service-specific evidence listed in the controls above.\n"
        )

    def _build_logs_troubleshooting_answer(self, message: str, pack: dict[str, Any]) -> str:
        queries = "\n\n".join(
            f"{query['name']}\nIntent: {query['intent']}\n```sql\n{query['query']}\n```"
            for query in pack["log_queries"]
        )

        return (
            f"{pack['name']} troubleshooting workflow\n\n"
            "Use this order when someone reports latency, errors, or failed requests:\n\n"
            "1. Check the primary error and latency metrics for the selected service.\n"
            "2. Check resource health, recent deployments, and configuration changes.\n"
            "3. Check saturation signals such as concurrency, CPU, memory, quota, backlog, or capacity.\n"
            "4. Search logs for error signatures and denied access events.\n"
            "5. Follow traces, request IDs, or audit events to find the failing dependency or control.\n\n"
            "CloudWatch Logs Insights queries\n"
            f"{queries}\n\n"
            "Decision rule\n"
            "- High errors after a deployment usually points to code, config, IAM, or dependency changes.\n"
            "- Health failures usually point to reachability, permissions, startup, quotas, or backend availability.\n"
            "- High latency with low errors usually needs trace, dependency, payload, or capacity analysis.\n"
        )

    def _build_adoption_answer(self, message: str, pack: dict[str, Any]) -> str:
        adoption = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(pack["adoption_plan"]))

        return (
            f"{pack['name']} organization adoption plan\n\n"
            f"{adoption}\n\n"
            "Operating model\n"
            "- Platform team owns Terraform module, dashboard template, and default alarms.\n"
            "- Application or service team owns SLOs, runbooks, and log quality.\n"
            "- Security team owns evidence review through Security Hub, Config, GuardDuty, CloudTrail, and ECR scans.\n"
            "- SRE or operations team owns incident routing and alarm tuning.\n\n"
            "Definition of done\n"
            "- Dashboard exists and is linked from the service runbook.\n"
            "- Required alarms exist and route to the correct team.\n"
            "- Network, identity, encryption, and logging controls are documented.\n"
            "- Logs, traces, metrics, or audit events can explain one end-to-end request or operation path.\n"
            "- Security evidence is reviewable without manual screenshots.\n"
        )

    def _build_cost_answer(self, message: str, pack: dict[str, Any]) -> str:
        return (
            f"{pack['name']} cost and efficiency lens\n\n"
            "Primary cost signals\n"
            "- Request or invocation volume versus provisioned capacity.\n"
            "- Error, retry, and throttling behavior that increases waste.\n"
            "- Logging, tracing, and retention volume.\n"
            "- Data transfer, storage, or token usage where relevant.\n"
            "- Idle capacity during off-peak periods.\n\n"
            "Optimization actions\n"
            "- Right-size capacity after observing one normal traffic cycle.\n"
            "- Tune autoscaling, quotas, caching, lifecycle, or retention policies.\n"
            "- Prefer private endpoints or managed controls where they reduce NAT or data-transfer cost.\n"
            "- Review CloudWatch dashboard usage, metric cardinality, and log retention.\n"
            "- Keep service-specific cleanup policies enabled for old artifacts and stale data.\n"
        )

    def _actions_for_intent(self, pack: dict[str, Any], intent: str) -> list[str]:
        if intent == "dashboard_alarms":
            return [alarm["name"] for alarm in pack["alarms"]]
        if intent == "security_evidence":
            return [control["name"] for control in pack["security_controls"]]
        if intent == "logs_troubleshooting":
            return [query["name"] for query in pack["log_queries"]]
        if intent == "cost_efficiency":
            return [
                "Review CPU and memory utilization",
                "Tune desired count and autoscaling",
                "Review NAT gateway and CloudWatch log costs",
            ]
        return pack["adoption_plan"][:5]
