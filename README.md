# Kurage Crypto Brain

[English README](README.en.md)

暗号資産の取引ボディから独立して利用できる、Gemma 4による構造化判断API集です。5つのOSSを固定コミットで`vendor/`へ配置し、実際の上流プロンプト、YAMLエージェント定義、応答契約を暗号資産向けHTTP APIとして実行します。

## Vendor intelligence APIs

- `POST /v1/vendor/ai-hedge-fund-crypto/portfolio` - 上流`generate_trading_decision()`のポートフォリオ統合
- `POST /v1/vendor/crypto-trading-agents/debate` - 強気、弱気、research managerの討論
- `POST /v1/vendor/vibe-trading/research` - funding/basis、liquidation、flow、desk riskのCrypto Trading Desk
- `POST /v1/vendor/llm-trader/analyze` - fresh analysisとdecision gatingを使う市場判断
- `POST /v1/vendor/helm-agents/consensus` - 市場、センチメント、ニュース、ファンダメンタルズとportfolio managerの合議

各応答は上流リポジトリ、固定commit、license、利用した機能を返します。vendorが壊れた場合は独自テンプレートへフォールバックせず、明示的なエラーを返します。

## Core APIs

- `POST /v1/analyze/technical`
- `POST /v1/analyze/onchain`
- `POST /v1/analyze/sentiment`
- `POST /v1/debate/bull-bear`
- `POST /v1/decide/trade`
- `POST /v1/assess/risk`
- `POST /v1/decide/portfolio`
- `POST /v1/review/trade`
- `POST /v1/analyze/full`

## Setup

```bash
git submodule update --init --recursive
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.sample .env
# KCBRAIN_API_TOKENを設定
set -a; source .env; set +a
.venv/bin/uvicorn kcbrain.api:app --host 0.0.0.0 --port 18328
```

Ollamaモデルは`gemma4:12b-it-qat`です。すべての呼び出しで`think: false`を指定します。

## Public test UI

`public/kcbrain.php`は共通ログイン済み管理者だけがAPIを実行できるテスト画面です。API tokenはPHPプロキシ側に保持し、ブラウザへ公開しません。

## Safety

- 取引所API、wallet、秘密鍵を持ちません。
- 注文を実行しません。
- 入力された証拠だけを利用し、不足情報を明示します。
- 実取引側には固定リスク制御と人間の確認が別途必要です。
