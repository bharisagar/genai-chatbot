from app.advisor import AdvisorEngine
from app.models import ChatRequest


def test_ecs_pack_is_loaded() -> None:
    advisor = AdvisorEngine()

    packs = advisor.list_packs()

    assert len(packs) == 1
    assert packs[0].id == "ecs-fargate"


def test_ecs_question_returns_dashboard_and_alarm_content() -> None:
    advisor = AdvisorEngine()

    response = advisor.answer(
        ChatRequest(
            message="Give me ECS Fargate dashboard sections and alarms.",
            service_id="ecs-fargate",
            use_bedrock=False,
        )
    )

    assert response.service_id == "ecs-fargate"
    assert response.intent == "dashboard_alarms"
    assert response.response_source == "service_pack"
    assert "CloudWatch dashboard sections" in response.answer
    assert "ECSHighCPU" in response.answer


def test_security_question_returns_security_content_only() -> None:
    advisor = AdvisorEngine()

    response = advisor.answer(
        ChatRequest(
            message="What security controls and evidence do we need?",
            service_id="ecs-fargate",
            use_bedrock=False,
        )
    )

    assert response.intent == "security_evidence"
    assert response.response_source == "service_pack"
    assert "Security controls to prove production readiness" in response.answer
    assert "Task role least privilege" in response.answer
    assert "CloudWatch dashboard sections" not in response.answer


def test_logs_question_returns_queries() -> None:
    advisor = AdvisorEngine()

    response = advisor.answer(
        ChatRequest(
            message="What logs queries should I use for ECS errors?",
            service_id="ecs-fargate",
            use_bedrock=False,
        )
    )

    assert response.intent == "logs_troubleshooting"
    assert response.response_source == "service_pack"
    assert "CloudWatch Logs Insights queries" in response.answer
    assert "Application errors by message" in response.answer


def test_adoption_question_returns_rollout_plan() -> None:
    advisor = AdvisorEngine()

    response = advisor.answer(
        ChatRequest(
            message="Give me an organization adoption plan.",
            service_id="ecs-fargate",
            use_bedrock=False,
        )
    )

    assert response.intent == "adoption_plan"
    assert response.response_source == "service_pack"
    assert "organization adoption plan" in response.answer
    assert "Operating model" in response.answer


def test_runtime_status_reports_service_pack_mode_by_default() -> None:
    advisor = AdvisorEngine()

    status = advisor.runtime_status()

    assert status.mode == "service_pack"
    assert status.bedrock_enabled is False
