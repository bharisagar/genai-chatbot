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
        intent = self._classify_intent(request.message)

        deterministic_answer = self._build_answer(request.message, pack, intent)
        bedrock_answer = self._maybe_generate_with_bedrock(request, pack, intent)
        answer = bedrock_answer or deterministic_answer

        return ChatResponse(
            answer=answer,
            service_id=pack["id"],
            service_name=pack["name"],
            intent=intent,
            confidence=0.92 if pack["id"] == service_id else 0.72,
            actions=self._actions_for_intent(pack, intent),
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

    def _classify_intent(self, message: str) -> str:
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
            ],
        }

        for intent, keywords in intent_keywords.items():
            if any(keyword in normalized for keyword in keywords):
                return intent
        return "monitoring_overview"

    def _maybe_generate_with_bedrock(
        self, request: ChatRequest, pack: dict[str, Any], intent: str
    ) -> str | None:
        if not request.use_bedrock:
            return None

        system_prompt = (
            "You are an AWS production observability architect. "
            "Answer concisely using only approved service-pack context. "
            f"The detected user intent is {intent}. "
            "Give a focused answer for that intent and avoid returning every available section."
        )
        return self.bedrock.generate(system_prompt, request.message, pack)

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
            "- Show service health first: desired vs running tasks and deployment state.\n"
            "- Show customer impact next: ALB latency, 4xx, 5xx, and unhealthy targets.\n"
            "- Show investigation depth: application errors, traces, and service map.\n"
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
            "- Amazon ECR image scanning for container vulnerability evidence.\n"
            "- AWS CloudTrail for deployment and API audit history.\n\n"
            "Evidence the security team should review\n"
            "- Task role policy and execution role policy.\n"
            "- Security group path: internet -> ALB -> ECS task only.\n"
            "- ECR scan result for the deployed image tag.\n"
            "- CloudTrail events for ECS, IAM, ECR, and deployment changes.\n"
            "- Security Hub and Config findings for the service VPC and workload.\n"
        )

    def _build_logs_troubleshooting_answer(self, message: str, pack: dict[str, Any]) -> str:
        queries = "\n\n".join(
            f"{query['name']}\nIntent: {query['intent']}\n```sql\n{query['query']}\n```"
            for query in pack["log_queries"]
        )

        return (
            f"{pack['name']} troubleshooting workflow\n\n"
            "Use this order when someone reports latency, errors, or failed requests:\n\n"
            "1. Check ALB target health and `HTTPCode_Target_5XX_Count`.\n"
            "2. Check ECS desired vs running task count and recent deployment events.\n"
            "3. Check CPU and memory saturation for the service.\n"
            "4. Search application logs for error signatures.\n"
            "5. Follow traces through X-Ray or OpenTelemetry to find the slow dependency.\n\n"
            "CloudWatch Logs Insights queries\n"
            f"{queries}\n\n"
            "Decision rule\n"
            "- ALB 5xx with healthy CPU/memory usually points to application or dependency failures.\n"
            "- Unhealthy targets usually point to health check, port, startup, or networking issues.\n"
            "- High latency with low errors usually needs trace analysis and downstream dependency checks.\n"
        )

    def _build_adoption_answer(self, message: str, pack: dict[str, Any]) -> str:
        adoption = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(pack["adoption_plan"]))

        return (
            f"{pack['name']} organization adoption plan\n\n"
            f"{adoption}\n\n"
            "Operating model\n"
            "- Platform team owns Terraform module, dashboard template, and default alarms.\n"
            "- Application team owns service SLOs, runbooks, and application log quality.\n"
            "- Security team owns evidence review through Security Hub, Config, GuardDuty, CloudTrail, and ECR scans.\n"
            "- SRE or operations team owns incident routing and alarm tuning.\n\n"
            "Definition of done\n"
            "- Dashboard exists and is linked from the service runbook.\n"
            "- Required alarms exist and route to the correct team.\n"
            "- ECS tasks are private behind the ALB.\n"
            "- Logs and traces can explain at least one end-to-end request path.\n"
            "- Security evidence is reviewable without manual screenshots.\n"
        )

    def _build_cost_answer(self, message: str, pack: dict[str, Any]) -> str:
        return (
            f"{pack['name']} cost and efficiency lens\n\n"
            "Primary cost signals\n"
            "- Fargate CPU and memory allocation versus actual utilization.\n"
            "- Desired task count versus request volume.\n"
            "- Idle capacity during off-peak periods.\n"
            "- ALB request volume and target response time.\n"
            "- NAT gateway usage when private tasks need internet egress.\n\n"
            "Optimization actions\n"
            "- Right-size task CPU and memory after observing one normal traffic cycle.\n"
            "- Use target tracking autoscaling for CPU, memory, or request count per target.\n"
            "- Prefer VPC endpoints for ECR, CloudWatch Logs, and AWS APIs when NAT cost becomes material.\n"
            "- Keep ECR lifecycle policy enabled to expire old images.\n"
            "- Review CloudWatch dashboard usage and log retention to control observability cost.\n"
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
