#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. /home/kojima/work/aixec/.env
set +a

remote="/web/kurage_exbridge_jp"
curl --fail --ftp-create-dirs -T public/kcbrain.php \
  "ftp://${FTP_USER}:${FTP_PASS}@${FTP_HOST}${remote}/kcbrain.php"

if [[ -f public/kcbrain_config.php ]]; then
  curl --fail --ftp-create-dirs -T public/kcbrain_config.php \
    "ftp://${FTP_USER}:${FTP_PASS}@${FTP_HOST}${remote}/kcbrain_config.php"
fi

echo "deployed: https://kurage.exbridge.jp/kcbrain.php"
