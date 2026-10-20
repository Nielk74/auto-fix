import json

import httpx
import pytest

from auto_fix.config import LLMConfig
from auto_fix.llm import RepairModel


def test_custom_endpoint_uses_chat_completions_and_validates_patch(monkeypatch):
    monkeypatch.setenv("MODEL_TOKEN", "test-model-token")
    proposal = {
        "summary": "Fix sum",
        "explanation": "Use addition",
        "edits": [
            {"path": "src/add.cpp", "old": "a-b", "new": "a+b"},
        ],
    }

    def handler(request):
        assert str(request.url) == "https://model.internal/custom/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-model-token"
        body = json.loads(request.content)
        assert body["model"] == "qwen3.8-27b"
        assert body["stream"] is False
        assert "tools" not in body
        assert body["messages"][1]["content"] == '{"test": "math.add"}'
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "<think>discard</think>\n```json\n"
                            + json.dumps(proposal)
                            + "\n```",
                        },
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = RepairModel(
            LLMConfig(
                url="https://model.internal/custom/v1",
                token_env="MODEL_TOKEN",
                model="qwen3.8-27b",
                extra_body={
                    "model": "cannot-override",
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            ),
            client,
        )
        assert model.propose({"test": "math.add"}).edits[0].new == "a+b"


@pytest.mark.parametrize(
    "content,reason",
    [
        ('{"summary":"fix","explanation":"fix","edits":[]}', "stop"),
        ('{"summary":"fix","explanation":"fix","edits":[{"path":"x","old":"","new":"y"}]}', "stop"),
        ("not JSON", "stop"),
        ("{}", "length"),
    ],
)
def test_invalid_or_truncated_proposals_are_rejected(monkeypatch, content, reason):
    monkeypatch.setenv("MODEL_TOKEN", "test-model-token")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "choices": [{"finish_reason": reason, "message": {"content": content}}],
                },
            )
        )
    ) as client:
        model = RepairModel(
            LLMConfig(url="https://model.internal/v1", token_env="MODEL_TOKEN", model="qwen"),
            client,
        )
        with pytest.raises(ValueError):
            model.propose({})


def test_http_failure_does_not_expose_server_body(monkeypatch):
    monkeypatch.setenv("MODEL_TOKEN", "test-model-token")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="secret-server-body"))
    ) as client:
        model = RepairModel(
            LLMConfig(url="https://model.internal/v1", token_env="MODEL_TOKEN", model="qwen"),
            client,
        )
        with pytest.raises(RuntimeError, match="HTTP 401") as error:
            model.propose({})
        assert "secret-server-body" not in str(error.value)
