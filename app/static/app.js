
const els = {
  assetClass: document.getElementById('asset-class'),
  symbol: document.getElementById('symbol'),
  timeframe: document.getElementById('timeframe'),
  provider: document.getElementById('provider'),
  limit: document.getElementById('limit'),
  loadBtn: document.getElementById('load-btn'),
  demoBotBtn: document.getElementById('demo-bot-btn'),
  demoTopBtn: document.getElementById('demo-top-btn'),
  status: document.getElementById('status'),
  chartCaption: document.getElementById('chart-caption'),
  patternCount: document.getElementById('pattern-count'),
  timeframeHint: document.getElementById('timeframe-hint'),
  signalSummary: document.getElementById('signal-summary'),
  patterns: document.getElementById('patterns'),
  qualityFilter: document.getElementById('quality-filter'),
  currentOnly: document.getElementById('current-only'),
  confirmedOnly: document.getElementById('confirmed-only'),
  resetFilters: document.getElementById('reset-filters'),
  filterSummary: document.getElementById('filter-summary'),
  newsBias: document.getElementById('news-bias'),
  newsSummary: document.getElementById('news-summary'),
  newsArticles: document.getElementById('news-articles'),
  providerBadge: document.getElementById('provider-badge'),
  presetSummary: document.getElementById('preset-summary'),
  presetButtons: Array.from(document.querySelectorAll('.preset-btn')),
  roleButtons: Array.from(document.querySelectorAll('.role-btn')),
  watchlistInput: document.getElementById('watchlist-input'),
  saveWatchlistBtn: document.getElementById('save-watchlist-btn'),
  restoreWatchlistBtn: document.getElementById('restore-watchlist-btn'),
  clearWatchlistBtn: document.getElementById('clear-watchlist-btn'),
  watchlistSaveStatus: document.getElementById('watchlist-save-status'),
  scanRecommendationsBtn: document.getElementById('scan-recommendations-btn'),
  recommendationSummary: document.getElementById('recommendation-summary'),
  recommendations: document.getElementById('recommendations'),
};


const STORAGE_KEY = 'tradeAssistantMvpPreferences:v1';

const state = {
  snapshot: null,
  visiblePatterns: [],
  hoverPatternId: null,
  pinnedPatternId: null,
  recommendations: null,
  watchlistTouched: false,
  savedAt: null,
  filters: {
    qualityMin: 70,
    currentOnly: false,
    confirmedOnly: false,
  },
  selectedPresetId: null,
  selectedPresetRole: 'pattern',
};

const PRESETS = {
  fx_day: {
    id: 'fx_day',
    label: 'FXデイトレ',
    assetClass: 'fx',
    defaultSymbol: 'USDJPY',
    roles: { upper: '1h', pattern: '15m', entry: '5m' },
    filters: { qualityMin: 70, currentOnly: true, confirmedOnly: true },
    watchlist: 'USDJPY,EURUSD,GBPJPY,AUDJPY,EURJPY,GBPUSD',
    demoWatchlist: 'BOT_USDJPY,TOP_EURUSD,USDJPY,EURUSD',
  },
  jp_stock_day: {
    id: 'jp_stock_day',
    label: '日本株デイトレ',
    assetClass: 'stock',
    defaultSymbol: '7203',
    roles: { upper: '1h', pattern: '15m', entry: '5m' },
    filters: { qualityMin: 70, currentOnly: true, confirmedOnly: true },
    watchlist: '7203,6758,9984,8306,9432,7974',
    demoWatchlist: 'BOT_7203,TOP_9984,7203,6758',
  },
  swing: {
    id: 'swing',
    label: 'スイング',
    assetClass: 'stock',
    defaultSymbol: '7203',
    roles: { upper: '4h', pattern: '1h', entry: '15m' },
    filters: { qualityMin: 75, currentOnly: false, confirmedOnly: true },
    watchlist: '7203,6758,9984,8306,9432,7974',
    demoWatchlist: 'BOT_7203,TOP_9984,7203,6758',
  },
};

const LABELS = {
  provider: {
    auto: '自動',
    demo: 'デモ',
    oanda: 'OANDA',
    alpaca: 'Alpaca',
    yfinance: 'Yahoo Finance',
  },
  assetClass: {
    fx: 'FX',
    stock: '株',
  },
  timeframe: {
    '1m': '1分',
    '5m': '5分',
    '15m': '15分',
    '30m': '30分',
    '1h': '1時間',
    '4h': '4時間',
    '1d': '日足',
  },
  patternType: {
    double_bottom: 'ダブルボトム',
    double_top: 'ダブルトップ',
    triple_bottom: 'トリプルボトム',
    triple_top: 'トリプルトップ',
    head_shoulders_top: 'ヘッドアンドショルダー・トップ',
    head_shoulders_bottom: 'ヘッドアンドショルダー・ボトム',
    ascending_triangle: '上昇トライアングル',
    descending_triangle: '下降トライアングル',
    bull_flag: '上昇フラッグ',
    bear_flag: '下降フラッグ',
    ascending_channel: '上昇チャネル',
    descending_channel: '下降チャネル',
    rising_wedge: '上昇ウェッジ',
    falling_wedge: '下降ウェッジ',
    bull_pennant: '上昇ペナント',
    bear_pennant: '下降ペナント',
    saucer_bottom: 'ソーサー・ボトム',
    saucer_top: 'ソーサー・トップ',
  },
  direction: {
    long: '買い候補',
    short: '売り候補',
  },
  state: {
    forming: '形成中',
    confirmed: 'ブレイク確定',
    invalidated: '無効',
  },
  bias: {
    bullish: '強気',
    bearish: '弱気',
    neutral: '中立',
  },
  alert: {
    none: '通知なし',
    watch: '監視',
    warning: '警戒',
  },
  source: {
    'demo-feed': 'デモ配信',
    'デモ配信': 'デモ配信',
    alpaca: 'Alpaca',
    yfinance: 'Yahoo Finance',
    'Yahoo Finance': 'Yahoo Finance',
  },
  action: {
    buy_watch: '買い監視',
    sell_watch: '売り監視',
    breakout_wait: 'ブレイク待ち',
    wait: '見送り',
  },
  trend: {
    up: '上向き',
    down: '下向き',
    range: 'レンジ',
  },
  dailyBias: {
    above_prev_high: '前日高値上抜け',
    near_prev_high: '前日高値接近',
    below_prev_low: '前日安値下抜け',
    near_prev_low: '前日安値接近',
    mid_range: '中間圏',
  },
};

