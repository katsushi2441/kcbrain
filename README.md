# Kurage Crypto Brain

[English README](README.en.md)

暗号資産の取引ボディから独立して利用できる構造化判断API集です。ローカルのGemma 4またはDeepSeek V4 Flashを設定で選択できます。5つのOSSを固定コミットで`vendor/`へ配置し、実際の上流プロンプト、YAMLエージェント定義、応答契約を暗号資産向けHTTP APIとして実行します。

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

## NOFX integration

`POST /v1/chat/completions`は、NOFXが生成した市場データ、戦略プロンプト、出力契約を選択中のLLMへ渡すOpenAI互換入口です。kcbrainは応答本文を加工せず返し、NOFX側が判断JSONの検証、リスク制御、取引所接続、注文実行を担当します。

NOFXのAIモデル設定で`Kurage Crypto Brain`を選び、kcbrainと同じ`KCBRAIN_API_TOKEN`をAPI Key欄へ設定します。同一ホストで動かす場合、接続先とモデル名は既定値のままで利用できます。

## Market intelligence APIs

- `POST /v1/market/opportunity-ranking` - 複数銘柄のリスク調整後機会ランキング
- `POST /v1/market/flow-ranking` - 資金流の方向、強度、継続性ランキング
- `POST /v1/market/anomaly` - 価格、出来高、OI、funding、清算などの異常検出
- `POST /v1/market/liquidation-risk` - ロング・ショート別の清算連鎖リスク
- `POST /v1/signal/pair/{symbol}` - 個別銘柄の根拠付き方向シグナル

ランキング系APIは`assets`へ最大40銘柄の観測値を渡します。個別シグナルはURLとJSON本文の`symbol`が一致しない場合、誤判定防止のため拒否します。いずれも入力された証拠だけを評価し、市場データの自動取得や注文実行は行いません。

## Setup

```bash
git submodule update --init --recursive
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.sample .env
# KCBRAIN_API_TOKENと利用するLLMを設定
set -a; source .env; set +a
.venv/bin/uvicorn kcbrain.api:app --host 0.0.0.0 --port 18328
```

ローカルGemma 4を使う既定設定です。

```dotenv
KCBRAIN_LLM_PROVIDER=ollama
KCBRAIN_OLLAMA_MODEL=gemma4:12b-it-qat
```

DeepSeek V4 Flashへ切り替える場合は次を設定し、サービスを再起動します。

```dotenv
KCBRAIN_LLM_PROVIDER=deepseek
KCBRAIN_DEEPSEEK_API_KEY=
KCBRAIN_DEEPSEEK_MODEL=deepseek-v4-flash
```

Gemma 4にはすべての呼び出しで`think: false`を指定し、DeepSeek V4 Flashはthinkingを無効にして呼び出します。選択したプロバイダーが失敗しても、別モデルへ自動フォールバックしません。DeepSeek APIキーは`.env`だけに保存し、ブラウザやGitへ公開しません。

## Public test UI

`public/kcbrain.php`は共通ログイン済み管理者だけがAPIを実行できるテスト画面です。API tokenはPHPプロキシ側に保持し、ブラウザへ公開しません。

## Safety

- 取引所API、wallet、秘密鍵を持ちません。
- 注文を実行しません。
- 入力された証拠だけを利用し、不足情報を明示します。
- 実取引側には固定リスク制御と人間の確認が別途必要です。
