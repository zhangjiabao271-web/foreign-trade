import json

import pytest
from app.ai.provider import ProviderError, configured_provider
from app.core.config import Settings
from pydantic import SecretStr
from urllib3 import PoolManager


@pytest.mark.parametrize("selection", ["openai", "deepseek"])
@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("redirect", "AI_PROVIDER_REQUEST_FAILED"),
        ("unauthorized", "AI_PROVIDER_REQUEST_FAILED"),
        ("rate_limit", "AI_PROVIDER_REQUEST_FAILED"),
        ("server_error", "AI_PROVIDER_REQUEST_FAILED"),
        ("too_large", "AI_PROVIDER_RESPONSE_TOO_LARGE"),
        ("invalid_json", "AI_PROVIDER_UNAVAILABLE"),
        ("negative_usage", "AI_PROVIDER_UNAVAILABLE"),
        ("missing_usage", "AI_PROVIDER_UNAVAILABLE"),
        ("read_failure", "AI_PROVIDER_UNAVAILABLE"),
        ("incomplete", "AI_PROVIDER_INCOMPLETE"),
    ],
)
def test_provider_failures_are_bounded_sanitized_and_release_connections(
    monkeypatch, selection, scenario, expected
):
    status = {
        "redirect": 302,
        "unauthorized": 401,
        "rate_limit": 429,
        "server_error": 503,
    }.get(scenario, 200)
    sentinel = "synthetic-private-response-and-credential"
    reads = []
    lifecycle = []
    requests = []

    class Response:
        def __init__(self):
            self.status = status

        def read(self, limit):
            reads.append(limit)
            if scenario == "read_failure":
                raise TimeoutError(sentinel)
            if scenario == "too_large":
                return b"x" * 1_000_001
            if scenario == "invalid_json":
                return sentinel.encode()
            content = {
                "status": "incomplete" if scenario == "incomplete" else "completed",
                "output": [],
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "private_detail": sentinel,
            }
            if scenario == "negative_usage":
                content["usage"]["input_tokens"] = -1
            if scenario == "missing_usage":
                del content["usage"]
            return json.dumps(content).encode()

        def close(self):
            lifecycle.append("close")

        def release_conn(self):
            lifecycle.append("release")

    def request(self, method, url, **kwargs):
        requests.append(url)
        expected_url = (
            "https://api.deepseek.com/responses"
            if selection == "deepseek"
            else "https://api.openai.com/v1/responses"
        )
        assert method == "POST" and url == expected_url
        assert kwargs["redirect"] is False
        assert kwargs["preload_content"] is False
        assert kwargs["headers"]["Authorization"] == f"Bearer synthetic-{selection}"
        return Response()

    monkeypatch.setattr(PoolManager, "request", request)
    settings = Settings(
        ai_provider=selection,
        openai_model="synthetic-model",
        openai_api_key=SecretStr("synthetic-openai"),
        deepseek_api_key=SecretStr("synthetic-deepseek"),
    )
    provider = configured_provider(settings)
    with pytest.raises(ProviderError) as failure:
        provider.next_turn(model=settings.ai_model_identity, inputs=[], tools=[])
    assert failure.value.code == expected
    assert str(failure.value) == expected
    assert sentinel not in str(failure.value)
    assert len(requests) == 1
    assert reads == ([1_000_001] if status == 200 else [])
    assert lifecycle == ["close", "release"]
