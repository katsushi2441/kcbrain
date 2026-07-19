from __future__ import annotations

import hmac
import time
import uuid
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import settings
from .ollama import BrainError, CryptoBrain
from .schemas import (
    BrainResponse,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    CryptoBrainRequest,
    MarketIntelligenceRequest,
    normalize_symbol,
)
from .vendor_adapters import (
    AiHedgeFundCryptoAdapter,
    CryptoTradingAgentsAdapter,
    HelmAgentsAdapter,
    LlmTraderAdapter,
    VibeTradingAdapter,
    vendor_status,
)


app = FastAPI(
    title="Kurage Crypto Brain API",
    version=__version__,
    description="Vendored crypto intelligence APIs with selectable LLM transport. No exchange execution.",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
brain = CryptoBrain(settings)
ai_hedge_fund_crypto = AiHedgeFundCryptoAdapter(brain)
crypto_trading_agents = CryptoTradingAgentsAdapter(brain)
vibe_trading = VibeTradingAdapter(brain)
llm_trader = LlmTraderAdapter(brain)
helm_agents = HelmAgentsAdapter(brain)


@app.middleware("http")
async def restrict_write_clients(request: Request, call_next: Callable):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and settings.allowed_client_ips:
        client_ip = request.client.host if request.client else ""
        if client_ip not in settings.allowed_client_ips and client_ip != "testclient":
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=403, content={"ok": False, "detail": "client IP is not allowed"})
    return await call_next(request)


def require_token(
    x_kcbrain_token: str = Header(default=""),
    authorization: str = Header(default=""),
) -> None:
    if not settings.api_token:
        raise HTTPException(503, "KCBRAIN_API_TOKEN is not configured")
    supplied_token = x_kcbrain_token
    if not supplied_token and authorization.lower().startswith("bearer "):
        supplied_token = authorization[7:].strip()
    if not hmac.compare_digest(supplied_token, settings.api_token):
        raise HTTPException(401, "invalid API token")


@app.get("/health")
def health() -> dict:
    status = brain.health()
    result = {
        "ok": bool(status.get("reachable") and status.get("model_available")),
        "service": "kcbrain",
        "version": __version__,
        "provider": brain.provider,
        "model": brain.model,
        "llm": status,
        "vendors": vendor_status(),
    }
    result[brain.provider] = status
    return result


@app.get("/v1/meta")
def meta() -> dict:
    return {
        "service": "Kurage Crypto Brain",
        "provider": brain.provider,
        "model": brain.model,
        "exchange_execution": False,
        "wallet_access": False,
        "fallback": False,
        "endpoints": [
            "/v1/analyze/technical",
            "/v1/analyze/onchain",
            "/v1/analyze/sentiment",
            "/v1/debate/bull-bear",
            "/v1/decide/trade",
            "/v1/assess/risk",
            "/v1/decide/portfolio",
            "/v1/review/trade",
            "/v1/analyze/full",
            "/v1/market/opportunity-ranking",
            "/v1/market/flow-ranking",
            "/v1/market/anomaly",
            "/v1/market/liquidation-risk",
            "/v1/signal/pair/{symbol}",
            "/v1/chat/completions",
            "/v1/vendor/ai-hedge-fund-crypto/portfolio",
            "/v1/vendor/crypto-trading-agents/debate",
            "/v1/vendor/vibe-trading/research",
            "/v1/vendor/llm-trader/analyze",
            "/v1/vendor/helm-agents/consensus",
        ],
        "vendors": vendor_status(),
        "notes": {
            "vendor_contracts": (
                "Adapters read pinned upstream prompts, YAML presets, and response contracts at runtime. "
                "The LLM transport is selected by KCBRAIN_LLM_PROVIDER."
            ),
            "nofx": (
                "NoFX can use /v1/chat/completions as its kcbrain model provider. Exchange execution, "
                "credentials, prompts, parsing, and risk controls remain in NoFX."
            ),
        },
    }


@app.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    dependencies=[Depends(require_token)],
)
def chat_completions(payload: ChatCompletionRequest) -> ChatCompletionResponse:
    try:
        result = brain.chat(
            [message.model_dump() for message in payload.messages],
            temperature=payload.temperature,
            max_tokens=payload.output_token_limit(),
        )
    except BrainError as exc:
        raise HTTPException(502, str(exc)) from exc
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:16]}",
        created=int(time.time()),
        model=brain.model,
        choices=[
            ChatCompletionChoice(
                message=ChatCompletionMessage(content=result["content"]),
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
        ),
    )


