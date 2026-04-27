from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import pandas as pd

from app.config import Settings
from app.schemas import (
    AssetClass,
    PatternTypeLiteral,
    ProviderName,
    RecommendationFailure,
    RecommendationItem,
    RecommendationsResponse,
    TradePlan,
)
from app.services.data_providers import DataProviderError, _is_jp_stock_symbol, load_bundle
from app.services.news import summarize_news
from app.services.patterns import RawPattern, detect_patterns
from app.services.scoring import score_pattern

TrendBias = Literal["up", "down", "range"]
DailyBias = Literal["near_prev_high", "near_prev_low", "above_prev_high", "below_prev_low", "mid_range"]
ActionType = Literal["buy_watch", "sell_watch", "breakout_wait", "wait"]
DirectionPref = Literal["long", "short", "neutral"]

PRESET_FRAMES: dict[str, dict[str, str]] = {
    "fx_day": {"daily": "1d", "upper": "1h", "pattern": "15m", "entry": "5m"},
    "jp_stock_day": {"daily": "1d", "upper": "1h", "pattern": "15m", "entry": "5m"},
    "swing": {"daily": "1d", "upper": "4h", "pattern": "1h", "entry": "15m"},
}


def parse_watchlist(raw: str | None, settings: Settings, asset_class: AssetClass, provider: ProviderName, preset_id: str, current_symbol: str | None = None) -> list[str]:
    items = _normalize_symbols(raw or "")
    current = (current_symbol or "").strip().upper().replace(" ", "")
    if current and current not in items:
        items.insert(0, current)
    if items:
        return items[: settings.recommendation_scan_limit]

    if provider == ProviderName.DEMO:
        source = settings.default_demo_fx_watchlist if asset_class == AssetClass.FX else settings.default_demo_stock_watchlist
    elif asset_class == AssetClass.FX or preset_id == "fx_day":
        source = settings.default_fx_watchlist
    elif preset_id in {"jp_stock_day", "swing"}:
        source = settings.default_jp_stock_watchlist
    elif current and not _is_jp_stock_symbol(current):
        source = settings.default_us_stock_watchlist
    else:
        source = settings.default_jp_stock_watchlist
    return _normalize_symbols(source)[: settings.recommendation_scan_limit]


async def build_recommendations(
    settings: Settings,
    asset_class: AssetClass,
    provider: ProviderName,
    preset_id: str,
    symbols: list[str],
) -> RecommendationsResponse:
    frames = PRESET_FRAMES.get(preset_id, PRESET_FRAMES["jp_stock_day" if asset_class == AssetClass.STOCK else "fx_day"])
    semaphore = asyncio.Semaphore(4)

    async def _wrapped(symbol: str) -> RecommendationItem | RecommendationFailure:
        async with semaphore:
            return await _scan_symbol(
                settings=settings,
                asset_class=asset_class,
                provider=provider,
                symbol=symbol,
                daily_tf=frames["daily"],
                upper_tf=frames["upper"],
                pattern_tf=frames["pattern"],
                entry_tf=frames["entry"],
            )

    gathered = await asyncio.gather(*[_wrapped(symbol) for symbol in symbols], return_exceptions=True)
    items: list[RecommendationItem] = []
    failures: list[RecommendationFailure] = []
    for result, symbol in zip(gathered, symbols):
        if isinstance(result, Exception):
            failures.append(RecommendationFailure(symbol=symbol, detail=str(result)))
        elif isinstance(result, RecommendationFailure):
            failures.append(result)
        else:
            items.append(result)

    items.sort(key=lambda item: (item.score, 1 if item.current_signal else 0, item.top_pattern_probability or 0.0), reverse=True)
    return RecommendationsResponse(
        asset_class=asset_class,
        requested_provider=provider,
        preset_id=preset_id,
        daily_timeframe=frames["daily"],
        upper_timeframe=frames["upper"],
        pattern_timeframe=frames["pattern"],
        entry_timeframe=frames["entry"],
        watchlist=symbols,
        items=items,
        failures=failures,
        generated_at=datetime.now(UTC),
    )


