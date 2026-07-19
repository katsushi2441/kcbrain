import pytest

from unittest.mock import Mock

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