function labelOf(group, key) {
  return LABELS[group]?.[key] ?? key;
}

function setStatus(message) {
  els.status.textContent = message;
}

function roundValue(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  if (Math.abs(value) >= 10) return Number(value).toFixed(3);
  return Number(value).toFixed(5);
}

function formatDate(isoOrTimestamp) {
  const date = new Date(isoOrTimestamp);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('ja-JP', { hour12: false });
}

function pill(text, cls = '') {
  return `<span class="pill ${cls}">${text}</span>`;
}

function directionColor(direction, alpha = 1) {
  return direction === 'long' ? `rgba(53,195,122,${alpha})` : `rgba(255,103,103,${alpha})`;
}

function patternLabel(patternType) {
  return labelOf('patternType', patternType);
}

function directionLabel(direction) {
  return labelOf('direction', direction);
}

function stateLabel(stateValue) {
  return labelOf('state', stateValue);
}

function biasLabel(bias) {
  return labelOf('bias', bias);
}

function alertLabel(alertLevel) {
  return labelOf('alert', alertLevel);
}

function providerLabel(provider) {
  return labelOf('provider', provider);
}

function assetLabel(assetClass) {
  return labelOf('assetClass', assetClass);
}

function timeframeLabel(timeframe) {
  return labelOf('timeframe', timeframe);
}

function sourceLabel(source) {
  return labelOf('source', source);
}


function actionLabel(action) {
  return labelOf('action', action);
}

function trendLabel(trend) {
  return labelOf('trend', trend);
}

function dailyBiasLabel(value) {
  return labelOf('dailyBias', value);
}

function currentPreset() {
  return state.selectedPresetId ? PRESETS[state.selectedPresetId] : null;
}

function normalizeSymbolForAsset(assetClass, symbol, fallback) {
  const value = (symbol || '').trim().toUpperCase().replace(/\s+/g, '');
  if (!value) return fallback;
  if (assetClass === 'fx') {
    if (/BOT_|TOP_/i.test(value) || /^[A-Z]{6}$/.test(value.replace('/', ''))) return value.replace('/', '');
    return fallback;
  }
  return value;
}

function ensureProviderForAsset(assetClass) {
  if (assetClass === 'stock' && els.provider.value === 'oanda') {
    els.provider.value = 'auto';
  }
  if (assetClass === 'fx' && els.provider.value === 'yfinance') {
    els.provider.value = 'auto';
  }
}

function applyPresetFilters(filters) {
  els.qualityFilter.value = filters.qualityMin ? String(filters.qualityMin) : 'all';
  els.currentOnly.checked = Boolean(filters.currentOnly);
  els.confirmedOnly.checked = Boolean(filters.confirmedOnly);
  syncFiltersFromUI();
}

function defaultWatchlistForPreset(preset) {
  if (!preset) return els.assetClass.value === 'fx' ? 'USDJPY,EURUSD,GBPJPY,AUDJPY,EURJPY,GBPUSD' : '7203,6758,9984,8306,9432,7974';
  return els.provider.value === 'demo' ? preset.demoWatchlist : preset.watchlist;
}

function storageAvailable() {
  try {
    const key = '__trade_assistant_storage_check__';
    localStorage.setItem(key, '1');
    localStorage.removeItem(key);
    return true;
  } catch (_) {
    return false;
  }
}

function readSavedPreferences() {
  if (!storageAvailable()) return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.warn('保存設定の読み込みに失敗しました', error);
    return null;
  }
}

function currentWatchlistKey() {
  return state.selectedPresetId || `${els.assetClass.value}:${els.provider.value}`;
}

function savedWatchlistForKey(key = currentWatchlistKey()) {
  const prefs = readSavedPreferences();
  const value = prefs?.watchlists?.[key] || '';
  return value.trim() ? value : null;
}

function updateWatchlistSaveStatus(message = '') {
  const prefs = readSavedPreferences();
  if (message) {
    els.watchlistSaveStatus.textContent = message;
    return;
  }
  if (!prefs?.savedAt) {
    els.watchlistSaveStatus.textContent = '保存すると、次回起動時に監視銘柄・足セット・フィルタが自動復元されます。';
    return;
  }
  const savedWatchlist = savedWatchlistForKey();
  const suffix = savedWatchlist ? ` / この足セットの保存銘柄: ${savedWatchlist}` : '';
  els.watchlistSaveStatus.textContent = `保存済み: ${formatDate(prefs.savedAt)}${suffix}`;
}

