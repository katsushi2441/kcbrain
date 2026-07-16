from kcbrain.schemas import CryptoBrainRequest
from kcbrain.vendor_adapters import (
    AiHedgeFundCryptoAdapter,
    CryptoTradingAgentsAdapter,
    HelmAgentsAdapter,
    LlmTraderAdapter,
    VibeTradingAdapter,
    vendor_status,
)


class FakeBrain:
    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt, max_tokens=2200):
        self.prompts.append(prompt)
        return {"generated": len(self.prompts)}


def request():
    return CryptoBrainRequest(
        symbol="BTC_USDT",
        timeframe="H1",
        market={"price": 64000, "volume_24h": 20000000000},
        technicals={"rsi_14": 55},
        derivatives={"funding_rate": 0.0001},
        onchain={"exchange_netflow": -1200},
        news=[{"title": "ETF inflow rises"}],
        portfolio={"cash": 100000, "max_position_value": 10000, "positions": {}},
    )


def test_all_vendors_are_pinned_and_installed():
    statuses = vendor_status()
    assert len(statuses) == 5
    assert all(item["installed"] for item in statuses.values())
    assert all(len(item["commit"]) == 40 for item in statuses.values())


def test_ai_hedge_fund_uses_upstream_portfolio_prompt():
    brain = FakeBrain()
    result = AiHedgeFundCryptoAdapter(brain).portfolio(request())
    assert result["function"].endswith("generate_trading_decision")
    assert "You are a portfolio manager" in brain.prompts[0]


def test_crypto_trading_agents_runs_three_roles():
    brain = FakeBrain()
    result = CryptoTradingAgentsAdapter(brain).debate(request())
    assert len(brain.prompts) == 3
    assert result["functions"] == ["bull_researcher", "bear_researcher", "research_manager"]


def test_vibe_trading_runs_pinned_crypto_desk():
    brain = FakeBrain()
    result = VibeTradingAdapter(brain).research(request())
    assert result["preset"].endswith("crypto_trading_desk.yaml")
    assert set(result["reports"]) == {"funding_basis_analyst", "liquidation_analyst", "flow_analyst"}
    assert len(brain.prompts) == 4


def test_llm_trader_reads_upstream_contract():
    brain = FakeBrain()
    result = LlmTraderAdapter(brain).analyze(request())
    assert result["contract"]["prompt_version"] == "trading-analysis-prompt-v1.2"
    assert "fresh analysis" in brain.prompts[0]


def test_helm_runs_four_analysts_and_manager():
    brain = FakeBrain()
    result = HelmAgentsAdapter(brain).consensus(request())
    assert set(result["reports"]) == {"market", "sentiment", "news", "fundamentals"}
    assert len(brain.prompts) == 5
