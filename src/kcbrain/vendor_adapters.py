from __future__ import annotations

import ast
import json
import re
import runpy
from pathlib import Path
from typing import Any

import yaml

from .ollama import BrainError, CryptoBrain
from .schemas import CryptoBrainRequest


VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor"
UPSTREAM = {
    "ai-hedge-fund-crypto": {
        "name": "51bitquant/ai-hedge-fund-crypto",
        "commit": "c6750e0041cb2e528856864783585427c45cc34d",
        "license": "MIT",
    },
    "crypto-trading-agents": {
        "name": "Tomortec/CryptoTradingAgents",
        "commit": "df6703a5763aaa6f6ac13ea52eaadb986c178f56",
        "license": "Apache-2.0",
    },
    "vibe-trading": {
        "name": "HKUDS/Vibe-Trading",
        "commit": "86f6012e00120e3fa5c3f0e15be8c94abe732dcf",
        "license": "MIT",
    },
    "llm-trader": {
        "name": "qrak/LLM_trader",
        "commit": "652279d09334f1061994e5228bcaf9114b35eb17",
        "license": "MIT",
    },
    "helm-agents": {
        "name": "QuantiaAI/helm-agents",
        "commit": "244225ca75f1d402341ad7c67c2d5fbaf9f148d7",
        "license": "Apache-2.0",
    },
}

FOLDERS = {
    "ai-hedge-fund-crypto": "ai-hedge-fund-crypto",
    "crypto-trading-agents": "CryptoTradingAgents",
    "vibe-trading": "Vibe-Trading",
    "llm-trader": "LLM_trader",
    "helm-agents": "helm-agents",
}


def vendor_status() -> dict[str, Any]:
    return {
        key: {**UPSTREAM[key], "installed": (VENDOR_ROOT / folder / ".git").exists()}
        for key, folder in FOLDERS.items()
    }


def _require_file(path: Path, vendor: str) -> Path:
    if not path.is_file():
        raise BrainError(f"{vendor} vendor source is not installed: {path}")
    return path


