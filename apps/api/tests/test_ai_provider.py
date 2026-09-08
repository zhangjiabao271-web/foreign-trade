import json

import pytest
from app.ai.provider import (
    DeepSeekResponsesProvider,
    OpenAIResponsesProvider,
    ProviderError,
    configured_provider,
)
from app.ai.tools import ApplicationTools
from app.core.config import Settings
from pydantic import SecretStr
from urllib3 import PoolManager


def test_deepseek_uses_only_its_credential_and_preserves_response_items(monkeypatch):
    output = [
        {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "test reasoning"}]},
        {
            "type": "function_call",
            "call_id": "fixture-call",
            "name": "read_order",
            "arguments": "{}",
        },
    ]

    class Response:
        status = 200

        def read(self, limit):
            assert limit == 1_000_001
            return json.dumps(
                {
                    "status": "completed",
                    "output": output,
                    "usage": {"input_tokens": 7, "output_tokens": 9},
                }
            ).encode()

        def close(self):
            pass

        def release_conn(self):
            pass

    def request(self, method, url, **kwargs):
        assert method == "POST" and url == "https://api.deepseek.com/responses"
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic-deepseek"
        assert kwargs["redirect"] is False
        body = json.loads(kwargs["body"])
        assert body["model"] == "deepseek-v4-pro"
        assert "include" not in body
        assert body["store"] is False and body["parallel_tool_calls"] is False
        assert body["max_output_tokens"] == 2000
        assert body["text"]["format"]["strict"] is True
        assert "use [] if none are warranted" in body["instructions"]
        assert "Call at most one tool per response" in body["instructions"]
        assert "Never infer them from agreed_deposit" in body["instructions"]
        assert body["input"] == output
        return Response()

    monkeypatch.setattr(PoolManager, "request", request)
    settings = Settings(
        ai_provider="deepseek",
        deepseek_api_key=SecretStr("synthetic-deepseek"),
        openai_api_key=SecretStr("must-not-send-openai"),
    )
    provider = configured_provider(settings)
    assert isinstance(provider, DeepSeekResponsesProvider)
    assert settings.ai_model_identity == "deepseek/deepseek-v4-pro"
    turn = provider.next_turn(
        model=settings.ai_model_identity,
        inputs=output,
        tools=ApplicationTools.definitions("EMAIL_DRAFT"),
    )
    assert turn.output == output and turn.input_tokens == 7 and turn.output_tokens == 9


@pytest.mark.parametrize(
    "selection,model",
    [
        ("deepseek", "legacy-openai-model"),
        ("deepseek", "deepseek-v4-pro"),
        ("deepseek", "deepseek/deepseek-v4-flash"),
        ("openai", "deepseek/deepseek-v4-pro"),
    ],
)
def test_provider_switch_never_retargets_existing_model(monkeypatch, selection, model):
    def forbidden(*args, **kwargs):
        raise AssertionError("Mismatched provider must not use network")

    monkeypatch.setattr(PoolManager, "request", forbidden)
    settings = Settings(
        ai_provider=selection,
        deepseek_api_key=SecretStr("synthetic-deepseek"),
        openai_api_key=SecretStr("synthetic-openai"),
        openai_model="fixture-model",
    )
    with pytest.raises(ProviderError, match="^AI_PROVIDER_MODEL_MISMATCH$"):
        configured_provider(settings).next_turn(model=model, inputs=[], tools=[])


def test_deepseek_missing_key_has_no_openai_fallback(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Missing key must not use network")

    monkeypatch.setattr(PoolManager, "request", forbidden)
    settings = Settings(
        ai_provider="deepseek", deepseek_api_key=None, openai_api_key=SecretStr("must-not-fallback")
    )
    with pytest.raises(ProviderError, match="^AI_PROVIDER_NOT_CONFIGURED$"):
        configured_provider(settings).next_turn(
            model=settings.ai_model_identity, inputs=[], tools=[]
        )


def test_unconfigured_provider_does_not_attempt_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network request should occur without configuration")

    monkeypatch.setattr(PoolManager, "request", forbidden)
    with pytest.raises(ProviderError, match="AI_PROVIDER_NOT_CONFIGURED"):
        OpenAIResponsesProvider(Settings()).next_turn(model="unconfigured", inputs=[], tools=[])


def test_responses_contract_is_strict_nonpersistent_and_bounded(monkeypatch):
    class Response:
        status = 200

        def read(self, limit):
            assert limit == 1_000_001
            return json.dumps(
                {
                    "status": "completed",
                    "output": [],
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                }
            ).encode()

        def close(self):
            pass

        def release_conn(self):
            pass

    def request(self, method, url, **kwargs):
        assert method == "POST" and url == "https://api.openai.com/v1/responses"
        body = json.loads(kwargs["body"])
        assert body["store"] is False and body["parallel_tool_calls"] is False
        assert body["include"] == ["reasoning.encrypted_content"]
        assert body["max_output_tokens"] == 2000
        assert body["text"]["format"]["strict"] is True
        for tool in body["tools"]:
            assert tool["parameters"]["additionalProperties"] is False
        assert kwargs["redirect"] is False
        return Response()

    monkeypatch.setattr(PoolManager, "request", request)
    provider = OpenAIResponsesProvider(
        Settings(openai_api_key=SecretStr("test-only-not-a-real-key"), openai_model="fixture-model")
    )
    turn = provider.next_turn(
        model="fixture-model", inputs=[], tools=ApplicationTools.definitions("PROFIT")
    )
    assert turn.input_tokens == 12 and turn.output_tokens == 3


def test_provider_error_does_not_expose_sensitive_details(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private provider response and credential")

    monkeypatch.setattr(PoolManager, "request", fail)
    provider = OpenAIResponsesProvider(
        Settings(openai_api_key=SecretStr("test-only"), openai_model="fixture-model")
    )
    with pytest.raises(ProviderError, match="^AI_PROVIDER_UNAVAILABLE$"):
        provider.next_turn(model="fixture-model", inputs=[], tools=[])
