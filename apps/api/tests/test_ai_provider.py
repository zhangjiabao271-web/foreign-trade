import json

import pytest
from app.ai.provider import OpenAIResponsesProvider, ProviderError
from app.ai.tools import ApplicationTools
from app.core.config import Settings
from pydantic import SecretStr
from urllib3 import PoolManager


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
