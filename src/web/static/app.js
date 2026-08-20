/* Investment Assistant – WebSocket Chat Client */

// Keep the active conversation tab-scoped while storing every conversation on
// the server. This lets the sidebar resume old chats without merging tabs.
let activeConversationId = sessionStorage.getItem('ia_active_conversation_id') || '';
let conversationWorkspace = { projects: [], unassigned: [], recent: [], total: 0 };
let conversationSearchTimer = null;
let conversationLoadToken = 0;

let ws = null;
let currentAssistantBubble = null;
let currentAssistantText = '';
const messageQueue = [];
const MAX_QUEUED_MESSAGES = 4;
let activeMessage = null;
let reconnectTimer = null;
let reconnectDelay = 1000;
const MAX_RECONNECT = 30000;
let portfolioSnapshot = null;
let portfolioLoading = false;
let portfolioSortKey = 'value_usd';
let portfolioSortDirection = 'desc';
let portfolioVisiblePositions = [];
let selectedPortfolioPosition = null;
const simulationRuns = new Map();
const SIDEBAR_WIDTH_KEY = 'ia_sidebar_width';
const SIDEBAR_WIDTH_MIN = 220;
const SIDEBAR_WIDTH_MAX = 480;

// ── WebSocket ──────────────────────────────────────────────────────────────────