function saveCurrentPreferences({ manual = false } = {}) {
  if (!storageAvailable()) {
    updateWatchlistSaveStatus('ブラウザ保存が使えません。localStorage が無効になっている可能性があります。');
    return;
  }
  syncFiltersFromUI();
  const prefs = readSavedPreferences() || {};
  const key = currentWatchlistKey();
  const now = new Date().toISOString();
  const watchlist = els.watchlistInput.value.trim();
  const watchlists = { ...(prefs.watchlists || {}) };
  if (watchlist) {
    watchlists[key] = watchlist;
    if (state.selectedPresetId) watchlists[state.selectedPresetId] = watchlist;
  }
  const payload = {
    version: 1,
    selectedPresetId: state.selectedPresetId,
    selectedPresetRole: state.selectedPresetRole,
    assetClass: els.assetClass.value,
    symbol: els.symbol.value.trim(),
    timeframe: els.timeframe.value,
    provider: els.provider.value,
    limit: Number(els.limit.value) || 240,
    filters: { ...state.filters },
    watchlist,
    watchlists,
    savedAt: now,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  state.savedAt = now;
  updateWatchlistSaveStatus(manual ? `保存しました: ${formatDate(now)} / ${watchlist || '監視銘柄なし'}` : '');
}

function loadSavedPreferences() {
  const prefs = readSavedPreferences();
  if (!prefs?.savedAt) return false;

  if (prefs.selectedPresetId && PRESETS[prefs.selectedPresetId]) {
    state.selectedPresetId = prefs.selectedPresetId;
  }
  state.selectedPresetRole = prefs.selectedPresetRole || 'pattern';
  els.assetClass.value = prefs.assetClass || currentPreset()?.assetClass || els.assetClass.value;
  els.provider.value = prefs.provider || els.provider.value;
  ensureProviderForAsset(els.assetClass.value);
  els.symbol.value = prefs.symbol || currentPreset()?.defaultSymbol || els.symbol.value;
  els.timeframe.value = prefs.timeframe || currentPreset()?.roles?.[state.selectedPresetRole] || els.timeframe.value;
  els.limit.value = prefs.limit || els.limit.value;

  const filters = prefs.filters || currentPreset()?.filters || state.filters;
  applyPresetFilters(filters);

  const key = currentWatchlistKey();
  const watchlist = prefs.watchlists?.[key] || prefs.watchlists?.[state.selectedPresetId] || prefs.watchlist || defaultWatchlistForPreset(currentPreset());
  els.watchlistInput.value = watchlist;
  state.watchlistTouched = Boolean(watchlist);
  state.savedAt = prefs.savedAt;

  updatePresetUI();
  syncPresetRoleFromTimeframe();
  updateWatchlistSaveStatus();
  return true;
}

function restoreSavedWatchlist() {
  const saved = savedWatchlistForKey() || readSavedPreferences()?.watchlist || '';
  if (!saved.trim()) {
    updateWatchlistSaveStatus('この足セットの保存リストはまだありません。先に「監視銘柄を保存」を押してください。');
    return;
  }
  els.watchlistInput.value = saved;
  state.watchlistTouched = true;
  updateWatchlistSaveStatus(`保存リストを復元しました: ${saved}`);
}

function clearSavedPreferences() {
  if (!storageAvailable()) return;
  localStorage.removeItem(STORAGE_KEY);
  state.savedAt = null;
  updateWatchlistSaveStatus('保存データを削除しました。現在の入力内容は画面上に残っています。');
}

function setWatchlistIfUntouched(force = false) {
  const preset = currentPreset();
  if (!preset && !force) return;
  const savedValue = savedWatchlistForKey();
  const nextValue = savedValue || defaultWatchlistForPreset(preset);
  if (force || !state.watchlistTouched || !els.watchlistInput.value.trim()) {
    els.watchlistInput.value = nextValue;
    state.watchlistTouched = Boolean(savedValue);
  }
  updateWatchlistSaveStatus();
}

function updatePresetUI() {
  const preset = currentPreset();
  els.presetButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.preset === state.selectedPresetId);
  });
  els.roleButtons.forEach((button) => {
    button.classList.toggle('active', Boolean(preset) && button.dataset.role === state.selectedPresetRole);
    button.disabled = !preset;
  });
  if (!preset) {
    els.presetSummary.textContent = '未選択。FXデイトレ / 日本株デイトレ / スイングから選べます。';
    return;
  }
  const roleLabel = state.selectedPresetRole === 'upper' ? '上位足' : state.selectedPresetRole === 'entry' ? '実行足' : 'パターン足';
  els.presetSummary.textContent = `${preset.label} / いま表示: ${roleLabel} ${timeframeLabel(els.timeframe.value)} / 推奨: 上位 ${timeframeLabel(preset.roles.upper)} → パターン ${timeframeLabel(preset.roles.pattern)} → 実行 ${timeframeLabel(preset.roles.entry)}`;
}

function syncPresetRoleFromTimeframe() {
  const preset = currentPreset();
  if (!preset) return;
  const matched = Object.entries(preset.roles).find(([, frame]) => frame === els.timeframe.value)?.[0];
  if (matched) {
    state.selectedPresetRole = matched;
  }
  updatePresetUI();
}

function applyPreset(presetId, role = 'pattern', shouldLoad = true) {
  const preset = PRESETS[presetId];
  if (!preset) return;
  state.selectedPresetId = presetId;
  state.selectedPresetRole = role;
  els.assetClass.value = preset.assetClass;
  els.symbol.value = normalizeSymbolForAsset(preset.assetClass, els.symbol.value, preset.defaultSymbol);
  ensureProviderForAsset(preset.assetClass);
  els.timeframe.value = preset.roles[role];
  applyPresetFilters(preset.filters);
  state.pinnedPatternId = null;
  state.hoverPatternId = null;
  updatePresetUI();
  setWatchlistIfUntouched(true);
  if (shouldLoad) {
    loadSnapshot();
    loadRecommendations();
  }
}

function switchPresetRole(role) {
  const preset = currentPreset();
  if (!preset) return;
  state.selectedPresetRole = role;
  els.timeframe.value = preset.roles[role];
  updatePresetUI();
  loadSnapshot();
}

function timeframeHint(timeframe) {
  if (['1m', '5m', '15m'].includes(timeframe)) return '短期足なのでフラッグ・ペナント・トライアングル・ウェッジを優先表示';
  if (['30m', '1h'].includes(timeframe)) return '中間足なのでチャネル・ウェッジ・反転系をバランス表示';
  if (['4h', '1d'].includes(timeframe)) return '上位足なのでヘッドアンドショルダー・ソーサー・トリプル系を重視';
  return '時間足に合わせて優先表示を調整';
}

