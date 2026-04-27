from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from app.schemas import GuideLine, PatternPoint, PatternSignal, TradePlan


PatternType = Literal[
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
PatternFamily = Literal["reversal", "continuation"]


@dataclass(slots=True)
class Pivot:
    index: int
    kind: Literal["high", "low"]
    price: float
    time: pd.Timestamp


@dataclass(slots=True)
class GuideLineSpec:
    label: str
    kind: Literal["neckline", "support", "resistance", "flag", "trigger", "invalidation"]
    x0: pd.Timestamp
    y0: float
    x1: pd.Timestamp
    y1: float


@dataclass(slots=True)
class RawPattern:
    pattern_type: PatternType
    family: PatternFamily
    direction: Literal["long", "short"]
    state: Literal["forming", "confirmed", "invalidated"]
    quality_score: float
    neckline: float
    invalidation: float
    breakout_price: float | None
    entry_zone: tuple[float, float]
    points: list[Pivot]
    breakout_index: int | None
    breakout_time: pd.Timestamp | None
    signal_index: int
    signal_time: pd.Timestamp
    targets: tuple[float, float]
    reasoning: list[str]
    point_labels: list[str] = field(default_factory=list)
    guide_lines: list[GuideLineSpec] = field(default_factory=list)
    is_current: bool = False
    signal_age_bars: int = 0


def detect_patterns(df: pd.DataFrame, timeframe: str | None = None, max_patterns: int = 24) -> list[RawPattern]:
    if len(df) < 30:
        return []

    work = df.copy().reset_index(drop=True)
    work["atr"] = _atr(work)
    pivots = _find_pivots(work)

    patterns: list[RawPattern] = []
    patterns.extend(_scan_saucer_patterns(work, bottom=True))
    patterns.extend(_scan_saucer_patterns(work, bottom=False))
    if len(pivots) >= 3:
        patterns.extend(_scan_double_patterns(work, pivots, bottom=True))
        patterns.extend(_scan_double_patterns(work, pivots, bottom=False))
    if len(pivots) >= 4:
        patterns.extend(_scan_channel_patterns(work, pivots, ascending=True))
        patterns.extend(_scan_channel_patterns(work, pivots, ascending=False))
        patterns.extend(_scan_wedge_patterns(work, pivots, rising=True))
        patterns.extend(_scan_wedge_patterns(work, pivots, rising=False))
        patterns.extend(_scan_pennant_patterns(work, pivots, bullish=True))
        patterns.extend(_scan_pennant_patterns(work, pivots, bullish=False))
    if len(pivots) >= 5:
        patterns.extend(_scan_triple_patterns(work, pivots, bottom=True))
        patterns.extend(_scan_triple_patterns(work, pivots, bottom=False))
        patterns.extend(_scan_head_shoulders_patterns(work, pivots, bottom=True))
        patterns.extend(_scan_head_shoulders_patterns(work, pivots, bottom=False))
        patterns.extend(_scan_triangle_patterns(work, pivots, ascending=True))
        patterns.extend(_scan_triangle_patterns(work, pivots, ascending=False))
        patterns.extend(_scan_flag_patterns(work, pivots, bullish=True))
        patterns.extend(_scan_flag_patterns(work, pivots, bullish=False))

    deduped = _dedupe_patterns(patterns)
    for pattern in deduped:
        pattern.signal_age_bars = max(0, len(work) - 1 - pattern.signal_index)
        pattern.is_current = _is_current_pattern(pattern, timeframe=timeframe)
    deduped.sort(key=lambda p: _ranking_key(p, timeframe), reverse=True)
    return deduped[:max_patterns] if max_patterns else deduped


def to_schema(pattern: RawPattern, probability: float, trade_plan: TradePlan) -> PatternSignal:
    high_count = 0
    low_count = 0
    point_models: list[PatternPoint] = []
    for idx, pivot in enumerate(pattern.points):
        if idx < len(pattern.point_labels):
            label = pattern.point_labels[idx]
        else:
            if pivot.kind == "high":
                high_count += 1
                label = f"高値{high_count}"
            else:
                low_count += 1
                label = f"安値{low_count}"
        point_models.append(
            PatternPoint(
                label=label,
                kind=pivot.kind,
                index=pivot.index,
                time=pivot.time.to_pydatetime(),
                price=round(pivot.price, 5),
            )
        )
    if pattern.breakout_index is not None:
        point_models.append(
            PatternPoint(
                label="上抜け" if pattern.direction == "long" else "下抜け",
                kind="breakout" if pattern.direction == "long" else "breakdown",
                index=pattern.breakout_index,
                time=(pattern.breakout_time or pattern.points[-1].time).to_pydatetime(),
                price=round(pattern.breakout_price or pattern.neckline, 5),
            )
        )

    return PatternSignal(
        id=f"sig_{uuid.uuid4().hex[:10]}",
        pattern_type=pattern.pattern_type,
        family=pattern.family,
        direction=pattern.direction,
        state=pattern.state,
        quality_score=round(pattern.quality_score, 1),
        probability=round(probability, 1),
        neckline=round(pattern.neckline, 5),
        invalidation=round(pattern.invalidation, 5),
        breakout_price=round(pattern.breakout_price, 5) if pattern.breakout_price is not None else None,
        entry_zone=[round(pattern.entry_zone[0], 5), round(pattern.entry_zone[1], 5)],
        trade_plan=trade_plan,
        explanation=pattern.reasoning,
        points=point_models,
        guide_lines=[
            GuideLine(
                label=line.label,
                kind=line.kind,
                x0=line.x0.to_pydatetime(),
                y0=round(line.y0, 5),
                x1=line.x1.to_pydatetime(),
                y1=round(line.y1, 5),
            )
            for line in pattern.guide_lines
        ],
        started_at=pattern.points[0].time.to_pydatetime(),
        completed_at=(pattern.breakout_time or pattern.points[-1].time).to_pydatetime(),
        signal_time=pattern.signal_time.to_pydatetime(),
        signal_index=pattern.signal_index,
        is_current=pattern.is_current,
        signal_age_bars=pattern.signal_age_bars,
    )


def _ranking_key(pattern: RawPattern, timeframe: str | None) -> tuple[int, int, int, float, float]:
    return (
        1 if pattern.is_current else 0,
        pattern.signal_index,
        _state_rank(pattern.state),
        pattern.quality_score + _timeframe_weight(pattern.pattern_type, timeframe),
        pattern.neckline,
    )


def _is_current_pattern(pattern: RawPattern, timeframe: str | None) -> bool:
    if pattern.state == "invalidated":
        return False
    age_limit = _current_window_bars(timeframe)
    return pattern.signal_age_bars <= age_limit


def _current_window_bars(timeframe: str | None) -> int:
    mapping = {
        "1m": 18,
        "5m": 14,
        "15m": 10,
        "30m": 8,
        "1h": 6,
        "4h": 4,
        "1d": 3,
    }
    return mapping.get(timeframe or "", 6)


def _state_rank(state: str) -> int:
    if state == "confirmed":
        return 3
    if state == "forming":
        return 2
    return 1


def _timeframe_weight(pattern_type: PatternType, timeframe: str | None) -> float:
    short_bias = {
        "double_bottom": 5.0,
        "double_top": 5.0,
        "ascending_triangle": 7.0,
        "descending_triangle": 7.0,
        "bull_flag": 8.0,
        "bear_flag": 8.0,
        "ascending_channel": 6.0,
        "descending_channel": 6.0,
        "rising_wedge": 7.0,
        "falling_wedge": 7.0,
        "bull_pennant": 8.0,
        "bear_pennant": 8.0,
    }
    long_bias = {
        "triple_bottom": 7.0,
        "triple_top": 7.0,
        "head_shoulders_bottom": 9.0,
        "head_shoulders_top": 9.0,
        "saucer_bottom": 9.0,
        "saucer_top": 9.0,
    }
    if timeframe in {"1m", "5m", "15m", "30m"}:
        return short_bias.get(pattern_type, 0.0)
    if timeframe in {"4h", "1d"}:
        return long_bias.get(pattern_type, 0.0)
    return 2.5


def _find_pivots(df: pd.DataFrame, window: int = 3) -> list[Pivot]:
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    atr = df["atr"].bfill().ffill().to_numpy()
    raw: list[Pivot] = []
    for i in range(window, len(df) - window):
        high_slice = highs[i - window : i + window + 1]
        low_slice = lows[i - window : i + window + 1]
        is_high = highs[i] == high_slice.max() and highs[i] > np.median(high_slice)
        is_low = lows[i] == low_slice.min() and lows[i] < np.median(low_slice)
        if is_high == is_low:
            continue
        if raw:
            min_move = max(atr[i] * 0.45, df["close"].iat[i] * 0.0015)
            if abs((highs[i] if is_high else lows[i]) - raw[-1].price) < min_move:
                continue
        raw.append(
            Pivot(
                index=i,
                kind="high" if is_high else "low",
                price=float(highs[i] if is_high else lows[i]),
                time=pd.Timestamp(df["time"].iat[i]),
            )
        )

    if not raw:
        return []

    filtered: list[Pivot] = [raw[0]]
    for pivot in raw[1:]:
        prev = filtered[-1]
        if pivot.kind == prev.kind:
            if pivot.kind == "high" and pivot.price > prev.price:
                filtered[-1] = pivot
            elif pivot.kind == "low" and pivot.price < prev.price:
                filtered[-1] = pivot
            continue
        filtered.append(pivot)
    return filtered


def _scan_double_patterns(df: pd.DataFrame, pivots: list[Pivot], bottom: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    pattern_type: PatternType = "double_bottom" if bottom else "double_top"
    direction: Literal["long", "short"] = "long" if bottom else "short"
    for i in range(len(pivots) - 2):
        p1, p2, p3 = pivots[i : i + 3]
        expected = ["low", "high", "low"] if bottom else ["high", "low", "high"]
        if [p1.kind, p2.kind, p3.kind] != expected:
            continue
        pattern = _build_double_pattern(df, p1, p2, p3, pattern_type, direction, bottom)
        if pattern:
            results.append(pattern)
    return results


def _scan_triple_patterns(df: pd.DataFrame, pivots: list[Pivot], bottom: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    pattern_type: PatternType = "triple_bottom" if bottom else "triple_top"
    direction: Literal["long", "short"] = "long" if bottom else "short"
    for i in range(len(pivots) - 4):
        seq = pivots[i : i + 5]
        expected = ["low", "high", "low", "high", "low"] if bottom else ["high", "low", "high", "low", "high"]
        if [pivot.kind for pivot in seq] != expected:
            continue
        pattern = _build_triple_pattern(df, seq, pattern_type, direction, bottom)
        if pattern:
            results.append(pattern)
    return results


def _scan_head_shoulders_patterns(df: pd.DataFrame, pivots: list[Pivot], bottom: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    expected = ["low", "high", "low", "high", "low"] if bottom else ["high", "low", "high", "low", "high"]
    pattern_type: PatternType = "head_shoulders_bottom" if bottom else "head_shoulders_top"
    direction: Literal["long", "short"] = "long" if bottom else "short"
    for i in range(len(pivots) - 4):
        seq = pivots[i : i + 5]
        if [pivot.kind for pivot in seq] != expected:
            continue
        pattern = _build_head_shoulders_pattern(df, seq, pattern_type, direction, bottom)
        if pattern:
            results.append(pattern)
    return results


def _scan_triangle_patterns(df: pd.DataFrame, pivots: list[Pivot], ascending: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    expected = ["high", "low", "high", "low", "high"] if ascending else ["low", "high", "low", "high", "low"]
    pattern_type: PatternType = "ascending_triangle" if ascending else "descending_triangle"
    direction: Literal["long", "short"] = "long" if ascending else "short"
    for i in range(len(pivots) - 4):
        seq = pivots[i : i + 5]
        if [pivot.kind for pivot in seq] != expected:
            continue
        pattern = _build_triangle_pattern(df, seq, pattern_type, direction, ascending)
        if pattern:
            results.append(pattern)
    return results


def _scan_flag_patterns(df: pd.DataFrame, pivots: list[Pivot], bullish: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    expected = ["low", "high", "low", "high", "low"] if bullish else ["high", "low", "high", "low", "high"]
    pattern_type: PatternType = "bull_flag" if bullish else "bear_flag"
    direction: Literal["long", "short"] = "long" if bullish else "short"
    for i in range(len(pivots) - 4):
        seq = pivots[i : i + 5]
        if [pivot.kind for pivot in seq] != expected:
            continue
        pattern = _build_flag_pattern(df, seq, pattern_type, direction, bullish)
        if pattern:
            results.append(pattern)
    return results


def _scan_channel_patterns(df: pd.DataFrame, pivots: list[Pivot], ascending: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    pattern_type: PatternType = "ascending_channel" if ascending else "descending_channel"
    direction: Literal["long", "short"] = "long" if ascending else "short"
    seen: set[tuple[int, int]] = set()
    for window in (4, 5, 6):
        for i in range(len(pivots) - window + 1):
            seq = pivots[i : i + window]
            if not _alternating_pivots(seq):
                continue
            pattern = _build_channel_pattern(df, seq, pattern_type, direction, ascending)
            if pattern:
                key = (pattern.points[0].index, pattern.points[-1].index)
                if key in seen:
                    continue
                seen.add(key)
                results.append(pattern)
    return results

def _scan_wedge_patterns(df: pd.DataFrame, pivots: list[Pivot], rising: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    pattern_type: PatternType = "rising_wedge" if rising else "falling_wedge"
    direction: Literal["long", "short"] = "short" if rising else "long"
    seen: set[tuple[int, int]] = set()
    for window in (4, 5, 6):
        for i in range(len(pivots) - window + 1):
            seq = pivots[i : i + window]
            if not _alternating_pivots(seq):
                continue
            pattern = _build_wedge_pattern(df, seq, pattern_type, direction, rising)
            if pattern:
                key = (pattern.points[0].index, pattern.points[-1].index)
                if key in seen:
                    continue
                seen.add(key)
                results.append(pattern)
    return results

def _scan_pennant_patterns(df: pd.DataFrame, pivots: list[Pivot], bullish: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    pattern_type: PatternType = "bull_pennant" if bullish else "bear_pennant"
    direction: Literal["long", "short"] = "long" if bullish else "short"
    seen: set[tuple[int, int]] = set()
    for window in (4, 5, 6):
        for i in range(len(pivots) - window + 1):
            seq = pivots[i : i + window]
            if not _alternating_pivots(seq):
                continue
            pattern = _build_pennant_pattern(df, seq, pattern_type, direction, bullish)
            if pattern:
                key = (pattern.points[0].index, pattern.points[-1].index)
                if key in seen:
                    continue
                seen.add(key)
                results.append(pattern)
    return results

def _scan_saucer_patterns(df: pd.DataFrame, bottom: bool) -> list[RawPattern]:
    results: list[RawPattern] = []
    if len(df) < 24:
        return results
    lengths = [length for length in (20, 24, 36, 48, 64, 80) if length <= len(df)]
    seen: set[tuple[int, int, str]] = set()
    for length in lengths:
        step = max(4, length // 8)
        ends = list(range(length - 1, len(df), step))
        if ends[-1] != len(df) - 1:
            ends.append(len(df) - 1)
        for end in ends:
            start = end - length + 1
            key = (start, end, "bottom" if bottom else "top")
            if key in seen:
                continue
            seen.add(key)
            pattern = _build_saucer_pattern(df, start, end, bottom=bottom)
            if pattern:
                results.append(pattern)
    return results


def _build_double_pattern(
    df: pd.DataFrame,
    p1: Pivot,
    p2: Pivot,
    p3: Pivot,
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    bottom: bool,
) -> RawPattern | None:
    atr = _local_atr(df, p1.index, p3.index)
    reference = statistics.mean([p1.price, p3.price])
    tolerance = max(atr * 1.2, abs(reference) * 0.003)
    level_distance = abs(p1.price - p3.price)
    if level_distance > tolerance:
        return None

    span = p3.index - p1.index
    if span < 8 or span > max(90, len(df) // 2):
        return None

    bounce = p2.price - min(p1.price, p3.price) if bottom else max(p1.price, p3.price) - p2.price
    if bounce < atr * 1.4:
        return None

    neckline = p2.price
    breakout_index, breakout_price = _breakout(df, start=p3.index + 1, neckline=neckline, direction=direction)
    invalidation = min(p1.price, p3.price) - atr * 0.25 if bottom else max(p1.price, p3.price) + atr * 0.25
    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    height = neckline - statistics.mean([p1.price, p3.price]) if bottom else statistics.mean([p1.price, p3.price]) - neckline
    targets = _targets(neckline=neckline, height=height, direction=direction)
    similarity = max(0.0, 1.0 - level_distance / tolerance)
    impulse = min(1.0, bounce / (atr * 2.8))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.8) + 0.55)
    quality = 100.0 * (0.5 * similarity + 0.3 * impulse + 0.2 * breakout_strength)

    reasoning = [
        f"2点の価格差は許容内 ({level_distance:.3f} <= {tolerance:.3f})",
        f"反発/反落幅は {bounce / atr:.2f} ATR",
    ]
    reasoning.append(_state_reasoning(state))

    signal_index = breakout_index if breakout_index is not None else p3.index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="reversal",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=[p1, p2, p3],
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=["安値1", "ネック", "安値2"] if bottom else ["高値1", "ネック", "高値2"],
        guide_lines=[
            GuideLineSpec("ネックライン", "neckline", p1.time, neckline, df["time"].iat[-1], neckline),
            GuideLineSpec("無効化", "invalidation", p1.time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )


def _build_triple_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    bottom: bool,
) -> RawPattern | None:
    lows_or_highs = [seq[0].price, seq[2].price, seq[4].price]
    mid_levels = [seq[1].price, seq[3].price]
    atr = _local_atr(df, seq[0].index, seq[4].index)
    reference = statistics.mean(lows_or_highs)
    tolerance = max(atr * 1.35, abs(reference) * 0.0035)
    spread = max(lows_or_highs) - min(lows_or_highs)
    if spread > tolerance:
        return None

    mid_tolerance = max(atr * 0.9, abs(statistics.mean(mid_levels)) * 0.0025)
    mid_spread = abs(mid_levels[0] - mid_levels[1])
    if mid_spread > mid_tolerance:
        return None

    span = seq[4].index - seq[0].index
    if span < 14 or span > max(120, len(df) * 0.7):
        return None

    bounce = statistics.mean(mid_levels) - min(lows_or_highs) if bottom else max(lows_or_highs) - statistics.mean(mid_levels)
    if bounce < atr * 1.7:
        return None

    neckline = statistics.mean(mid_levels)
    breakout_index, breakout_price = _breakout(df, start=seq[4].index + 1, neckline=neckline, direction=direction)
    invalidation = min(lows_or_highs) - atr * 0.25 if bottom else max(lows_or_highs) + atr * 0.25
    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    height = neckline - statistics.mean(lows_or_highs) if bottom else statistics.mean(lows_or_highs) - neckline
    targets = _targets(neckline=neckline, height=height, direction=direction)
    similarity = max(0.0, 1.0 - spread / tolerance)
    neckline_cohesion = max(0.0, 1.0 - mid_spread / mid_tolerance)
    impulse = min(1.0, bounce / (atr * 3.2))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.8) + 0.55)
    quality = 100.0 * (0.35 * similarity + 0.2 * neckline_cohesion + 0.25 * impulse + 0.2 * breakout_strength)

    reasoning = [
        f"3点の価格差は許容内 ({spread:.3f} <= {tolerance:.3f})",
        f"ネック候補のズレも小さい ({mid_spread:.3f} <= {mid_tolerance:.3f})",
        f"反発/反落幅は {bounce / atr:.2f} ATR",
        _state_reasoning(state),
    ]

    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="reversal",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=["安値1", "ネック1", "安値2", "ネック2", "安値3"] if bottom else ["高値1", "ネック1", "高値2", "ネック2", "高値3"],
        guide_lines=[
            GuideLineSpec("ネックライン", "neckline", seq[0].time, neckline, df["time"].iat[-1], neckline),
            GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )


def _build_head_shoulders_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    bottom: bool,
) -> RawPattern | None:
    atr = _local_atr(df, seq[0].index, seq[4].index)
    shoulders = [seq[0].price, seq[4].price]
    head = seq[2].price
    shoulder_ref = statistics.mean(shoulders)
    shoulder_tol = max(atr * 1.2, abs(shoulder_ref) * 0.004)
    if abs(shoulders[0] - shoulders[1]) > shoulder_tol:
        return None

    head_move = (min(shoulders) - head) if bottom else (head - max(shoulders))
    if head_move < atr * 0.9:
        return None

    span = seq[4].index - seq[0].index
    if span < 14 or span > max(130, len(df) * 0.75):
        return None

    neck_a, neck_b = seq[1], seq[3]
    neckline_avg = statistics.mean([neck_a.price, neck_b.price])
    breakout_index, breakout_price = _breakout_line(
        df,
        start=seq[4].index + 1,
        direction=direction,
        i0=neck_a.index,
        y0=neck_a.price,
        i1=neck_b.index,
        y1=neck_b.price,
    )
    invalidation = max(shoulders) + atr * 0.25 if not bottom else min(shoulders) - atr * 0.25
    state = _resolve_state(df, direction, invalidation, breakout_index)
    neckline_now = _line_value(neck_a.index, neck_a.price, neck_b.index, neck_b.price, seq[4].index)
    entry_zone = _entry_zone(neckline=neckline_now, atr=atr, direction=direction)
    height = (neckline_avg - head) if bottom else (head - neckline_avg)
    targets = _targets(neckline=neckline_avg, height=height, direction=direction)
    shoulder_similarity = max(0.0, 1.0 - abs(shoulders[0] - shoulders[1]) / shoulder_tol)
    prominence = min(1.0, head_move / (atr * 2.0))
    neckline_balance = max(0.0, 1.0 - abs(neck_a.price - neck_b.price) / max(atr * 1.4, abs(neckline_avg) * 0.005))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline_avg) - neckline_avg) / (atr * 0.9) + 0.55)
    quality = 100.0 * (0.3 * shoulder_similarity + 0.3 * prominence + 0.15 * neckline_balance + 0.25 * breakout_strength)

    reasoning = [
        f"左右の肩は近い ({abs(shoulders[0]-shoulders[1]):.3f} <= {shoulder_tol:.3f})",
        f"ヘッドの突出は {head_move / atr:.2f} ATR",
        f"ネックラインの傾き差は {abs(neck_a.price-neck_b.price):.3f}",
        _state_reasoning(state),
    ]

    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    labels = ["左肩", "谷1", "ヘッド", "谷2", "右肩"] if not bottom else ["左肩", "山1", "ヘッド", "山2", "右肩"]
    return RawPattern(
        pattern_type=pattern_type,
        family="reversal",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline_avg,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=labels,
        guide_lines=[
            GuideLineSpec("ネックライン", "neckline", neck_a.time, neck_a.price, neck_b.time, neck_b.price),
            GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )


def _build_triangle_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    ascending: bool,
) -> RawPattern | None:
    atr = _local_atr(df, seq[0].index, seq[4].index)
    span = seq[4].index - seq[0].index
    if span < 12 or span > max(140, len(df) * 0.8):
        return None

    if ascending:
        highs = [seq[0].price, seq[2].price, seq[4].price]
        lows = [seq[1].price, seq[3].price]
        resistance = statistics.mean(highs)
        tol = max(atr * 1.2, abs(resistance) * 0.0035)
        if max(highs) - min(highs) > tol:
            return None
        if lows[1] <= lows[0] + atr * 0.2:
            return None
        breakout_index, breakout_price = _breakout(df, start=seq[4].index + 1, neckline=resistance, direction=direction)
        invalidation = lows[-1] - atr * 0.25
        height = resistance - statistics.mean(lows)
        rising_strength = (lows[1] - lows[0]) / max(atr, 1e-9)
        guide_lines = [
            GuideLineSpec("上値抵抗", "resistance", seq[0].time, resistance, df["time"].iat[-1], resistance),
            GuideLineSpec("下値支持", "support", seq[1].time, seq[1].price, seq[3].time, seq[3].price),
        ]
        reasoning = [
            f"高値群は横ばい ({max(highs)-min(highs):.3f} <= {tol:.3f})",
            f"安値は切り上がり ({rising_strength:.2f} ATR)",
        ]
    else:
        lows = [seq[0].price, seq[2].price, seq[4].price]
        highs = [seq[1].price, seq[3].price]
        support = statistics.mean(lows)
        tol = max(atr * 1.2, abs(support) * 0.0035)
        if max(lows) - min(lows) > tol:
            return None
        if highs[1] >= highs[0] - atr * 0.2:
            return None
        breakout_index, breakout_price = _breakout(df, start=seq[4].index + 1, neckline=support, direction=direction)
        invalidation = highs[-1] + atr * 0.25
        height = statistics.mean(highs) - support
        rising_strength = (highs[0] - highs[1]) / max(atr, 1e-9)
        guide_lines = [
            GuideLineSpec("下値支持", "support", seq[0].time, support, df["time"].iat[-1], support),
            GuideLineSpec("上値抵抗", "resistance", seq[1].time, seq[1].price, seq[3].time, seq[3].price),
        ]
        reasoning = [
            f"安値群は横ばい ({max(lows)-min(lows):.3f} <= {tol:.3f})",
            f"高値は切り下がり ({rising_strength:.2f} ATR)",
        ]

    state = _resolve_state(df, direction, invalidation, breakout_index)
    neckline = statistics.mean([line.y0 for line in guide_lines if line.kind in {"support", "resistance"}])
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    targets = _targets(neckline=neckline, height=max(height, atr * 0.8), direction=direction)
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.85) + 0.55)
    compression = min(1.0, span / 60)
    quality = 100.0 * (0.35 * breakout_strength + 0.3 * compression + 0.35 * min(1.0, rising_strength / 2.0))
    reasoning.append(_state_reasoning(state))
    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="continuation",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=["高値1", "安値1", "高値2", "安値2", "高値3"] if ascending else ["安値1", "高値1", "安値2", "高値2", "安値3"],
        guide_lines=guide_lines + [GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation)],
    )