function connect() {
  if (!activeConversationId) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws/chat/${activeConversationId}`;

  setStatus('connecting');
  setSendEnabled(false);
  ws = new WebSocket(url);

  ws.onopen = () => {
    setStatus('online');
    setSendEnabled(true);
    processMessageQueue();
    reconnectDelay = 1000;
    clearTimeout(reconnectTimer);
    console.log('WebSocket connected');
  };

  ws.onclose = (e) => {
    setStatus('offline');
    setSendEnabled(false);
    if (activeMessage) {
      discardAssistantMessage();
      appendErrorMessage('The connection closed while this request was running. It was not retried automatically.');
      activeMessage = null;
    }
    updateQueueStatus();
    if (e.code === 4001 || e.code === 4003) {
      window.location.assign('/login');
      return;
    }
    if (e.code !== 1000) {
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT);
        connect();
      }, reconnectDelay);
    }
  };

  ws.onerror = (e) => console.error('WS error', e);

  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event);
  };
}

function handleEvent(event) {
  switch (event.type) {
    case 'final_answer':
      // The server emits this only after the agent has completed its tool
      // work and validated the response as a final answer.
      discardAssistantMessage();
      if (event.text) appendAssistantMessage(event.text);
      break;
    case 'text_delta':
      // Never render raw model deltas. Only the server's validated
      // final_answer event may create an assistant chat bubble.
      break;
    case 'tool_call':
      appendToolCall(event.name, event.input);
      break;
    case 'tool_result':
      appendToolResult(event.name, event.result);
      break;
    case 'done':
      finaliseAssistantMessage();
      activeMessage = null;
      updateQueueStatus();
      processMessageQueue();
      loadConversationWorkspace();
      break;
    case 'error':
      discardAssistantMessage();
      appendErrorMessage(event.message);
      activeMessage = null;
      updateQueueStatus();
      processMessageQueue();
      break;
  }
}

// ── Message Rendering ─────────────────────────────────────────────────────────

function appendUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = `
    <div class="msg-bubble">${escapeHtml(text)}</div>
    <div class="msg-time">${timeNow()}</div>
  `;
  messagesEl().appendChild(div);
  scrollBottom();
}

function appendStoredUserMessage(text, createdAt = null) {
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = `
    <div class="msg-bubble">${escapeHtml(text)}</div>
    <div class="msg-time">${formatMessageTime(createdAt)}</div>
  `;
  messagesEl().appendChild(div);
  scrollBottom();
}

function appendAssistantMessage(text, createdAt = null) {
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `
    <div class="msg-bubble">${markdownToHtml(text)}</div>
    <div class="msg-time">${formatMessageTime(createdAt)}</div>
  `;
  messagesEl().appendChild(div);
  scrollBottom();
}

function startAssistantMessage() {
  // Typing indicator first
  currentAssistantText = '';
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `
    <div class="msg-bubble" id="streaming-bubble">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>
    <div class="msg-time">${timeNow()}</div>
  `;
  messagesEl().appendChild(div);
  currentAssistantBubble = div.querySelector('#streaming-bubble');
  currentAssistantBubble.removeAttribute('id');
  scrollBottom();
}

function appendAssistantDelta(text) {
  if (!currentAssistantBubble) startAssistantMessage();
  currentAssistantText += text;
  currentAssistantBubble.innerHTML = markdownToHtml(currentAssistantText);
  scrollBottom();
}

function finaliseAssistantMessage() {
  if (currentAssistantBubble && currentAssistantText) {
    currentAssistantBubble.innerHTML = markdownToHtml(currentAssistantText);
  }
  currentAssistantBubble = null;
  currentAssistantText = '';
  scrollBottom();
}

function discardAssistantMessage() {
  if (currentAssistantBubble) {
    currentAssistantBubble.closest('.msg')?.remove();
  }
  currentAssistantBubble = null;
  currentAssistantText = '';
}

function appendToolCall(name, input) {
  const el = document.createElement('div');
  el.className = 'tool-call';
  el.innerHTML = `<span class="tool-icon">🔧</span> Calling <strong>${escapeHtml(name)}</strong>&hellip;`;
  messagesEl().appendChild(el);
  scrollBottom();
}

function appendToolResult(name, resultStr) {
  let preview = resultStr;
  try {
    const obj = JSON.parse(resultStr);
    preview = JSON.stringify(obj, null, 0).slice(0, 120) + (resultStr.length > 120 ? '…' : '');
  } catch (_) { /* resultStr is not valid JSON — use the raw string as preview */ }
  const el = document.createElement('div');
  el.className = 'tool-call result';
  el.innerHTML = `<span class="tool-icon">✅</span> <strong>${escapeHtml(name)}</strong> → ${escapeHtml(preview)}`;
  messagesEl().appendChild(el);
  scrollBottom();
}

function appendErrorMessage(msg) {
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `<div class="msg-bubble" style="border-color:#ef4444;color:#ef4444;">⚠️ Error: ${escapeHtml(msg)}</div>`;
  messagesEl().appendChild(div);
  scrollBottom();
}

// ── Send ──────────────────────────────────────────────────────────────────────

function sendMessage() {
  const input = document.getElementById('user-input');
  const text = input.value.trim();
  if (!text) return;
  if (!activeConversationId) {
    appendErrorMessage('Create a new chat before sending a message.');
    return;
  }
  if (ws?.readyState !== WebSocket.OPEN) {
    appendErrorMessage('The assistant is disconnected. Please wait for it to reconnect.');
    return;
  }
  if (messageQueue.length >= MAX_QUEUED_MESSAGES) {
    appendErrorMessage(`The assistant can queue up to ${MAX_QUEUED_MESSAGES} messages.`);
    return;
  }

  input.value = '';
  input.style.height = '';
  appendUserMessage(text);
  messageQueue.push(text);
  updateQueueStatus();
  processMessageQueue();
}

function processMessageQueue() {
  if (activeMessage || !messageQueue.length || ws?.readyState !== WebSocket.OPEN) {
    updateQueueStatus();
    return;
  }
  activeMessage = messageQueue.shift();
  startAssistantMessage();
  updateQueueStatus();
  ws.send(JSON.stringify({ message: activeMessage }));
}

function updateQueueStatus() {
  const el = document.getElementById('queue-status');
  if (!el) return;
  if (activeMessage && messageQueue.length) {
    el.textContent = `Working · ${messageQueue.length} queued`;
  } else if (activeMessage) {
    el.textContent = 'Working…';
  } else if (messageQueue.length) {
    el.textContent = `${messageQueue.length} queued`;
  } else {
    el.textContent = '';
  }
}

function sendQuick(text) {
  document.getElementById('user-input').value = text;
  sendMessage();
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
  // Auto-resize textarea
  const ta = e.target;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

// ── Trading Mode ──────────────────────────────────────────────────────────────

async function setMode(mode) {
  const statusEl = document.getElementById('mode-status');
  statusEl.textContent = 'Saving trading mode…';
  try {
    const resp = await fetch('/api/profile/trading-mode', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
      },
      body: JSON.stringify({ mode }),
    });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || 'Trading mode could not be saved.');
    }
    document.getElementById('btn-recommend').classList.toggle('active', mode === 'recommend');
    document.getElementById('btn-auto').classList.toggle('active', mode === 'auto');
    statusEl.textContent = mode === 'auto'
      ? '⚡ Auto mode — only bounded, configured trades can execute.'
      : '✋ Recommend mode — agent proposes, you confirm.';
  } catch (error) {
    statusEl.textContent = error.message;
    appendErrorMessage(error.message);
  }
}

// ── Market Snapshot ────────────────────────────────────────────────────────────

async function loadSnapshot() {
  const el = document.getElementById('market-snapshot');
  el.textContent = 'Loading…';
  try {
    const resp = await fetch('/api/market/snapshot');
    if (resp.status === 401) { window.location.assign('/login'); return; }
    const data = await resp.json();
    if (data.message) { el.textContent = data.message; return; }
    const markets = data.market_overview?.markets || {};
    let html = '';
    for (const [name, info] of Object.entries(markets)) {
      const price = info.price ? info.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : 'N/A';
      const chg = info.change_pct;
      let cls = '';
      if (chg > 0) cls = 'up';
      else if (chg < 0) cls = 'down';
      const sign = chg > 0 ? '+' : '';
      const chgStr = chg == null ? '' : ` (${sign}${chg}%)`;
      html += `<div class="market-row"><span class="name">${name}</span><span class="price ${cls}">${price}${chgStr}</span></div>`;
    }
    el.innerHTML = html || 'No data available';
  } catch (e) {
    console.error('Snapshot load failed', e);
    el.textContent = 'Failed to load snapshot.';
  }
}

// ── Portfolio and simulation dashboards ──────────────────────────────────────

function switchView(view) {
  const isPortfolio = view === 'portfolio';
  const isSimulation = view === 'simulation';
  document.getElementById('chat-view').hidden = isPortfolio || isSimulation;
  document.getElementById('portfolio-view').hidden = !isPortfolio;
  document.getElementById('simulation-view').hidden = !isSimulation;
  document.querySelectorAll('.view-tab').forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  if (isPortfolio) {
    loadPortfolio();
  } else if (isSimulation) {
    loadSimulations();
  } else {
    document.getElementById('user-input')?.focus();
  }
}

async function loadPortfolio(force = false) {
  if (portfolioLoading || (!force && portfolioSnapshot)) {
    if (!portfolioSnapshot) renderPortfolioLoading();
    return;
  }
  portfolioLoading = true;
  renderPortfolioLoading();
  const refreshButton = document.getElementById('portfolio-refresh');
  if (refreshButton) refreshButton.disabled = true;
  try {
    const resp = await fetch('/api/portfolio', { cache: 'no-store' });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Portfolio data could not be loaded.');
    renderPortfolio(data);
  } catch (error) {
    console.error('Portfolio load failed', error);
    renderPortfolioError(error.message);
  } finally {
    portfolioLoading = false;
    if (refreshButton) refreshButton.disabled = false;
  }
}

function renderPortfolioLoading() {
  const status = document.getElementById('portfolio-status');
  if (!status) return;
  status.className = 'portfolio-status neutral';
  status.textContent = 'Loading…';
  document.getElementById('portfolio-updated').textContent = 'Fetching live broker data…';
}

function renderPortfolioError(message) {
  const status = document.getElementById('portfolio-status');
  status.className = 'portfolio-status error';
  status.textContent = 'Unavailable';
  document.getElementById('portfolio-updated').textContent = message;
  document.getElementById('portfolio-alerts').innerHTML = `<div class="portfolio-alert error">${escapeHtml(message)}</div>`;
  document.getElementById('portfolio-empty').hidden = false;
  document.getElementById('portfolio-content').hidden = true;
  document.getElementById('portfolio-empty-title').textContent = 'Portfolio data is unavailable';
  document.getElementById('portfolio-empty-copy').textContent = 'Check the deployment and broker connection, then refresh this dashboard.';
}

function renderPortfolio(data) {
  portfolioSnapshot = data;
  const status = document.getElementById('portfolio-status');
  const statusLabel = data.status === 'ready' ? 'Live' : data.status === 'warning' ? 'Partial data' : data.status === 'error' ? 'Error' : 'Not connected';
  status.className = `portfolio-status ${data.status === 'ready' ? 'ready' : data.status === 'warning' ? 'warning' : data.status === 'error' ? 'error' : 'neutral'}`;
  status.textContent = statusLabel;
  document.getElementById('portfolio-updated').textContent = data.updated_at
    ? `Last refreshed ${formatMessageTime(data.updated_at)} · Values are supplied by your brokers`
    : 'Values are supplied by your brokers';

  const alerts = data.errors || [];
  document.getElementById('portfolio-alerts').innerHTML = alerts.length
    ? alerts.map((error) => `<div class="portfolio-alert ${data.status === 'error' ? 'error' : ''}"><strong>${escapeHtml(formatBrokerName(error.broker))}</strong>${error.account_name ? ` · ${escapeHtml(error.account_name)}` : ''}: ${escapeHtml(error.error)}</div>`).join('')
    : '';

  document.getElementById('portfolio-equity').textContent = formatCurrency(data.total_equity_usd);
  document.getElementById('portfolio-market-value').textContent = formatCurrency(data.total_market_value_usd);
  const pnl = document.getElementById('portfolio-pnl');
  pnl.textContent = formatCurrency(data.total_unrealized_pnl_usd);
  pnl.classList.toggle('up', Number(data.total_unrealized_pnl_usd) > 0);
  pnl.classList.toggle('down', Number(data.total_unrealized_pnl_usd) < 0);
  document.getElementById('portfolio-cash').textContent = formatCurrency(data.cash_usd);
  document.getElementById('portfolio-equity-note').textContent = data.total_equity_usd == null
    ? 'Broker does not report equity'
    : `${(data.connected_accounts || []).length} active account${(data.connected_accounts || []).length === 1 ? '' : 's'}`;
  document.getElementById('portfolio-pnl-note').textContent = data.positions?.some((position) => position.pnl_usd != null)
    ? 'Broker-reported positions'
    : 'No position P&L reported';

  renderPortfolioFilters(data);
  renderPortfolioHoldings();
  renderPortfolioAllocation(data);
  renderPortfolioAccounts(data);

  const showEmpty = data.empty_state === 'connect_broker' || data.empty_state === 'provider_error';
  const empty = document.getElementById('portfolio-empty');
  empty.hidden = !showEmpty;
  document.getElementById('portfolio-content').hidden = showEmpty;
  if (showEmpty) {
    const providerError = data.empty_state === 'provider_error';
    document.getElementById('portfolio-empty-title').textContent = providerError
      ? 'Broker data is unavailable'
      : 'Connect a brokerage account';
    document.getElementById('portfolio-empty-copy').textContent = providerError
      ? 'The account is configured, but the broker did not return a usable snapshot. Review the connection message above.'
      : 'Your live portfolio will appear here after an active broker account is configured.';
  }
}

function renderPortfolioFilters(data) {
  const select = document.getElementById('portfolio-broker-filter');
  const current = select.value;
  const brokers = [...new Set((data.positions || []).map((position) => position.broker).filter(Boolean))].sort();
  select.innerHTML = '<option value="all">All brokers</option>'
    + brokers.map((broker) => `<option value="${escapeHtml(broker)}">${escapeHtml(formatBrokerName(broker))}</option>`).join('');
  select.value = brokers.includes(current) ? current : 'all';
}

function renderPortfolioHoldings() {
  const body = document.getElementById('portfolio-holdings-body');
  const empty = document.getElementById('portfolio-holdings-empty');
  if (!body || !portfolioSnapshot) return;
  const search = (document.getElementById('portfolio-search').value || '').trim().toLowerCase();
  const broker = document.getElementById('portfolio-broker-filter').value;
  const positions = (portfolioSnapshot.positions || []).filter((position) => {
    const haystack = `${position.symbol || ''} ${position.broker || ''} ${position.account_name || ''}`.toLowerCase();
    return (!search || haystack.includes(search)) && (broker === 'all' || position.broker === broker);
  });
  positions.sort((left, right) => {
    const a = left[portfolioSortKey];
    const b = right[portfolioSortKey];
    if (portfolioSortKey === 'symbol') {
      return portfolioSortDirection === 'asc'
        ? String(a || '').localeCompare(String(b || ''))
        : String(b || '').localeCompare(String(a || ''));
    }
    const aNumber = a == null ? -Infinity : Number(a);
    const bNumber = b == null ? -Infinity : Number(b);
    return portfolioSortDirection === 'asc' ? aNumber - bNumber : bNumber - aNumber;
  });
  portfolioVisiblePositions = positions;
  document.getElementById('portfolio-position-count').textContent = String(positions.length);
  body.innerHTML = positions.map((position, index) => {
    const selected = selectedPortfolioPosition === position;
    const pnl = position.pnl_usd;
    const pnlClass = pnl > 0 ? 'up' : pnl < 0 ? 'down' : '';
    return `<tr tabindex="0" class="${selected ? 'selected' : ''}" onclick="selectPortfolioPosition(${index})" onkeydown="if(event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectPortfolioPosition(${index}); }">
      <td><div class="asset-cell"><span class="asset-symbol">${escapeHtml(position.symbol)}</span><span class="asset-meta">${escapeHtml(formatBrokerName(position.broker))}${position.account_name ? ` · ${escapeHtml(position.account_name)}` : ''}</span></div></td>
      <td>${formatQuantity(position.quantity)}</td>
      <td>${formatCurrency(position.price_usd)}</td>
      <td class="${position.value_usd == null ? 'value-unavailable' : ''}">${formatCurrency(position.value_usd)}</td>
      <td class="${pnlClass}">${formatCurrency(pnl)}</td>
    </tr>`;
  }).join('');
  empty.hidden = positions.length > 0;
  renderPortfolioDetail(selectedPortfolioPosition && positions.includes(selectedPortfolioPosition) ? selectedPortfolioPosition : null);
  document.querySelectorAll('.sort-btn').forEach((button) => {
    const indicator = button.querySelector('span');
    indicator.textContent = button.dataset.sort === portfolioSortKey ? (portfolioSortDirection === 'asc' ? '↑' : '↓') : '↕';
  });
}

function sortPortfolioBy(key) {
  if (portfolioSortKey === key) portfolioSortDirection = portfolioSortDirection === 'asc' ? 'desc' : 'asc';
  else { portfolioSortKey = key; portfolioSortDirection = key === 'symbol' ? 'asc' : 'desc'; }
  renderPortfolioHoldings();
}

function selectPortfolioPosition(index) {
  selectedPortfolioPosition = portfolioVisiblePositions[index] || null;
  renderPortfolioHoldings();
}

function renderPortfolioAllocation(data) {
  const allocation = data.allocation || [];
  const colors = ['#60a5fa', '#34d399', '#fbbf24', '#f472b6', '#a78bfa', '#fb7185', '#22d3ee'];
  const donut = document.getElementById('portfolio-donut');
  const label = document.getElementById('portfolio-donut-label');
  const legend = document.getElementById('portfolio-allocation-legend');
  if (!allocation.length) {
    donut.style.background = 'conic-gradient(var(--border) 0 100%)';
    label.textContent = '—';
    legend.innerHTML = '<div class="table-empty">No USD allocation available.</div>';
    return;
  }
  let cursor = 0;
  const segments = allocation.map((item, index) => {
    const end = cursor + Number(item.percentage || 0);
    const segment = `${colors[index % colors.length]} ${cursor}% ${end}%`;
    cursor = end;
    return segment;
  });
  donut.style.background = `conic-gradient(${segments.join(', ')})`;
  label.textContent = `${Math.round(allocation.reduce((sum, item) => sum + Number(item.percentage || 0), 0))}%`;
  legend.innerHTML = allocation.slice(0, 7).map((item, index) => `<div class="legend-row"><span class="legend-swatch" style="background:${colors[index % colors.length]}"></span><span class="legend-label">${escapeHtml(item.symbol)}</span><span class="legend-value">${formatCurrency(item.value_usd)} · ${formatPct(item.percentage)}</span></div>`).join('');
}

function renderPortfolioAccounts(data) {
  const list = document.getElementById('portfolio-accounts-list');
  const accounts = data.connected_accounts || [];
  if (!accounts.length) {
    list.innerHTML = '<div class="table-empty">No active broker accounts.</div>';
    return;
  }
  list.innerHTML = accounts.map((account) => {
    const isError = account.status === 'error';
    return `<div class="portfolio-account"><div class="portfolio-account-main"><div class="portfolio-account-name">${escapeHtml(account.display_name)}</div><div class="portfolio-account-meta">${escapeHtml(formatBrokerName(account.broker))}</div></div><span class="account-state ${isError ? 'error' : ''}">${isError ? 'Needs attention' : 'Connected'}</span></div>`;
  }).join('');
}

function renderPortfolioDetail(position) {
  const title = document.getElementById('portfolio-detail-title');
  const broker = document.getElementById('portfolio-detail-broker');
  const body = document.getElementById('portfolio-detail-body');
  if (!position) {
    title.textContent = 'Select a holding';
    broker.textContent = '—';
    body.textContent = 'Choose a row above to inspect its broker-reported details.';
    return;
  }
  title.textContent = position.symbol;
  broker.textContent = formatBrokerName(position.broker);
  const pnlClass = position.pnl_usd > 0 ? 'up' : position.pnl_usd < 0 ? 'down' : '';
  body.innerHTML = `<div class="detail-metrics">
    <div class="detail-metric"><span>Quantity</span><strong>${formatQuantity(position.quantity)}</strong></div>
    <div class="detail-metric"><span>Price</span><strong>${formatCurrency(position.price_usd)}</strong></div>
    <div class="detail-metric"><span>Market value</span><strong>${formatCurrency(position.value_usd)}</strong></div>
    <div class="detail-metric"><span>Unrealized P&amp;L</span><strong class="${pnlClass}">${formatCurrency(position.pnl_usd)}</strong></div>
  </div><p class="card-note">Account: ${escapeHtml(position.account_name || 'Broker account')} · Values are read-only broker data.</p>`;
}

function focusBrokerAccounts() {
  const section = document.getElementById('broker-section');
  if (!section) return;
  document.getElementById('sidebar').classList.remove('hidden');
  section.scrollIntoView({ behavior: 'smooth', block: 'center' });
  window.setTimeout(() => document.getElementById('broker-provider')?.focus(), 350);
}

function formatCurrency(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value));
}

function formatQuantity(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function formatPct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)}%`;
}

