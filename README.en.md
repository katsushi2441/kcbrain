# Kurage Crypto Brain

Kurage Crypto Brain exposes structured crypto-market intelligence from five pinned open-source agent frameworks. Its LLM transport can be switched between local Gemma 4 and DeepSeek V4 Flash. It reads upstream prompts, YAML agent definitions, and response contracts at runtime.

## Vendor APIs

- `POST /v1/vendor/ai-hedge-fund-crypto/portfolio`
- `POST /v1/vendor/crypto-trading-agents/debate`
- `POST /v1/vendor/vibe-trading/research`
- `POST /v1/vendor/llm-trader/analyze`
- `POST /v1/vendor/helm-agents/consensus`

Every response identifies the upstream repository, pinned commit, license, and source feature. There are no silent model or template fallbacks.

## NOFX integration

`POST /v1/chat/completions` is an OpenAI-compatible entry point for the market context, strategy prompt, and output contract produced by NOFX. kcbrain returns the model content unchanged; NOFX remains responsible for decision validation, risk controls, exchange connectivity, and order execution.

Select `Kurage Crypto Brain` as the AI model in NOFX and enter the same `KCBRAIN_API_TOKEN` in the API key field. When both services run on the same host, the default endpoint and model name work without customization.

## Market intelligence APIs

- `POST /v1/market/opportunity-ranking`
- `POST /v1/market/flow-ranking`
- `POST /v1/market/anomaly`
- `POST /v1/market/liquidation-risk`
- `POST /v1/signal/pair/{symbol}`

Ranking endpoints accept up to 40 caller-supplied asset snapshots. Pair signals reject requests when the URL symbol and JSON symbol differ. These APIs analyze supplied evidence only; they do not fetch market data or execute orders.

## Run

```bash
git submodule update --init --recursive
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.sample .env
.venv/bin/uvicorn kcbrain.api:app --host 0.0.0.0 --port 18328
```

Use local Gemma 4 (the default):

```dotenv
KCBRAIN_LLM_PROVIDER=ollama
KCBRAIN_OLLAMA_MODEL=gemma4:12b-it-qat
```

Use DeepSeek V4 Flash and restart the service:

```dotenv
KCBRAIN_LLM_PROVIDER=deepseek
KCBRAIN_DEEPSEEK_API_KEY=
KCBRAIN_DEEPSEEK_MODEL=deepseek-v4-flash
```

Gemma requests always set `think: false`; DeepSeek requests disable thinking explicitly. kcbrain never falls back silently to the other provider. Keep the DeepSeek API key in `.env`; it is never sent to the browser or committed to Git.

The service contains no exchange credentials, wallet access, or order execution. It produces decision support only.