def _build_flag_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    bullish: bool,
) -> RawPattern | None:
    atr = _local_atr(df, seq[0].index, seq[4].index)
    span = seq[4].index - seq[0].index
    if span < 10 or span > max(100, len(df) * 0.65):
        return None

    if bullish:
        pole = seq[1].price - seq[0].price
        if pole < atr * 2.4:
            return None
        if not (seq[3].price < seq[1].price and seq[4].price < seq[2].price):
            return None
        if seq[4].price <= seq[0].price + pole * 0.15:
            return None
        upper = (seq[1], seq[3])
        lower = (seq[2], seq[4])
        breakout_index, breakout_price = _breakout_line(df, start=seq[4].index + 1, direction=direction, i0=upper[0].index, y0=upper[0].price, i1=upper[1].index, y1=upper[1].price)
        invalidation = _line_value(lower[0].index, lower[0].price, lower[1].index, lower[1].price, seq[4].index) - atr * 0.25
        retrace = seq[1].price - seq[4].price
        if retrace > pole * 0.65:
            return None
        slope_quality = max(0.0, 1.0 - abs((upper[1].price - upper[0].price) - (lower[1].price - lower[0].price)) / max(atr * 1.5, 1e-9))
        guide_lines = [
            GuideLineSpec("上辺", "resistance", upper[0].time, upper[0].price, upper[1].time, upper[1].price),
            GuideLineSpec("下辺", "support", lower[0].time, lower[0].price, lower[1].time, lower[1].price),
            GuideLineSpec("ポール", "flag", seq[0].time, seq[0].price, seq[1].time, seq[1].price),
        ]
        height = pole
        reasoning = [
            f"上昇ポールは {pole / atr:.2f} ATR",
            f"押し幅はポールの {retrace / max(pole, 1e-9) * 100:.1f}%",
        ]
        neckline = _line_value(upper[0].index, upper[0].price, upper[1].index, upper[1].price, seq[4].index)
    else:
        pole = seq[0].price - seq[1].price
        if pole < atr * 2.4:
            return None
        if not (seq[3].price > seq[1].price and seq[4].price > seq[2].price):
            return None
        if seq[4].price >= seq[0].price - pole * 0.15:
            return None
        lower = (seq[1], seq[3])
        upper = (seq[2], seq[4])
        breakout_index, breakout_price = _breakout_line(df, start=seq[4].index + 1, direction=direction, i0=lower[0].index, y0=lower[0].price, i1=lower[1].index, y1=lower[1].price)
        invalidation = _line_value(upper[0].index, upper[0].price, upper[1].index, upper[1].price, seq[4].index) + atr * 0.25
        retrace = seq[4].price - seq[1].price
        if retrace > pole * 0.65:
            return None
        slope_quality = max(0.0, 1.0 - abs((upper[1].price - upper[0].price) - (lower[1].price - lower[0].price)) / max(atr * 1.5, 1e-9))
        guide_lines = [
            GuideLineSpec("上辺", "resistance", upper[0].time, upper[0].price, upper[1].time, upper[1].price),
            GuideLineSpec("下辺", "support", lower[0].time, lower[0].price, lower[1].time, lower[1].price),
            GuideLineSpec("ポール", "flag", seq[0].time, seq[0].price, seq[1].time, seq[1].price),
        ]
        height = pole
        reasoning = [
            f"下降ポールは {pole / atr:.2f} ATR",
            f"戻り幅はポールの {retrace / max(pole, 1e-9) * 100:.1f}%",
        ]
        neckline = _line_value(lower[0].index, lower[0].price, lower[1].index, lower[1].price, seq[4].index)

    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    targets = _targets(neckline=neckline, height=max(height * 0.75, atr * 1.2), direction=direction)
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.8) + 0.55)
    orderly_pullback = slope_quality
    quality = 100.0 * (0.35 * breakout_strength + 0.35 * orderly_pullback + 0.3 * min(1.0, pole / (atr * 3.6)))
    reasoning.append(_state_reasoning(state))
    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="continuation",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=["起点", "ポール高値", "押し安値", "戻り高値", "最終安値"] if bullish else ["起点", "ポール安値", "戻り高値", "戻り安値", "最終高値"],
        guide_lines=guide_lines + [GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation)],
    )


