from fastapi.testclient import TestClient

from kcbrain import api


SAMPLE = {
    "symbol": "BTC_USDT",
    "timeframe": "H1",
    "market": {"price": 64000, "volume_24h": 24000000000},
    "technicals": {"rsi_14": 57.2, "ema_20": 63500, "ema_50": 62100},
}


def test_health(monkeypatch):
    monkeypatch.setattr(api.brain, "health", lambda: {"reachable": True, "model_available": True})
    response = TestClient(api.app).get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert all(vendor["installed"] for vendor in response.json()["vendors"].values())


def test_post_requires_token(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    response = TestClient(api.app).post("/v1/analyze/technical", json=SAMPLE)
    assert response.status_code == 401


def test_technical_returns_structured_result(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.brain,
        "analyze",
        lambda task, payload: {"signal": "bullish", "confidence": 0.72, "evidence": ["EMA"]},
    )
    response = TestClient(api.app).post(
        "/v1/analyze/technical",
        headers={"X-KCBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    assert response.json()["result"]["signal"] == "bullish"


def test_invalid_symbol_is_rejected(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    response = TestClient(api.app).post(
        "/v1/analyze/technical",
        headers={"X-KCBrain-Token": "secret"},
        json={**SAMPLE, "symbol": "invalid"},
    )
    assert response.status_code == 422


def test_vendor_route(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(api.llm_trader, "analyze", lambda payload: {"source": "LLM_trader"})
    response = TestClient(api.app).post(
        "/v1/vendor/llm-trader/analyze",
        headers={"X-KCBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    assert response.json()["result"]["source"] == "LLM_trader"
