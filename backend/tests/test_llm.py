import asyncio
import json

import pytest

from app import llm


def _answer(text="ok"):
    return {"choices": [{"message": {"content": text}}]}


def test_dropped_connections_are_retried(monkeypatch):
    calls = []

    def flaky(payload, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise llm.TransportError("schannel: SEC_E_MESSAGE_ALTERED")
        return _answer()

    monkeypatch.setattr(llm, "_post_once", flaky)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm._extract(llm.post_json({})) == "ok" and len(calls) == 3


def test_gives_up_with_a_helpful_message(monkeypatch):
    def down(payload, timeout):
        raise llm.TransportError("connection reset")

    monkeypatch.setattr(llm, "_post_once", down)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(llm.LLMError, match="Couldn't reach OpenRouter"):
        llm.post_json({})


def test_api_errors_are_not_retried(monkeypatch):
    calls = []

    def rejected(payload, timeout):
        calls.append(1)
        raise llm.LLMError("invalid model")

    monkeypatch.setattr(llm, "_post_once", rejected)
    with pytest.raises(llm.LLMError, match="invalid model"):
        llm.post_json({})
    assert len(calls) == 1


def test_curl_keeps_the_api_key_off_the_command_line(monkeypatch):
    monkeypatch.setattr(llm, "curl_path", lambda: "curl")
    command = llm._curl_command("body.json", True, 60)
    assert command[:2] == ["curl", "-N"] and "@-" in command and "@body.json" in command
    assert not any("Bearer" in part for part in command)


def _sse(text):
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n"


def _stream(monkeypatch, attempts):
    """Run chat_stream over a fake transport; each attempt is a list of lines and exceptions."""
    calls = []

    async def lines(payload, timeout):
        calls.append(1)
        for item in attempts[len(calls) - 1]:
            if isinstance(item, Exception):
                raise item
            yield item

    async def no_wait(seconds):
        return None

    monkeypatch.setattr(llm, "use_curl", lambda: False)
    monkeypatch.setattr(llm, "_httpx_lines", lines)
    monkeypatch.setattr(llm.asyncio, "sleep", no_wait)

    async def collect():
        return "".join([d async for d in llm.chat_stream([{"role": "user", "content": "hi"}], "context")])

    return asyncio.run(collect()), len(calls)


def test_stream_retries_a_connection_dropped_before_the_answer(monkeypatch):
    attempts = [[llm.TransportError("reset")], [": keep-alive\n", _sse("Hel"), _sse("lo"), "data: [DONE]\n"]]
    assert _stream(monkeypatch, attempts) == ("Hello", 2)


def test_stream_reports_api_errors(monkeypatch):
    body = ['{"error": {"message": "x is not a valid model ID"}}\n', llm.STATUS_MARK + "400\n"]
    with pytest.raises(llm.LLMError, match="not a valid model ID"):
        _stream(monkeypatch, [body])


def test_stream_is_not_retried_once_the_answer_started(monkeypatch):
    with pytest.raises(llm.LLMError, match="dropped while the answer was streaming"):
        _stream(monkeypatch, [[_sse("Hel"), llm.TransportError("reset")], [_sse("never")]])