function formatBrokerName(broker) {
  return String(broker || 'Unknown').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function loadSafety() {
  try {
    const resp = await fetch('/api/safety');
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) return;
    const policy = await resp.json();
    const mode = policy.trading_mode;
    document.getElementById('btn-recommend').classList.toggle('active', mode === 'recommend');
    document.getElementById('btn-auto').classList.toggle('active', mode === 'auto');
    document.getElementById('mode-status').textContent = policy.daily_halted
      ? '🛑 Auto-trading is halted for today.'
      : mode === 'auto'
        ? `Auto mode · cap $${policy.auto_max_trade_usd} · live ${policy.live_trading_enabled ? 'enabled' : 'disabled'}`
        : 'Recommend mode — every order needs explicit confirmation.';
  } catch (e) {
    console.error('Safety policy load failed', e);
  }
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )ia_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

async function activateKillSwitch() {
  if (!window.confirm('Block all future autonomous orders for the rest of today?')) return;
  try {
    const resp = await fetch('/api/safety/kill-switch', {
      method: 'POST',
      headers: {'X-CSRF-Token': csrfToken()},
    });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) throw new Error('Kill switch could not be persisted.');
    const data = await resp.json();
    document.getElementById('mode-status').textContent = `🛑 ${data.message}`;
  } catch (error) {
    appendErrorMessage(error.message);
  }
}

