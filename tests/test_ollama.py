import pytest

from unittest.mock import Mock

from kcbrain.config import Settings
from kcbrain.ollama import BrainError, CryptoBrain, extract_json_object, validate_result
from kcbrain.schemas import MarketIntelligenceRequest


def test_extract_json_object():
    assert extract_json_object('```json\n{"action":"hold"}\n```') == {"action": "hold"}


def test_invalid_json_raises():
    with pytest.raises(BrainError):
        extract_json_object("not json")


def test_missing_required_result_fields_raise():
    with pytest.raises(BrainError, match="missing required fields"):
        validate_result("technical", {"signal": "neutral"})


def test_market_result_contract_is_validated():
    with pytest.raises(BrainError, match="missing required fields"):
        validate_result("market_opportunity_ranking", {"ranking": []})


def test_analyze_repairs_missing_market_fields_once():
    brain = CryptoBrain()
    brain.generate_json = Mock(side_effect=[
        {"ranking": [{"rank": 1, "symbol": "BTC_USDT"}]},
        {
            "ranking": [{"rank": 1, "symbol": "BTC_USDT"}],
            "market_summary": "BTC leads the supplied universe.",
            "missing_data": ["on-chain history"],
        },
    ])
    request = MarketIntelligenceRequest(
        timeframe="H1",
        assets=[{"symbol": "BTC_USDT", "market": {"price": 64000}}],
    )

    result = brain.analyze("market_opportunity_ranking", request)

    assert result["market_summary"] == "BTC leads the supplied universe."
    assert brain.generate_json.call_count == 2
    repair_prompt = brain.generate_json.call_args_list[1].args[0]
    assert "market_summary, missing_data" in repair_prompt
    assert '"ranking"' in repair_prompt


def test_analyze_rejects_incomplete_repair():
    brain = CryptoBrain()
    brain.generate_json = Mock(side_effect=[{"ranking": []}, {"ranking": []}])
    request = MarketIntelligenceRequest(
        timeframe="H1",
        assets=[{"symbol": "BTC_USDT", "market": {"price": 64000}}],
    )

    with pytest.raises(BrainError, match="market_summary, missing_data"):
        brain.analyze("market_opportunity_ranking", request)


def test_chat_calls_ollama_without_thinking(monkeypatch):
    config = Settings(
        host="127.0.0.1",
        port=18328,
        api_token="secret",
        allowed_client_ips=frozenset({"127.0.0.1"}),
        ollama_url="http://ollama.test",
        ollama_model="gemma4:12b-it-qat",
        ollama_timeout=30,
        max_input_chars=1000,
    )
    brain = CryptoBrain(config)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "message": {"role": "assistant", "content": "decision"},
        "prompt_eval_count": 11,
        "eval_count": 7,
    }
    post = Mock(return_value=response)
    monkeypatch.setattr("kcbrain.ollama.requests.post", post)

    result = brain.chat([{"role": "user", "content": "BTC"}], temperature=0.3, max_tokens=900)

    assert result == {
        "content": "decision",
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    payload = post.call_args.kwargs["json"]
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.3, "num_predict": 900}


def test_chat_calls_deepseek_v4_flash_without_thinking(monkeypatch):
    config = Settings(
        host="127.0.0.1",
        port=18328,
        api_token="secret",
        allowed_client_ips=frozenset({"127.0.0.1"}),
        ollama_url="http://ollama.test",
        ollama_model="gemma4:12b-it-qat",
        ollama_timeout=30,
        max_input_chars=1000,
        llm_provider="deepseek",
        deepseek_base_url="https://deepseek.test",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout=45,
    )
    brain = CryptoBrain(config)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "decision"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
    }
    post = Mock(return_value=response)
    monkeypatch.setattr("kcbrain.ollama.requests.post", post)

    result = brain.chat([{"role": "user", "content": "BTC"}], temperature=0.3, max_tokens=900)

    assert result == {
        "content": "decision",
        "prompt_tokens": 13,
        "completion_tokens": 5,
        "total_tokens": 18,
    }
    assert post.call_args.args[0] == "https://deepseek.test/chat/completions"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer deepseek-secret"
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 900
    assert "response_format" not in payload


def test_generate_json_uses_deepseek_json_mode(monkeypatch):
    config = Settings(
        host="127.0.0.1",
        port=18328,
        api_token="secret",
        allowed_client_ips=frozenset({"127.0.0.1"}),
        ollama_url="http://ollama.test",
        ollama_model="gemma4:12b-it-qat",
        ollama_timeout=30,
        max_input_chars=1000,
        llm_provider="deepseek",
        deepseek_base_url="https://deepseek.test",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout=45,
    )
    brain = CryptoBrain(config)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": '{"signal":"neutral"}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }
    post = Mock(return_value=response)
    monkeypatch.setattr("kcbrain.ollama.requests.post", post)

    result = brain.generate_json("Return a market signal.")

    assert result == {"signal": "neutral"}
    payload = post.call_args.kwargs["json"]
    assert payload["response_format"] == {"type": "json_object"}
    assert "JSON" in payload["messages"][0]["content"]


def test_deepseek_health_checks_configured_model(monkeypatch):
    config = Settings(
        host="127.0.0.1",
        port=18328,
        api_token="secret",
        allowed_client_ips=frozenset({"127.0.0.1"}),
        ollama_url="http://ollama.test",
        ollama_model="gemma4:12b-it-qat",
        ollama_timeout=30,
        max_input_chars=1000,
        llm_provider="deepseek",
        deepseek_base_url="https://deepseek.test",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout=45,
    )
    brain = CryptoBrain(config)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": [
            {"id": "deepseek-v4-flash"},
            {"id": "deepseek-v4-pro"},
        ]
    }
    get = Mock(return_value=response)
    monkeypatch.setattr("kcbrain.ollama.requests.get", get)

    health = brain.health()

    assert health == {
        "provider": "deepseek",
        "reachable": True,
        "model_available": True,
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    }