async def _scan_symbol(
    settings: Settings,
    asset_class: AssetClass,
    provider: ProviderName,
    symbol: str,
    daily_tf: str,
    upper_tf: str,
    pattern_tf: str,
    entry_tf: str,
) -> RecommendationItem | RecommendationFailure:
    try:
        daily_bundle, upper_bundle, pattern_bundle = await asyncio.gather(
            load_bundle(settings=settings, asset_class=asset_class, symbol=symbol, timeframe=daily_tf, provider=provider, limit=90),
            load_bundle(settings=settings, asset_class=asset_class, symbol=symbol, timeframe=upper_tf, provider=provider, limit=180),
            load_bundle(settings=settings, asset_class=asset_class, symbol=symbol, timeframe=pattern_tf, provider=provider, limit=240),
        )
    except (DataProviderError, ValueError) as exc:
        return RecommendationFailure(symbol=symbol, detail=str(exc))

    daily_df = daily_bundle.candles.copy().reset_index(drop=True)
    upper_df = upper_bundle.candles.copy().reset_index(drop=True)
    pattern_df = pattern_bundle.candles.copy().reset_index(drop=True)
    if len(daily_df) < 3 or len(upper_df) < 40 or len(pattern_df) < 40:
        return RecommendationFailure(symbol=symbol, detail="推奨判定に必要な本数が不足しています。")

    latest_close = float(pattern_df["close"].iat[-1])
    prev_day_high = float(daily_df["high"].iat[-2])
    prev_day_low = float(daily_df["low"].iat[-2])
    key_resistance = float(daily_df["high"].tail(20).max())
    key_support = float(daily_df["low"].tail(20).min())
    daily_atr = max(float(_atr(daily_df).iat[-1]), 1e-9)

    daily_bias, daily_score, daily_reasons, daily_direction = _evaluate_daily_context(
        latest_close=latest_close,
        prev_day_high=prev_day_high,
        prev_day_low=prev_day_low,
        key_resistance=key_resistance,
        key_support=key_support,
        daily_atr=daily_atr,
    )
    upper_trend, upper_score, upper_reasons = _evaluate_upper_trend(upper_df)

    scored_patterns: list[tuple[RawPattern, float, TradePlan]] = []
    for raw in detect_patterns(pattern_df, timeframe=pattern_tf, max_patterns=20):
        probability, plan = score_pattern(pattern_df, raw, asset_class=asset_class)
        scored_patterns.append((raw, probability, plan))
    scored_patterns.sort(
        key=lambda item: (1 if item[0].is_current else 0, 1 if item[0].state == "confirmed" else 0, item[1], item[0].quality_score),
        reverse=True,
    )
    current_patterns = [item for item in scored_patterns if item[0].is_current and item[0].state != "invalidated"]
    top_pattern = current_patterns[0] if current_patterns else (scored_patterns[0] if scored_patterns else None)
    pattern_score, pattern_reasons, pattern_direction = _evaluate_pattern_block(top_pattern, current_patterns)

    news_summary = summarize_news(pattern_bundle.news)
    news_score, news_reasons = _evaluate_news_block(news_summary, preferred_direction=pattern_direction or daily_direction)
    alignment_score, alignment_reasons = _evaluate_alignment(
        daily_direction=daily_direction,
        upper_trend=upper_trend,
        pattern_direction=pattern_direction,
        has_current=bool(current_patterns),
    )

    total_score = max(0.0, min(100.0, daily_score + upper_score + pattern_score + news_score + alignment_score))
    action = _decide_action(
        total_score=total_score,
        daily_direction=daily_direction,
        upper_trend=upper_trend,
        pattern_direction=pattern_direction,
        has_current=bool(current_patterns),
    )

    top_pattern_type: PatternTypeLiteral | None = None
    top_pattern_direction = None
    top_pattern_state = None
    top_pattern_quality = None
    top_pattern_probability = None
    top_trade_plan = None
    if top_pattern:
        raw, probability, plan = top_pattern
        top_pattern_type = raw.pattern_type
        top_pattern_direction = raw.direction
        top_pattern_state = raw.state
        top_pattern_quality = round(raw.quality_score, 1)
        top_pattern_probability = round(probability, 1)
        top_trade_plan = plan

    reasons = [*daily_reasons[:2], *upper_reasons[:1], *pattern_reasons[:2], *news_reasons[:1], *alignment_reasons[:1]]
    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason and reason not in deduped_reasons:
            deduped_reasons.append(reason)

    return RecommendationItem(
        symbol=symbol,
        asset_class=asset_class,
        provider=pattern_bundle.provider,
        score=round(total_score, 1),
        rank_label=_rank_label(total_score),
        action=action,
        daily_bias=daily_bias,
        upper_trend=upper_trend,
        latest_close=round(latest_close, 5),
        previous_day_high=round(prev_day_high, 5),
        previous_day_low=round(prev_day_low, 5),
        key_resistance=round(key_resistance, 5),
        key_support=round(key_support, 5),
        current_signal=bool(current_patterns),
        current_signal_count=len(current_patterns),
        daily_timeframe=daily_tf,
        upper_timeframe=upper_tf,
        pattern_timeframe=pattern_tf,
        entry_timeframe=entry_tf,
        top_pattern_type=top_pattern_type,
        top_pattern_direction=top_pattern_direction,
        top_pattern_state=top_pattern_state,
        top_pattern_quality=top_pattern_quality,
        top_pattern_probability=top_pattern_probability,
        top_trade_plan=top_trade_plan,
        summary=_build_summary(symbol, action, upper_trend, daily_bias, top_pattern_type),
        deep_reason=_build_deep_reason(
            action=action,
            daily_bias=daily_bias,
            prev_day_high=prev_day_high,
            prev_day_low=prev_day_low,
            key_resistance=key_resistance,
            key_support=key_support,
            upper_trend=upper_trend,
            upper_timeframe=upper_tf,
            pattern_timeframe=pattern_tf,
            top_pattern=top_pattern,
            news_summary=news_summary,
        ),
        reasons=deduped_reasons[:6],
    )