// ── Durable user experience ─────────────────────────────────────────────────

async function loadProfile() {
  const statusEl = document.getElementById('profile-status');
  try {
    const resp = await fetch('/api/profile');
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) throw new Error('Profile unavailable');
    const profile = await resp.json();
    document.getElementById('profile-display-name').value = profile.display_name || '';
    document.getElementById('profile-description').value = profile.description || '';
    document.getElementById('profile-preferences').value = JSON.stringify(
      profile.preferences || {}, null, 2
    );
    statusEl.textContent = 'Profile loaded';
    statusEl.className = 'profile-status saved';
  } catch (error) {
    console.error('Profile load failed', error);
    statusEl.textContent = 'Profile could not be loaded.';
    statusEl.className = 'profile-status error';
  }
}

async function saveProfile() {
  const statusEl = document.getElementById('profile-status');
  let preferences;
  try {
    preferences = JSON.parse(document.getElementById('profile-preferences').value || '{}');
  } catch (_) {
    statusEl.textContent = 'Preferences must be valid JSON.';
    statusEl.className = 'profile-status error';
    return;
  }
  if (!preferences || Array.isArray(preferences) || typeof preferences !== 'object') {
    statusEl.textContent = 'Preferences must be a JSON object.';
    statusEl.className = 'profile-status error';
    return;
  }
  statusEl.textContent = 'Saving…';
  statusEl.className = 'profile-status';
  try {
    const resp = await fetch('/api/profile', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
      },
      body: JSON.stringify({
        display_name: document.getElementById('profile-display-name').value,
        description: document.getElementById('profile-description').value,
        preferences,
      }),
    });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || 'Profile could not be saved.');
    }
    const saved = await resp.json();
    document.getElementById('profile-preferences').value = JSON.stringify(
      saved.preferences || {}, null, 2
    );
    statusEl.textContent = 'Profile saved';
    statusEl.className = 'profile-status saved';
  } catch (error) {
    console.error('Profile save failed', error);
    statusEl.textContent = error.message;
    statusEl.className = 'profile-status error';
  }
}

// ── Per-user brokerage accounts ─────────────────────────────────────────────

const DEFAULT_BROKER_PROVIDERS = {
  alpaca: {fields: ['api_key', 'paper', 'secret_key'], secret_fields: ['api_key', 'secret_key']},
  ibkr: {fields: ['client_id', 'enabled', 'host', 'port'], secret_fields: []},
  coinbase: {fields: ['api_key', 'api_secret'], secret_fields: ['api_key', 'api_secret']},
  binance: {fields: ['api_key', 'secret_key', 'testnet'], secret_fields: ['api_key', 'secret_key']},
};
let brokerProviders = {...DEFAULT_BROKER_PROVIDERS};
let brokerAccounts = [];
let editingBrokerAccountId = null;
let editingBrokerAccount = null;

function brokerLabel(broker) {
  return {alpaca: 'Alpaca', ibkr: 'Interactive Brokers', coinbase: 'Coinbase', binance: 'Binance'}[broker] || broker;
}

