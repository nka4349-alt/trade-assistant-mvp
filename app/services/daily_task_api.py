
from __future__ import annotations

import inspect, math
from datetime import datetime
from typing import Any
import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from app.services.data_providers import load_bundle
from app.services.patterns import detect_patterns
try:
    from app.services.scoring import score_pattern
except Exception:
    score_pattern = None

router = APIRouter(prefix="/api/task", tags=["task"])

MAJOR_JP = ["7203","6758","9984","8306","9432","6861","8035","7011","6501","6098","4063","9983","7974","6954","8316","7267","7741","4502","4519","6367","6503","8001","8058","8031","2914","4568","8766","8801","8802","9020"]
DAYTRADE_JP = ["7203","6758","9984","8306","6861","8035","7011","6501","6098","6920","6857","6594","7735","6723","6146","9101","9104","9107","7012","7013","1570","9983","9432","9433","4755","4689","2413","3436","7267","6503"]
SWING_JP = ["7203","6758","9984","8306","9432","6861","8035","7011","6501","4063","8001","8058","8031","2914","4568","8766","8801","8802","9020","9022","2502","2802","3382","4502","4519","6367","6902","6954","7974","9983"]

BUY_PATTERN_HINTS = {"double_bottom","triple_bottom","head_and_shoulders_bottom","ascending_triangle","bull_flag","bullish_flag","ascending_channel","falling_wedge","bullish_wedge","bull_pennant","ascending_pennant","saucer_bottom"}

def _universe(name: str) -> list[str]:
    key=(name or "daytrade").lower()
    if key in {"major","large","largecap","主要大型株"}: return MAJOR_JP
    if key in {"swing","スイング"}: return SWING_JP
    return DAYTRADE_JP

def _safe_float(v: Any, default: float=0.0) -> float:
    try:
        if v is None: return default
        f=float(v)
        return default if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return default

def _as_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict): return dict(obj)
    if hasattr(obj, "model_dump"): return obj.model_dump()
    if hasattr(obj, "dict"): return obj.dict()
    if hasattr(obj, "__dict__"): return dict(obj.__dict__)
    return {}

def _get(obj: Any, *names: str, default=None):
    for n in names:
        if isinstance(obj, dict) and n in obj: return obj[n]
        if hasattr(obj, n): return getattr(obj, n)
    return default

def _normalize_symbol(symbol: str) -> str:
    s=symbol.strip().upper()
    return s.replace(".T","") if (s.endswith(".T") or (s.isdigit() and len(s)==4)) else s

def _bundle_to_df(bundle: Any) -> pd.DataFrame:
    if isinstance(bundle, pd.DataFrame): return bundle.copy()
    for name in ("candles","data","df","frame"):
        v=_get(bundle, name)
        if isinstance(v, pd.DataFrame): return v.copy()
        if isinstance(v, list): return pd.DataFrame(v)
    if isinstance(bundle, dict):
        for k in ("candles","data","df","frame"):
            v=bundle.get(k)
            if isinstance(v, pd.DataFrame): return v.copy()
            if isinstance(v, list): return pd.DataFrame(v)
    raise ValueError("ローソク足データをDataFrameに変換できませんでした。")

def _call_load_bundle(asset_class: str, symbol: str, timeframe: str, provider: str, limit: int) -> Any:
    kwargs={"asset_class":asset_class,"symbol":symbol,"timeframe":timeframe,"provider":provider,"limit":limit}
    try:
        sig=inspect.signature(load_bundle)
        usable={k:v for k,v in kwargs.items() if k in sig.parameters}
        if usable: return load_bundle(**usable)
    except Exception:
        pass
    try: return load_bundle(asset_class, symbol, timeframe, provider, limit)
    except TypeError:
        try: return load_bundle(symbol, timeframe, provider, limit)
        except TypeError: return load_bundle(symbol=symbol, timeframe=timeframe)