def _evaluate_daily_context(*, latest_close: float, prev_day_high: float, prev_day_low: float, key_resistance: float, key_support: float, daily_atr: float) -> tuple[DailyBias, float, list[str], DirectionPref]:
    near_high = (prev_day_high - latest_close) <= daily_atr * 0.45
    near_low = (latest_close - prev_day_low) <= daily_atr * 0.45
    if latest_close >= prev_day_high:
        return "above_prev_high", 24.0, [f"日足で前日高値 {prev_day_high:.3f} を上抜けています。", f"次の重要上値は {key_resistance:.3f} です。"], "long"
    if latest_close <= prev_day_low:
        return "below_prev_low", 24.0, [f"日足で前日安値 {prev_day_low:.3f} を下抜けています。", f"次の重要下値は {key_support:.3f} です。"], "short"
    if near_high:
        return "near_prev_high", 18.0, [f"日足で前日高値 {prev_day_high:.3f} が近く、上抜け監視がしやすい位置です。", f"重要上値は {key_resistance:.3f} です。"], "long"
    if near_low:
        return "near_prev_low", 18.0, [f"日足で前日安値 {prev_day_low:.3f} が近く、下抜け監視がしやすい位置です。", f"重要下値は {key_support:.3f} です。"], "short"
    return "mid_range", 10.0, [f"日足は前日高値 {prev_day_high:.3f} と前日安値 {prev_day_low:.3f} の中間にあり、ブレイク待ちです。"], "neutral"