def _build_channel_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    ascending: bool,
) -> RawPattern | None:
    highs = [pivot for pivot in seq if pivot.kind == "high"]
    lows = [pivot for pivot in seq if pivot.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return None

    atr = _local_atr(df, seq[0].index, seq[-1].index)
    span = seq[-1].index - seq[0].index
    if span < 12 or span > max(180, len(df) * 0.85):
        return None

    if ascending:
        if not (_strictly_monotonic([p.price for p in highs], increasing=True) and _strictly_monotonic([p.price for p in lows], increasing=True)):
            return None
    else:
        if not (_strictly_monotonic([p.price for p in highs], increasing=False) and _strictly_monotonic([p.price for p in lows], increasing=False)):
            return None

    support_slope = _slope(lows[0], lows[-1])
    resistance_slope = _slope(highs[0], highs[-1])
    if ascending and (support_slope <= 0 or resistance_slope <= 0):
        return None
    if not ascending and (support_slope >= 0 or resistance_slope >= 0):
        return None

    overlap_start = max(highs[0].index, lows[0].index)
    overlap_end = min(highs[-1].index, lows[-1].index)
    if overlap_end <= overlap_start:
        return None
    width_start = abs(
        _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, overlap_start)
        - _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, overlap_start)
    )
    width_end = abs(
        _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, overlap_end)
        - _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, overlap_end)
    )
    avg_width = statistics.mean([width_start, width_end])
    if avg_width < atr * 0.9:
        return None

    slope_delta = abs((support_slope - resistance_slope) * span)
    if slope_delta > max(atr * 1.8, avg_width * 0.5):
        return None

    if ascending:
        breakout_index, breakout_price = _breakout_line(df, start=seq[-1].index + 1, direction=direction, i0=highs[0].index, y0=highs[0].price, i1=highs[-1].index, y1=highs[-1].price)
        neckline = _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, seq[-1].index)
        invalidation = _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, seq[-1].index) - atr * 0.25
        direction_ratio = min(1.0, (lows[-1].price - lows[0].price) / max(atr * 4.5, 1e-9))
    else:
        breakout_index, breakout_price = _breakout_line(df, start=seq[-1].index + 1, direction=direction, i0=lows[0].index, y0=lows[0].price, i1=lows[-1].index, y1=lows[-1].price)
        neckline = _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, seq[-1].index)
        invalidation = _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, seq[-1].index) + atr * 0.25
        direction_ratio = min(1.0, (highs[0].price - highs[-1].price) / max(atr * 4.5, 1e-9))

    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    targets = _targets(neckline=neckline, height=max(avg_width, atr * 1.0), direction=direction)
    parallel_quality = max(0.0, 1.0 - slope_delta / max(atr * 1.8, avg_width * 0.5))
    width_quality = max(0.0, 1.0 - abs(width_end - width_start) / max(avg_width, 1e-9))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.85) + 0.55)
    quality = 100.0 * (0.3 * direction_ratio + 0.25 * parallel_quality + 0.2 * width_quality + 0.25 * breakout_strength)

    reasoning = [
        f"上下ラインはほぼ平行 (差 {slope_delta:.3f})",
        f"チャネル幅は {avg_width / max(atr, 1e-9):.2f} ATR",
        f"傾きの持続は {direction_ratio * 100:.1f}%",
        _state_reasoning(state),
    ]
    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="continuation",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=[],
        guide_lines=[
            GuideLineSpec("上値抵抗", "resistance", highs[0].time, highs[0].price, highs[-1].time, highs[-1].price),
            GuideLineSpec("下値支持", "support", lows[0].time, lows[0].price, lows[-1].time, lows[-1].price),
            GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )

def _build_wedge_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    rising: bool,
) -> RawPattern | None:
    highs = [pivot for pivot in seq if pivot.kind == "high"]
    lows = [pivot for pivot in seq if pivot.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return None

    atr = _local_atr(df, seq[0].index, seq[-1].index)
    span = seq[-1].index - seq[0].index
    if span < 12 or span > max(170, len(df) * 0.8):
        return None

    if rising:
        if not (_strictly_monotonic([p.price for p in highs], increasing=True) and _strictly_monotonic([p.price for p in lows], increasing=True)):
            return None
    else:
        if not (_strictly_monotonic([p.price for p in highs], increasing=False) and _strictly_monotonic([p.price for p in lows], increasing=False)):
            return None

    support_slope = _slope(lows[0], lows[-1])
    resistance_slope = _slope(highs[0], highs[-1])
    overlap_start = max(highs[0].index, lows[0].index)
    overlap_end = min(highs[-1].index, lows[-1].index)
    if overlap_end <= overlap_start:
        return None
    width_start = abs(
        _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, overlap_start)
        - _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, overlap_start)
    )
    width_end = abs(
        _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, overlap_end)
        - _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, overlap_end)
    )
    if width_start < atr * 0.9 or width_end <= atr * 0.3 or width_end >= width_start * 0.85:
        return None

    if rising:
        if not (support_slope > 0 and resistance_slope > 0 and support_slope > resistance_slope):
            return None
        breakout_index, breakout_price = _breakout_line(df, start=seq[-1].index + 1, direction=direction, i0=lows[0].index, y0=lows[0].price, i1=lows[-1].index, y1=lows[-1].price)
        neckline = _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, seq[-1].index)
        invalidation = _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, seq[-1].index) + atr * 0.25
        slope_edge = (support_slope - resistance_slope) * span
    else:
        if not (support_slope < 0 and resistance_slope < 0 and abs(resistance_slope) > abs(support_slope)):
            return None
        breakout_index, breakout_price = _breakout_line(df, start=seq[-1].index + 1, direction=direction, i0=highs[0].index, y0=highs[0].price, i1=highs[-1].index, y1=highs[-1].price)
        neckline = _line_value(highs[0].index, highs[0].price, highs[-1].index, highs[-1].price, seq[-1].index)
        invalidation = _line_value(lows[0].index, lows[0].price, lows[-1].index, lows[-1].price, seq[-1].index) - atr * 0.25
        slope_edge = (abs(resistance_slope) - abs(support_slope)) * span

    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    targets = _targets(neckline=neckline, height=max(width_start * 0.85, atr * 1.0), direction=direction)
    convergence = max(0.0, 1.0 - width_end / max(width_start, 1e-9))
    slope_quality = min(1.0, abs(slope_edge) / max(atr * 1.8, 1e-9))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.85) + 0.55)
    quality = 100.0 * (0.35 * convergence + 0.25 * slope_quality + 0.15 * min(1.0, width_start / (atr * 2.8)) + 0.25 * breakout_strength)

    reasoning = [
        f"ウェッジ幅は縮小 ({width_start:.3f} → {width_end:.3f})",
        f"ライン収束差は {slope_edge:.3f}",
        f"終盤の幅は {width_end / max(atr, 1e-9):.2f} ATR",
        _state_reasoning(state),
    ]
    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="continuation",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=[],
        guide_lines=[
            GuideLineSpec("上辺", "resistance", highs[0].time, highs[0].price, highs[-1].time, highs[-1].price),
            GuideLineSpec("下辺", "support", lows[0].time, lows[0].price, lows[-1].time, lows[-1].price),
            GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )

def _build_pennant_pattern(
    df: pd.DataFrame,
    seq: list[Pivot],
    pattern_type: PatternType,
    direction: Literal["long", "short"],
    bullish: bool,
) -> RawPattern | None:
    if not _alternating_pivots(seq):
        return None
    atr = _local_atr(df, seq[0].index, seq[-1].index)
    span = seq[-1].index - seq[0].index
    if span < 8 or span > max(120, len(df) * 0.65):
        return None

    highs = [pivot for pivot in seq if pivot.kind == "high"]
    lows = [pivot for pivot in seq if pivot.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return None

    if bullish:
        pole_high = highs[0]
        post_highs = [pivot for pivot in highs if pivot.index >= pole_high.index]
        post_lows = [pivot for pivot in lows if pivot.index > pole_high.index]
        if len(post_highs) < 2 or len(post_lows) < 2:
            return None
        upper = (post_highs[0], post_highs[-1])
        lower = (post_lows[0], post_lows[-1])
        lookback_start = max(0, pole_high.index - max(10, span))
        pole_start = float(df["low"].iloc[lookback_start : pole_high.index + 1].min())
        pole = pole_high.price - pole_start
        if pole < atr * 2.2:
            return None
        retrace = pole_high.price - min(pivot.price for pivot in post_lows)
        if retrace > pole * 0.6:
            return None
        breakout_index, breakout_price = _breakout_line(df, start=seq[-1].index + 1, direction=direction, i0=upper[0].index, y0=upper[0].price, i1=upper[1].index, y1=upper[1].price)
        neckline = _line_value(upper[0].index, upper[0].price, upper[1].index, upper[1].price, seq[-1].index)
        invalidation = _line_value(lower[0].index, lower[0].price, lower[1].index, lower[1].price, seq[-1].index) - atr * 0.25
        reasoning = [
            f"ポールは {pole / atr:.2f} ATR",
            f"押し幅はポールの {retrace / max(pole, 1e-9) * 100:.1f}%",
        ]
    else:
        pole_low = lows[0]
        post_lows = [pivot for pivot in lows if pivot.index >= pole_low.index]
        post_highs = [pivot for pivot in highs if pivot.index > pole_low.index]
        if len(post_lows) < 2 or len(post_highs) < 2:
            return None
        upper = (post_highs[0], post_highs[-1])
        lower = (post_lows[0], post_lows[-1])
        lookback_start = max(0, pole_low.index - max(10, span))
        pole_start = float(df["high"].iloc[lookback_start : pole_low.index + 1].max())
        pole = pole_start - pole_low.price
        if pole < atr * 2.2:
            return None
        retrace = max(pivot.price for pivot in post_highs) - pole_low.price
        if retrace > pole * 0.6:
            return None
        breakout_index, breakout_price = _breakout_line(df, start=seq[-1].index + 1, direction=direction, i0=lower[0].index, y0=lower[0].price, i1=lower[1].index, y1=lower[1].price)
        neckline = _line_value(lower[0].index, lower[0].price, lower[1].index, lower[1].price, seq[-1].index)
        invalidation = _line_value(upper[0].index, upper[0].price, upper[1].index, upper[1].price, seq[-1].index) + atr * 0.25
        reasoning = [
            f"ポールは {pole / atr:.2f} ATR",
            f"戻り幅はポールの {retrace / max(pole, 1e-9) * 100:.1f}%",
        ]

    upper_slope = _slope(upper[0], upper[1])
    lower_slope = _slope(lower[0], lower[1])
    if not (upper_slope < 0 < lower_slope):
        return None

    overlap_start = max(upper[0].index, lower[0].index)
    overlap_end = min(upper[1].index, lower[1].index)
    if overlap_end <= overlap_start:
        return None
    width_start = abs(
        _line_value(upper[0].index, upper[0].price, upper[1].index, upper[1].price, overlap_start)
        - _line_value(lower[0].index, lower[0].price, lower[1].index, lower[1].price, overlap_start)
    )
    width_end = abs(
        _line_value(upper[0].index, upper[0].price, upper[1].index, upper[1].price, overlap_end)
        - _line_value(lower[0].index, lower[0].price, lower[1].index, lower[1].price, overlap_end)
    )
    if width_start < atr * 0.8 or width_end >= width_start * 0.86:
        return None

    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    targets = _targets(neckline=neckline, height=max(pole * 0.7, atr * 1.0), direction=direction)
    convergence = max(0.0, 1.0 - width_end / max(width_start, 1e-9))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.8) + 0.55)
    quality = 100.0 * (0.35 * min(1.0, pole / (atr * 3.6)) + 0.25 * convergence + 0.15 * min(1.0, span / 45) + 0.25 * breakout_strength)
    reasoning.append(f"収束率は {convergence * 100:.1f}%")
    reasoning.append(_state_reasoning(state))
    signal_index = breakout_index if breakout_index is not None else seq[-1].index
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="continuation",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=seq,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=[],
        guide_lines=[
            GuideLineSpec("上辺", "resistance", upper[0].time, upper[0].price, upper[1].time, upper[1].price),
            GuideLineSpec("下辺", "support", lower[0].time, lower[0].price, lower[1].time, lower[1].price),
            GuideLineSpec("ポール", "flag", seq[0].time, seq[0].price, highs[0].time if bullish else lows[0].time, highs[0].price if bullish else lows[0].price),
            GuideLineSpec("無効化", "invalidation", seq[0].time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )

def _build_saucer_pattern(df: pd.DataFrame, start: int, end: int, bottom: bool) -> RawPattern | None:
    segment = df.iloc[start : end + 1].reset_index(drop=True)
    if len(segment) < 24:
        return None

    closes = segment["close"].to_numpy(dtype=float)
    atr = _local_atr(df, start, end)
    x = np.linspace(-1.0, 1.0, len(segment))
    coeffs = np.polyfit(x, closes, 2)
    a, b, _ = coeffs
    if bottom and a <= 0:
        return None
    if not bottom and a >= 0:
        return None

    vertex = -b / (2 * a) if abs(a) > 1e-9 else 99.0
    if abs(vertex) > 0.35:
        return None

    fitted = np.polyval(coeffs, x)
    denom = float(((closes - closes.mean()) ** 2).sum())
    r2 = 1.0 - float(((closes - fitted) ** 2).sum()) / denom if denom > 1e-9 else 0.0
    if r2 < 0.45:
        return None

    edge_span = max(4, len(segment) // 5)
    middle_slice = closes[len(segment) // 3 : len(segment) - len(segment) // 3]
    if len(middle_slice) == 0:
        return None
    left_band = closes[:edge_span]
    right_band = closes[-edge_span:]
    if bottom:
        left_rim_local = int(np.argmax(left_band))
        right_rim_local = len(segment) - edge_span + int(np.argmax(right_band))
        center_local = len(segment) // 3 + int(np.argmin(middle_slice))
        left_rim = float(closes[left_rim_local])
        right_rim = float(closes[right_rim_local])
        bowl = float(closes[center_local])
        rim_avg = statistics.mean([left_rim, right_rim])
        rim_tol = max(atr * 1.15, abs(rim_avg) * 0.005)
        if abs(left_rim - right_rim) > rim_tol:
            return None
        depth = rim_avg - bowl
        if depth < atr * 1.35:
            return None
        neckline = max(left_rim, right_rim)
        breakout_index, breakout_price = _breakout(df, start=end + 1, neckline=neckline, direction="long")
        invalidation = bowl - atr * 0.25
        direction: Literal["long", "short"] = "long"
        pattern_type: PatternType = "saucer_bottom"
        labels = ["左縁", "底", "右縁"]
        reasoning = [
            f"縁の差は小さい ({abs(left_rim-right_rim):.3f} <= {rim_tol:.3f})",
            f"丸底の深さは {depth / max(atr, 1e-9):.2f} ATR",
            f"曲線適合度 R²={r2:.2f}",
        ]
    else:
        left_rim_local = int(np.argmin(left_band))
        right_rim_local = len(segment) - edge_span + int(np.argmin(right_band))
        center_local = len(segment) // 3 + int(np.argmax(middle_slice))
        left_rim = float(closes[left_rim_local])
        right_rim = float(closes[right_rim_local])
        bowl = float(closes[center_local])
        rim_avg = statistics.mean([left_rim, right_rim])
        rim_tol = max(atr * 1.15, abs(rim_avg) * 0.005)
        if abs(left_rim - right_rim) > rim_tol:
            return None
        depth = bowl - rim_avg
        if depth < atr * 1.35:
            return None
        neckline = min(left_rim, right_rim)
        breakout_index, breakout_price = _breakout(df, start=end + 1, neckline=neckline, direction="short")
        invalidation = bowl + atr * 0.25
        direction = "short"
        pattern_type = "saucer_top"
        labels = ["左縁", "天井", "右縁"]
        reasoning = [
            f"縁の差は小さい ({abs(left_rim-right_rim):.3f} <= {rim_tol:.3f})",
            f"丸天井の高さは {depth / max(atr, 1e-9):.2f} ATR",
            f"曲線適合度 R²={r2:.2f}",
        ]

    state = _resolve_state(df, direction, invalidation, breakout_index)
    entry_zone = _entry_zone(neckline=neckline, atr=atr, direction=direction)
    targets = _targets(neckline=neckline, height=max(depth * 0.85, atr * 1.0), direction=direction)
    symmetry = max(0.0, 1.0 - abs(left_rim - right_rim) / max(rim_tol, 1e-9))
    curvature = min(1.0, abs(depth) / max(atr * 3.0, 1e-9))
    breakout_strength = 0.45 if breakout_index is None else min(1.0, abs((breakout_price or neckline) - neckline) / (atr * 0.8) + 0.55)
    quality = 100.0 * (0.35 * min(1.0, r2) + 0.25 * symmetry + 0.2 * curvature + 0.2 * breakout_strength)
    reasoning.append(_state_reasoning(state))

    left_idx = start + left_rim_local
    center_idx = start + center_local
    right_idx = start + right_rim_local
    points = [
        Pivot(index=left_idx, kind="high" if bottom else "low", price=float(df["close"].iat[left_idx]), time=pd.Timestamp(df["time"].iat[left_idx])),
        Pivot(index=center_idx, kind="low" if bottom else "high", price=float(df["close"].iat[center_idx]), time=pd.Timestamp(df["time"].iat[center_idx])),
        Pivot(index=right_idx, kind="high" if bottom else "low", price=float(df["close"].iat[right_idx]), time=pd.Timestamp(df["time"].iat[right_idx])),
    ]
    signal_index = breakout_index if breakout_index is not None else right_idx
    signal_time = pd.Timestamp(df["time"].iat[signal_index])
    return RawPattern(
        pattern_type=pattern_type,
        family="reversal",
        direction=direction,
        state=state,
        quality_score=quality,
        neckline=neckline,
        invalidation=invalidation,
        breakout_price=breakout_price,
        entry_zone=entry_zone,
        points=points,
        breakout_index=breakout_index,
        breakout_time=pd.Timestamp(df["time"].iat[breakout_index]) if breakout_index is not None else None,
        signal_index=signal_index,
        signal_time=signal_time,
        targets=targets,
        reasoning=reasoning,
        point_labels=labels,
        guide_lines=[
            GuideLineSpec("ネックライン", "neckline", points[0].time, neckline, df["time"].iat[-1], neckline),
            GuideLineSpec("無効化", "invalidation", points[0].time, invalidation, df["time"].iat[-1], invalidation),
        ],
    )


def _resolve_state(df: pd.DataFrame, direction: Literal["long", "short"], invalidation: float, breakout_index: int | None) -> Literal["forming", "confirmed", "invalidated"]:
    last_close = float(df["close"].iat[-1])
    if breakout_index is not None:
        return "confirmed"
    if (direction == "long" and last_close < invalidation) or (direction == "short" and last_close > invalidation):
        return "invalidated"
    return "forming"


def _state_reasoning(state: str) -> str:
    if state == "confirmed":
        return "ブレイクが確認済み"
    if state == "forming":
        return "まだ最終ブレイク待ち"
    return "無効化ラインを超えて失敗"


def _breakout(df: pd.DataFrame, start: int, neckline: float, direction: Literal["long", "short"]) -> tuple[int | None, float | None]:
    closes = df["close"].to_numpy()
    for idx in range(start, len(df)):
        if direction == "long" and closes[idx] > neckline:
            return idx, float(closes[idx])
        if direction == "short" and closes[idx] < neckline:
            return idx, float(closes[idx])
    return None, None


def _breakout_line(
    df: pd.DataFrame,
    start: int,
    direction: Literal["long", "short"],
    i0: int,
    y0: float,
    i1: int,
    y1: float,
) -> tuple[int | None, float | None]:
    closes = df["close"].to_numpy()
    for idx in range(start, len(df)):
        trigger = _line_value(i0, y0, i1, y1, idx)
        if direction == "long" and closes[idx] > trigger:
            return idx, float(closes[idx])
        if direction == "short" and closes[idx] < trigger:
            return idx, float(closes[idx])
    return None, None


def _line_value(i0: int, y0: float, i1: int, y1: float, idx: int) -> float:
    if i1 == i0:
        return y1
    slope = (y1 - y0) / (i1 - i0)
    return y0 + slope * (idx - i0)


def _strictly_monotonic(values: list[float], increasing: bool) -> bool:
    comparisons = [b > a for a, b in zip(values, values[1:])] if increasing else [b < a for a, b in zip(values, values[1:])]
    return all(comparisons)


def _alternating_pivots(seq: list[Pivot]) -> bool:
    return all(left.kind != right.kind for left, right in zip(seq, seq[1:]))


def _slope(p0: Pivot, p1: Pivot) -> float:
    return (p1.price - p0.price) / max(p1.index - p0.index, 1)


def _entry_zone(neckline: float, atr: float, direction: Literal["long", "short"]) -> tuple[float, float]:
    if direction == "long":
        return neckline - atr * 0.35, neckline + atr * 0.1
    return neckline - atr * 0.1, neckline + atr * 0.35


def _targets(neckline: float, height: float, direction: Literal["long", "short"]) -> tuple[float, float]:
    if direction == "long":
        return neckline + height, neckline + height * 1.6
    return neckline - height, neckline - height * 1.6


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def _local_atr(df: pd.DataFrame, start: int, end: int) -> float:
    atr_slice = _atr(df.iloc[max(0, start - 14) : end + 1])
    return float(atr_slice.iloc[-1]) if not atr_slice.empty else float(df["close"].std())


def _dedupe_patterns(patterns: list[RawPattern]) -> list[RawPattern]:
    deduped: list[RawPattern] = []
    seen: set[tuple[str, int, int]] = set()
    for pattern in patterns:
        key = (pattern.pattern_type, pattern.points[0].index, pattern.points[-1].index)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(pattern)
    return deduped