def _load_df(symbol: str, timeframe: str, provider: str="auto", limit: int=240) -> pd.DataFrame:
    df=_bundle_to_df(_call_load_bundle("stock", symbol, timeframe, provider, limit))
    df=df.copy()
    df.columns=[str(c).lower() for c in df.columns]
    if "datetime" in df.columns and "time" not in df.columns:
        df=df.rename(columns={"datetime":"time"})
    for col in ("open","high","low","close"):
        if col not in df.columns: raise ValueError(f"{symbol} {timeframe}: {col}列がありません。")
        df[col]=pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open","high","low","close"]).tail(limit).reset_index(drop=True)

def _ema(series: pd.Series, span: int) -> float:
    if len(series) < max(5, span//2): return _safe_float(series.iloc[-1])
    return _safe_float(series.ewm(span=span, adjust=False).mean().iloc[-1])

def _entry_timing(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or len(df)<20: return {"label":"判断不足","score":0,"reason":"データ不足"}
    close=df["close"].astype(float); high=df["high"].astype(float); low=df["low"].astype(float)
    last=_safe_float(close.iloc[-1]); ema20=_ema(close,20); ema50=_ema(close,50)
    prev_high=_safe_float(high.iloc[-2]) if len(high)>=2 else _safe_float(high.iloc[-1])
    prev_low=_safe_float(low.iloc[-2]) if len(low)>=2 else _safe_float(low.iloc[-1])
    dist=(last-ema20)/ema20*100 if ema20 else 0
    score=0; reasons=[]
    if last>=ema20>=ema50: score+=35; reasons.append("EMA20/EMA50の上で上向き")
    elif last>=ema20: score+=20; reasons.append("EMA20上で短期は強め")
    else: reasons.append("EMA20を下回り買いは慎重")
    if -2.0 <= dist <= 3.5: score+=25; reasons.append("EMA20からの距離が入りやすい")
    elif dist>6.0: score-=15; reasons.append("やや伸び切り")
    else: reasons.append("押し目確認待ち")
    if last>=prev_high: score+=15; reasons.append("前日/前足高値を上回る")
    elif last<=prev_low: score-=15; reasons.append("前日/前足安値付近で注意")
    label="入り良好" if score>=55 else "入り監視" if score>=35 else "入り注意" if score>=15 else "入り見送り"
    return {"label":label,"score":round(score,1),"last":round(last,2),"ema20":round(ema20,2),"ema50":round(ema50,2),"prev_high":round(prev_high,2),"prev_low":round(prev_low,2),"dist_ema20_pct":round(dist,2),"reason":" / ".join(reasons[:3])}

def _pattern_to_candidate(symbol: str, pattern: Any, df: pd.DataFrame) -> dict[str, Any] | None:
    d=_as_dict(pattern)
    name=str(d.get("pattern_type") or d.get("type") or d.get("name") or "").lower()
    direction=str(d.get("direction") or d.get("side") or "").lower()
    is_buy=direction in {"long","buy","買い"} or any(h in name for h in BUY_PATTERN_HINTS)
    if not is_buy: return None
    quality=_safe_float(d.get("quality_score", d.get("quality", 0)))
    probability=_safe_float(d.get("probability", d.get("edge", 0)))
    if score_pattern is not None and probability<=0:
        try:
            sd=_as_dict(score_pattern(pattern, df)); d.update(sd)
            quality=max(quality, _safe_float(d.get("quality_score", d.get("quality",0))))
            probability=max(probability, _safe_float(d.get("probability", d.get("edge",0))))
        except Exception: pass
    return {"symbol":symbol,"pattern":d.get("label") or d.get("pattern_label") or name or "買いパターン","status":d.get("status") or "検出","quality":round(quality,1),"probability":round(probability,1),"entry":_safe_float(d.get("entry_price",d.get("entry",d.get("recommended_entry",0)))),"stop":_safe_float(d.get("stop_loss",d.get("stop",0))),"tp1":_safe_float(d.get("take_profit_1",d.get("tp1",0))),"tp2":_safe_float(d.get("take_profit_2",d.get("tp2",0)))}

def _scan_symbol(symbol: str, quality_min: float, provider: str) -> dict[str, Any] | None:
    symbol=_normalize_symbol(symbol)
    daily=_load_df(symbol,"1d",provider,260)
    weekly=_load_df(symbol,"1wk",provider,160)
    pattern_df=_load_df(symbol,"15m",provider,240)
    candidates=[]
    for p in detect_patterns(pattern_df):
        c=_pattern_to_candidate(symbol,p,pattern_df)
        if c and c["quality"]>=quality_min: candidates.append(c)
    if not candidates: return None
    de=_entry_timing(daily); we=_entry_timing(weekly)
    best=sorted(candidates, key=lambda x:(x["quality"],x["probability"]), reverse=True)[0]
    score=best["quality"]*0.45+best["probability"]*0.25+de["score"]*0.20+we["score"]*0.10
    rank="A" if score>=75 else "B" if score>=62 else "C"
    reason=f"{best['pattern']}を検出。形の質{best['quality']:.1f}、推定優位度{best['probability']:.1f}%。日足は{de['label']}、週足は{we['label']}。{de['reason']}"
    return {"symbol":symbol,"rank":rank,"score":round(score,1),"best_signal":best,"daily_entry":de,"weekly_entry":we,"reason":reason}

def _build_markdown(items: list[dict[str, Any]], mode: str, universe: str, quality_min: float) -> str:
    title="寄り前 買い候補" if mode=="preopen" else "大引け後 翌日買い候補"
    lines=[f"# {title}","",f"- 作成時刻: {datetime.now().strftime('%Y-%m-%d %H:%M')}",f"- 対象: 日本株 / {universe}",f"- 条件: 買い候補、品質{quality_min:.0f}以上、日足・週足の入りを加味","- 注意: これは売買補助の機械スキャンであり、投資助言ではありません。",""]
    if not items:
        return "\\n".join(lines+["条件に合う買い候補は見つかりませんでした。",""])
    for i,item in enumerate(items,1):
        sig=item["best_signal"]; de=item["daily_entry"]; we=item["weekly_entry"]
        lines += [f"## {i}. {item['symbol']}  評価{item['rank']} / 総合{item['score']}","",
            f"- サイン: {sig['pattern']} / {sig['status']}",
            f"- 品質: {sig['quality']:.1f}",
            f"- 推定優位度: {sig['probability']:.1f}%",
            f"- 推奨エントリー価格: {sig['entry'] or '未算出'}",
            f"- 損切り: {sig['stop'] or '未算出'}",
            f"- TP1 / TP2: {sig['tp1'] or '未算出'} / {sig['tp2'] or '未算出'}",
            f"- 日足の入り: {de['label']}（EMA20距離 {de.get('dist_ema20_pct',0)}%）",
            f"- 週足の入り: {we['label']}（EMA20距離 {we.get('dist_ema20_pct',0)}%）",
            f"- 理由: {item['reason']}",""]
    return "\\n".join(lines)

@router.get("/buy-candidates")
async def buy_candidates(mode: str=Query("preopen"), universe: str=Query("daytrade"), symbols: str|None=Query(None), quality_min: float=Query(70,ge=0,le=100), limit: int=Query(5,ge=1,le=20), scan_limit: int=Query(30,ge=1,le=80), provider: str=Query("auto")):
    raw=[s.strip() for s in symbols.split(",")] if symbols else _universe(universe)
    raw=[s for s in raw if s][:scan_limit]
    results=[]; errors=[]
    for symbol in raw:
        try:
            item=_scan_symbol(symbol,quality_min,provider)
            if item: results.append(item)
        except Exception as e:
            errors.append({"symbol":symbol,"error":str(e)[:200]})
    results=sorted(results, key=lambda x:(x["rank"],x["score"]), reverse=True)[:limit]
    md=_build_markdown(results,mode,universe,quality_min)
    return {"mode":mode,"universe":universe,"quality_min":quality_min,"count":len(results),"items":results,"errors":errors[:10],"markdown":md}

@router.get("/buy-candidates.md", response_class=PlainTextResponse)
async def buy_candidates_markdown(mode: str=Query("preopen"), universe: str=Query("daytrade"), symbols: str|None=Query(None), quality_min: float=Query(70,ge=0,le=100), limit: int=Query(5,ge=1,le=20), scan_limit: int=Query(30,ge=1,le=80), provider: str=Query("auto")):
    data=await buy_candidates(mode=mode, universe=universe, symbols=symbols, quality_min=quality_min, limit=limit, scan_limit=scan_limit, provider=provider)
    return data["markdown"]
