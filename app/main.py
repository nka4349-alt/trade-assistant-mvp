from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, Settings, get_settings
from app.schemas import AssetClass, ErrorResponse, ProviderName, RecommendationsResponse, SnapshotResponse
from app.services.data_providers import DataProviderError, load_bundle
from app.services.news import summarize_news
from app.services.patterns import detect_patterns, to_schema
from app.services.recommendations import build_recommendations, parse_watchlist
from app.services.scoring import score_pattern


app = FastAPI(
    title="トレード補佐ツール MVP",
    version="0.6.0",
    description="個人用の FX / 株デイトレ補佐ツール。チャートパターン、ニュース監視、日本株コード入力、時間足プリセット、注目銘柄スキャン、深掘り理由表示、監視銘柄リスト保存に対応。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = PROJECT_ROOT / "app" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/api/snapshot",
    response_model=SnapshotResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def snapshot(
    asset_class: AssetClass = Query(default=AssetClass.FX),
    symbol: str = Query(default="USDJPY"),
    timeframe: str = Query(default="5m"),
    provider: ProviderName = Query(default=ProviderName.AUTO),
    limit: int = Query(default=300, ge=80, le=1000),
    settings: Settings = Depends(get_settings),
) -> SnapshotResponse:
    if timeframe not in {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="未対応の時間足です。1m, 5m, 15m, 30m, 1h, 4h, 1d のいずれかを指定してください。")

    normalized_symbol = _normalize_symbol(asset_class=asset_class, symbol=symbol, settings=settings)

    try:
        bundle = await load_bundle(
            settings=settings,
            asset_class=asset_class,
            symbol=normalized_symbol,
            timeframe=timeframe,
            provider=provider,
            limit=limit,
        )

        candles_df = bundle.candles.copy().reset_index(drop=True)
        raw_patterns = detect_patterns(candles_df, timeframe=timeframe, max_patterns=24)
        patterns = []
        for raw in raw_patterns:
            probability, plan = score_pattern(candles_df, raw, asset_class=asset_class)
            patterns.append(to_schema(raw, probability=probability, trade_plan=plan))
        patterns.sort(
            key=lambda p: (
                1 if p.is_current else 0,
                p.signal_index,
                1 if p.state == "confirmed" else 0,
                p.probability,
                p.quality_score,
            ),
            reverse=True,
        )
        patterns = patterns[:12]

        candles = [
            {
                "time": pd.Timestamp(row.time).to_pydatetime(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume) if row.volume is not None else None,
            }
            for row in candles_df.itertuples(index=False)
        ]

        news_summary = summarize_news(bundle.news)

        return SnapshotResponse(
            asset_class=asset_class,
            provider=bundle.provider,
            symbol=normalized_symbol,
            timeframe=timeframe,
            candles=candles,
            patterns=patterns,
            news=news_summary,
            generated_at=datetime.now(UTC),
        )
    except DataProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"スナップショット生成に失敗しました: {exc}") from exc


@app.get(
    "/api/recommendations",
    response_model=RecommendationsResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def recommendations(
    asset_class: AssetClass = Query(default=AssetClass.STOCK),
    provider: ProviderName = Query(default=ProviderName.AUTO),
    preset_id: str = Query(default="jp_stock_day"),
    watchlist: str | None = Query(default=None),
    current_symbol: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> RecommendationsResponse:
    symbols = parse_watchlist(
        raw=watchlist,
        settings=settings,
        asset_class=asset_class,
        provider=provider,
        preset_id=preset_id,
        current_symbol=current_symbol,
    )
    if not symbols:
        raise HTTPException(status_code=400, detail="監視銘柄が空です。シンボルをカンマ区切りで指定してください。")

    try:
        return await build_recommendations(
            settings=settings,
            asset_class=asset_class,
            provider=provider,
            preset_id=preset_id,
            symbols=symbols,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"注目銘柄スキャンに失敗しました: {exc}") from exc


@app.get("/api/demo-symbols")
def demo_symbols() -> dict[str, list[str]]:
    return {
        "fx": ["USDJPY", "EURUSD", "BOT_USDJPY", "TOP_EURUSD"],
        "stock": ["AAPL", "7203", "6758", "BOT_7203", "TOP_9984"],
    }


def _normalize_symbol(asset_class: AssetClass, symbol: str, settings: Settings) -> str:
    value = symbol.strip().upper().replace(" ", "")
    if not value:
        return settings.default_fx_symbol if asset_class == AssetClass.FX else settings.default_stock_symbol
    if asset_class == AssetClass.FX:
        return value.replace("/", "")
    return value
