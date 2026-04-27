from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from app.config import Settings
from app.schemas import AssetClass, NewsArticle, ProviderName


TIMEFRAME_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


@dataclass(slots=True)
class ProviderBundle:
    provider: ProviderName
    candles: pd.DataFrame
    news: list[NewsArticle]


class DataProviderError(RuntimeError):
    pass


class BaseProvider:
    provider_name: ProviderName

    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_candles(
        self,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame:
        raise NotImplementedError

    async def fetch_news(self, asset_class: AssetClass, symbol: str, limit: int = 5) -> list[NewsArticle]:
        return []


class DemoProvider(BaseProvider):
    provider_name = ProviderName.DEMO

    async def fetch_candles(
        self,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame:
        minutes = TIMEFRAME_TO_MINUTES.get(timeframe, 5)
        return _generate_demo_candles(symbol=symbol, asset_class=asset_class, minutes=minutes, limit=limit)

    async def fetch_news(self, asset_class: AssetClass, symbol: str, limit: int = 5) -> list[NewsArticle]:
        now = datetime.now(UTC)
        symbol_u = symbol.upper()
        if asset_class == AssetClass.STOCK:
            base = [
                NewsArticle(
                    headline=f"{symbol_u}、次の材料待ちでも短期資金の流れは底堅い",
                    summary="短期の勢いはまだ保たれていますが、現在の上抜けが当日 VWAP の上で維持できるかを市場は見ています。",
                    source="デモ配信",
                    published_at=now - timedelta(minutes=18),
                    sentiment_score=0.25,
                ),
                NewsArticle(
                    headline=f"{symbol_u} にオプション市場の注目が集まる",
                    summary="前回セッションでは出来高が増えており、デモ配信上では強い悪材料は見当たりません。地合いは中立からやや強気です。",
                    source="デモ配信",
                    published_at=now - timedelta(minutes=7),
                    sentiment_score=0.15,
                ),
            ]
        else:
            base = [
                NewsArticle(
                    headline=f"{symbol_u}、次のマクロ材料待ち",
                    summary="通貨ペアは落ち着いたレンジ推移で、次の指標や要人発言を待つ状況です。デモ配信上では介入や急な金利ショックは確認されていません。",
                    source="デモ配信",
                    published_at=now - timedelta(minutes=21),
                    sentiment_score=0.0,
                ),
                NewsArticle(
                    headline=f"{symbol_u}、短期ポジションは強弱まちまち",
                    summary="初動のあとで勢いがやや鈍り、近いセッション高値・安値のブレイクに反応しやすい地合いです。",
                    source="デモ配信",
                    published_at=now - timedelta(minutes=8),
                    sentiment_score=-0.05,
                ),
            ]

        if "TOP" in symbol_u:
            base.insert(
                0,
                NewsArticle(
                    headline=f"{symbol_u}、悪材料が戻り売り圧力を強める可能性",
                    summary="直近ヘッドラインは弱気寄りで、価格が近いサポート帯を割ると戻り売りが強まりやすい状況です。",
                    source="デモ配信",
                    published_at=now - timedelta(minutes=3),
                    sentiment_score=-0.55,
                ),
            )
        if "BOT" in symbol_u:
            base.insert(
                0,
                NewsArticle(
                    headline=f"{symbol_u}、反発シナリオを支える地合い",
                    summary="直近コメントはやや支援的で、ネックラインを抜けたあとに買いが続けば底打ち型が機能しやすい状況です。",
                    source="デモ配信",
                    published_at=now - timedelta(minutes=4),
                    sentiment_score=0.55,
                ),
            )

        return base[:limit]


class OandaProvider(BaseProvider):
    provider_name = ProviderName.OANDA

    async def fetch_candles(
        self,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame:
        if asset_class != AssetClass.FX:
            raise DataProviderError("この MVP の OANDA 連携は FX のみ対応です。")
        if not self.settings.oanda_token:
            raise DataProviderError("環境変数 OANDA_TOKEN が未設定です。")

        instrument = _normalize_oanda_symbol(symbol)
        granularity = _oanda_granularity(timeframe)
        params = {"price": "M", "granularity": granularity, "count": min(limit, 5000)}
        headers = {"Authorization": f"Bearer {self.settings.oanda_token}"}
        url = f"{self.settings.oanda_base_url}/v3/instruments/{instrument}/candles"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        rows: list[dict[str, Any]] = []
        for candle in payload.get("candles", []):
            mid = candle.get("mid") or {}
            if not candle.get("complete", True):
                continue
            rows.append(
                {
                    "time": pd.to_datetime(candle["time"], utc=True),
                    "open": float(mid.get("o", 0.0)),
                    "high": float(mid.get("h", 0.0)),
                    "low": float(mid.get("l", 0.0)),
                    "close": float(mid.get("c", 0.0)),
                    "volume": float(candle.get("volume", 0.0)),
                }
            )

        if not rows:
            raise DataProviderError(f"OANDA から {instrument} のローソク足が返りませんでした。")

        return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)

    async def fetch_news(self, asset_class: AssetClass, symbol: str, limit: int = 5) -> list[NewsArticle]:
        return []


class AlpacaProvider(BaseProvider):
    provider_name = ProviderName.ALPACA

    async def fetch_candles(
        self,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame:
        if asset_class != AssetClass.STOCK:
            raise DataProviderError("この MVP の Alpaca 連携は株データ用です。FX は OANDA か demo を使ってください。")
        if _is_jp_stock_symbol(symbol):
            raise DataProviderError("日本株は Alpaca では取得できません。provider=auto または provider=yfinance を使ってください。")
        if not self.settings.alpaca_key_id or not self.settings.alpaca_secret_key:
            raise DataProviderError("環境変数 ALPACA_KEY_ID / ALPACA_SECRET_KEY が未設定です。")

        tf = _alpaca_timeframe(timeframe)
        end = datetime.now(UTC)
        start = end - timedelta(minutes=TIMEFRAME_TO_MINUTES.get(timeframe, 5) * max(limit, 100))
        params = {
            "symbols": symbol.upper(),
            "timeframe": tf,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "limit": min(limit, 10000),
            "adjustment": "raw",
            "feed": self.settings.alpaca_feed,
            "sort": "asc",
        }
        headers = {
            "APCA-API-KEY-ID": self.settings.alpaca_key_id,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
        }
        url = f"{self.settings.alpaca_data_url}/v2/stocks/bars"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        bars = payload.get("bars", {}).get(symbol.upper(), [])
        rows = [
            {
                "time": pd.to_datetime(bar["t"], utc=True),
                "open": float(bar["o"]),
                "high": float(bar["h"]),
                "low": float(bar["l"]),
                "close": float(bar["c"]),
                "volume": float(bar.get("v", 0.0)),
            }
            for bar in bars
        ]

        if not rows:
            raise DataProviderError(f"Alpaca から {symbol.upper()} のバーが返りませんでした。")

        return pd.DataFrame(rows).sort_values("time").tail(limit).reset_index(drop=True)

    async def fetch_news(self, asset_class: AssetClass, symbol: str, limit: int = 5) -> list[NewsArticle]:
        if not self.settings.alpaca_key_id or not self.settings.alpaca_secret_key:
            return []
        headers = {
            "APCA-API-KEY-ID": self.settings.alpaca_key_id,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
        }
        params = {
            "symbols": symbol.upper(),
            "limit": min(limit, 10),
            "sort": "desc",
            "include_content": "true",
        }
        url = f"{self.settings.alpaca_data_url}/v1beta1/news"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        articles: list[NewsArticle] = []
        for item in payload.get("news", []):
            text = (item.get("headline") or "") + " " + (item.get("summary") or "") + " " + (item.get("content") or "")
            articles.append(
                NewsArticle(
                    headline=item.get("headline", "（見出しなし）"),
                    summary=item.get("summary") or _trim_whitespace(item.get("content") or "")[:280],
                    source=item.get("source", "Alpaca"),
                    published_at=pd.to_datetime(item.get("updated_at") or item.get("created_at"), utc=True).to_pydatetime(),
                    url=item.get("url"),
                    sentiment_score=_keyword_sentiment(text),
                )
            )
        return articles


class YFinanceProvider(BaseProvider):
    provider_name = ProviderName.YFINANCE

    async def fetch_candles(
        self,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame:
        if asset_class != AssetClass.STOCK:
            raise DataProviderError("yfinance 連携は株のみ対応です。")
        return await asyncio.to_thread(_download_yfinance_candles, symbol, timeframe, limit)

    async def fetch_news(self, asset_class: AssetClass, symbol: str, limit: int = 5) -> list[NewsArticle]:
        if asset_class != AssetClass.STOCK:
            return []
        return await asyncio.to_thread(_download_yfinance_news, symbol, limit)


async def load_bundle(
    settings: Settings,
    asset_class: AssetClass,
    symbol: str,
    timeframe: str,
    provider: ProviderName,
    limit: int,
) -> ProviderBundle:
    provider_instance = _select_provider(settings=settings, asset_class=asset_class, provider=provider, symbol=symbol)
    candles = await provider_instance.fetch_candles(asset_class=asset_class, symbol=symbol, timeframe=timeframe, limit=limit)
    news = await provider_instance.fetch_news(asset_class=asset_class, symbol=symbol, limit=5)
    return ProviderBundle(provider=provider_instance.provider_name, candles=candles, news=news)


def _select_provider(settings: Settings, asset_class: AssetClass, provider: ProviderName, symbol: str) -> BaseProvider:
    if provider == ProviderName.DEMO:
        return DemoProvider(settings)
    if provider == ProviderName.OANDA:
        return OandaProvider(settings)
    if provider == ProviderName.ALPACA:
        return AlpacaProvider(settings)
    if provider == ProviderName.YFINANCE:
        return YFinanceProvider(settings)

    if _is_demo_symbol(symbol):
        return DemoProvider(settings)

    if asset_class == AssetClass.FX:
        if settings.oanda_token:
            return OandaProvider(settings)
        return DemoProvider(settings)

    if _is_jp_stock_symbol(symbol):
        return YFinanceProvider(settings)

    if settings.alpaca_key_id and settings.alpaca_secret_key:
        return AlpacaProvider(settings)
    return YFinanceProvider(settings)


def _normalize_oanda_symbol(symbol: str) -> str:
    cleaned = symbol.upper().replace("/", "_")
    if "_" in cleaned:
        return cleaned
    if len(cleaned) == 6:
        return f"{cleaned[:3]}_{cleaned[3:]}"
    return cleaned


def _oanda_granularity(timeframe: str) -> str:
    mapping = {
        "1m": "M1",
        "5m": "M5",
        "15m": "M15",
        "30m": "M30",
        "1h": "H1",
        "4h": "H4",
        "1d": "D",
    }
    return mapping.get(timeframe, "M5")


def _alpaca_timeframe(timeframe: str) -> str:
    mapping = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "30m": "30Min",
        "1h": "1Hour",
        "4h": "4Hour",
        "1d": "1Day",
    }
    return mapping.get(timeframe, "5Min")


def _is_demo_symbol(symbol: str) -> bool:
    symbol_u = symbol.upper()
    return any(flag in symbol_u for flag in ["BOT", "TOP", "DB", "TT", "BOTTOM", "TRIPLE"])


def _is_jp_stock_symbol(symbol: str) -> bool:
    value = symbol.strip().upper()
    if _is_demo_symbol(value):
        return False
    if value.endswith(".T"):
        return True
    if value.isdigit() and len(value) in {4, 5}:
        return True
    return False


def _normalize_yfinance_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.endswith(".T"):
        return value
    if value.isdigit() and len(value) in {4, 5}:
        return f"{value}.T"
    return value


def _require_yfinance():
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency at test time
        raise DataProviderError("yfinance が未インストールです。仮想環境で requirements.txt を再インストールしてください。") from exc
    return yf


def _download_yfinance_candles(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    yf = _require_yfinance()
    yf_symbol = _normalize_yfinance_symbol(symbol)
    base_interval = _yfinance_base_interval(timeframe)
    period = _yfinance_period(base_interval)

    data = yf.download(
        yf_symbol,
        period=period,
        interval=base_interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
        prepost=False,
    )
    if data is None or data.empty:
        raise DataProviderError(f"yfinance から {yf_symbol} の価格データを取得できませんでした。銘柄コードを確認してください。")

    frame = data.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [str(col[0]).lower() for col in frame.columns]
    else:
        frame.columns = [str(col).lower() for col in frame.columns]

    if "adj close" in frame.columns:
        frame = frame.drop(columns=["adj close"])
    frame = frame.loc[:, ~frame.columns.duplicated()]

    required = ["open", "high", "low", "close"]
    for column in required:
        if column not in frame.columns:
            raise DataProviderError(f"yfinance の応答に {column} 列が見つかりませんでした。")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0

    frame = frame[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.rename_axis("time").reset_index()

    if timeframe == "4h":
        frame = _aggregate_four_hour_bars(frame)

    frame = frame.sort_values("time").tail(limit).reset_index(drop=True)
    if frame.empty:
        raise DataProviderError(f"yfinance から {yf_symbol} のローソク足を整形できませんでした。")
    return frame


def _download_yfinance_news(symbol: str, limit: int) -> list[NewsArticle]:
    yf = _require_yfinance()
    yf_symbol = _normalize_yfinance_symbol(symbol)
    ticker = yf.Ticker(yf_symbol)
    try:
        raw_items = ticker.news or []
    except Exception:
        return []

    articles: list[NewsArticle] = []
    for item in raw_items[:limit]:
        title = _first_text(
            item.get("title"),
            item.get("content", {}).get("title") if isinstance(item.get("content"), dict) else None,
            "（見出しなし）",
        )
        summary = _first_text(
            item.get("summary"),
            item.get("content", {}).get("summary") if isinstance(item.get("content"), dict) else None,
            item.get("content", {}).get("description") if isinstance(item.get("content"), dict) else None,
            "要約なし",
        )
        source = _first_text(
            item.get("publisher"),
            item.get("provider"),
            item.get("content", {}).get("provider", {}).get("displayName") if isinstance(item.get("content"), dict) else None,
            "Yahoo Finance",
        )
        url = _first_text(
            item.get("link"),
            item.get("canonicalUrl", {}).get("url") if isinstance(item.get("canonicalUrl"), dict) else None,
            item.get("content", {}).get("canonicalUrl", {}).get("url") if isinstance(item.get("content"), dict) and isinstance(item.get("content", {}).get("canonicalUrl"), dict) else None,
            None,
        )
        published_raw = (
            item.get("providerPublishTime")
            or item.get("pubDate")
            or (item.get("content", {}).get("pubDate") if isinstance(item.get("content"), dict) else None)
        )
        published_at = _parse_news_datetime(published_raw)
        text = f"{title} {summary}"
        articles.append(
            NewsArticle(
                headline=title,
                summary=summary,
                source=source,
                published_at=published_at,
                url=url,
                sentiment_score=_keyword_sentiment(text),
            )
        )
    return articles


def _yfinance_base_interval(timeframe: str) -> str:
    if timeframe == "4h":
        return "1h"
    return timeframe


def _yfinance_period(base_interval: str) -> str:
    if base_interval == "1m":
        return "7d"
    if base_interval in {"5m", "15m", "30m", "1h"}:
        return "60d"
    return "max"


def _aggregate_four_hour_bars(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    work = frame.copy()
    local_times = pd.to_datetime(work["time"], utc=True).dt.tz_convert(None)
    work["session_date"] = local_times.dt.date

    aggregated: list[dict[str, Any]] = []
    for _, day_frame in work.groupby("session_date", sort=True):
        day_frame = day_frame.reset_index(drop=True)
        for start in range(0, len(day_frame), 4):
            chunk = day_frame.iloc[start : start + 4]
            if chunk.empty:
                continue
            aggregated.append(
                {
                    "time": chunk["time"].iloc[-1],
                    "open": float(chunk["open"].iloc[0]),
                    "high": float(chunk["high"].max()),
                    "low": float(chunk["low"].min()),
                    "close": float(chunk["close"].iloc[-1]),
                    "volume": float(chunk["volume"].sum()),
                }
            )

    if not aggregated:
        return frame
    return pd.DataFrame(aggregated)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_news_datetime(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if value:
        try:
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:
            pass
    return datetime.now(UTC)


def _generate_demo_candles(symbol: str, asset_class: AssetClass, minutes: int, limit: int) -> pd.DataFrame:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    times = [now - timedelta(minutes=minutes * (limit - i - 1)) for i in range(limit)]

    symbol_u = symbol.upper()
    is_bottom_demo = any(flag in symbol_u for flag in ["DB", "BOT", "BOTTOM"])
    is_top_demo = any(flag in symbol_u for flag in ["TT", "TOP", "TRIPLE"]) and not is_bottom_demo

    if asset_class == AssetClass.FX:
        base_price = 150.0 if symbol_u.startswith("USD") or symbol_u.startswith("BOT_USD") else 1.08
        precision = 3 if base_price >= 10 else 5
        scale = base_price / 100
    else:
        base_price = 180.0 if len(symbol_u) <= 5 or "AAPL" in symbol_u or "TSLA" in symbol_u else 95.0
        precision = 2
        scale = base_price / 100

    rng = random.Random(f"{symbol_u}:{asset_class.value}:{minutes}:{limit}")

    preamble_len = max(40, int(limit * 0.58))
    preamble: list[float] = []
    current = base_price * (0.985 if is_bottom_demo else 1.0)
    drift = -0.018 * scale if is_bottom_demo else 0.018 * scale if is_top_demo else 0.006 * scale
    noise = 0.05 * scale
    for i in range(preamble_len):
        cycle = math.sin(i / 6.0) * 0.025 * scale
        current = current + drift + cycle + rng.uniform(-noise, noise)
        preamble.append(current)

    pattern_levels = None
    if is_bottom_demo:
        pattern_levels = [1.00, 0.975, 0.997, 0.976, 1.006, 0.999, 1.018, 1.028]
    elif is_top_demo:
        pattern_levels = [1.00, 1.025, 1.011, 1.026, 1.012, 1.024, 0.998, 0.988]

    values = preamble.copy()
    if pattern_levels is not None:
        anchor_base = preamble[-1]
        anchor_prices = [anchor_base * level for level in pattern_levels]
        bars_left = limit - len(values)
        segment_len = max(3, bars_left // (len(anchor_prices) - 1))
        pattern_noise = 0.018 * scale
        for start_price, end_price in zip(anchor_prices[:-1], anchor_prices[1:]):
            for step in range(segment_len):
                alpha = step / segment_len
                value = start_price * (1 - alpha) + end_price * alpha + rng.uniform(-pattern_noise, pattern_noise)
                values.append(value)
        while len(values) < limit:
            continuation_drift = 0.02 * scale if is_bottom_demo else -0.02 * scale if is_top_demo else 0.004 * scale
            values.append(values[-1] + continuation_drift + rng.uniform(-pattern_noise, pattern_noise))
    else:
        while len(values) < limit:
            values.append(values[-1] + 0.004 * scale + math.sin(len(values) / 7.0) * 0.02 * scale + rng.uniform(-0.05 * scale, 0.05 * scale))

    values = values[:limit]

    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    prev_close = values[0] * (1 - 0.001)
    for idx, close in enumerate(values):
        open_ = prev_close + rng.uniform(-0.04, 0.04) * scale
        wick = abs(rng.uniform(0.035, 0.15)) * scale
        high = max(open_, close) + wick
        low = min(open_, close) - wick
        if idx > len(values) - max(12, limit // 8):
            volume = 1_000 + 500 * math.sin(idx / 3) + rng.uniform(200, 700)
        else:
            volume = 650 + 150 * math.sin(idx / 5) + rng.uniform(100, 350)
        opens.append(round(open_, precision))
        highs.append(round(high, precision))
        lows.append(round(low, precision))
        closes.append(round(close, precision))
        volumes.append(max(round(volume, 2), 1.0))
        prev_close = close

    return pd.DataFrame(
        {
            "time": pd.to_datetime(times, utc=True),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


_NEGATIVE_KEYWORDS = {
    "miss",
    "cut",
    "cuts",
    "weak",
    "warning",
    "downgrade",
    "lawsuit",
    "investigation",
    "selloff",
    "intervention",
    "hawkish",
    "geopolitical",
    "tariff",
    "delay",
    "下方修正",
    "減益",
    "急落",
    "赤字",
    "悪化",
}
_POSITIVE_KEYWORDS = {
    "beat",
    "beats",
    "raise",
    "raised",
    "upgrade",
    "growth",
    "strong",
    "partnership",
    "rebound",
    "support",
    "optimism",
    "eases",
    "cooling",
    "上方修正",
    "増益",
    "反発",
    "提携",
    "好調",
}


def _keyword_sentiment(text: str) -> float:
    text_lower = text.lower()
    score = 0.0
    for token in _POSITIVE_KEYWORDS:
        if token.lower() in text_lower:
            score += 0.2
    for token in _NEGATIVE_KEYWORDS:
        if token.lower() in text_lower:
            score -= 0.2
    return max(min(score, 1.0), -1.0)


def _trim_whitespace(value: str) -> str:
    return " ".join((value or "").split())
