# Vendored OSS sources

Kurage Crypto Brain reads the pinned upstream intelligence contracts below at runtime and replaces only the LLM transport with local Gemma 4.

| Directory | Upstream | Pinned commit | License | Used intelligence |
| --- | --- | --- | --- | --- |
| `vendor/ai-hedge-fund-crypto` | `51bitquant/ai-hedge-fund-crypto` | `c6750e0041cb2e528856864783585427c45cc34d` | MIT | Exact `generate_trading_decision()` portfolio-manager prompt |
| `vendor/CryptoTradingAgents` | `Tomortec/CryptoTradingAgents` | `df6703a5763aaa6f6ac13ea52eaadb986c178f56` | Apache-2.0 | Bull researcher, bear researcher, and research-manager prompt contracts |
| `vendor/Vibe-Trading` | `HKUDS/Vibe-Trading` | `86f6012e00120e3fa5c3f0e15be8c94abe732dcf` | MIT | `crypto_trading_desk.yaml`: funding/basis, liquidation, flow, and desk-risk roles |
| `vendor/LLM_trader` | `qrak/LLM_trader` | `652279d09334f1061994e5228bcaf9114b35eb17` | MIT | Fresh-analysis, prompt-version, response-contract, and decision-gating rules |
| `vendor/helm-agents` | `QuantiaAI/helm-agents` | `244225ca75f1d402341ad7c67c2d5fbaf9f148d7` | Apache-2.0 | Four analyst prompts and portfolio-manager consensus prompt |

NoFX is intentionally not linked. Its AGPL-3.0 runtime combines LLM decisions with exchange execution. Kurage Crypto Brain has no exchange credentials, wallet keys, or order execution.