function brokerFieldLabel(field) {
  return field.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

function renderBrokerFields() {
  const provider = document.getElementById('broker-provider').value;
  const definition = brokerProviders[provider] || DEFAULT_BROKER_PROVIDERS[provider];
  const secretFields = new Set(definition.secret_fields || []);
  const publicConfig = editingBrokerAccount?.broker === provider
    ? (editingBrokerAccount.masked_fields || {}) : {};
  const configured = editingBrokerAccount?.broker === provider
    ? (editingBrokerAccount.configured_fields || {}) : {};
  const fieldsEl = document.getElementById('broker-fields');
  fieldsEl.innerHTML = (definition.fields || []).map(field => {
    const isBoolean = ['paper', 'testnet', 'enabled'].includes(field);
    const inputType = secretFields.has(field) ? 'password' : isBoolean ? 'checkbox' : field === 'port' || field === 'client_id' ? 'number' : 'text';
    if (isBoolean) {
      const defaultChecked = editingBrokerAccountId ? Boolean(publicConfig[field]) : provider === 'ibkr' ? true : true;
      return `<label class="broker-field broker-check"><input id="broker-field-${field}" data-broker-field="${field}" type="checkbox" ${defaultChecked ? 'checked' : ''} /> ${escapeHtml(brokerFieldLabel(field))}</label>`;
    }
    const placeholder = secretFields.has(field)
      ? configured[field] ? 'Configured — leave blank to keep it' : 'Required credential'
      : publicConfig[field] ?? '';
    const value = secretFields.has(field) ? '' : publicConfig[field] ?? (field === 'port' ? '4002' : field === 'client_id' ? '1' : '');
    return `<label class="broker-field">${escapeHtml(brokerFieldLabel(field))}<input id="broker-field-${field}" data-broker-field="${field}" type="${inputType}" value="${escapeHtml(value)}" placeholder="${escapeHtml(String(placeholder))}" /></label>`;
  }).join('');
}

function renderBrokerAccounts() {
  const el = document.getElementById('broker-accounts-list');
  if (!brokerAccounts.length) {
    el.textContent = 'No active brokerage accounts. Market analysis still works without them.';
    return;
  }
  el.innerHTML = brokerAccounts.map(account => {
    const fields = Object.entries(account.masked_fields || {})
      .filter(([field]) => account.configured_fields?.[field] || account.masked_fields[field] !== '')
      .map(([field, value]) => `${escapeHtml(brokerFieldLabel(field))}: ${escapeHtml(String(value))}`)
      .join(' · ');
    return `<div class="broker-account">
      <div class="broker-account-head"><span class="broker-account-name">${escapeHtml(account.display_name)}</span><span class="broker-account-provider">${escapeHtml(brokerLabel(account.broker))}</span></div>
      <div class="broker-account-fields">${fields || 'No fields configured'}</div>
      <div class="broker-account-actions"><button data-edit-account="${escapeHtml(account.id)}">Edit</button><button data-delete-account="${escapeHtml(account.id)}">Disable</button></div>
    </div>`;
  }).join('');
  el.querySelectorAll('[data-edit-account]').forEach(button => {
    button.addEventListener('click', () => editBrokerAccount(button.dataset.editAccount));
  });
  el.querySelectorAll('[data-delete-account]').forEach(button => {
    button.addEventListener('click', () => deleteBrokerAccount(button.dataset.deleteAccount));
  });
}

function setBrokerStatus(message, kind = '') {
  const el = document.getElementById('broker-status');
  el.textContent = message;
  el.className = `profile-status ${kind}`;
}

async function loadBrokerAccounts() {
  try {
    const providerResp = await fetch('/api/broker-accounts/providers');
    if (providerResp.ok) {
      const providerData = await providerResp.json();
      brokerProviders = providerData.providers || brokerProviders;
    }
    renderBrokerFields();
    const resp = await fetch('/api/broker-accounts');
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || 'Brokerage account management is unavailable.');
    }
    const data = await resp.json();
    brokerAccounts = Array.isArray(data.accounts) ? data.accounts : [];
    renderBrokerAccounts();
    setBrokerStatus('Encrypted account settings ready', 'saved');
  } catch (error) {
    console.error('Broker account load failed', error);
    document.getElementById('broker-accounts-list').textContent = error.message;
    setBrokerStatus(error.message, 'error');
  }
}

function editBrokerAccount(accountId) {
  const account = brokerAccounts.find(item => item.id === accountId);
  if (!account) return;
  editingBrokerAccountId = account.id;
  editingBrokerAccount = account;
  const providerEl = document.getElementById('broker-provider');
  providerEl.value = account.broker;
  providerEl.disabled = true;
  document.getElementById('broker-display-name').value = account.display_name || '';
  document.getElementById('broker-cancel').hidden = false;
  renderBrokerFields();
  setBrokerStatus('Editing account — blank secrets keep the existing values');
}

function resetBrokerForm() {
  editingBrokerAccountId = null;
  editingBrokerAccount = null;
  document.getElementById('broker-provider').disabled = false;
  document.getElementById('broker-display-name').value = '';
  document.getElementById('broker-cancel').hidden = true;
  renderBrokerFields();
  setBrokerStatus('');
}

function collectBrokerConfig() {
  const config = {};
  document.querySelectorAll('[data-broker-field]').forEach(input => {
    if (input.type === 'checkbox') config[input.dataset.brokerField] = input.checked;
    else if (input.value !== '') config[input.dataset.brokerField] = input.type === 'number' ? Number(input.value) : input.value;
    else if (editingBrokerAccountId) config[input.dataset.brokerField] = '';
  });
  return config;
}

async function saveBrokerAccount() {
  const provider = document.getElementById('broker-provider').value;
  const body = {
    broker: provider,
    display_name: document.getElementById('broker-display-name').value.trim(),
    config: collectBrokerConfig(),
  };
  setBrokerStatus('Saving encrypted settings…');
  try {
    const url = editingBrokerAccountId ? `/api/broker-accounts/${encodeURIComponent(editingBrokerAccountId)}` : '/api/broker-accounts';
    const resp = await fetch(url, {
      method: editingBrokerAccountId ? 'PUT' : 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
      body: JSON.stringify(body),
    });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || 'Brokerage account could not be saved.');
    }
    resetBrokerForm();
    await loadBrokerAccounts();
  } catch (error) {
    setBrokerStatus(error.message, 'error');
  }
}

async function deleteBrokerAccount(accountId) {
  if (!window.confirm('Disable this brokerage account? Its encrypted record will be retained.')) return;
  try {
    const resp = await fetch(`/api/broker-accounts/${encodeURIComponent(accountId)}`, {
      method: 'DELETE', headers: {'X-CSRF-Token': csrfToken()},
    });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || 'Brokerage account could not be disabled.');
    }
    if (editingBrokerAccountId === accountId) resetBrokerForm();
    await loadBrokerAccounts();
  } catch (error) {
    setBrokerStatus(error.message, 'error');
  }
}

// ── Projects and chat history ───────────────────────────────────────────────

function persistActiveConversation(id) {
  activeConversationId = id || '';
  if (activeConversationId) sessionStorage.setItem('ia_active_conversation_id', activeConversationId);
  else sessionStorage.removeItem('ia_active_conversation_id');
}

async function createConversation(projectId = null) {
  const resp = await fetch('/api/conversations', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
    body: JSON.stringify({ project_id: projectId || null }),
  });
  if (resp.status === 401) { window.location.assign('/login'); return null; }
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail || 'A new chat could not be created.');
  }
  return resp.json();
}

async function loadConversationWorkspace(search = null) {
  const searchEl = document.getElementById('conversation-search');
  const query = search === null ? (searchEl?.value || '') : search;
  try {
    const resp = await fetch(`/api/projects?search=${encodeURIComponent(query)}`);
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) throw new Error('Conversation history unavailable');
    conversationWorkspace = await resp.json();
    const visibleIds = new Set((conversationWorkspace.recent || []).map(item => item.id));
    if (!activeConversationId && conversationWorkspace.recent?.length) {
      persistActiveConversation(conversationWorkspace.recent[0].id);
    }
    if (activeConversationId && !query && !visibleIds.has(activeConversationId)) {
      if (conversationWorkspace.recent?.length) {
        persistActiveConversation(conversationWorkspace.recent[0].id);
      } else {
        const created = await createConversation();
        if (created) persistActiveConversation(created.id);
      }
      const refreshed = await fetch('/api/projects');
      if (refreshed.ok) conversationWorkspace = await refreshed.json();
    }
    if (!activeConversationId && !query) {
      const created = await createConversation();
      if (created) persistActiveConversation(created.id);
      const refreshed = await fetch('/api/projects');
      if (refreshed.ok) conversationWorkspace = await refreshed.json();
    }
    renderConversationSidebar();
    renderConversationProjectSelect();
  } catch (error) {
    console.error('Conversation workspace load failed', error);
    const el = document.getElementById('conversation-history-error');
    if (el) el.textContent = error.message;
  }
}