function patternSignalTimestamp(pattern) {
  const candidates = [pattern.signal_time, pattern.completed_at, ...(pattern.points || []).map((point) => point.time)]
    .map((value) => new Date(value).getTime())
    .filter((value) => Number.isFinite(value));
  return candidates.length ? Math.max(...candidates) : 0;
}

function sortPatternsForDisplay(patterns) {
  return [...patterns].sort((a, b) => {
    const currentDiff = Number(Boolean(b.is_current)) - Number(Boolean(a.is_current));
    if (currentDiff !== 0) return currentDiff;
    const timeDiff = patternSignalTimestamp(b) - patternSignalTimestamp(a);
    if (timeDiff !== 0) return timeDiff;
    const stateRank = (pattern) => (pattern.state === 'confirmed' ? 2 : pattern.state === 'forming' ? 1 : 0);
    const stateDiff = stateRank(b) - stateRank(a);
    if (stateDiff !== 0) return stateDiff;
    const probDiff = (b.probability || 0) - (a.probability || 0);
    if (probDiff !== 0) return probDiff;
    return (b.quality_score || 0) - (a.quality_score || 0);
  });
}

function qualityThresholdLabel(value) {
  return value ? `品質 ${value}以上` : '品質 すべて';
}

function syncFiltersFromUI() {
  state.filters = {
    qualityMin: els.qualityFilter.value === 'all' ? 0 : Number(els.qualityFilter.value || 0),
    currentOnly: els.currentOnly.checked,
    confirmedOnly: els.confirmedOnly.checked,
  };
}

function filterPatterns(patterns) {
  const { qualityMin, currentOnly, confirmedOnly } = state.filters;
  return patterns.filter((pattern) => {
    if (qualityMin && (pattern.quality_score || 0) < qualityMin) return false;
    if (currentOnly && !(pattern.is_current && pattern.state !== 'invalidated')) return false;
    if (confirmedOnly && pattern.state !== 'confirmed') return false;
    return true;
  });
}

function renderFilterSummary(totalCount, visibleCount) {
  const filterPills = [];
  filterPills.push(pill(qualityThresholdLabel(state.filters.qualityMin || 0)));
  if (state.filters.currentOnly) filterPills.push(pill('現在サインのみ', 'current'));
  if (state.filters.confirmedOnly) filterPills.push(pill('確定のみ', 'confirmed'));
  els.filterSummary.innerHTML = `
    <span>表示中 ${visibleCount} / 全${totalCount} 件</span>
    <span class="filter-meta">${filterPills.join('')}</span>
  `;
}

function rerenderWithCurrentFilters() {
  if (!state.snapshot) return;
  syncFiltersFromUI();
  const filteredPatterns = filterPatterns(state.snapshot.patterns || []);
  state.visiblePatterns = filteredPatterns;
  if (state.pinnedPatternId && !filteredPatterns.some((pattern) => pattern.id === state.pinnedPatternId)) {
    state.pinnedPatternId = null;
  }
  if (state.hoverPatternId && !filteredPatterns.some((pattern) => pattern.id === state.hoverPatternId)) {
    state.hoverPatternId = null;
  }
  els.patternCount.textContent = `${filteredPatterns.length} / ${state.snapshot.patterns.length} 件`;
  renderSignalSummary(state.snapshot.patterns, filteredPatterns, state.snapshot.timeframe);
  renderFilterSummary(state.snapshot.patterns.length, filteredPatterns.length);
  renderChart(state.snapshot);
  renderPatterns(filteredPatterns);
}


function activePatternId() {
  return state.pinnedPatternId || state.hoverPatternId;
}

function findPattern(patternId) {
  return state.visiblePatterns?.find((pattern) => pattern.id === patternId) || null;
}

function buildLabelPositions(patterns) {
  if (!patterns.length) return new Map();
  const priceCandidates = patterns.flatMap((pattern) => [
    ...(pattern.points || []).map((point) => point.price),
    pattern.neckline,
    pattern.invalidation,
    ...(pattern.entry_zone || []),
  ]).filter((value) => Number.isFinite(value));
  const minPrice = Math.min(...priceCandidates);
  const maxPrice = Math.max(...priceCandidates);
  const minGap = Math.max((maxPrice - minPrice) * 0.09, Math.abs(maxPrice || 1) * 0.004, 0.18);
  const sorted = [...patterns].sort((a, b) => {
    const ay = Math.max(...a.points.map((point) => point.price), a.neckline, ...(a.entry_zone || []));
    const by = Math.max(...b.points.map((point) => point.price), b.neckline, ...(b.entry_zone || []));
    return by - ay;
  });

  const placed = [];
  const result = new Map();
  sorted.forEach((pattern) => {
    let y = Math.max(...pattern.points.map((point) => point.price), pattern.neckline, ...(pattern.entry_zone || []));
    placed.forEach((usedY) => {
      if (Math.abs(usedY - y) < minGap) {
        y = usedY - minGap;
      }
    });
    if (y < minPrice) {
      y = minPrice;
    }
    placed.push(y);
    result.set(pattern.id, y);
  });
  return result;
}

function candleIntervalMs(candles) {
  if (!candles || candles.length < 2) return 60_000;
  const first = new Date(candles[0].time).getTime();
  const second = new Date(candles[1].time).getTime();
  return Math.max(60_000, Math.abs(second - first));
}

function shiftIso(iso, deltaMs) {
  return new Date(new Date(iso).getTime() + deltaMs).toISOString();
}