def _evaluate_upper_trend(df: pd.DataFrame) -> tuple[TrendBias, float, list[str]]:
    close = df["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    slope = float(ema20.iat[-1] - ema20.iat[-5]) if len(ema20) >= 6 else float(ema20.iat[-1] - ema20.iat[0])
    latest = float(close.iat[-1])
    if float(ema20.iat[-1]) > float(ema50.iat[-1]) and slope > 0 and latest >= float(ema20.iat[-1]):
        return "up", 22.0, ["上位足は EMA20 が EMA50 を上回り、上向きです。"]
    if float(ema20.iat[-1]) < float(ema50.iat[-1]) and slope < 0 and latest <= float(ema20.iat[-1]):
        return "down", 22.0, ["上位足は EMA20 が EMA50 を下回り、下向きです。"]
    return "range", 12.0, ["上位足は方向感が弱く、レンジ寄りです。"]


def _evaluate_pattern_block(top_pattern: tuple[RawPattern, float, TradePlan] | None, current_patterns: list[tuple[RawPattern, float, TradePlan]]) -> tuple[float, list[str], DirectionPref]:
    if not top_pattern:
        return 6.0, ["現在ははっきりしたパターンが少なく、ブレイク待ちです。"], "neutral"
    raw, probability, plan = top_pattern
    score = raw.quality_score * 0.24 + (probability - 35.0) * 0.26
    score += 12.0 if raw.state == "confirmed" else 5.0 if raw.state == "forming" else -8.0
    if raw.is_current:
        score += 10.0
    score += min(max(plan.risk_reward_1, 0.0), 2.0) * 4.0
    score = max(5.0, min(score, 34.0))
    reasons = [f"{raw.pattern_type} が {('現在サイン' if raw.is_current else '履歴サイン')} で、形の質 {raw.quality_score:.1f} です。", f"推定優位度 {probability:.1f}% / RR1 {plan.risk_reward_1:.2f} です。"]
    if current_patterns and len(current_patterns) > 1:
        reasons.append(f"現在サインは {len(current_patterns)} 件あり、その中で最上位の形を採用しています。")
    return score, reasons, raw.direction


def _evaluate_news_block(news_summary, preferred_direction: DirectionPref) -> tuple[float, list[str]]:
    if news_summary.overall_bias == "neutral":
        return 6.0, ["ニュースは中立で、チャート判断を邪魔しにくい状態です。"]
    if preferred_direction == "long":
        return (10.0, ["ニュースも強気寄りで、買いシナリオの追い風です。"]) if news_summary.overall_bias == "bullish" else (2.0, ["ニュースは弱気寄りで、買いシナリオの重しです。"])
    if preferred_direction == "short":
        return (10.0, ["ニュースも弱気寄りで、売りシナリオの追い風です。"]) if news_summary.overall_bias == "bearish" else (2.0, ["ニュースは強気寄りで、売りシナリオの逆風です。"])
    return 5.0, ["ニュースは方向判断の補助としては中程度です。"]


def _evaluate_alignment(*, daily_direction: DirectionPref, upper_trend: TrendBias, pattern_direction: DirectionPref, has_current: bool) -> tuple[float, list[str]]:
    trend_direction: DirectionPref = "long" if upper_trend == "up" else "short" if upper_trend == "down" else "neutral"
    aligned = [direction for direction in [daily_direction, trend_direction, pattern_direction] if direction != "neutral"]
    if len(aligned) >= 2 and len(set(aligned)) == 1:
        return (18.0 if has_current else 14.0), ["日足・上位足・パターン足の方向が揃っています。"]
    if pattern_direction != "neutral" and trend_direction == pattern_direction:
        return 10.0, ["上位足とパターン足の方向が揃っています。"]
    if daily_direction != "neutral" and daily_direction == trend_direction:
        return 9.0, ["日足と上位足の方向が揃っています。"]
    return 3.0, ["方向感がやや割れているため、飛び乗りは控えめです。"]


def _decide_action(*, total_score: float, daily_direction: DirectionPref, upper_trend: TrendBias, pattern_direction: DirectionPref, has_current: bool) -> ActionType:
    preferred = pattern_direction if pattern_direction != "neutral" else daily_direction
    if total_score >= 74 and has_current:
        if preferred == "long":
            return "buy_watch"
        if preferred == "short":
            return "sell_watch"
        return "breakout_wait"
    if total_score >= 62 and preferred in {"long", "short"}:
        if has_current:
            return "buy_watch" if preferred == "long" else "sell_watch"
        return "breakout_wait"
    if upper_trend != "range" and preferred in {"long", "short"}:
        return "breakout_wait"
    return "wait"


def _rank_label(score: float) -> str:
    if score >= 82:
        return "A"
    if score >= 68:
        return "B"
    return "C"


def _build_summary(symbol: str, action: ActionType, upper_trend: TrendBias, daily_bias: DailyBias, pattern_type: PatternTypeLiteral | None) -> str:
    action_label = {"buy_watch": "買い監視", "sell_watch": "売り監視", "breakout_wait": "ブレイク待ち", "wait": "見送り"}[action]
    trend_label = {"up": "上向き", "down": "下向き", "range": "レンジ"}[upper_trend]
    daily_label = {"above_prev_high": "前日高値上抜け", "near_prev_high": "前日高値接近", "below_prev_low": "前日安値下抜け", "near_prev_low": "前日安値接近", "mid_range": "中間圏"}[daily_bias]
    pattern_name = pattern_type or "パターン待ち"
    return f"{symbol}: {action_label} / 日足 {daily_label} / 上位足 {trend_label} / 監視パターン {pattern_name}"


def _build_deep_reason(*, action: ActionType, daily_bias: DailyBias, prev_day_high: float, prev_day_low: float, key_resistance: float, key_support: float, upper_trend: TrendBias, upper_timeframe: str, pattern_timeframe: str, top_pattern: tuple[RawPattern, float, TradePlan] | None, news_summary) -> str:
    action_label = {"buy_watch": "買い監視", "sell_watch": "売り監視", "breakout_wait": "ブレイク待ち", "wait": "見送り"}[action]
    daily_text = {
        "above_prev_high": f"日足では前日高値 {prev_day_high:.3f} を上抜け、次の重要上値 {key_resistance:.3f} を意識しやすい位置です。",
        "near_prev_high": f"日足では前日高値 {prev_day_high:.3f} が近く、上抜け監視がしやすい位置です。",
        "below_prev_low": f"日足では前日安値 {prev_day_low:.3f} を下抜け、次の重要下値 {key_support:.3f} を意識しやすい位置です。",
        "near_prev_low": f"日足では前日安値 {prev_day_low:.3f} が近く、下抜け監視がしやすい位置です。",
        "mid_range": f"日足では前日高値 {prev_day_high:.3f} と前日安値 {prev_day_low:.3f} の中間で、重要ライン待ちです。",
    }[daily_bias]
    upper_text = {"up": "上向き", "down": "下向き", "range": "レンジ気味"}[upper_trend]
    if top_pattern:
        raw, probability, plan = top_pattern
        pattern_text = f"{pattern_timeframe} では {raw.pattern_type} が {('現在サイン' if raw.is_current else '履歴サイン')} で、形の質 {raw.quality_score:.1f} / 推定優位度 {probability:.1f}% です。推奨指値 {plan.suggested_limit:.3f}、TP1 {plan.target_1:.3f} が目安です。"
    else:
        pattern_text = f"{pattern_timeframe} ではまだ強い現在サインがなく、形の完成待ちです。"
    return f"{action_label}。{daily_text} {upper_timeframe} では {upper_text}。 {pattern_text} ニュースは {news_summary.one_line_summary}。"


def _normalize_symbols(raw: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for token in raw.replace("\n", ",").split(","):
        symbol = token.strip().upper().replace(" ", "")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()