function scheduleConversationSearch() {
  clearTimeout(conversationSearchTimer);
  conversationSearchTimer = setTimeout(() => loadConversationWorkspace(), 180);
}

function renderConversationSidebar() {
  const projectsEl = document.getElementById('conversation-projects');
  const unassignedEl = document.getElementById('conversation-unassigned');
  if (!projectsEl || !unassignedEl) return;
  const projects = conversationWorkspace.projects || [];
  projectsEl.innerHTML = projects.length
    ? projects.map(project => `
      <section class="history-project">
        <button class="history-project-title" onclick="toggleProjectHistory('${escapeHtml(project.id)}')">
          <span class="project-chevron" id="project-chevron-${escapeHtml(project.id)}">⌄</span>
          <span>${escapeHtml(project.name)}</span>
          <span class="history-count">${project.conversations?.length || 0}</span>
        </button>
        <div class="history-project-chats" id="project-chats-${escapeHtml(project.id)}">
          ${(project.conversations || []).map(renderConversationRow).join('') || '<div class="history-empty">No chats yet</div>'}
        </div>
      </section>
    `).join('')
    : '<div class="history-empty">Create a project to organise chats.</div>';
  unassignedEl.innerHTML = (conversationWorkspace.unassigned || []).length
    ? `<div class="history-group-label">Other chats</div>${conversationWorkspace.unassigned.map(renderConversationRow).join('')}`
    : '';
  const errorEl = document.getElementById('conversation-history-error');
  if (errorEl) errorEl.textContent = '';
}

function renderConversationRow(conversation) {
  const active = conversation.id === activeConversationId ? ' active' : '';
  const preview = conversation.preview || 'No messages yet';
  return `
    <div class="conversation-row-wrap">
      <button class="conversation-row${active}" onclick="selectConversation('${escapeHtml(conversation.id)}')">
        <span class="conversation-row-main">
          <span class="conversation-row-title">${escapeHtml(conversation.title || 'New chat')}</span>
          <span class="conversation-row-preview">${escapeHtml(preview)}</span>
        </span>
        <span class="conversation-row-meta">${relativeTime(conversation.last_message_at || conversation.updated_at)}</span>
      </button>
      <button class="conversation-delete-btn" type="button" onclick="deleteConversation(event, '${escapeHtml(conversation.id)}')" aria-label="Delete chat" title="Delete chat">
        <svg class="conversation-delete-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7l1-3h4l1 3" />
        </svg>
      </button>
    </div>
  `;
}

function toggleProjectHistory(projectId) {
  const chats = document.getElementById(`project-chats-${projectId}`);
  const chevron = document.getElementById(`project-chevron-${projectId}`);
  if (!chats) return;
  const collapsed = chats.hidden;
  chats.hidden = !collapsed;
  if (chevron) chevron.textContent = collapsed ? '⌄' : '›';
}

function renderConversationProjectSelect(projectId = null) {
  const select = document.getElementById('conversation-project');
  if (!select) return;
  const current = projectId || select.dataset.selected || '';
  select.innerHTML = '<option value="">No project</option>'
    + (conversationWorkspace.projects || []).map(project =>
      `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`
    ).join('');
  select.value = current;
  select.dataset.selected = current;
}

function updateConversationHeader(conversation = null) {
  const titleEl = document.getElementById('conversation-title');
  const subtitleEl = document.getElementById('conversation-subtitle');
  if (titleEl) titleEl.textContent = conversation?.title || 'New chat';
  if (subtitleEl) subtitleEl.textContent = conversation?.project_name || 'Personal workspace';
  renderConversationProjectSelect(conversation?.project_id || '');
}

async function startNewConversation() {
  if (activeMessage || messageQueue.length) {
    appendErrorMessage('Wait for the current chat queue to finish before starting another chat.');
    return;
  }
  try {
    const created = await createConversation();
    if (created) await selectConversation(created.id);
  } catch (error) {
    appendErrorMessage(error.message);
  }
}

async function selectConversation(id) {
  if (!id || id === activeConversationId) return;
  if (activeMessage || messageQueue.length) {
    appendErrorMessage('Wait for the current chat queue to finish before switching chats.');
    return;
  }
  clearTimeout(reconnectTimer);
  if (ws) {
    ws.onerror = null;
    ws.onclose = null;
    ws.close(1000);
    ws = null;
  }
  persistActiveConversation(id);
  currentAssistantBubble = null;
  currentAssistantText = '';
  messagesEl().replaceChildren();
  updateConversationHeader();
  renderConversationSidebar();
  setStatus('connecting');
  setSendEnabled(false);
  await loadHistory();
  renderConversationSidebar();
  connect();
}

async function renameActiveConversation() {
  if (!activeConversationId) return;
  const current = document.getElementById('conversation-title')?.textContent || 'New chat';
  const title = window.prompt('Conversation name', current);
  if (title === null) return;
  try {
    const resp = await fetch(`/api/conversations/${encodeURIComponent(activeConversationId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
      body: JSON.stringify({ title: title.trim() || 'New chat' }),
    });
    if (!resp.ok) throw new Error('Conversation could not be renamed.');
    const conversation = await resp.json();
    updateConversationHeader(conversation);
    await loadConversationWorkspace();
  } catch (error) {
    appendErrorMessage(error.message);
  }
}

function conversationTitleById(conversationId) {
  const conversations = [
    ...(conversationWorkspace.unassigned || []),
    ...(conversationWorkspace.recent || []),
    ...(conversationWorkspace.projects || []).flatMap((project) => project.conversations || []),
  ];
  return conversations.find((conversation) => conversation.id === conversationId)?.title || 'this chat';
}

async function deleteConversation(event, conversationId) {
  event?.stopPropagation();
  const title = conversationTitleById(conversationId);
  if (!window.confirm(`Delete “${title}” permanently?`)) return;
  const wasActive = conversationId === activeConversationId;
  try {
    const resp = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
      method: 'DELETE',
      headers: {'X-CSRF-Token': csrfToken()},
    });
    if (resp.status === 401) { window.location.assign('/login'); return; }
    const detail = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(detail.detail || 'Chat could not be deleted.');

    if (wasActive) {
      if (ws) {
        ws.onerror = null;
        ws.onclose = null;
        ws.close(1000);
        ws = null;
      }
      persistActiveConversation('');
      currentAssistantBubble = null;
      currentAssistantText = '';
      messagesEl().replaceChildren();
    }
    await loadConversationWorkspace();
    if (wasActive) {
      await loadHistory();
      connect();
    }
    renderConversationSidebar();
  } catch (error) {
    const errorEl = document.getElementById('conversation-history-error');
    if (errorEl) errorEl.textContent = error.message;
    console.error('Conversation deletion failed', error);
  }
}

async function createProject() {
  const name = window.prompt('Project name');
  if (name === null || !name.trim()) return;
  try {
    const resp = await fetch('/api/projects', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
      body: JSON.stringify({ name: name.trim() }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || 'Project could not be created.');
    }
    await loadConversationWorkspace();
  } catch (error) {
    appendErrorMessage(error.message);
  }
}

async function moveActiveConversation(projectId) {
  if (!activeConversationId) return;
  try {
    const resp = await fetch(`/api/conversations/${encodeURIComponent(activeConversationId)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
      body: JSON.stringify({ project_id: projectId || null }),
    });
    if (!resp.ok) throw new Error('Conversation could not be moved.');
    const conversation = await resp.json();
    updateConversationHeader(conversation);
    await loadConversationWorkspace();
  } catch (error) {
    appendErrorMessage(error.message);
    renderConversationProjectSelect();
  }
}