def run(task: str, endpoint: str, payload: CryptoBrainRequest | MarketIntelligenceRequest) -> BrainResponse:
    started = time.monotonic()
    try:
        result = brain.analyze(task, payload)
    except BrainError as exc:
        raise HTTPException(502, str(exc)) from exc
    return BrainResponse(
        endpoint=endpoint,
        request_id=uuid.uuid4().hex[:16],
        model=brain.model,
        latency_ms=round((time.monotonic() - started) * 1000),
        result=result,
    )


def run_vendor(endpoint: str, operation: Callable[[], dict]) -> BrainResponse:
    started = time.monotonic()
    try:
        result = operation()
    except BrainError as exc:
        raise HTTPException(502, str(exc)) from exc
    return BrainResponse(
        endpoint=endpoint,
        request_id=uuid.uuid4().hex[:16],
        model=brain.model,
        latency_ms=round((time.monotonic() - started) * 1000),
        result=result,
    )


def protected_post(path: str, task: str):
    def endpoint(payload: CryptoBrainRequest):
        return run(task, task, payload)

    endpoint.__name__ = f"run_{task}"
    app.post(path, response_model=BrainResponse, dependencies=[Depends(require_token)])(endpoint)


for route, task_name in {
    "/v1/analyze/technical": "technical",
    "/v1/analyze/onchain": "onchain",
    "/v1/analyze/sentiment": "sentiment",
    "/v1/debate/bull-bear": "debate",
    "/v1/decide/trade": "trade",
    "/v1/assess/risk": "risk",
    "/v1/decide/portfolio": "portfolio",
    "/v1/review/trade": "review",
    "/v1/analyze/full": "full",
}.items():
    protected_post(route, task_name)


def protected_market_post(path: str, task: str):
    def endpoint(payload: MarketIntelligenceRequest):
        return run(task, path, payload)

    endpoint.__name__ = f"run_{task}"
    app.post(path, response_model=BrainResponse, dependencies=[Depends(require_token)])(endpoint)


for route, task_name in {
    "/v1/market/opportunity-ranking": "market_opportunity_ranking",
    "/v1/market/flow-ranking": "market_flow_ranking",
    "/v1/market/anomaly": "market_anomaly",
    "/v1/market/liquidation-risk": "market_liquidation_risk",
}.items():
    protected_market_post(route, task_name)


@app.post(
    "/v1/signal/pair/{symbol}",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def pair_signal(symbol: str, payload: CryptoBrainRequest):
    try:
        path_symbol = normalize_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if path_symbol != payload.symbol:
        raise HTTPException(422, "path symbol must match payload symbol")
    return run("pair_signal", f"/v1/signal/pair/{path_symbol}", payload)


@app.post(
    "/v1/vendor/ai-hedge-fund-crypto/portfolio",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def vendor_aihf_portfolio(payload: CryptoBrainRequest):
    return run_vendor(
        "vendor/ai-hedge-fund-crypto/portfolio",
        lambda: ai_hedge_fund_crypto.portfolio(payload),
    )


@app.post(
    "/v1/vendor/crypto-trading-agents/debate",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def vendor_crypto_agents_debate(payload: CryptoBrainRequest):
    return run_vendor(
        "vendor/crypto-trading-agents/debate",
        lambda: crypto_trading_agents.debate(payload),
    )


@app.post(
    "/v1/vendor/vibe-trading/research",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def vendor_vibe_research(payload: CryptoBrainRequest):
    return run_vendor("vendor/vibe-trading/research", lambda: vibe_trading.research(payload))


@app.post(
    "/v1/vendor/llm-trader/analyze",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def vendor_llm_trader(payload: CryptoBrainRequest):
    return run_vendor("vendor/llm-trader/analyze", lambda: llm_trader.analyze(payload))


@app.post(
    "/v1/vendor/helm-agents/consensus",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def vendor_helm_consensus(payload: CryptoBrainRequest):
    return run_vendor("vendor/helm-agents/consensus", lambda: helm_agents.consensus(payload))