async function loadSnapshot() {
  const params = new URLSearchParams({
    asset_class: els.assetClass.value,
    symbol: els.symbol.value.trim(),
    timeframe: els.timeframe.value,
    provider: els.provider.value,
    limit: els.limit.value,
  });

  setStatus('読み込み中...');
  try {
    const response = await fetch(`/api/snapshot?${params.toString()}`);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      throw new Error(typeof payload === 'string' ? payload : (payload.detail || 'データ取得に失敗しました'));
    }
    renderSnapshot(payload);
    setStatus(`更新完了: ${formatDate(payload.generated_at)}`);
  } catch (error) {
    console.error(error);
    setStatus(`エラー: ${error.message}`);
  }
}

function renderSnapshot(snapshot) {
  const sortedPatterns = sortPatternsForDisplay(snapshot.patterns || []);
  state.snapshot = { ...snapshot, patterns: sortedPatterns };

  els.providerBadge.textContent = `データ元: ${providerLabel(snapshot.provider)}`;
  els.chartCaption.textContent = `${snapshot.symbol} / ${timeframeLabel(snapshot.timeframe)} / ${assetLabel(snapshot.asset_class)}`;
  els.timeframeHint.textContent = timeframeHint(snapshot.timeframe);
  syncPresetRoleFromTimeframe();
  rerenderWithCurrentFilters();
  renderNews(snapshot.news);
}


async function loadRecommendations() {
  const presetId = state.selectedPresetId || (els.assetClass.value === 'fx' ? 'fx_day' : 'jp_stock_day');
  const params = new URLSearchParams({
    asset_class: els.assetClass.value,
    provider: els.provider.value,
    preset_id: presetId,
    watchlist: els.watchlistInput.value.trim(),
    current_symbol: els.symbol.value.trim(),
  });

  els.recommendationSummary.textContent = '注目銘柄をスキャン中...';
  try {
    const response = await fetch(`/api/recommendations?${params.toString()}`);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      throw new Error(typeof payload === 'string' ? payload : (payload.detail || '注目銘柄スキャンに失敗しました'));
    }
    renderRecommendations(payload);
  } catch (error) {
    console.error(error);
    els.recommendationSummary.textContent = `注目銘柄スキャン失敗: ${error.message}`;
    els.recommendations.innerHTML = '<div class="card">注目銘柄を取得できませんでした。</div>';
  }
}

function renderRecommendations(payload) {
  state.recommendations = payload;
  const summaryParts = [
    `${payload.items.length}件表示`,
    `日足 ${timeframeLabel(payload.daily_timeframe)}`,
    `上位足 ${timeframeLabel(payload.upper_timeframe)}`,
    `パターン足 ${timeframeLabel(payload.pattern_timeframe)}`,
  ];
  if (payload.failures?.length) {
    summaryParts.push(`取得失敗 ${payload.failures.length}件`);
  }
  els.recommendationSummary.textContent = `${summaryParts.join(' / ')} / 更新 ${formatDate(payload.generated_at)}`;

  if (!payload.items?.length) {
    const failureText = payload.failures?.length ? `<ul>${payload.failures.map((f) => `<li>${f.symbol}: ${f.detail}</li>`).join('')}</ul>` : '';
    els.recommendations.innerHTML = `<div class="card">条件に合う注目銘柄がありません。${failureText}</div>`;
    return;
  }

  els.recommendations.innerHTML = payload.items.map((item) => {
    const trade = item.top_trade_plan;
    return `
      <div class="card reco-card" data-symbol="${item.symbol}">
        <div class="card-head">
          <h3>${item.symbol}</h3>
          <span class="score-badge rank-${item.rank_label.toLowerCase()}">${item.rank_label} ${item.score.toFixed(1)}</span>
        </div>
        <p class="summary-line">${item.summary}</p>
        <div class="meta">
          ${pill(actionLabel(item.action), item.action.replace('_', '-'))}
          ${pill(trendLabel(item.upper_trend), item.upper_trend)}
          ${pill(dailyBiasLabel(item.daily_bias), item.daily_bias)}
          ${item.current_signal ? pill(`現在サイン ${item.current_signal_count}件`, 'current') : pill('現在サインなし', 'history')}
          ${item.top_pattern_type ? pill(patternLabel(item.top_pattern_type)) : pill('パターン待ち')}
          ${item.top_pattern_probability ? pill(`優位度 ${item.top_pattern_probability.toFixed(1)}%`) : ''}
        </div>
        <p class="deep-reason">${item.deep_reason}</p>
        <dl>
          <dt>前日高値</dt><dd>${roundValue(item.previous_day_high)}</dd>
          <dt>前日安値</dt><dd>${roundValue(item.previous_day_low)}</dd>
          <dt>重要上値</dt><dd>${roundValue(item.key_resistance)}</dd>
          <dt>重要下値</dt><dd>${roundValue(item.key_support)}</dd>
          <dt>現在値</dt><dd>${roundValue(item.latest_close)}</dd>
          <dt>上位足</dt><dd>${timeframeLabel(item.upper_timeframe)}</dd>
          ${trade ? `<dt>推奨指値</dt><dd>${roundValue(trade.suggested_limit)}</dd>` : ''}
          ${trade ? `<dt>TP1 / TP2</dt><dd>${roundValue(trade.target_1)} / ${roundValue(trade.target_2)}</dd>` : ''}
        </dl>
        <ul>${(item.reasons || []).map((reason) => `<li>${reason}</li>`).join('')}</ul>
        <div class="reco-actions">
          <button class="secondary small reco-open-btn" data-symbol="${item.symbol}" data-role="upper">上位足で開く</button>
          <button class="secondary small reco-open-btn" data-symbol="${item.symbol}" data-role="pattern">パターン足で開く</button>
          <button class="secondary small reco-open-btn" data-symbol="${item.symbol}" data-role="entry">実行足で開く</button>
        </div>
      </div>
    `;
  }).join('');

  els.recommendations.querySelectorAll('.reco-open-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const preset = currentPreset();
      const role = button.dataset.role || 'pattern';
      if (preset?.roles?.[role]) {
        els.timeframe.value = preset.roles[role];
        state.selectedPresetRole = role;
      }
      els.symbol.value = button.dataset.symbol || els.symbol.value;
      syncPresetRoleFromTimeframe();
      loadSnapshot();
    });
  });
}

