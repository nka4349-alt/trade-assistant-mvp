from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    FX = "fx"
    STOCK = "stock"


class ProviderName(str, Enum):
    AUTO = "auto"
    DEMO = "demo"
    OANDA = "oanda"
    ALPACA = "alpaca"
    YFINANCE = "yfinance"


class Candle(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class PatternPoint(BaseModel):
    label: str
    kind: Literal["high", "low", "breakout", "breakdown", "retest"]
    index: int
    time: datetime
    price: float


class GuideLine(BaseModel):
    label: str
    kind: Literal["neckline", "support", "resistance", "flag", "trigger", "invalidation"]
    x0: datetime
    y0: float
    x1: datetime
    y1: float


class TradePlan(BaseModel):
    suggested_limit: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward_1: float
    risk_reward_2: float
    order_side: Literal["buy", "sell"]
    notes: list[str] = Field(default_factory=list)


PatternTypeLiteral = Literal[
    "double_bottom",
    "double_top",
    "triple_bottom",
    "triple_top",
    "head_shoulders_bottom",
    "head_shoulders_top",
    "ascending_triangle",
    "descending_triangle",
    "bull_flag",
    "bear_flag",
    "ascending_channel",
    "descending_channel",
    "rising_wedge",
    "falling_wedge",
    "bull_pennant",
    "bear_pennant",
    "saucer_bottom",
    "saucer_top",
]


class PatternSignal(BaseModel):
    id: str
    pattern_type: PatternTypeLiteral
    family: Literal["reversal", "continuation"] = "reversal"
    direction: Literal["long", "short"]
    state: Literal["forming", "confirmed", "invalidated"]
    quality_score: float
    probability: float
    neckline: float
    invalidation: float
    entry_zone: list[float]
    breakout_price: float | None = None
    trade_plan: TradePlan
    explanation: list[str] = Field(default_factory=list)
    points: list[PatternPoint] = Field(default_factory=list)
    guide_lines: list[GuideLine] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    signal_time: datetime
    signal_index: int
    is_current: bool = False
    signal_age_bars: int = 0


class NewsArticle(BaseModel):
    headline: str
    summary: str
    source: str
    published_at: datetime
    url: str | None = None
    sentiment_score: float = 0.0


class NewsSummary(BaseModel):
    overall_bias: Literal["bullish", "bearish", "neutral"]
    alert_level: Literal["none", "watch", "warning"]
    one_line_summary: str
    why: list[str] = Field(default_factory=list)
    articles: list[NewsArticle] = Field(default_factory=list)


class SnapshotResponse(BaseModel):
    asset_class: AssetClass
    provider: ProviderName
    symbol: str
    timeframe: str
    candles: list[Candle]
    patterns: list[PatternSignal]
    news: NewsSummary
    generated_at: datetime


class RecommendationFailure(BaseModel):
    symbol: str
    detail: str


class RecommendationItem(BaseModel):
    symbol: str
    asset_class: AssetClass
    provider: ProviderName
    score: float
    rank_label: Literal["A", "B", "C"]
    action: Literal["buy_watch", "sell_watch", "breakout_wait", "wait"]
    daily_bias: Literal["near_prev_high", "near_prev_low", "above_prev_high", "below_prev_low", "mid_range"]
    upper_trend: Literal["up", "down", "range"]
    latest_close: float
    previous_day_high: float
    previous_day_low: float
    key_resistance: float
    key_support: float
    current_signal: bool = False
    current_signal_count: int = 0
    daily_timeframe: str
    upper_timeframe: str
    pattern_timeframe: str
    entry_timeframe: str
    top_pattern_type: PatternTypeLiteral | None = None
    top_pattern_direction: Literal["long", "short"] | None = None
    top_pattern_state: Literal["forming", "confirmed", "invalidated"] | None = None
    top_pattern_quality: float | None = None
    top_pattern_probability: float | None = None
    top_trade_plan: TradePlan | None = None
    summary: str
    deep_reason: str
    reasons: list[str] = Field(default_factory=list)


class RecommendationsResponse(BaseModel):
    asset_class: AssetClass
    requested_provider: ProviderName
    preset_id: str
    daily_timeframe: str
    upper_timeframe: str
    pattern_timeframe: str
    entry_timeframe: str
    watchlist: list[str] = Field(default_factory=list)
    items: list[RecommendationItem] = Field(default_factory=list)
    failures: list[RecommendationFailure] = Field(default_factory=list)
    generated_at: datetime


class ErrorResponse(BaseModel):
    detail: str
