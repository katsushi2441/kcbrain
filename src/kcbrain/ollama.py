from __future__ import annotations

import json
import re
import threading
from typing import Any

import requests

from .config import Settings, settings
from .prompts import build_prompt
from .schemas import CryptoBrainRequest, MarketIntelligenceRequest


class BrainError(RuntimeError):
    pass


REQUIRED_RESULT_KEYS = {
    "technical": {"signal", "confidence", "evidence"},
    "onchain": {"signal", "confidence", "drivers"},
    "sentiment": {"sentiment", "market_impact", "confidence"},
    "debate": {"bull_case", "bear_case", "balance"},
    "trade": {"action", "confidence", "invalidation", "rationale"},
    "risk": {"verdict", "risk_score", "hazards", "safeguards"},
    "portfolio": {"action", "confidence", "rationale"},
    "review": {"process_quality", "classification", "lesson", "next_rule"},
    "full": {"technical", "onchain", "sentiment", "debate", "trade", "risk"},
    "market_opportunity_ranking": {"ranking", "market_summary", "missing_data"},
    "market_flow_ranking": {"ranking", "market_summary", "missing_data"},
    "market_anomaly": {"anomalies", "normal_assets", "market_summary", "missing_data"},
    "market_liquidation_risk": {"ranking", "systemic_risk", "market_summary"},
    "pair_signal": {"symbol", "direction", "action", "confidence", "invalidation", "risk_flags"},
}


def extract_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise BrainError("LLM returned an invalid JSON object")


def validate_result(task: str, result: dict[str, Any]) -> dict[str, Any]:
    missing = REQUIRED_RESULT_KEYS[task] - set(result)
    if missing:
        raise BrainError(f"LLM result is missing required fields: {', '.join(sorted(missing))}")
    return result


def missing_result_keys(task: str, result: dict[str, Any]) -> set[str]:
    return REQUIRED_RESULT_KEYS[task] - set(result)


class CryptoBrain:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._lock = threading.Lock()

    def health(self) -> dict[str, Any]:
        if self.config.llm_provider == "deepseek":
            return self._deepseek_health()
        if self.config.llm_provider != "ollama":
            return {
                "provider": self.config.llm_provider,
                "reachable": False,
                "model_available": False,
                "error": "KCBRAIN_LLM_PROVIDER must be ollama or deepseek",
            }
        try:
            response = requests.get(f"{self.config.ollama_url}/api/tags", timeout=4)
            response.raise_for_status()
            names = {str(item.get("name") or "") for item in response.json().get("models", [])}
            return {
                "provider": "ollama",
                "reachable": True,
                "model_available": self.config.ollama_model in names,
                "models": sorted(names),
            }
        except Exception as exc:
            return {
                "provider": "ollama",
                "reachable": False,
                "model_available": False,
                "error": str(exc)[:200],
            }

    @property
    def provider(self) -> str:
        return self.config.llm_provider

    @property
    def model(self) -> str:
        return self.config.active_model

    def _deepseek_headers(self) -> dict[str, str]:
        if not self.config.deepseek_api_key:
            raise BrainError("KCBRAIN_DEEPSEEK_API_KEY is not configured")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    def _deepseek_health(self) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.config.deepseek_base_url}/models",
                headers=self._deepseek_headers(),
                timeout=min(self.config.deepseek_timeout, 10),
            )
            response.raise_for_status()
            names = {str(item.get("id") or "") for item in response.json().get("data", [])}
            return {
                "provider": "deepseek",
                "reachable": True,
                "model_available": self.config.deepseek_model in names,
                "models": sorted(names),
            }
        except Exception as exc:
            return {
                "provider": "deepseek",
                "reachable": False,
                "model_available": False,
                "error": str(exc)[:200],
            }

    def analyze(self, task: str, request: CryptoBrainRequest | MarketIntelligenceRequest) -> dict[str, Any]:
        evidence = request.compact_json()
        prompt = build_prompt(task, evidence)
        result = self.generate_json(prompt)
        missing = missing_result_keys(task, result)
        if missing:
            repair_prompt = (
                f"{prompt}\n\n"
                "PREVIOUS OUTPUT (INVALID)\n"
                f"{json.dumps(result, ensure_ascii=False, separators=(',', ':'))}\n\n"
                "REPAIR INSTRUCTION\n"
                f"The previous JSON omitted these required top-level fields: {', '.join(sorted(missing))}. "
                "Return one complete corrected JSON object. Preserve valid existing values, add every missing "
                "field using only CALLER EVIDENCE, and list unavailable evidence explicitly in missing_data. "
                "Do not return commentary or markdown."
            )
            result = self.generate_json(repair_prompt)
        return validate_result(task, result)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        input_chars = sum(len(message.get("role", "")) + len(message.get("content", "")) for message in messages)
        if input_chars > self.config.max_input_chars:
            raise BrainError(f"input exceeds {self.config.max_input_chars} characters")
        if self.config.llm_provider == "deepseek":
            return self._chat_deepseek(messages, temperature, max_tokens)
        if self.config.llm_provider != "ollama":
            raise BrainError("KCBRAIN_LLM_PROVIDER must be ollama or deepseek")
        payload = {
            "model": self.config.ollama_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            with self._lock:
                response = requests.post(
                    f"{self.config.ollama_url}/api/chat",
                    json=payload,
                    timeout=self.config.ollama_timeout,
                )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise BrainError(f"Ollama request failed: {exc}") from exc
        content = str((body.get("message") or {}).get("content") or "").strip()
        if not content:
            reason = str(body.get("done_reason") or "unknown")
            raise BrainError(f"Ollama returned an empty response (done_reason={reason})")
        prompt_tokens = int(body.get("prompt_eval_count") or 0)
        completion_tokens = int(body.get("eval_count") or 0)
        return {
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _chat_deepseek(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.deepseek_model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        try:
            response = requests.post(
                f"{self.config.deepseek_base_url}/chat/completions",
                headers=self._deepseek_headers(),
                json=payload,
                timeout=self.config.deepseek_timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise BrainError(f"DeepSeek request failed: {exc}") from exc
        choices = body.get("choices") or []
        content = str(((choices[0] if choices else {}).get("message") or {}).get("content") or "").strip()
        if not content:
            finish_reason = str((choices[0] if choices else {}).get("finish_reason") or "unknown")
            raise BrainError(f"DeepSeek returned an empty response (finish_reason={finish_reason})")
        usage = body.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        return {
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
        }

    def generate_json(self, prompt: str, max_tokens: int = 2200) -> dict[str, Any]:
        if len(prompt) > self.config.max_input_chars:
            raise BrainError(f"input exceeds {self.config.max_input_chars} characters")
        if self.config.llm_provider == "deepseek":
            result = self._chat_deepseek(
                [
                    {
                        "role": "system",
                        "content": "Return exactly one valid JSON object and no commentary or markdown.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.15,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return extract_json_object(result["content"])
        if self.config.llm_provider != "ollama":
            raise BrainError("KCBRAIN_LLM_PROVIDER must be ollama or deepseek")
        payload = {
            "model": self.config.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0.15, "num_predict": max_tokens},
        }
        try:
            with self._lock:
                response = requests.post(
                    f"{self.config.ollama_url}/api/generate",
                    json=payload,
                    timeout=self.config.ollama_timeout,
                )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise BrainError(f"Ollama request failed: {exc}") from exc
        raw = str(body.get("response") or "").strip()
        if not raw:
            reason = str(body.get("done_reason") or "unknown")
            raise BrainError(f"Ollama returned an empty response (done_reason={reason})")
        return extract_json_object(raw)