function appendWelcomeMessage() {
  appendAssistantMessage(
    '**Welcome to your Investment Assistant! 📈**\n\n'
    + 'I can analyse markets, news, simulations, and — depending on your trading mode — execute bounded trades on your behalf.\n\n'
    + 'Use the quick prompts on the left, or ask me anything.'
  );
}

function relativeTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 172800) return 'yesterday';
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

async function loadHistory() {
  if (!activeConversationId) return false;
  try {
    const resp = await fetch(`/api/conversations/${encodeURIComponent(activeConversationId)}`);
    if (resp.status === 401) { window.location.assign('/login'); return false; }
    if (!resp.ok) throw new Error('Conversation history unavailable');
    const conversation = await resp.json();
    messagesEl().replaceChildren();
    for (const message of conversation.messages || []) {
      if (message.role === 'user') appendStoredUserMessage(message.content, message.created_at);
      if (message.role === 'assistant') appendAssistantMessage(message.content, message.created_at);
    }
    updateConversationHeader(conversation);
    if (!conversation.messages?.length) appendWelcomeMessage();
    return Boolean(conversation.messages?.length);
  } catch (error) {
    console.error('Conversation history load failed', error);
    return false;
  }
}

async function loadReports() {
  const el = document.getElementById('reports-list');
  try {
    const resp = await fetch('/api/reports');
    if (resp.status === 401) { window.location.assign('/login'); return; }
    const reports = await resp.json();
    if (!reports.length) { el.textContent = 'No reports yet.'; return; }
    el.innerHTML = reports.slice(0, 5).map(r => `
      <div class="report-item">
        <span>${r.period_start.slice(0, 10)} → ${r.period_end.slice(0, 10)}</span>
        ${r.pdf_available ? `<a href="/api/reports/${r.id}/pdf" target="_blank">PDF ↗</a>` : ''}
      </div>
    `).join('');
  } catch (e) {
    console.error('Reports load failed', e);
    el.textContent = 'Could not load reports.';
  }
}

// ── Fake-money simulation dashboard ─────────────────────────────────────────

function updateSimulationFields() {
  const strategy = document.getElementById('simulation-strategy')?.value;
  const showSma = strategy === 'sma_crossover';
  const showMomentum = strategy === 'momentum';
  ['simulation-fast-wrap', 'simulation-slow-wrap'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !showSma;
  });
  ['simulation-lookback-wrap', 'simulation-topn-wrap'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !showMomentum;
  });
}

function defaultSimulationStart() {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 1);
  return date.toISOString().slice(0, 10);
}

function setSimulationStatus(text, state = 'neutral') {
  const el = document.getElementById('simulation-status');
  if (!el) return;
  el.className = `portfolio-status ${state}`;
  el.textContent = text;
}

