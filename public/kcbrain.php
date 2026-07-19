<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/auth_common.php';
require_once __DIR__ . '/kcbrain_config.php';
date_default_timezone_set('Asia/Tokyo');

$THIS_FILE = 'kcbrain.php';
if (isset($_GET['login'])) {
    header('Location: ' . url2ai_auth_login_url('/' . $THIS_FILE));
    exit;
}
if (isset($_GET['logout'])) {
    header('Location: ' . url2ai_auth_logout_url('/' . $THIS_FILE));
    exit;
}

$auth = url2ai_auth_bootstrap();
$is_admin = !empty($auth['is_admin']);
$logged_in = !empty($auth['logged_in']);
if (empty($_SESSION['kcbrain_csrf'])) {
    $_SESSION['kcbrain_csrf'] = bin2hex(random_bytes(24));
}
$csrf = $_SESSION['kcbrain_csrf'];

function kcb_h($value) {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function kcb_api($method, $path, $payload = null, $timeout = 600) {
    $base = rtrim(KCBRAIN_API_BASE, '/');
    $headers = array('Accept: application/json', 'Content-Type: application/json');
    if (KCBRAIN_API_TOKEN !== '') {
        $headers[] = 'X-KCBrain-Token: ' . KCBRAIN_API_TOKEN;
    }
    $ch = curl_init($base . $path);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 8);
    curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    if ($payload !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
    }
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    if ($body === false || $error !== '') {
        return array('status' => 502, 'data' => array('ok' => false, 'detail' => $error ?: 'API connection failed'));
    }
    $decoded = json_decode($body, true);
    if (!is_array($decoded)) {
        $decoded = array('ok' => false, 'detail' => 'API returned invalid JSON');
        $status = 502;
    }
    return array('status' => $status ?: 502, 'data' => $decoded);
}

$endpoint_map = array(
    'technical' => '/v1/analyze/technical',
    'onchain' => '/v1/analyze/onchain',
    'sentiment' => '/v1/analyze/sentiment',
    'debate' => '/v1/debate/bull-bear',
    'trade' => '/v1/decide/trade',
    'risk' => '/v1/assess/risk',
    'portfolio' => '/v1/decide/portfolio',
    'review' => '/v1/review/trade',
    'full' => '/v1/analyze/full',
    'opportunity-ranking' => '/v1/market/opportunity-ranking',
    'flow-ranking' => '/v1/market/flow-ranking',
    'market-anomaly' => '/v1/market/anomaly',
    'liquidation-risk' => '/v1/market/liquidation-risk',
    'pair-signal' => '/v1/signal/pair/{symbol}',
    'aihf-portfolio' => '/v1/vendor/ai-hedge-fund-crypto/portfolio',
    'crypto-agents' => '/v1/vendor/crypto-trading-agents/debate',
    'vibe-research' => '/v1/vendor/vibe-trading/research',
    'llm-trader' => '/v1/vendor/llm-trader/analyze',
    'helm-consensus' => '/v1/vendor/helm-agents/consensus',
);

