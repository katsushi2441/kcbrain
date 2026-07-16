# Kurage Crypto Brain

Kurage Crypto Brain exposes structured crypto-market intelligence from five pinned open-source agent frameworks through a Gemma 4 API. It reads upstream prompts, YAML agent definitions, and response contracts at runtime while replacing the LLM transport with local Ollama.

## Vendor APIs

- `POST /v1/vendor/ai-hedge-fund-crypto/portfolio`
- `POST /v1/vendor/crypto-trading-agents/debate`
- `POST /v1/vendor/vibe-trading/research`
- `POST /v1/vendor/llm-trader/analyze`
- `POST /v1/vendor/helm-agents/consensus`

Every response identifies the upstream repository, pinned commit, license, and source feature. There are no silent model or template fallbacks.

## Run

```bash
git submodule update --init --recursive
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.sample .env
.venv/bin/uvicorn kcbrain.api:app --host 0.0.0.0 --port 18328
```

The service contains no exchange credentials, wallet access, or order execution. It produces decision support only.
