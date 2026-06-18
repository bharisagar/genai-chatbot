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
            message="How do we monitor ECS Fargate in production?",
            service_id="ecs-fargate",
            use_bedrock=False,
        )
    )

    assert response.service_id == "ecs-fargate"
    assert "Production dashboard sections" in response.answer
    assert "ECSHighCPU" in response.answer
    assert "Security and governance evidence" in response.answer

