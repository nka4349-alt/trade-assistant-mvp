from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import AssetClass, ProviderName  # noqa: E402
from app.services.data_providers import _is_jp_stock_symbol, _normalize_yfinance_symbol, _select_provider  # noqa: E402
from app.services.patterns import detect_patterns  # noqa: E402


client = TestClient(app)


def test_health() -> None:
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'



def test_demo_snapshot_fx_contains_pattern() -> None:
    response = client.get(
        '/api/snapshot',
        params={
            'asset_class': 'fx',
            'symbol': 'BOT_USDJPY',
            'timeframe': '5m',
            'provider': 'demo',
            'limit': 240,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['provider'] == 'demo'
    assert len(payload['candles']) == 240
    assert any(p['pattern_type'] in {'double_bottom', 'triple_bottom'} for p in payload['patterns'])



def test_demo_snapshot_stock_contains_pattern() -> None:
    response = client.get(
        '/api/snapshot',
        params={
            'asset_class': 'stock',
            'symbol': 'TOP_9984',
            'timeframe': '5m',
            'provider': 'demo',
            'limit': 240,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['provider'] == 'demo'
    assert any(p['direction'] == 'short' for p in payload['patterns'])



def test_jp_stock_symbol_detection() -> None:
    assert _is_jp_stock_symbol('7203')
    assert _is_jp_stock_symbol('7203.T')
    assert not _is_jp_stock_symbol('AAPL')
    assert _normalize_yfinance_symbol('7203') == '7203.T'
    assert _normalize_yfinance_symbol('6758.T') == '6758.T'



def test_auto_provider_prefers_yfinance_for_jp_stock() -> None:
    settings = Settings()
    provider = _select_provider(settings=settings, asset_class=AssetClass.STOCK, provider=ProviderName.AUTO, symbol='7203')
    assert provider.provider_name == ProviderName.YFINANCE



def test_demo_snapshot_marks_current_or_recent_patterns() -> None:
    response = client.get(
        '/api/snapshot',
        params={
            'asset_class': 'fx',
            'symbol': 'BOT_USDJPY',
            'timeframe': '5m',
            'provider': 'demo',
            'limit': 240,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert any('is_current' in pattern for pattern in payload['patterns'])
    assert payload['patterns'] == sorted(
        payload['patterns'],
        key=lambda p: (
            1 if p.get('is_current') else 0,
            p.get('signal_index', 0),
            1 if p.get('state') == 'confirmed' else 0,
            p.get('probability', 0),
            p.get('quality_score', 0),
        ),
        reverse=True,
    )



def _make_candles(values: list[float], bars_per_segment: int = 6) -> pd.DataFrame:
    rows = []
    t = datetime(2026, 1, 1, tzinfo=UTC)
    for a, b in zip(values, values[1:]):
        for step in range(bars_per_segment):
            frac = (step + 1) / bars_per_segment
            close = a + (b - a) * frac
            open_ = a + (b - a) * (step / bars_per_segment)
            rows.append(
                {
                    'time': t,
                    'open': open_,
                    'high': max(open_, close) + 0.25,
                    'low': min(open_, close) - 0.25,
                    'close': close,
                    'volume': 1000.0,
                }
            )
            t += timedelta(minutes=5)
    return pd.DataFrame(rows)



def test_detects_head_shoulders_top() -> None:
    df = _make_candles([98, 110, 104, 117, 105, 110, 99, 97])
    patterns = detect_patterns(df, timeframe='1h', max_patterns=20)
    assert any(pattern.pattern_type == 'head_shoulders_top' for pattern in patterns)



def test_detects_ascending_triangle() -> None:
    df = _make_candles([95, 100, 94.5, 100.3, 96.7, 100.2, 98.8, 103])
    patterns = detect_patterns(df, timeframe='5m', max_patterns=20)
    target = next((pattern for pattern in patterns if pattern.pattern_type == 'ascending_triangle'), None)
    assert target is not None
    assert target.family == 'continuation'



def test_detects_bull_flag() -> None:
    df = _make_candles([95, 90, 110, 101, 107, 98, 104, 96, 112])
    patterns = detect_patterns(df, timeframe='5m', max_patterns=20)
    target = next((pattern for pattern in patterns if pattern.pattern_type == 'bull_flag'), None)
    assert target is not None
    assert target.direction == 'long'


def test_detects_ascending_channel() -> None:
    df = _make_candles([102, 108, 103, 111, 105, 114, 107, 117, 121])
    patterns = detect_patterns(df, timeframe='1h', max_patterns=30)
    target = next((pattern for pattern in patterns if pattern.pattern_type == 'ascending_channel'), None)
    assert target is not None
    assert target.direction == 'long'


def test_detects_falling_wedge() -> None:
    df = _make_candles([115, 105, 112, 103.5, 109, 102.8, 117])
    patterns = detect_patterns(df, timeframe='30m', max_patterns=30)
    target = next((pattern for pattern in patterns if pattern.pattern_type == 'falling_wedge'), None)
    assert target is not None
    assert target.direction == 'long'


def test_detects_bull_pennant() -> None:
    df = _make_candles([100, 118, 109, 114, 110, 113, 111, 121])
    patterns = detect_patterns(df, timeframe='5m', max_patterns=30)
    target = next((pattern for pattern in patterns if pattern.pattern_type == 'bull_pennant'), None)
    assert target is not None
    assert target.family == 'continuation'


def test_detects_saucer_bottom() -> None:
    closes = [110, 109, 108, 107, 106, 105, 104, 103, 102.5, 102, 101.8, 101.5, 101.4, 101.5, 101.8, 102.2, 102.8, 103.5, 104.3, 105.2, 106.3, 107.2, 108.3, 109.2, 110.1, 111.0, 112.0, 112.8, 113.6, 114.5, 115.3, 116.2]
    rows = []
    t = datetime(2026, 1, 1, tzinfo=UTC)
    prev = closes[0]
    for close in closes:
        rows.append({
            'time': t,
            'open': prev,
            'high': max(prev, close) + 0.2,
            'low': min(prev, close) - 0.2,
            'close': close,
            'volume': 1000.0,
        })
        prev = close
        t += timedelta(hours=1)
    df = pd.DataFrame(rows)
    patterns = detect_patterns(df, timeframe='1d', max_patterns=40)
    target = next((pattern for pattern in patterns if pattern.pattern_type == 'saucer_bottom'), None)
    assert target is not None
    assert target.family == 'reversal'


def test_demo_recommendations_stock_returns_items() -> None:
    response = client.get(
        '/api/recommendations',
        params={
            'asset_class': 'stock',
            'provider': 'demo',
            'preset_id': 'jp_stock_day',
            'watchlist': 'BOT_7203,TOP_9984,7203',
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['preset_id'] == 'jp_stock_day'
    assert payload['items']
    assert 'deep_reason' in payload['items'][0]



def test_demo_recommendations_sorted_by_score() -> None:
    response = client.get(
        '/api/recommendations',
        params={
            'asset_class': 'fx',
            'provider': 'demo',
            'preset_id': 'fx_day',
            'watchlist': 'BOT_USDJPY,TOP_EURUSD,USDJPY',
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    scores = [item['score'] for item in payload['items']]
    assert scores == sorted(scores, reverse=True)
