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
.api-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:9px}.api-btn{border:1px solid var(--line);background:#fff;color:var(--navy);border-radius:8px;padding:8px 7px;font:700 11px/1.25 inherit;cursor:pointer}.api-btn:hover{border-color:#90cbd2}.api-btn.active{color:#fff;background:linear-gradient(135deg,var(--aqua),#177184);border-color:transparent}.vendor-select{width:100%;margin-bottom:10px;border:1px solid #b8d3d1;border-radius:8px;background:#f5fbfa;color:var(--navy);padding:8px 10px;font:700 11px inherit}.toolbar{display:flex;gap:7px;margin-bottom:9px}.tool{border:1px solid var(--line);background:#fff;color:var(--muted);border-radius:7px;padding:6px 9px;font:700 11px inherit;cursor:pointer}.editor{display:block;width:100%;height:336px;resize:vertical;border:1px solid #cadbd8;border-radius:9px;background:var(--code);padding:12px;color:#1c3840;font:12px/1.55 "IBM Plex Mono","SFMono-Regular",Consolas,monospace;outline:none;tab-size:2}.editor:focus{border-color:var(--aqua);box-shadow:0 0 0 3px rgba(0,141,163,.09)}.run{margin-top:10px;width:100%;border:0;border-radius:9px;background:linear-gradient(135deg,var(--navy),var(--aqua));color:#fff;padding:11px 16px;font:800 13px inherit;cursor:pointer;box-shadow:0 8px 18px rgba(0,111,137,.18)}.run:disabled{opacity:.55;cursor:wait}
.result{height:494px;overflow:auto;margin:0;background:#102d35;color:#d7f0eb;padding:15px;font:12px/1.6 "IBM Plex Mono","SFMono-Regular",Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.result.empty{color:#8fb1b3}.result.error{color:#ffd0c9}.metrics{display:flex;gap:12px;color:var(--muted);font-size:10px}.notice{background:#fff8e8;border:1px solid #ecdbaa;border-radius:10px;padding:12px 14px;color:#705d25;line-height:1.7;font-size:12px}.login-box{max-width:520px;margin:90px auto;background:#fff;border:1px solid var(--line);border-radius:14px;padding:28px;box-shadow:var(--shadow);text-align:center}.login-box h2{margin:0 0 8px;font-size:19px}.login-box p{color:var(--muted);line-height:1.7}.login-box a{display:inline-block;margin-top:8px;background:var(--navy);color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-weight:800}
footer{position:relative;z-index:1;text-align:center;color:var(--muted);font-size:10px;padding:0 20px 22px}footer a{color:var(--aqua);text-decoration:none}
@media(max-width:900px){header{padding:0 14px}.shell{padding:14px}.workspace{grid-template-columns:1fr}.result{height:390px}.intro{align-items:flex-start;flex-direction:column}.api-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:520px){.api-grid{grid-template-columns:repeat(2,1fr)}.editor{height:330px}.user span{display:none}.intro h1{font-size:20px}}
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
        <div class="api-grid" id="apiGrid">
          <button class="api-btn active" data-key="technical" data-path="/v1/analyze/technical">テクニカル</button>
          <button class="api-btn" data-key="onchain" data-path="/v1/analyze/onchain">オンチェーン</button>
          <button class="api-btn" data-key="sentiment" data-path="/v1/analyze/sentiment">センチメント</button>
          <button class="api-btn" data-key="debate" data-path="/v1/debate/bull-bear">強気 / 弱気</button>
          <button class="api-btn" data-key="trade" data-path="/v1/decide/trade">売買判断</button>
          <button class="api-btn" data-key="risk" data-path="/v1/assess/risk">リスク</button>
          <button class="api-btn" data-key="portfolio" data-path="/v1/decide/portfolio">保有管理</button>
          <button class="api-btn" data-key="review" data-path="/v1/review/trade">取引レビュー</button>
          <button class="api-btn" data-key="full" data-path="/v1/analyze/full">総合分析</button>
        </div>
        <select class="vendor-select" id="marketSelect">
          <option value="">Market Intelligence APIを選択</option>
          <option value="opportunity-ranking" data-path="/v1/market/opportunity-ranking">市場機会ランキング</option>
          <option value="flow-ranking" data-path="/v1/market/flow-ranking">資金フローランキング</option>
          <option value="market-anomaly" data-path="/v1/market/anomaly">市場異常検出</option>
          <option value="liquidation-risk" data-path="/v1/market/liquidation-risk">清算連鎖リスク</option>
          <option value="pair-signal" data-path="/v1/signal/pair/{symbol}">個別銘柄シグナル</option>
        </select>
        <select class="vendor-select" id="vendorSelect">
          <option value="">OSS Intelligence APIを選択</option>
          <option value="aihf-portfolio" data-path="/v1/vendor/ai-hedge-fund-crypto/portfolio">AI Hedge Fund Crypto: ポートフォリオ</option>
          <option value="crypto-agents" data-path="/v1/vendor/crypto-trading-agents/debate">CryptoTradingAgents: 強気・弱気討論</option>
          <option value="vibe-research" data-path="/v1/vendor/vibe-trading/research">Vibe-Trading: Crypto Desk</option>
          <option value="llm-trader" data-path="/v1/vendor/llm-trader/analyze">LLM Trader: Decision Gate</option>
          <option value="helm-consensus" data-path="/v1/vendor/helm-agents/consensus">HELM Agents: 合議判断</option>
        </select>
        <div class="toolbar"><button class="tool" id="btcPreset">BTC例</button><button class="tool" id="ethPreset">ETH例</button><button class="tool" id="formatBtn">JSON整形</button></div>
        <textarea class="editor" id="payload" spellcheck="false"></textarea>
        <button class="run" id="runBtn">Gemma 4で実行</button>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><strong>Response</strong><div class="metrics"><span id="statusMetric">READY</span><span id="latencyMetric">- ms</span><span id="modelMetric">gemma4:12b</span></div></div>
      <pre class="result empty" id="result">APIを選び、左のJSONを確認して実行してください。</pre>
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
document.querySelectorAll('.api-btn').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.api-btn').forEach(x=>x.classList.remove('active'));btn.classList.add('active');document.querySelector('#vendorSelect').value='';document.querySelector('#marketSelect').value='';endpoint=btn.dataset.key;document.querySelector('#endpointPath').textContent=btn.dataset.path}));
document.querySelector('#vendorSelect').addEventListener('change',e=>{if(!e.target.value)return;document.querySelectorAll('.api-btn').forEach(x=>x.classList.remove('active'));document.querySelector('#marketSelect').value='';endpoint=e.target.value;const option=e.target.options[e.target.selectedIndex];document.querySelector('#endpointPath').textContent=option.dataset.path;if(!editor.value.trim()||!editor.value.includes('"market"'))setPreset(presets.btc)});
document.querySelector('#marketSelect').addEventListener('change',e=>{if(!e.target.value)return;document.querySelectorAll('.api-btn').forEach(x=>x.classList.remove('active'));document.querySelector('#vendorSelect').value='';endpoint=e.target.value;const option=e.target.options[e.target.selectedIndex];document.querySelector('#endpointPath').textContent=option.dataset.path;setPreset(endpoint==='pair-signal'?presets.btc:presets.market)});
document.querySelector('#btcPreset').onclick=()=>setPreset(presets.btc);document.querySelector('#ethPreset').onclick=()=>setPreset(presets.eth);
document.querySelector('#formatBtn').onclick=()=>{try{setPreset(JSON.parse(editor.value))}catch(e){showError('JSON: '+e.message)}};
function showError(message){result.className='result error';result.textContent=message;document.querySelector('#statusMetric').textContent='ERROR'}
run.onclick=async()=>{let payload;try{payload=JSON.parse(editor.value)}catch(e){showError('JSON: '+e.message);return}run.disabled=true;run.textContent='Gemma 4 実行中...';result.className='result empty';result.textContent='Ollamaからの応答を待っています。';const start=performance.now();try{const response=await fetch(`kcbrain.php?proxy=run&endpoint=${encodeURIComponent(endpoint)}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});const data=await response.json();document.querySelector('#statusMetric').textContent=String(response.status);document.querySelector('#latencyMetric').textContent=`${data.latency_ms??Math.round(performance.now()-start)} ms`;document.querySelector('#modelMetric').textContent=data.model||'Gemma';result.className=response.ok?'result':'result error';result.textContent=JSON.stringify(data,null,2)}catch(e){showError(e.message)}finally{run.disabled=false;run.textContent='Gemma 4で実行'}};
fetch('kcbrain.php?proxy=health',{cache:'no-store'}).then(r=>r.json()).then(d=>{const ok=Boolean(d.ok);document.querySelector('#healthDot').className='dot '+(ok?'ok':'bad');document.querySelector('#healthText').textContent=ok?`${d.model} READY`:'API OFFLINE'}).catch(()=>{document.querySelector('#healthDot').className='dot bad';document.querySelector('#healthText').textContent='API OFFLINE'});
</script>
<?php endif; ?>
</body>
</html>