function renderSignalSummary(allPatterns, visiblePatterns, timeframe) {
  const current = allPatterns.filter((pattern) => pattern.is_current && pattern.state !== 'invalidated');
  const visibleCurrent = visiblePatterns.filter((pattern) => pattern.is_current && pattern.state !== 'invalidated');
  const buyCount = current.filter((pattern) => pattern.direction === 'long').length;
  const sellCount = current.filter((pattern) => pattern.direction === 'short').length;
  const latest = allPatterns[0];
  const summaryClass = current.length ? 'active' : 'none';

  els.signalSummary.innerHTML = `
    <div class="summary-box signal-box ${summaryClass}">
      <div>
        <strong>現在サイン: ${current.length ? 'あり' : 'なし'}</strong>
        <div class="caption">${timeframeHint(timeframe)}</div>
      </div>
      <div class="meta">
        ${current.length ? pill(`買い ${buyCount} 件`, 'long') : ''}
        ${current.length ? pill(`売り ${sellCount} 件`, 'short') : ''}
        ${visibleCurrent.length !== current.length ? pill(`表示中の現在サイン ${visibleCurrent.length} 件`) : ''}
        ${latest ? pill(`最新検出 ${formatDate(patternSignalTimestamp(latest))}`, latest.is_current ? 'confirmed' : 'forming') : ''}
      </div>
    </div>
  `;
}

