import pytest
from conftest import provider, register, space


async def test_invocation_preserves_existing_errors_and_usage():
    from app.providers.fake import FakeAdapter
    from app.providers.invocation import invoke_structured
    from app.schemas.chat import ChatDecision

    result = await invoke_structured(
        FakeAdapter(), ChatDecision, {"message": "每天15分钟", "concepts": []}, system_prompt="plan"
    )
    assert result.error is None
    assert result.validated.patch.daily_minutes == 15
    assert result.usage["cost_status"] == "demo_no_charge"


def test_context_excludes_answer_keys_credentials_and_other_spaces(client):
    from app.chat.context import build_context
    from app.db.models import StudySpace

    register(client)
    pid = provider(client)
    sid = space(client, pid)
    space(client, pid, "other-space")
    client.post(f"/api/v1/study-spaces/{sid}/diagnostics")
    with client.app.state.session_factory() as db:
        context = build_context(db, db.get(StudySpace, sid), "调整计划")
    import json

    raw = json.dumps(context)
    assert "encrypted_api_key" not in raw and "rubric" not in raw and "answer" not in context
    assert context["message"] == "调整计划"


async def test_fixed_demo_added_concept_can_be_taught():
    from app.providers.fake import FakeAdapter
    from app.providers.invocation import TEACHING_PROMPT, invoke_structured
    from app.schemas.domain import LessonContent

    result = await invoke_structured(
        FakeAdapter(),
        LessonContent,
        {"concept_ids": ["virtual_memory"], "existing_question_count": 0},
        system_prompt=TEACHING_PROMPT,
    )
    assert result.error is None
    assert result.validated.exercises[0].concept_keys == ["virtual_memory"]


@pytest.mark.parametrize("kind", ["compatible", "native"])
async def test_chat_decision_uses_existing_http_adapter_contract(kind):
    import json

    import httpx

    from app.providers.compatible import CompatibleAdapter
    from app.providers.invocation import PLANNING_PROMPT, invoke_structured
    from app.providers.native import NativeFileAdapter
    from app.schemas.chat import ChatDecision

    def handle(request):
        body = json.loads(request.content)
        assert request.url.path.endswith("/chat/completions")
        assert body["messages"][-1]["role"] == "user"
        assert json.loads(body["messages"][-1]["content"])["message"] == "每天15分钟"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "kind": "update_plan",
                                    "reply": "提出修改",
                                    "patch": {"daily_minutes": 15},
                                    "reason": "用户明确要求",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 9},
            },
        )

    async def resolver(host, port):
        return ["8.8.8.8"]

    cls = CompatibleAdapter if kind == "compatible" else NativeFileAdapter
    adapter = cls(
        "https://example.com/v1",
        "test-secret",
        "test-model",
        resolver=resolver,
        transport=httpx.MockTransport(handle),
        retries=0,
    )
    result = await invoke_structured(
        adapter, ChatDecision, {"message": "每天15分钟"}, system_prompt=PLANNING_PROMPT
    )
    assert result.error is None and result.validated.patch.daily_minutes == 15
    assert result.usage["prompt_tokens"] == 7


def test_history_trims_oldest_whole_turns(client):
    from app.chat.context import build_context
    from app.db.models import ChatTurn, StudySpace

    register(client)
    sid = space(client, provider(client))
    with client.app.state.session_factory() as db:
        s = db.get(StudySpace, sid)
        for i in range(25):
            db.add(
                ChatTurn(
                    user_id=s.user_id,
                    space_id=sid,
                    request_key=str(i),
                    request_digest=str(i),
                    content="u" * 4000,
                    reply="r" * 8000,
                    status="completed",
                )
            )
        db.flush()
        context = build_context(db, s, "current")
        assert len(context["history"]) == 2
        assert sum(len(h["user"]) + len(h["assistant"]) for h in context["history"]) == 24000
        assert context["intent"]["goal"] == s.goal