if (isset($_GET['proxy'])) {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');
    $proxy = (string)$_GET['proxy'];
    if ($proxy === 'health') {
        $response = kcb_api('GET', '/health', null, 10);
    } elseif ($proxy === 'meta') {
        $response = kcb_api('GET', '/v1/meta', null, 10);
    } elseif ($proxy === 'run' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_admin) {
            http_response_code(403);
            echo json_encode(array('ok' => false, 'detail' => '管理者ログインが必要です'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $sent_csrf = isset($_SERVER['HTTP_X_CSRF_TOKEN']) ? (string)$_SERVER['HTTP_X_CSRF_TOKEN'] : '';
        if (!hash_equals($csrf, $sent_csrf)) {
            http_response_code(403);
            echo json_encode(array('ok' => false, 'detail' => 'CSRF検証に失敗しました'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $endpoint = isset($_GET['endpoint']) ? (string)$_GET['endpoint'] : '';
        if (!isset($endpoint_map[$endpoint])) {
            http_response_code(400);
            echo json_encode(array('ok' => false, 'detail' => '未対応のAPIです'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $raw = file_get_contents('php://input');
        if (strlen($raw) > 60000) {
            http_response_code(413);
            echo json_encode(array('ok' => false, 'detail' => '入力が大きすぎます'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $payload = json_decode($raw, true);
        if (!is_array($payload)) {
            http_response_code(400);
            echo json_encode(array('ok' => false, 'detail' => 'JSONを確認してください'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $api_path = $endpoint_map[$endpoint];
        if ($endpoint === 'pair-signal') {
            $symbol = isset($payload['symbol']) ? strtoupper(str_replace(array('/', '-'), '_', trim((string)$payload['symbol']))) : '';
            if (!preg_match('/^[A-Z0-9]{2,12}_[A-Z0-9]{2,12}$/', $symbol)) {
                http_response_code(422);
                echo json_encode(array('ok' => false, 'detail' => 'symbolを確認してください'), JSON_UNESCAPED_UNICODE);
                exit;
            }
            $api_path = str_replace('{symbol}', rawurlencode($symbol), $api_path);
        }
        $slow = in_array($endpoint, array('crypto-agents', 'vibe-research', 'helm-consensus'), true);
        $timeout = $slow ? 1800 : 600;
        if ($slow) {
            @set_time_limit(0);
        }
        $response = kcb_api('POST', $api_path, $payload, $timeout);
    } else {
        $response = array('status' => 404, 'data' => array('ok' => false, 'detail' => 'unknown proxy'));
    }
    http_response_code((int)$response['status']);
    echo json_encode($response['data'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}
?><!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kurage Crypto Brain | Gemma 暗号資産判断API</title>
<meta name="description" content="Gemma 4を使った暗号資産分析・討論・売買判断・リスク判定APIのテストコンソール。">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23008da3'/%3E%3Ctext x='32' y='39' text-anchor='middle' font-family='sans-serif' font-size='20' font-weight='700' fill='white'%3EKCB%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#f3f7f6;--surface:#fff;--ink:#102b33;--muted:#60777d;--line:#d9e5e3;--aqua:#008da3;--navy:#153f55;--mint:#dff4ef;--coral:#d75a4a;--code:#f7faf9;--shadow:0 12px 34px rgba(22,66,72,.08)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at 84% 4%,#dff5f0 0,transparent 28%),linear-gradient(135deg,#f8faf7 0,#eef6f6 100%);color:var(--ink);font-family:"Noto Sans JP","Avenir Next","Yu Gothic",sans-serif;font-size:14px}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(0,141,163,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,141,163,.025) 1px,transparent 1px);background-size:34px 34px}
header{height:58px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.88);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:space-between;padding:0 24px;position:relative;z-index:2}
.brand{display:flex;align-items:center;gap:11px}.mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,var(--aqua),var(--navy));display:grid;place-items:center;color:#fff;font-size:13px;font-weight:900}.brand strong{font-size:16px;letter-spacing:.01em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.16em;margin-top:1px}.user{display:flex;align-items:center;gap:9px;color:var(--muted);font-size:12px}.user a{color:var(--navy);text-decoration:none;border:1px solid var(--line);background:#fff;padding:6px 10px;border-radius:7px}
.shell{position:relative;z-index:1;max-width:1240px;margin:0 auto;padding:18px 22px 28px}.intro{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:14px}.intro h1{font-size:23px;line-height:1.25;margin:0 0 5px;letter-spacing:-.02em}.intro p{margin:0;color:var(--muted);font-size:12px;line-height:1.6}.health{display:flex;align-items:center;gap:7px;background:#fff;border:1px solid var(--line);padding:7px 11px;border-radius:9px;font-size:11px;font-weight:800;white-space:nowrap}.dot{width:8px;height:8px;border-radius:50%;background:#9aa}.dot.ok{background:#27a56d;box-shadow:0 0 0 4px rgba(39,165,109,.12)}.dot.bad{background:var(--coral)}
.workspace{display:grid;grid-template-columns:minmax(420px,.94fr) minmax(440px,1.06fr);gap:14px;min-height:590px}.panel{background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);overflow:hidden;min-width:0}.panel-head{height:46px;display:flex;align-items:center;justify-content:space-between;padding:0 15px;border-bottom:1px solid var(--line);background:#fbfdfc}.panel-head strong{font-size:13px}.panel-head span{color:var(--muted);font-size:10px}.panel-body{padding:14px}
.steps{display:flex;align-items:center;gap:6px;margin-bottom:10px;color:var(--muted);font-size:10px}.steps b{display:inline-grid;place-items:center;width:19px;height:19px;border-radius:50%;background:var(--mint);color:var(--aqua);font-size:10px}.steps i{height:1px;flex:1;background:var(--line)}
.function-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-bottom:8px}.function-tab{border:1px solid var(--line);border-radius:8px;background:#f8fbfa;color:var(--muted);padding:8px 4px;font:800 11px/1.2 inherit;cursor:pointer}.function-tab.active{background:var(--navy);border-color:var(--navy);color:#fff}.function-pane{display:none;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;max-height:210px;overflow:auto;padding:1px 3px 3px 1px}.function-pane.active{display:grid}.function-card{min-height:61px;border:1px solid var(--line);border-radius:9px;background:#fff;padding:8px 9px;text-align:left;color:var(--ink);cursor:pointer}.function-card:hover{border-color:#85c5cd;background:#fbfefd}.function-card.active{border-color:var(--aqua);background:#eef9f7;box-shadow:inset 3px 0 0 var(--aqua)}.function-card strong{display:block;color:var(--navy);font-size:12px;line-height:1.25}.function-card small{display:block;margin-top:4px;color:var(--muted);font-size:10px;line-height:1.4}.selected-function{margin:9px 0;padding:9px 11px;border:1px solid #b8dcd8;border-radius:9px;background:linear-gradient(135deg,#f3fbf9,#f8fbfd)}.selected-function span{color:var(--aqua);font-size:9px;font-weight:900;letter-spacing:.12em}.selected-function strong{display:block;margin-top:2px;font-size:13px}.selected-function p{margin:3px 0 0;color:var(--muted);font-size:11px;line-height:1.45}.input-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}.input-head strong{font-size:11px}.toolbar{display:flex;gap:6px}.tool{border:1px solid var(--line);background:#fff;color:var(--muted);border-radius:7px;padding:5px 8px;font:700 10px inherit;cursor:pointer}.editor{display:block;width:100%;height:270px;resize:vertical;border:1px solid #cadbd8;border-radius:9px;background:var(--code);padding:12px;color:#1c3840;font:12px/1.55 "IBM Plex Mono","SFMono-Regular",Consolas,monospace;outline:none;tab-size:2}.editor:focus{border-color:var(--aqua);box-shadow:0 0 0 3px rgba(0,141,163,.09)}.run{margin-top:10px;width:100%;border:0;border-radius:9px;background:linear-gradient(135deg,var(--navy),var(--aqua));color:#fff;padding:11px 16px;font:800 13px inherit;cursor:pointer;box-shadow:0 8px 18px rgba(0,111,137,.18)}.run:disabled{opacity:.55;cursor:wait}
.result{height:622px;overflow:auto;margin:0;background:#102d35;color:#d7f0eb;padding:15px;font:12px/1.6 "IBM Plex Mono","SFMono-Regular",Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.result.empty{color:#8fb1b3}.result.error{color:#ffd0c9}.metrics{display:flex;gap:12px;color:var(--muted);font-size:10px}.notice{background:#fff8e8;border:1px solid #ecdbaa;border-radius:10px;padding:12px 14px;color:#705d25;line-height:1.7;font-size:12px}.login-box{max-width:520px;margin:90px auto;background:#fff;border:1px solid var(--line);border-radius:14px;padding:28px;box-shadow:var(--shadow);text-align:center}.login-box h2{margin:0 0 8px;font-size:19px}.login-box p{color:var(--muted);line-height:1.7}.login-box a{display:inline-block;margin-top:8px;background:var(--navy);color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-weight:800}
footer{position:relative;z-index:1;text-align:center;color:var(--muted);font-size:10px;padding:0 20px 22px}footer a{color:var(--aqua);text-decoration:none}
@media(max-width:900px){header{padding:0 14px}.shell{padding:14px}.workspace{grid-template-columns:1fr}.result{height:390px}.intro{align-items:flex-start;flex-direction:column}}
@media(max-width:520px){.function-tabs{grid-template-columns:repeat(2,1fr)}.function-pane{grid-template-columns:1fr;max-height:230px}.editor{height:290px}.user span{display:none}.intro h1{font-size:20px}.steps span{display:none}}
</style>
</head>
<body>
<header>
  <div class="brand"><div class="mark">KCB</div><div><strong>Kurage Crypto Brain</strong><small>GEMMA CRYPTO API</small></div></div>
  <div class="user"><span><?php echo $logged_in ? kcb_h($auth['session_user']) : 'guest'; ?></span><?php if ($logged_in): ?><a href="?logout=1">ログアウト</a><?php else: ?><a href="?login=1">ログイン</a><?php endif; ?></div>
</header>
<?php if (!$is_admin): ?>
<main class="shell"><div class="login-box"><h2>管理者用APIテスト画面</h2><p>Gemma 暗号資産判断APIの実行には、共通管理者ログインが必要です。</p><a href="?login=1">共通ログインへ</a></div></main>
<?php else: ?>
<main class="shell">
  <div class="intro"><div><h1>Crypto Intelligence Workbench</h1><p>構造化した市場情報をGemma 4へ渡し、分析役ごとのJSON判断を確認します。注文は実行しません。</p></div><div class="health"><i class="dot" id="healthDot"></i><span id="healthText">API確認中</span></div></div>
  <div class="workspace">
    <section class="panel">
      <div class="panel-head"><strong>Request</strong><span id="endpointPath">/v1/analyze/technical</span></div>
      <div class="panel-body">
        <div class="steps"><b>1</b><span>機能を選ぶ</span><i></i><b>2</b><span>入力を確認</span><i></i><b>3</b><span>実行する</span></div>
        <div class="function-tabs" role="tablist" aria-label="機能カテゴリ">
          <button class="function-tab active" data-tab="basic" role="tab" aria-selected="true">基本分析</button>
          <button class="function-tab" data-tab="decision" role="tab" aria-selected="false">売買判断</button>
          <button class="function-tab" data-tab="market" role="tab" aria-selected="false">市場スキャン</button>
          <button class="function-tab" data-tab="oss" role="tab" aria-selected="false">OSSエージェント</button>
        </div>
        <div class="function-pane active" data-pane="basic">
          <button class="function-card active" data-key="technical" data-path="/v1/analyze/technical" data-preset="btc" data-title="テクニカル分析" data-description="価格・RSI・移動平均から相場の方向を分析します。"><strong>テクニカル分析</strong><small>値動きと指標から方向を確認</small></button>
          <button class="function-card" data-key="onchain" data-path="/v1/analyze/onchain" data-preset="btc" data-title="オンチェーン分析" data-description="取引所流入出やステーブルコイン供給から資金移動を分析します。"><strong>オンチェーン分析</strong><small>ブロックチェーン上の資金移動</small></button>
          <button class="function-card" data-key="sentiment" data-path="/v1/analyze/sentiment" data-preset="btc" data-title="センチメント分析" data-description="ニュースとSNSの情報から市場心理を整理します。"><strong>センチメント分析</strong><small>ニュースとSNSの市場心理</small></button>
          <button class="function-card" data-key="full" data-path="/v1/analyze/full" data-preset="btc" data-title="総合分析" data-description="テクニカル・需給・ニュースをまとめて総合評価します。"><strong>総合分析</strong><small>複数の材料をまとめて評価</small></button>
        </div>
        <div class="function-pane" data-pane="decision">
          <button class="function-card" data-key="debate" data-path="/v1/debate/bull-bear" data-preset="btc" data-title="強気・弱気討論" data-description="強気派と弱気派の根拠を比較します。"><strong>強気・弱気討論</strong><small>上昇・下落の両方の根拠</small></button>
          <button class="function-card" data-key="trade" data-path="/v1/decide/trade" data-preset="btc" data-title="売買判断" data-description="入力した市場情報から売買・待機の判断を返します。"><strong>売買判断</strong><small>買う・売る・待つを判断</small></button>
          <button class="function-card" data-key="risk" data-path="/v1/assess/risk" data-preset="btc" data-title="リスク評価" data-description="値動きやポジションの危険要因を評価します。"><strong>リスク評価</strong><small>損失につながる要因を確認</small></button>
          <button class="function-card" data-key="portfolio" data-path="/v1/decide/portfolio" data-preset="btc" data-title="保有管理" data-description="現在の保有内容を継続・縮小・整理する判断を返します。"><strong>保有管理</strong><small>保有ポジションを見直す</small></button>
          <button class="function-card" data-key="review" data-path="/v1/review/trade" data-preset="btc" data-title="取引レビュー" data-description="過去の取引結果を振り返り、改善点を抽出します。"><strong>取引レビュー</strong><small>取引結果から改善点を抽出</small></button>
        </div>
        <div class="function-pane" data-pane="market">
          <button class="function-card" data-key="opportunity-ranking" data-path="/v1/market/opportunity-ranking" data-preset="market" data-title="市場機会ランキング" data-description="複数銘柄を比較し、有望な機会を順位付けします。"><strong>市場機会ランキング</strong><small>有望な銘柄を順位付け</small></button>
          <button class="function-card" data-key="flow-ranking" data-path="/v1/market/flow-ranking" data-preset="market" data-title="資金フローランキング" data-description="資金が流入・流出している銘柄を比較します。"><strong>資金フローランキング</strong><small>資金が向かう銘柄を比較</small></button>
          <button class="function-card" data-key="market-anomaly" data-path="/v1/market/anomaly" data-preset="market" data-title="市場異常検出" data-description="急変や通常と異なる市場状態を検出します。"><strong>市場異常検出</strong><small>急変と異常な動きを検出</small></button>
          <button class="function-card" data-key="liquidation-risk" data-path="/v1/market/liquidation-risk" data-preset="market" data-title="清算連鎖リスク" data-description="デリバティブ市場の清算連鎖リスクを評価します。"><strong>清算連鎖リスク</strong><small>連鎖的な清算の危険度</small></button>
          <button class="function-card" data-key="pair-signal" data-path="/v1/signal/pair/{symbol}" data-preset="btc" data-title="個別銘柄シグナル" data-description="指定した1銘柄の現在のシグナルを分析します。"><strong>個別銘柄シグナル</strong><small>1銘柄を詳しく判断</small></button>
        </div>
        <div class="function-pane" data-pane="oss">
          <button class="function-card" data-key="aihf-portfolio" data-path="/v1/vendor/ai-hedge-fund-crypto/portfolio" data-preset="btc" data-title="AI Hedge Fund ポートフォリオ" data-description="AI Hedge Fund由来の役割分担で保有構成を検討します。"><strong>AI Hedge Fund</strong><small>ポートフォリオを統合判断</small></button>
          <button class="function-card" data-key="crypto-agents" data-path="/v1/vendor/crypto-trading-agents/debate" data-preset="btc" data-title="CryptoTradingAgents 討論" data-description="複数の暗号資産エージェントで強気・弱気を討論します。"><strong>CryptoTradingAgents</strong><small>複数エージェントで討論</small></button>
          <button class="function-card" data-key="vibe-research" data-path="/v1/vendor/vibe-trading/research" data-preset="btc" data-title="Vibe-Trading リサーチ" data-description="Crypto Desk形式で市場材料を調査します。"><strong>Vibe-Trading</strong><small>市場材料をデスク形式で調査</small></button>
          <button class="function-card" data-key="llm-trader" data-path="/v1/vendor/llm-trader/analyze" data-preset="btc" data-title="LLM Trader 判断" data-description="LLM TraderのDecision Gateで売買条件を確認します。"><strong>LLM Trader</strong><small>売買条件をゲート判定</small></button>
          <button class="function-card" data-key="helm-consensus" data-path="/v1/vendor/helm-agents/consensus" data-preset="btc" data-title="HELM Agents 合議" data-description="複数エージェントの意見をまとめて合議判断します。"><strong>HELM Agents</strong><small>複数意見を合議して判断</small></button>
        </div>
        <div class="selected-function"><span>選択中</span><strong id="selectedTitle">テクニカル分析</strong><p id="selectedDescription">価格・RSI・移動平均から相場の方向を分析します。</p></div>
        <div class="input-head"><strong>入力データ</strong><div class="toolbar"><button class="tool" id="btcPreset">BTC例</button><button class="tool" id="ethPreset">ETH例</button><button class="tool" id="formatBtn">JSON整形</button></div></div>
        <textarea class="editor" id="payload" spellcheck="false"></textarea>
        <button class="run" id="runBtn">テクニカル分析を実行</button>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><strong>Response</strong><div class="metrics"><span id="statusMetric">READY</span><span id="latencyMetric">- ms</span><span id="modelMetric">gemma4:12b</span></div></div>
      <pre class="result empty" id="result">「テクニカル分析を実行」を押すと、ここに結果が表示されます。</pre>
    </section>
  </div>
  <div class="notice" style="margin-top:14px">出力は分析材料です。実注文、注文数量、損失上限はCrypto Brainではなく、呼び出し側の固定リスク制御が決定します。</div>
</main>
<?php endif; ?>
<footer><a href="https://kurage.exbridge.jp/">Kurageプロジェクト</a> / <a href="https://exbridge.jp/">株式会社エクスブリッジ</a></footer>
<?php if ($is_admin): ?>
<script>
const csrf=<?php echo json_encode($csrf, JSON_UNESCAPED_SLASHES); ?>;
const presets={
btc:{symbol:"BTC_USDT",timeframe:"H1",as_of:new Date().toISOString(),market:{price:64000,volume_24h:24000000000,spread_bps:1.2},technicals:{return_1h_pct:0.18,return_24h_pct:1.4,rsi_14:57.2,ema_20:63500,ema_50:62100,support:62000,resistance:66000},derivatives:{funding_rate_8h:0.0001,open_interest_24h_change_pct:2.1,long_short_ratio:1.04},onchain:{exchange_netflow_btc:-1200,stablecoin_supply_7d_change_pct:0.8},defi:{tvl_7d_change_pct:1.1},news:[{title:"Spot ETF net inflows increased",sentiment:"positive"}],social:[{source:"aggregate",sentiment:"neutral"}],position:{side:"flat"},portfolio:{cash:100000,max_position_value:10000,positions:{}},history:[],prior_reports:{},question:"次の24時間の判断材料を整理"},
eth:{symbol:"ETH_USDT",timeframe:"H4",as_of:new Date().toISOString(),market:{price:3400,volume_24h:12000000000,spread_bps:1.5},technicals:{return_4h_pct:-0.3,return_24h_pct:0.7,rsi_14:51.4,ema_20:3380,ema_50:3310,support:3250,resistance:3550},derivatives:{funding_rate_8h:0.00005,open_interest_24h_change_pct:-0.8},onchain:{exchange_netflow_eth:-18000,staking_netflow_7d:12000},defi:{ethereum_tvl_7d_change_pct:1.6},news:[],social:[],position:{side:"long",unrealized_pct:2.4},portfolio:{cash:75000,max_position_value:12000,positions:{ETH_USDT:{side:"long",units:2}}},history:[],prior_reports:{},question:"保有継続か縮小かを評価"},
market:{timeframe:"H1",as_of:new Date().toISOString(),market_context:{btc_dominance_pct:54.2,total_market_return_24h_pct:1.1},assets:[{symbol:"BTC_USDT",market:{price:64000,volume_24h:24000000000,return_24h_pct:1.4},technicals:{rsi_14:57.2},derivatives:{funding_rate_8h:0.0001,open_interest_24h_change_pct:2.1,liquidations_1h_usd:4200000},onchain:{exchange_netflow:-1200}},{symbol:"ETH_USDT",market:{price:3400,volume_24h:12000000000,return_24h_pct:0.7},technicals:{rsi_14:51.4},derivatives:{funding_rate_8h:0.00005,open_interest_24h_change_pct:-0.8,liquidations_1h_usd:2100000},onchain:{exchange_netflow:-18000}},{symbol:"SOL_USDT",market:{price:148,volume_24h:2800000000,return_24h_pct:3.8},technicals:{rsi_14:68.1},derivatives:{funding_rate_8h:0.00032,open_interest_24h_change_pct:11.4,liquidations_1h_usd:7800000},social:[{sentiment:"greed",mention_change_pct:42}]}],question:"機会、資金フロー、異常、清算リスクを比較"}
};
let endpoint="technical";
const editor=document.querySelector('#payload'),result=document.querySelector('#result'),run=document.querySelector('#runBtn');
function setPreset(value){editor.value=JSON.stringify(value,null,2)}setPreset(presets.btc);
let selectedTitle="テクニカル分析";
function selectFunction(card){document.querySelectorAll('.function-card').forEach(x=>x.classList.remove('active'));card.classList.add('active');endpoint=card.dataset.key;selectedTitle=card.dataset.title;document.querySelector('#endpointPath').textContent=card.dataset.path;document.querySelector('#selectedTitle').textContent=selectedTitle;document.querySelector('#selectedDescription').textContent=card.dataset.description;run.textContent=`${selectedTitle}を実行`;setPreset(presets[card.dataset.preset]||presets.btc);result.className='result empty';result.textContent=`「${selectedTitle}を実行」を押すと、ここに結果が表示されます。`}
document.querySelectorAll('.function-card').forEach(card=>card.addEventListener('click',()=>selectFunction(card)));
document.querySelectorAll('.function-tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.function-tab').forEach(x=>{x.classList.remove('active');x.setAttribute('aria-selected','false')});document.querySelectorAll('.function-pane').forEach(x=>x.classList.remove('active'));tab.classList.add('active');tab.setAttribute('aria-selected','true');const pane=document.querySelector(`[data-pane="${tab.dataset.tab}"]`);pane.classList.add('active');selectFunction(pane.querySelector('.function-card'))}));
document.querySelector('#btcPreset').onclick=()=>setPreset(presets.btc);document.querySelector('#ethPreset').onclick=()=>setPreset(presets.eth);
document.querySelector('#formatBtn').onclick=()=>{try{setPreset(JSON.parse(editor.value))}catch(e){showError('JSON: '+e.message)}};
function showError(message){result.className='result error';result.textContent=message;document.querySelector('#statusMetric').textContent='ERROR'}
run.onclick=async()=>{let payload;try{payload=JSON.parse(editor.value)}catch(e){showError('JSON: '+e.message);return}run.disabled=true;run.textContent=`${selectedTitle}を実行中...`;result.className='result empty';result.textContent='Ollamaからの応答を待っています。';const start=performance.now();try{const response=await fetch(`kcbrain.php?proxy=run&endpoint=${encodeURIComponent(endpoint)}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});const data=await response.json();document.querySelector('#statusMetric').textContent=String(response.status);document.querySelector('#latencyMetric').textContent=`${data.latency_ms??Math.round(performance.now()-start)} ms`;document.querySelector('#modelMetric').textContent=data.model||'Gemma';result.className=response.ok?'result':'result error';result.textContent=JSON.stringify(data,null,2)}catch(e){showError(e.message)}finally{run.disabled=false;run.textContent=`${selectedTitle}を実行`}};
fetch('kcbrain.php?proxy=health',{cache:'no-store'}).then(r=>r.json()).then(d=>{const ok=Boolean(d.ok);document.querySelector('#healthDot').className='dot '+(ok?'ok':'bad');document.querySelector('#healthText').textContent=ok?`${d.model} READY`:'API OFFLINE'}).catch(()=>{document.querySelector('#healthDot').className='dot bad';document.querySelector('#healthText').textContent='API OFFLINE'});
</script>
<?php endif; ?>
</body>
</html>