function renderChart(snapshot) {
  const candles = snapshot.candles;
  const x = candles.map((c) => c.time);
  const open = candles.map((c) => c.open);
  const high = candles.map((c) => c.high);
  const low = candles.map((c) => c.low);
  const close = candles.map((c) => c.close);
  const intervalMs = candleIntervalMs(candles);
  const pinnedPattern = state.pinnedPatternId ? findPattern(state.pinnedPatternId) : null;
  const highlightedId = activePatternId();

  const traces = [
    {
      type: 'candlestick',
      x,
      open,
      high,
      low,
      close,
      name: snapshot.symbol,
      increasing: { line: { color: '#35c37a' }, fillcolor: '#35c37a' },
      decreasing: { line: { color: '#ff6767' }, fillcolor: '#ff6767' },
      whiskerwidth: 0.5,
    },
  ];

  const shapes = [];
  const annotations = [];
  const sourcePatterns = state.visiblePatterns.length ? state.visiblePatterns : [];
  const basePatterns = sourcePatterns.slice(0, 6);
  const patternsToDraw = highlightedId
    ? [findPattern(highlightedId)].filter(Boolean)
    : basePatterns;
  const labelPositions = buildLabelPositions(patternsToDraw);

  patternsToDraw.forEach((pattern, patternIndex) => {
    const isActive = pattern.id === highlightedId;
    const color = directionColor(pattern.direction, isActive ? 0.98 : pattern.is_current ? 0.88 : 0.62);
    const fillColor = directionColor(pattern.direction, isActive ? 0.16 : pattern.is_current ? 0.10 : 0.05);
    const patternName = patternLabel(pattern.pattern_type);
    const patternX = pattern.points.map((point) => point.time);
    const patternY = pattern.points.map((point) => point.price);
    const lineWidth = isActive ? 3.3 : pattern.is_current ? 2.3 : 1.5;

    traces.push({
      type: 'scatter',
      mode: 'lines+markers+text',
      x: patternX,
      y: patternY,
      text: pattern.points.map((point) => point.label),
      textposition: pattern.points.map((point) => (point.kind === 'high' ? 'top center' : 'bottom center')),
      marker: { size: isActive ? 12 : 8, color },
      line: { color, width: lineWidth },
      textfont: { color, size: isActive ? 12 : 10 },
      name: patternName,
      showlegend: false,
      hovertemplate: `${patternName}<br>%{text}: %{y}<extra></extra>`,
    });

    const signalTime = pattern.signal_time || pattern.completed_at || pattern.points[pattern.points.length - 1]?.time;
    const startTime = pattern.started_at || pattern.points[0]?.time;
    const endTime = pattern.completed_at || signalTime;
    const bandEnd = shiftIso(endTime, intervalMs * 1.3);

    shapes.push({
      type: 'rect',
      x0: startTime,
      x1: bandEnd,
      y0: Math.min(...patternY, pattern.neckline, pattern.invalidation),
      y1: Math.max(...patternY, pattern.neckline, pattern.invalidation),
      fillcolor: fillColor,
      line: { color: isActive ? color : 'rgba(255,255,255,0.06)', width: isActive ? 1.1 : 0.6 },
      layer: 'below',
    });
    const guideLines = pattern.guide_lines || [];
    if (guideLines.length) {
      guideLines.forEach((lineSpec) => {
        const guideColor = lineSpec.kind === 'invalidation' ? 'rgba(255,255,255,0.58)' : color;
        const guideDash = lineSpec.kind === 'invalidation' ? 'dash' : (lineSpec.kind === 'flag' ? 'solid' : 'dot');
        const guideWidth = isActive ? (lineSpec.kind === 'flag' ? 2.6 : 2.4) : (lineSpec.kind === 'flag' ? 1.8 : 1.4);
        shapes.push({
          type: 'line',
          x0: lineSpec.x0,
          x1: lineSpec.x1,
          y0: lineSpec.y0,
          y1: lineSpec.y1,
          line: { color: guideColor, width: guideWidth, dash: guideDash },
        });
      });
    } else {
      shapes.push({
        type: 'line',
        x0: startTime,
        x1: shiftIso(x[x.length - 1], intervalMs * 0.25),
        y0: pattern.neckline,
        y1: pattern.neckline,
        line: { color, width: isActive ? 2.8 : 1.8, dash: 'dot' },
      });
      shapes.push({
        type: 'line',
        x0: startTime,
        x1: shiftIso(x[x.length - 1], intervalMs * 0.25),
        y0: pattern.invalidation,
        y1: pattern.invalidation,
        line: { color: 'rgba(255,255,255,0.58)', width: isActive ? 2 : 1.3, dash: 'dash' },
      });
    }
    shapes.push({
      type: 'line',
      x0: signalTime,
      x1: signalTime,
      y0: Math.min(...pattern.entry_zone, pattern.neckline, pattern.invalidation, ...patternY),
      y1: Math.max(...pattern.entry_zone, pattern.neckline, pattern.invalidation, ...patternY),
      line: { color, width: isActive ? 2.4 : 1.2, dash: 'solid' },
    });
    shapes.push({
      type: 'rect',
      x0: signalTime,
      x1: shiftIso(x[x.length - 1], intervalMs * 0.8),
      y0: Math.min(pattern.entry_zone[0], pattern.entry_zone[1]),
      y1: Math.max(pattern.entry_zone[0], pattern.entry_zone[1]),
      fillcolor: fillColor,
      line: { color, width: isActive ? 1 : 0.5 },
      layer: 'below',
    });

    annotations.push({
      x: 1.01,
      xref: 'paper',
      xanchor: 'left',
      y: labelPositions.get(pattern.id) ?? pattern.neckline,
      yref: 'y',
      text: `${patternName} ${pattern.is_current ? '現在サイン' : '履歴サイン'}`,
      showarrow: false,
      font: { color, size: isActive ? 12 : 11 },
      bgcolor: 'rgba(11,16,32,0.92)',
      bordercolor: color,
      borderwidth: 1,
      align: 'left',
    });
  });

  const layout = {
    margin: { t: 16, r: highlightedId ? 160 : 140, b: 32, l: 50 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: '#0f1730',
    font: { color: '#e6ecff' },
    xaxis: {
      rangeslider: { visible: false },
      gridcolor: 'rgba(255,255,255,0.06)',
      showspikes: true,
    },
    yaxis: {
      side: 'right',
      gridcolor: 'rgba(255,255,255,0.06)',
      tickformat: '.5f',
      fixedrange: false,
    },
    legend: { orientation: 'h', y: 1.08 },
    shapes,
    annotations,
    hovermode: 'x unified',
  };

  if (pinnedPattern) {
    const times = [pinnedPattern.started_at, pinnedPattern.completed_at, pinnedPattern.signal_time]
      .filter(Boolean)
      .map((value) => new Date(value).getTime());
    if (times.length) {
      const pad = intervalMs * 6;
      layout.xaxis.range = [new Date(Math.min(...times) - pad).toISOString(), new Date(Math.max(...times) + pad).toISOString()];
    }
    const yValues = [
      ...pinnedPattern.points.map((point) => point.price),
      pinnedPattern.neckline,
      pinnedPattern.invalidation,
      ...pinnedPattern.entry_zone,
    ];
    const yMin = Math.min(...yValues);
    const yMax = Math.max(...yValues);
    const yPad = Math.max((yMax - yMin) * 0.18, Math.abs(yMax) * 0.01, 0.5);
    layout.yaxis.range = [yMin - yPad, yMax + yPad];
  }

  Plotly.react('chart', traces, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
}

function renderPatterns(patterns) {
  if (!patterns.length) {
    const hasRaw = (state.snapshot?.patterns?.length || 0) > 0;
    els.patterns.innerHTML = `<div class="card">${hasRaw ? '条件に合うパターンがありません。品質フィルタや現在サインのみを見直してください。' : 'まだ条件に合うパターンはありません。'}</div>`;
    return;
  }

  const selectedId = activePatternId();
  els.patterns.innerHTML = patterns
    .map((pattern) => {
      const stateClass = pattern.state === 'confirmed' ? 'confirmed' : pattern.state === 'forming' ? 'forming' : 'invalidated';
      const dirClass = pattern.direction === 'long' ? 'long' : 'short';
      const notes = pattern.trade_plan.notes || [];
      const activeClass = pattern.id === selectedId ? 'active' : '';
      const currentClass = pattern.is_current ? 'current' : 'history';
      return `
        <div class="card pattern-card ${activeClass} ${currentClass}" data-pattern-id="${pattern.id}">
          <div class="card-head">
            <h3>${patternLabel(pattern.pattern_type)}</h3>
            <span class="card-tip">${pattern.id === state.pinnedPatternId ? '単独表示中・再クリックで解除' : 'ホバー/クリックで該当サインのみ表示'}</span>
          </div>
          <div class="meta">
            ${pill(directionLabel(pattern.direction), dirClass)}
            ${pill(stateLabel(pattern.state), stateClass)}
            ${pill(pattern.family === 'continuation' ? '継続型' : '反転型')}
            ${pill(`形の質 ${pattern.quality_score.toFixed(1)}`)}
            ${pill(`推定優位度 ${pattern.probability.toFixed(1)}%`)}
            ${pattern.is_current ? pill('現在サイン', 'current') : pill(`最新足から ${pattern.signal_age_bars} 本前`, 'history')}
          </div>
          <dl>
            <dt>検出時刻</dt><dd>${formatDate(pattern.signal_time)}</dd>
            <dt>形成期間</dt><dd>${formatDate(pattern.started_at)} 〜 ${formatDate(pattern.completed_at)}</dd>
            <dt>推奨指値</dt><dd>${roundValue(pattern.trade_plan.suggested_limit)}</dd>
            <dt>損切り</dt><dd>${roundValue(pattern.trade_plan.stop_loss)}</dd>
            <dt>TP1 / RR</dt><dd>${roundValue(pattern.trade_plan.target_1)} / ${pattern.trade_plan.risk_reward_1.toFixed(2)}</dd>
            <dt>TP2 / RR</dt><dd>${roundValue(pattern.trade_plan.target_2)} / ${pattern.trade_plan.risk_reward_2.toFixed(2)}</dd>
            <dt>ネックライン</dt><dd>${roundValue(pattern.neckline)}</dd>
            <dt>無効化</dt><dd>${roundValue(pattern.invalidation)}</dd>
          </dl>
          <ul>
            ${pattern.explanation.map((item) => `<li>${item}</li>`).join('')}
            ${notes.slice(0, 1).map((item) => `<li>${item}</li>`).join('')}
          </ul>
        </div>
      `;
    })
    .join('');

  els.patterns.querySelectorAll('.pattern-card').forEach((card) => {
    const patternId = card.dataset.patternId;
    card.addEventListener('mouseenter', () => {
      state.hoverPatternId = patternId;
      renderChart(state.snapshot);
      refreshPatternCardState();
    });
    card.addEventListener('mouseleave', () => {
      state.hoverPatternId = null;
      renderChart(state.snapshot);
      refreshPatternCardState();
    });
    card.addEventListener('click', () => {
      state.pinnedPatternId = state.pinnedPatternId === patternId ? null : patternId;
      renderChart(state.snapshot);
      refreshPatternCardState();
    });
  });

  refreshPatternCardState();
}

function refreshPatternCardState() {
  const selectedId = activePatternId();
  els.patterns.querySelectorAll('.pattern-card').forEach((card) => {
    const isActive = card.dataset.patternId === selectedId;
    const isPinned = card.dataset.patternId === state.pinnedPatternId;
    card.classList.toggle('active', isActive);
    card.classList.toggle('pinned', isPinned);
  });
}

function renderNews(news) {
  els.newsBias.textContent = `${biasLabel(news.overall_bias)} / ${alertLabel(news.alert_level)}`;
  els.newsSummary.innerHTML = `
    <div class="summary-box">
      <strong>${news.one_line_summary}</strong>
      <ul>${news.why.map((item) => `<li>${item}</li>`).join('')}</ul>
    </div>
  `;

  els.newsArticles.innerHTML = news.articles.length
    ? news.articles
        .map(
          (article) => `
        <div class="card article-card">
          <div class="meta">
            ${pill(biasLabel(article.sentiment_score > 0.12 ? 'bullish' : article.sentiment_score < -0.12 ? 'bearish' : 'neutral'), article.sentiment_score > 0.12 ? 'bullish' : article.sentiment_score < -0.12 ? 'bearish' : 'neutral')}
            ${pill(sourceLabel(article.source))}
          </div>
          <strong>${article.headline}</strong>
          <small>${formatDate(article.published_at)}</small>
          <p>${article.summary}</p>
        </div>
      `,
        )
        .join('')
    : '<div class="card">ニュースはありません。</div>';
}

function setDemoSymbol(isBottom) {
  els.provider.value = 'demo';
  if (els.assetClass.value === 'fx') {
    els.symbol.value = isBottom ? 'BOT_USDJPY' : 'TOP_EURUSD';
  } else {
    els.symbol.value = isBottom ? 'BOT_7203' : 'TOP_9984';
  }
  setWatchlistIfUntouched(true);
  loadSnapshot();
  loadRecommendations();
}

els.loadBtn.addEventListener('click', loadSnapshot);
els.demoBotBtn.addEventListener('click', () => setDemoSymbol(true));
els.demoTopBtn.addEventListener('click', () => setDemoSymbol(false));
els.scanRecommendationsBtn.addEventListener('click', loadRecommendations);
els.saveWatchlistBtn.addEventListener('click', () => saveCurrentPreferences({ manual: true }));
els.restoreWatchlistBtn.addEventListener('click', restoreSavedWatchlist);
els.clearWatchlistBtn.addEventListener('click', clearSavedPreferences);
els.watchlistInput.addEventListener('input', () => {
  state.watchlistTouched = true;
  updateWatchlistSaveStatus('未保存の変更があります。残したい場合は「監視銘柄を保存」を押してください。');
});

els.assetClass.addEventListener('change', () => {
  if (els.assetClass.value === 'fx' && !/[A-Z]{6}|BOT_|TOP_/i.test(els.symbol.value)) {
    els.symbol.value = 'USDJPY';
  }
  if (els.assetClass.value === 'stock' && /USD|EUR|JPY/.test(els.symbol.value)) {
    els.symbol.value = '7203';
  }
  ensureProviderForAsset(els.assetClass.value);
  if (state.selectedPresetId && currentPreset()?.assetClass !== els.assetClass.value) {
    state.selectedPresetId = null;
    state.selectedPresetRole = 'pattern';
  }
  updatePresetUI();
  setWatchlistIfUntouched(true);
});

els.provider.addEventListener('change', () => {
  ensureProviderForAsset(els.assetClass.value);
  setWatchlistIfUntouched(true);
});

els.timeframe.addEventListener('change', () => {
  syncPresetRoleFromTimeframe();
});

[els.qualityFilter, els.currentOnly, els.confirmedOnly].forEach((element) => {
  element.addEventListener('change', rerenderWithCurrentFilters);
});

els.resetFilters.addEventListener('click', () => {
  els.qualityFilter.value = 'all';
  els.currentOnly.checked = false;
  els.confirmedOnly.checked = false;
  rerenderWithCurrentFilters();
});

els.presetButtons.forEach((button) => {
  button.addEventListener('click', () => applyPreset(button.dataset.preset, 'pattern', true));
});

els.roleButtons.forEach((button) => {
  button.addEventListener('click', () => switchPresetRole(button.dataset.role));
});

window.addEventListener('load', () => {
  syncFiltersFromUI();
  const restored = loadSavedPreferences();
  if (restored) {
    loadSnapshot();
    loadRecommendations();
  } else {
    applyPreset('fx_day', 'pattern', true);
  }
});

