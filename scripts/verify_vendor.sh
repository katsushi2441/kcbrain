#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

declare -A expected=(
  [ai-hedge-fund-crypto]=c6750e0041cb2e528856864783585427c45cc34d
  [CryptoTradingAgents]=df6703a5763aaa6f6ac13ea52eaadb986c178f56
  [Vibe-Trading]=86f6012e00120e3fa5c3f0e15be8c94abe732dcf
  [LLM_trader]=652279d09334f1061994e5228bcaf9114b35eb17
  [helm-agents]=244225ca75f1d402341ad7c67c2d5fbaf9f148d7
)

for name in "${!expected[@]}"; do
  actual=$(git -C "vendor/$name" rev-parse HEAD)
  if [[ "$actual" != "${expected[$name]}" ]]; then
    echo "$name: expected ${expected[$name]}, got $actual" >&2
    exit 1
  fi
  echo "$name: $actual"
done
