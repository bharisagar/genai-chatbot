from app.advisor import AdvisorEngine
from app.models import ChatRequest


def test_ecs_pack_is_loaded() -> None:
    advisor = AdvisorEngine()

    packs = advisor.list_packs()

    pack_ids = {pack.id for pack in packs}

    assert {
        "api-gateway",
        "bedrock",
        "ecs-fargate",
        "lambda",
        "load-balancer",
        "s3",
        "sagemaker",
        "vpc",
    }.issubset(pack_ids)


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


def test_classifier_routes_common_service_questions() -> None:
    advisor = AdvisorEngine()

    cases = {
        "monitor Lambda errors": "lambda",
        "S3 bucket security evidence": "s3",
        "API Gateway latency dashboard": "api-gateway",
        "ALB unhealthy targets": "load-balancer",
        "VPC flow logs rejects": "vpc",
        "Bedrock token usage": "bedrock",
        "SageMaker model drift": "sagemaker",
    }

    for question, expected_service_id in cases.items():
        response = advisor.answer(ChatRequest(message=question, use_bedrock=False))

        assert response.service_id == expected_service_id


def test_response_includes_observability_and_explainability_fields() -> None:
    advisor = AdvisorEngine()

    response = advisor.answer(
        ChatRequest(message="Show me S3 bucket security evidence", use_bedrock=False)
    )

    assert response.service_id == "s3"
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.total_tokens == response.input_tokens + response.output_tokens
    assert response.estimated_cost_usd == 0.0
    assert "selected_service_reason" in response.explainability
    assert "selected_intent_reason" in response.explainability
    assert response.explainability["fallback_used"] is False