function renderSimulationCurve(curve) {
  const el = document.getElementById('simulation-equity-curve');
  if (!el) return;
  if (!curve?.length) {
    el.textContent = 'No equity curve was returned.';
    return;
  }
  const values = curve.map((point) => Number(point.value) || 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  el.innerHTML = curve.slice(-24).map((point) => {
    const value = Number(point.value) || 0;
    const height = Math.max(8, Math.round(((value - min) / span) * 92) + 8);
    return `<div class="simulation-bar-wrap" title="${escapeHtml(point.date)}: $${value.toLocaleString(undefined, {maximumFractionDigits: 2})}">
      <div class="simulation-bar" style="height:${height}%"></div><span>${escapeHtml(point.date.slice(5))}</span></div>`;
  }).join('');
}

function renderSimulationResult(result) {
  document.getElementById('simulation-result').hidden = false;
  document.getElementById('simulation-result-title').textContent = result.name || 'Latest run';
  document.getElementById('sim-result-period').textContent = `${result.period_start} → ${result.period_end}`;
  document.getElementById('sim-final-value').textContent = `$${Number(result.final_value || 0).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
  document.getElementById('sim-return').textContent = `${Number(result.total_return_pct || 0) >= 0 ? '+' : ''}${Number(result.total_return_pct || 0).toFixed(2)}%`;
  document.getElementById('sim-drawdown').textContent = result.max_drawdown_pct == null ? 'n/a' : `${Number(result.max_drawdown_pct).toFixed(2)}%`;
  document.getElementById('sim-trades').textContent = String(result.trades_count ?? 0);
  renderSimulationCurve(result.equity_curve);
}

function renderSimulationHistory(runs) {
  const el = document.getElementById('simulation-history');
  if (!el) return;
  if (!runs?.length) {
    el.textContent = 'No simulations saved yet.';
    return;
  }
  simulationRuns.clear();
  runs.forEach((run) => simulationRuns.set(run.id, run));
  el.innerHTML = runs.map((run) => `
    <button class="simulation-history-row" onclick="showSimulationRun('${escapeHtml(run.id)}')">
      <span><strong>${escapeHtml(run.name)}</strong><small>${escapeHtml(run.period_start)} → ${escapeHtml(run.period_end)}</small></span>
      <span class="${Number(run.total_return_pct) >= 0 ? 'up' : 'down'}">${Number(run.total_return_pct) >= 0 ? '+' : ''}${Number(run.total_return_pct).toFixed(2)}%</span>
    </button>`).join('');
}

function showSimulationRun(id) {
  const run = simulationRuns.get(id);
  if (run) renderSimulationResult(run);
}

async function loadSimulations() {
  const el = document.getElementById('simulation-history');
  if (!el) return;
  try {
    const resp = await fetch('/api/simulations', {cache: 'no-store'});
    if (resp.status === 401) { window.location.assign('/login'); return; }
    if (!resp.ok) throw new Error('Simulation history unavailable.');
    renderSimulationHistory(await resp.json());
  } catch (error) {
    el.textContent = error.message;
  }
}

async function submitSimulation(event) {
  event.preventDefault();
  const strategyType = document.getElementById('simulation-strategy').value;
  const params = {};
  if (strategyType === 'sma_crossover') {
    params.fast = Number(document.getElementById('simulation-fast').value);
    params.slow = Number(document.getElementById('simulation-slow').value);
  } else if (strategyType === 'momentum') {
    params.lookback_days = Number(document.getElementById('simulation-lookback').value);
    params.top_n = Number(document.getElementById('simulation-topn').value);
  }
  const button = document.getElementById('simulation-run-btn');
  button.disabled = true;
  setSimulationStatus('Running…', 'neutral');
  try {
    const resp = await fetch('/api/simulations', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
      body: JSON.stringify({
        name: `${strategyType.replaceAll('_', ' ')} — ${document.getElementById('simulation-symbols').value}`,
        symbols: document.getElementById('simulation-symbols').value,
        strategy: {type: strategyType, params},
        initial_capital: Number(document.getElementById('simulation-capital').value),
        period_start: document.getElementById('simulation-start').value,
        period_end: document.getElementById('simulation-end').value || null,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Simulation failed.');
    renderSimulationResult(data);
    setSimulationStatus('Complete', 'ready');
    await loadSimulations();
  } catch (error) {
    setSimulationStatus(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

// ── Utilities ──────────────────────────────────────────────────────────────────

function messagesEl() { return document.getElementById('messages'); }
function scrollBottom() {
  const el = messagesEl();
  el.scrollTop = el.scrollHeight;
}
function setSendEnabled(enabled) {
  const canSend = enabled && ws?.readyState === WebSocket.OPEN;
  document.getElementById('send-btn').disabled = !canSend;
  document.getElementById('user-input').disabled = !canSend;
}
function setStatus(state) {
  const el = document.getElementById('connection-status');
  el.className = 'conn-status ' + state;
  if (state === 'online') el.textContent = 'Connected';
  else if (state === 'connecting') el.textContent = 'Connecting…';
  else el.textContent = 'Disconnected';
}
function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function formatMessageTime(value) {
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime())
    ? timeNow()
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function escapeHtml(str) {
  return String(str).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
}

/**
 * Replace fenced code blocks (``` … ```) using a linear indexOf scan.
 * Regex-based approaches require backtracking over the block content and are
 * vulnerable to super-linear runtime when there is no closing fence.
 */
function replaceCodeBlocks(html) {
  const FENCE = '```';
  let result = '';
  let pos = 0;
  while (pos < html.length) {
    const open = html.indexOf(FENCE, pos);
    if (open === -1) { result += html.slice(pos); break; }
    result += html.slice(pos, open);
    const bodyStart = open + FENCE.length;
    const close = html.indexOf(FENCE, bodyStart);
    if (close === -1) { result += html.slice(open); break; } // unclosed fence — leave as-is
    const body = html.slice(bodyStart, close);
    const nl = body.indexOf('\n');
    const code = (nl >= 0 ? body.slice(nl + 1) : body).trim(); // strip optional language hint
    result += `<pre><code>${code}</code></pre>`;
    pos = close + FENCE.length;
  }
  return result;
}

/** Very minimal Markdown → HTML for chat messages. */
function markdownToHtml(md) {
  let html = escapeHtml(md);
  // Code blocks — handled by linear scan above (no regex backtracking)
  html = replaceCodeBlocks(html);
  // Inline code
  html = html.replaceAll(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  html = html.replaceAll(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replaceAll(/\*(.+?)\*/g, '<em>$1</em>');
  // Headers
  html = html.replaceAll(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replaceAll(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replaceAll(/^# (.+)$/gm, '<h1>$1</h1>');
  // Unordered list
  html = html.replaceAll(/^[-*] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)+/s, '<ul>$&</ul>');
  // Ordered list
  html = html.replaceAll(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Horizontal rule
  html = html.replaceAll(/^---$/gm, '<hr>');
  // Paragraphs (blank lines)
  html = html.replaceAll(/\n\n+/g, '</p><p>');
  html = html.replaceAll('\n', '<br>');
  return `<p>${html}</p>`;
}

function clampPanelSize(value, min, max) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return min;
  return Math.min(Math.max(numericValue, min), max);
}

function readStoredPanelSize(key, fallback, min, max) {
  try {
    const storedValue = Number(globalThis.localStorage.getItem(key));
    return Number.isFinite(storedValue) ? clampPanelSize(storedValue, min, max) : fallback;
  } catch {
    return fallback;
  }
}

function storePanelSize(key, value) {
  try {
    globalThis.localStorage.setItem(key, String(Math.round(value)));
  } catch {
    // Private browsing and locked-down web views can disable local storage.
  }
}

function setSidebarWidth(width, persist = false) {
  const value = clampPanelSize(width, SIDEBAR_WIDTH_MIN, SIDEBAR_WIDTH_MAX);
  document.documentElement.style.setProperty('--sidebar-w', `${value}px`);
  const resizer = document.getElementById('sidebar-resizer');
  resizer?.setAttribute('aria-valuenow', String(Math.round(value)));
  if (persist) storePanelSize(SIDEBAR_WIDTH_KEY, value);
  return value;
}

function setupPanelResizers() {
  setSidebarWidth(readStoredPanelSize(SIDEBAR_WIDTH_KEY, 280, SIDEBAR_WIDTH_MIN, SIDEBAR_WIDTH_MAX));

  const sidebarResizer = document.getElementById('sidebar-resizer');
  if (sidebarResizer) {
    let resizeState = null;
    const stopSidebarResize = () => {
      if (!resizeState) return;
      setSidebarWidth(resizeState.width, true);
      resizeState = null;
      sidebarResizer.classList.remove('is-active');
      document.body.classList.remove('is-resizing-sidebar');
    };

    sidebarResizer.addEventListener('pointerdown', (event) => {
      if (globalThis.matchMedia?.('(max-width: 768px)').matches) return;
      event.preventDefault();
      const currentWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sidebar-w')) || 280;
      resizeState = { startX: event.clientX, width: currentWidth };
      sidebarResizer.classList.add('is-active');
      document.body.classList.add('is-resizing-sidebar');
      sidebarResizer.setPointerCapture?.(event.pointerId);
    });
    sidebarResizer.addEventListener('pointermove', (event) => {
      if (!resizeState) return;
      resizeState.width = setSidebarWidth(resizeState.width + event.clientX - resizeState.startX);
      resizeState.startX = event.clientX;
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((eventName) => {
      sidebarResizer.addEventListener(eventName, stopSidebarResize);
    });
    sidebarResizer.addEventListener('keydown', (event) => {
      const currentWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sidebar-w')) || 280;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        setSidebarWidth(currentWidth + (event.key === 'ArrowRight' ? 16 : -16), true);
      } else if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault();
        setSidebarWidth(event.key === 'End' ? SIDEBAR_WIDTH_MAX : SIDEBAR_WIDTH_MIN, true);
      }
    });
  }

}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('hidden');
}

// ── Init ──────────────────────────────────────────────────────────────────────

globalThis.addEventListener('DOMContentLoaded', async () => {
  setupPanelResizers();
  if (window.matchMedia?.('(max-width: 768px)').matches) {
    document.getElementById('sidebar').classList.add('hidden');
  }
  await loadConversationWorkspace();
  await loadHistory();
  await loadProfile();
  loadBrokerAccounts();
  connect();
  loadSnapshot();
  loadSafety();
  loadReports();
  const startInput = document.getElementById('simulation-start');
  if (startInput) startInput.value = defaultSimulationStart();
  updateSimulationFields();
  setInterval(loadSnapshot, 5 * 60 * 1000); // auto-refresh every 5 min
  setSendEnabled(true);
});
