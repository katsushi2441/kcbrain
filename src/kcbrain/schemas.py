from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_symbol(value: str) -> str:
    normalized = value.strip().upper().replace("/", "_").replace("-", "_")
    if not re.fullmatch(r"[A-Z0-9]{2,12}_[A-Z0-9]{2,12}", normalized):
        raise ValueError("symbol must look like BTC_USDT or ETH_USD")
    return normalized


class CryptoBrainRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=24, examples=["BTC_USDT"])
    timeframe: str = Field(default="H1", min_length=1, max_length=16)
    as_of: str = Field(default="", max_length=40)
    market: dict[str, Any] = Field(default_factory=dict)
    technicals: dict[str, Any] = Field(default_factory=dict)
    derivatives: dict[str, Any] = Field(default_factory=dict)
    onchain: dict[str, Any] = Field(default_factory=dict)
    defi: dict[str, Any] = Field(default_factory=dict)
    news: list[Any] = Field(default_factory=list, max_length=60)
    social: list[Any] = Field(default_factory=list, max_length=60)
    position: dict[str, Any] = Field(default_factory=dict)
    portfolio: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    prior_reports: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=3000)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[SMHDW]\d{1,3}|INTRADAY|SWING|POSITION", normalized):
            raise ValueError("timeframe must look like M15, H1, D1, SWING or POSITION")
        return normalized

    @model_validator(mode="after")
    def require_evidence(self) -> "CryptoBrainRequest":
        fields = (
            self.market,
            self.technicals,
            self.derivatives,
            self.onchain,
            self.defi,
            self.news,
            self.social,
            self.position,
            self.portfolio,
            self.history,
            self.prior_reports,
        )
        if not any(fields):
            raise ValueError("at least one evidence field is required")
        return self

    def compact_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"), default=str)


class MarketAssetEvidence(BaseModel):
    symbol: str = Field(min_length=3, max_length=24)
    market: dict[str, Any] = Field(default_factory=dict)
    technicals: dict[str, Any] = Field(default_factory=dict)
    derivatives: dict[str, Any] = Field(default_factory=dict)
    onchain: dict[str, Any] = Field(default_factory=dict)
    news: list[Any] = Field(default_factory=list, max_length=20)
    social: list[Any] = Field(default_factory=list, max_length=20)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @model_validator(mode="after")
    def require_evidence(self) -> "MarketAssetEvidence":
        if not any((self.market, self.technicals, self.derivatives, self.onchain, self.news, self.social)):
            raise ValueError("each asset requires at least one evidence field")
        return self


class MarketIntelligenceRequest(BaseModel):
    timeframe: str = Field(default="H1", min_length=1, max_length=16)
    as_of: str = Field(default="", max_length=40)
    assets: list[MarketAssetEvidence] = Field(min_length=1, max_length=40)
    market_context: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=3000)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        return CryptoBrainRequest.validate_timeframe(value)

    @model_validator(mode="after")
    def require_unique_symbols(self) -> "MarketIntelligenceRequest":
        symbols = [asset.symbol for asset in self.assets]
        if len(symbols) != len(set(symbols)):
            raise ValueError("assets must contain unique symbols")
        return self

    def compact_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"), default=str)


class BrainResponse(BaseModel):
    ok: bool = True
    endpoint: str
    request_id: str
    model: str
    latency_ms: int
    result: dict[str, Any]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="gemma4:12b-it-qat", min_length=1, max_length=120)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    temperature: float = Field(default=0.5, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=32768)
    stream: bool = False

    @model_validator(mode="after")
    def reject_streaming(self) -> "ChatCompletionRequest":
        if self.stream:
            raise ValueError("streaming is not supported")
        return self

    def output_token_limit(self) -> int:
        return self.max_completion_tokens or self.max_tokens or 8192


class ChatCompletionMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage
