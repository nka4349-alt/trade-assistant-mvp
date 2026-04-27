from __future__ import annotations

import math

import pandas as pd

from app.schemas import AssetClass, TradePlan
from app.services.patterns import RawPattern


def score_pattern(df: pd.DataFrame, pattern: RawPattern, asset_class: AssetClass) -> tuple[float, TradePlan]:
    latest_close = float(df["close"].iat[-1])
    ema_fast = df["close"].ewm(span=20, adjust=False).mean()
    ema_slow = df["close"].ewm(span=50, adjust=False).mean()
    trend_up = float(ema_fast.iat[-1]) > float(ema_slow.iat[-1])
    trend_down = float(ema_fast.iat[-1]) < float(ema_slow.iat[-1])

    atr = _atr(df).iat[-1]
    rel_vol = (df["volume"].iat[-1] / max(df["volume"].rolling(20, min_periods=1).mean().iat[-1], 1.0)) if "volume" in df.columns else 1.0
    quality = pattern.quality_score / 100.0

    score = 0.10 + 0.50 * quality
    if pattern.state == "confirmed":
        score += 0.18
    elif pattern.state == "forming":
        score += 0.04
    else:
        score -= 0.18

    if pattern.direction == "long":
        score += 0.10 if trend_up else -0.06
        if latest_close >= pattern.neckline:
            score += 0.05
    else:
        score += 0.10 if trend_down else -0.06
        if latest_close <= pattern.neckline:
            score += 0.05

    if asset_class == AssetClass.STOCK:
        if rel_vol > 1.15:
            score += 0.06
        elif rel_vol < 0.85:
            score -= 0.03

    atr_ratio = atr / max(latest_close, 1e-9)
    if atr_ratio > 0.03:
        score -= 0.03
    elif atr_ratio < 0.008:
        score += 0.03

    probability = 100 / (1 + math.exp(-5.0 * (score - 0.52)))
    probability = max(35.0, min(probability, 89.5))

    zone_low, zone_high = pattern.entry_zone
    aggression = max(0.0, min((probability - 50.0) / 35.0, 1.0))
    if pattern.direction == "long":
        suggested_limit = zone_low * (1 - aggression) + zone_high * aggression
        stop = pattern.invalidation
        target_1, target_2 = pattern.targets
        rr1 = (target_1 - suggested_limit) / max(suggested_limit - stop, 1e-9)
        rr2 = (target_2 - suggested_limit) / max(suggested_limit - stop, 1e-9)
        side = "buy"
    else:
        suggested_limit = zone_high * (1 - aggression) + zone_low * aggression
        stop = pattern.invalidation
        target_1, target_2 = pattern.targets
        rr1 = (suggested_limit - target_1) / max(stop - suggested_limit, 1e-9)
        rr2 = (suggested_limit - target_2) / max(stop - suggested_limit, 1e-9)
        side = "sell"

    notes = [
        "確率は現時点ではヒューリスティック計算です。ジャーナルが溜まったら XGBoost + 確率校正に差し替えてください。",
        f"品質スコア={pattern.quality_score:.1f}",
        f"トレンド={'上昇' if trend_up else '下降' if trend_down else '横ばい'}",
        f"相対出来高={rel_vol:.2f}",
        f"ATR比率={atr_ratio:.4f}",
    ]

    plan = TradePlan(
        suggested_limit=round(suggested_limit, 5),
        stop_loss=round(stop, 5),
        target_1=round(target_1, 5),
        target_2=round(target_2, 5),
        risk_reward_1=round(rr1, 2),
        risk_reward_2=round(rr2, 2),
        order_side=side,
        notes=notes,
    )
    return probability, plan


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