def _source_strings(path: Path, function_name: str) -> list[str]:
    tree = ast.parse(_require_file(path, function_name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return [
                value.value
                for value in ast.walk(node)
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
    raise BrainError(f"upstream function not found: {function_name}")


def _json_schema_instruction(schema: str) -> str:
    return f"\n\nReturn one JSON object only. Do not invent missing evidence. Required schema:\n{schema}"


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return "(not supplied)"


class AiHedgeFundCryptoAdapter:
    """Runs the exact upstream portfolio-manager prompt with the selected LLM transport."""

    def __init__(self, brain: CryptoBrain) -> None:
        self.brain = brain

    def portfolio(self, request: CryptoBrainRequest) -> dict[str, Any]:
        price = request.market.get("price") or request.market.get("current_price")
        if not isinstance(price, (int, float)) or price <= 0:
            raise BrainError("ai-hedge-fund-crypto requires market.price greater than zero")
        max_units = request.portfolio.get("max_units")
        if not isinstance(max_units, (int, float)):
            max_value = request.portfolio.get("max_position_value")
            if not isinstance(max_value, (int, float)) or max_value < 0:
                raise BrainError("portfolio.max_units or portfolio.max_position_value is required")
            max_units = float(max_value) / float(price)

        source = (
            VENDOR_ROOT
            / "ai-hedge-fund-crypto/src/graph/portfolio_management_node.py"
        )
        strings = _source_strings(source, "generate_trading_decision")
        system_prompt = next((value for value in strings if "You are a portfolio manager" in value), "")
        human_prompt = next((value for value in strings if "Based on the team's analysis" in value), "")
        if not system_prompt or not human_prompt:
            raise BrainError("upstream ai-hedge-fund-crypto prompt contract changed")

        signals = request.prior_reports or {
            "technical_analyst_agent": request.technicals,
            "onchain_analyst_agent": request.onchain,
            "sentiment_analyst_agent": {
                "derivatives": request.derivatives,
                "news": request.news,
                "social": request.social,
            },
        }
        prompt = system_prompt + "\n\n" + human_prompt.format(
            signals_by_ticker=json.dumps({request.symbol: signals}, ensure_ascii=False, indent=2),
            current_prices=json.dumps({request.symbol: price}),
            max_shares=json.dumps({request.symbol: max_units}),
            portfolio_cash=f"{float(request.portfolio.get('cash', 0.0)):.2f}",
            portfolio_positions=json.dumps(request.portfolio.get("positions", {}), ensure_ascii=False),
            margin_requirement=f"{float(request.portfolio.get('margin_requirement', 0.0)):.2f}",
            total_margin_used=f"{float(request.portfolio.get('margin_used', 0.0)):.2f}",
        )
        prompt += "\n\nThis is a decision proposal only. Do not execute an order or call an exchange."
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["ai-hedge-fund-crypto"],
            "function": "src.graph.portfolio_management_node.generate_trading_decision",
            "transport": f"{self.brain.provider}:{self.brain.model}",
            "output": output,
        }


class CryptoTradingAgentsAdapter:
    """Executes the upstream bull, bear, and research-manager prompt contracts."""

    def __init__(self, brain: CryptoBrain) -> None:
        self.brain = brain

    def debate(self, request: CryptoBrainRequest) -> dict[str, Any]:
        path = _require_file(
            VENDOR_ROOT / "CryptoTradingAgents/tradingagents/i18n/prompts/en.py",
            "CryptoTradingAgents",
        )
        prompts = runpy.run_path(str(path)).get("PROMPTS")
        if not isinstance(prompts, dict):
            raise BrainError("CryptoTradingAgents PROMPTS could not be loaded")
        evidence = request.compact_json()
        reports = {
            "market_research_report": json.dumps(request.technicals or request.market, ensure_ascii=False),
            "sentiment_report": json.dumps(
                {"derivatives": request.derivatives, "social": request.social}, ensure_ascii=False
            ),
            "news_report": json.dumps(request.news, ensure_ascii=False),
            "fundamentals_report": json.dumps(
                {"onchain": request.onchain, "defi": request.defi}, ensure_ascii=False
            ),
            "history": json.dumps(request.history, ensure_ascii=False),
            "current_response": "",
            "past_memory_str": json.dumps(request.prior_reports, ensure_ascii=False),
            "external_reports": json.dumps(request.prior_reports, ensure_ascii=False),
        }
        researchers = prompts.get("researchers", {})
        bull_template = str(researchers.get("bull_researcher", ""))
        bear_template = str(researchers.get("bear_researcher", ""))
        manager_template = str(prompts.get("managers", {}).get("research_manager", ""))
        if not all((bull_template, bear_template, manager_template)):
            raise BrainError("CryptoTradingAgents debate prompt contract changed")

        bull = self.brain.generate_json(
            bull_template.format_map(_SafeFormat(reports))
            + f"\n\nCaller evidence:\n{evidence}"
            + _json_schema_instruction('{"case":["..."],"confidence":0,"invalidators":["..."]}')
        )
        bear_reports = {**reports, "current_response": json.dumps(bull, ensure_ascii=False)}
        bear = self.brain.generate_json(
            bear_template.format_map(_SafeFormat(bear_reports))
            + f"\n\nCaller evidence:\n{evidence}"
            + _json_schema_instruction('{"case":["..."],"confidence":0,"invalidators":["..."]}')
        )
        manager_values = {
            **reports,
            "history": json.dumps({"bull": bull, "bear": bear}, ensure_ascii=False),
        }
        decision = self.brain.generate_json(
            manager_template.format_map(_SafeFormat(manager_values))
            + _json_schema_instruction(
                '{"recommendation":"buy|sell|hold","confidence":0,"rationale":["..."],'
                '"entry_condition":"...","invalidation":"...","missing_data":["..."]}'
            )
        )
        return {
            "vendor": UPSTREAM["crypto-trading-agents"],
            "functions": ["bull_researcher", "bear_researcher", "research_manager"],
            "bull": bull,
            "bear": bear,
            "decision": decision,
        }


class VibeTradingAdapter:
    """Runs the pinned crypto trading desk YAML as a supplied-evidence agent team."""

    def __init__(self, brain: CryptoBrain) -> None:
        self.brain = brain

    def research(self, request: CryptoBrainRequest) -> dict[str, Any]:
        path = _require_file(
            VENDOR_ROOT / "Vibe-Trading/agent/src/swarm/presets/crypto_trading_desk.yaml",
            "Vibe-Trading",
        )
        preset = yaml.safe_load(path.read_text(encoding="utf-8"))
        agents = preset.get("agents", []) if isinstance(preset, dict) else []
        if len(agents) < 4:
            raise BrainError("Vibe-Trading crypto_trading_desk preset changed")
        evidence = request.compact_json()
        reports: dict[str, Any] = {}
        for agent in agents:
            agent_id = str(agent.get("id", ""))
            if agent_id == "desk_risk_manager":
                continue
            system_prompt = str(agent.get("system_prompt", "")).format_map(
                _SafeFormat(
                    target=request.symbol.replace("_", "-"),
                    timeframe=request.timeframe,
                    upstream_context="",
                )
            )
            reports[agent_id] = self.brain.generate_json(
                system_prompt
                + f"\n\nUse only this caller-supplied evidence; unavailable fields must be listed as missing:\n{evidence}"
                + _json_schema_instruction(
                    '{"signal":"bullish|neutral|bearish","confidence":0,"findings":["..."],'
                    '"risks":["..."],"missing_data":["..."]}'
                )
            )
        manager = next(agent for agent in agents if agent.get("id") == "desk_risk_manager")
        manager_prompt = str(manager.get("system_prompt", "")).format_map(
            _SafeFormat(
                target=request.symbol.replace("_", "-"),
                timeframe=request.timeframe,
                upstream_context=json.dumps(reports, ensure_ascii=False),
            )
        )
        decision = self.brain.generate_json(
            manager_prompt
            + "\n\nDo not execute. Return a proposal only."
            + _json_schema_instruction(
                '{"direction":"long|short|neutral|wait","confidence":0,"rationale":["..."],'
                '"entry_condition":"...","risk_gates":["..."],"missing_data":["..."]}'
            )
        )
        return {
            "vendor": UPSTREAM["vibe-trading"],
            "preset": "agent/src/swarm/presets/crypto_trading_desk.yaml",
            "reports": reports,
            "decision": decision,
        }


class LlmTraderAdapter:
    """Applies the upstream fresh-analysis and decision-gating contract to supplied evidence."""

    def __init__(self, brain: CryptoBrain) -> None:
        self.brain = brain

    def analyze(self, request: CryptoBrainRequest) -> dict[str, Any]:
        template_path = _require_file(
            VENDOR_ROOT / "LLM_trader/src/analyzer/prompts/template_manager.py", "LLM_trader"
        )
        builder_path = _require_file(
            VENDOR_ROOT / "LLM_trader/src/analyzer/prompts/prompt_builder.py", "LLM_trader"
        )
        tree = ast.parse(template_path.read_text(encoding="utf-8"))
        metadata: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "TemplateManager":
                for item in node.body:
                    if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id in {
                                "PROMPT_VERSION",
                                "RESPONSE_CONTRACT_VERSION",
                                "PROMPT_VARIANT",
                            }:
                                metadata[target.id.lower()] = str(item.value.value)
        task_literals = _source_strings(builder_path, "build_prompt")
        fresh_rule = next(
            (value for value in task_literals if "perform a fresh analysis" in value),
            "Perform a fresh analysis and re-derive the decision from current evidence.",
        )
        prompt = (
            "You are executing LLM_trader's decision-gated crypto analysis contract.\n"
            f"{fresh_rule}\n"
            "Assess trend, momentum, volatility, market microstructure, funding, position state and risk/reward. "
            "Do not reuse a prior signal when current evidence contradicts it.\n"
            f"Evidence: {request.compact_json()}"
            + _json_schema_instruction(
                '{"signal":"buy|sell|hold","confidence":0,"trend":"...","confluence":["..."],'
                '"entry_condition":"...","stop_condition":"...","risk_reward":"...",'
                '"reasoning":["..."],"missing_data":["..."]}'
            )
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["llm-trader"],
            "source": "src/analyzer/prompts/{prompt_builder.py,template_manager.py}",
            "contract": metadata,
            "output": output,
        }


def _typescript_prompt(source: str, name: str) -> str:
    match = re.search(rf"export const {re.escape(name)}[^=]*= `([\s\S]*?)`;", source)
    if not match:
        raise BrainError(f"HELM Agents prompt not found: {name}")
    return match.group(1).replace("${RATING_SCALE}", "Use one rating: Buy, Overweight, Hold, Underweight, Sell.")


class HelmAgentsAdapter:
    """Runs HELM's analyst and portfolio-manager prompt contracts as a consensus."""

    def __init__(self, brain: CryptoBrain) -> None:
        self.brain = brain

    def consensus(self, request: CryptoBrainRequest) -> dict[str, Any]:
        path = _require_file(
            VENDOR_ROOT / "helm-agents/packages/agents/src/prompts.ts", "HELM Agents"
        )
        source = path.read_text(encoding="utf-8")
        evidence = request.compact_json()
        reports: dict[str, Any] = {}
        for role, constant in {
            "market": "MARKET_ANALYST_SYSTEM",
            "sentiment": "SENTIMENT_ANALYST_SYSTEM",
            "news": "NEWS_ANALYST_SYSTEM",
            "fundamentals": "FUNDAMENTALS_ANALYST_SYSTEM",
        }.items():
            reports[role] = self.brain.generate_json(
                _typescript_prompt(source, constant)
                + f"\n\nInstrument: {request.symbol}\nCaller evidence: {evidence}"
                + _json_schema_instruction(
                    '{"signal":"bullish|neutral|bearish","confidence":0,"findings":["..."],'
                    '"risks":["..."],"missing_data":["..."]}'
                )
            )
        manager_prompt = _typescript_prompt(source, "PORTFOLIO_MANAGER_SYSTEM")
        decision = self.brain.generate_json(
            manager_prompt
            + f"\n\nInstrument: {request.symbol}\nAnalyst reports: "
            + json.dumps(reports, ensure_ascii=False)
            + "\nThis is analysis only; do not execute an order."
            + _json_schema_instruction(
                '{"rating":"Buy|Overweight|Hold|Underweight|Sell","confidence":0,'
                '"rationale":["..."],"risk_conditions":["..."],"missing_data":["..."]}'
            )
        )
        return {
            "vendor": UPSTREAM["helm-agents"],
            "source": "packages/agents/src/prompts.ts",
            "reports": reports,
            "decision": decision,
        }
