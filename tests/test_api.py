from fastapi.testclient import TestClient

from kcbrain import api


SAMPLE = {
    "symbol": "BTC_USDT",
    "timeframe": "H1",
    "market": {"price": 64000, "volume_24h": 24000000000},
    "technicals": {"rsi_14": 57.2, "ema_20": 63500, "ema_50": 62100},
}

MARKET_SAMPLE = {
    "timeframe": "H1",
    "assets": [
        {
            "symbol": "BTC_USDT",
            "market": {"price": 64000, "volume_24h": 24000000000},
            "derivatives": {"funding_rate_8h": 0.0001, "open_interest_24h_change_pct": 2.1},
        },
        {
            "symbol": "ETH_USDT",
            "market": {"price": 3400, "volume_24h": 12000000000},
            "derivatives": {"funding_rate_8h": 0.00005, "open_interest_24h_change_pct": -0.8},
        },
    ],
}


def test_health(monkeypatch):
    monkeypatch.setattr(api.brain, "health", lambda: {"reachable": True, "model_available": True})
    response = TestClient(api.app).get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["provider"] == api.brain.provider
    assert response.json()["llm"]["reachable"] is True
    assert all(vendor["installed"] for vendor in response.json()["vendors"].values())


def test_post_requires_token(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    response = TestClient(api.app).post("/v1/analyze/technical", json=SAMPLE)
    assert response.status_code == 401


def test_chat_completions_returns_openai_contract(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.brain,
        "chat",
        lambda messages, temperature, max_tokens: {
            "content": '<reasoning>evidence</reasoning>{"action":"hold"}',
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        },
    )
    response = TestClient(api.app).post(
        "/v1/chat/completions",
        headers={"X-KCBrain-Token": "secret"},
        json={
            "model": "kcbrain-gemma4",
            "messages": [
                {"role": "system", "content": "Trade safely."},
                {"role": "user", "content": "Evaluate BTC."},
            ],
            "temperature": 0.4,
            "max_tokens": 4096,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == api.brain.model
    assert body["choices"][0]["message"]["content"].endswith('{"action":"hold"}')
    assert body["usage"]["total_tokens"] == 20


def test_chat_completions_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.brain,
        "chat",
        lambda messages, temperature, max_tokens: {
            "content": "ok",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    )
    response = TestClient(api.app).post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer secret"},
        json={"messages": [{"role": "user", "content": "ping"}]},
    )
    assert response.status_code == 200


def test_chat_completions_rejects_streaming(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    response = TestClient(api.app).post(
        "/v1/chat/completions",
        headers={"X-KCBrain-Token": "secret"},
        json={"messages": [{"role": "user", "content": "ping"}], "stream": True},
    )
    assert response.status_code == 422


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


def test_market_intelligence_routes(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    calls = []

    def fake_analyze(task, payload):
        calls.append((task, len(payload.assets)))
        return {"task": task}

    monkeypatch.setattr(api.brain, "analyze", fake_analyze)
    client = TestClient(api.app)
    routes = {
        "/v1/market/opportunity-ranking": "market_opportunity_ranking",
        "/v1/market/flow-ranking": "market_flow_ranking",
        "/v1/market/anomaly": "market_anomaly",
        "/v1/market/liquidation-risk": "market_liquidation_risk",
    }
    for route, task in routes.items():
        response = client.post(route, headers={"X-KCBrain-Token": "secret"}, json=MARKET_SAMPLE)
        assert response.status_code == 200
        assert response.json()["result"]["task"] == task
    assert calls == [(task, 2) for task in routes.values()]


def test_market_assets_must_be_unique(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    duplicate = {**MARKET_SAMPLE, "assets": [MARKET_SAMPLE["assets"][0]] * 2}
    response = TestClient(api.app).post(
        "/v1/market/opportunity-ranking",
        headers={"X-KCBrain-Token": "secret"},
        json=duplicate,
    )
    assert response.status_code == 422


def test_pair_signal_requires_matching_symbol(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.brain,
        "analyze",
        lambda task, payload: {"symbol": payload.symbol, "task": task},
    )
    client = TestClient(api.app)
    response = client.post(
        "/v1/signal/pair/BTC-USDT",
        headers={"X-KCBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    assert response.json()["result"]["task"] == "pair_signal"

    mismatch = client.post(
        "/v1/signal/pair/ETH_USDT",
        headers={"X-KCBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert mismatch.status_code == 422
