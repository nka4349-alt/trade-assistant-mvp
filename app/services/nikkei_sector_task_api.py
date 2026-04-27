from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.schemas import AssetClass, ProviderName, RecommendationItem
from app.services.recommendations import build_recommendations

router = APIRouter(prefix="/api/task", tags=["task"])

# 日経225系の内蔵ユニバースです。構成銘柄は定期的に入れ替わるため、必要に応じてこのリストを更新してください。
# まずはスキャン速度を優先し、主要銘柄をセクター別に持たせています。
NIKKEI225_BY_SECTOR: dict[str, list[str]] = {
    "半導体・電機": ["8035", "6857", "6920", "6723", "6758", "6762", "6971", "6981", "6954", "6501", "6503", "6504", "6506", "6645", "6701", "6702", "6724", "6752", "6753", "6770", "6841", "6861", "6952", "6988", "7735", "7741", "7751", "7752"],
    "自動車・機械・重工": ["7203", "7267", "7269", "7201", "7202", "7261", "7270", "7272", "6902", "7011", "7012", "7013", "6301", "6302", "6305", "6326", "6361", "6367", "6471", "6472", "6473", "7004"],
    "金融": ["8306", "8316", "8411", "8308", "8309", "8331", "8354", "7186", "8601", "8604", "8725", "8766", "8795", "8591", "8253"],
    "商社": ["8001", "8002", "8031", "8053", "8058"],
    "医薬・精密": ["4502", "4503", "4506", "4507", "4519", "4523", "4568", "4578", "4151", "4543", "7731", "7733", "7762"],
    "化学・素材": ["3401", "3402", "3405", "3407", "4004", "4005", "4021", "4042", "4043", "4061", "4063", "4183", "4188", "4452", "4631", "4901", "4911", "5201", "5202", "5214", "5232", "5233", "5301", "5332", "5333", "5401", "5406", "5411", "3436", "5711", "5713", "5714", "5801", "5802", "5803", "5631", "5706", "5715"],
    "通信・サービス・小売": ["9983", "8267", "3382", "3092", "3086", "4755", "4689", "2413", "7974", "7832", "3659", "9766", "4324", "2432", "4704", "9735", "9602", "9613", "9432", "9433", "9434", "9984", "4661", "6098"],
    "運輸・不動産": ["9001", "9005", "9007", "9008", "9009", "9020", "9021", "9022", "9064", "9101", "9104", "9107", "9201", "9202", "8801", "8802", "8804", "8830", "3289"],
    "食品・生活": ["2501", "2502", "2503", "2002", "2269", "2282", "2801", "2802", "2871", "2914", "2531"],
    "資源・エネルギー": ["5020", "5019", "1605", "9501", "9502", "9503", "9531", "9532"],
}

DAYTRADE_PRIORITY = [
    "8035", "6857", "6920", "6723", "7203", "6758", "9984", "8306", "7011", "7012", "7013", "6861", "6098", "9983", "9432", "9433", "8316", "8411", "6501", "6367", "4063", "6954", "8001", "8058", "9101", "9104", "9107", "7735", "6146", "6981",
]

SECTOR_ALIAS = {
    "all": "all",
    "nikkei225": "all",
    "日経225": "all",
    "large": "all",
    "daytrade": "daytrade",
    "デイトレ": "daytrade",
}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = item.strip().upper().replace(".T", "")
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _sector_for(symbol: str) -> str:
    code = symbol.strip().upper().replace(".T", "")
    for sector, codes in NIKKEI225_BY_SECTOR.items():
        if code in codes:
            return sector
    return "その他"


def _universe_symbols(universe: str, sector: str | None = None) -> list[str]:
    key = SECTOR_ALIAS.get((universe or "nikkei225").strip(), (universe or "nikkei225").strip())
    if key == "daytrade":
        return _unique(DAYTRADE_PRIORITY)
    if sector and sector != "all":
        return _unique(NIKKEI225_BY_SECTOR.get(sector, []))
    symbols: list[str] = []
    for codes in NIKKEI225_BY_SECTOR.values():
        symbols.extend(codes)
    return _unique(symbols)


def _is_buy_candidate(item: RecommendationItem, quality_min: float) -> bool:
    if item.top_pattern_direction != "long":
        return False
    if item.top_pattern_quality is None or item.top_pattern_quality < quality_min:
        return False
    if item.entry_grade not in {"good", "watch"}:
        return False
    return item.action in {"buy_watch", "breakout_wait", "wait"}


def _sort_buy_items(items: list[RecommendationItem]) -> list[RecommendationItem]:
    return sorted(
        items,
        key=lambda x: (
            1 if x.current_signal else 0,
            1 if x.top_pattern_state == "confirmed" else 0,
            x.score,
            x.top_pattern_quality or 0.0,
            x.top_pattern_probability or 0.0,
        ),
        reverse=True,
    )


def _item_to_dict(item: RecommendationItem) -> dict[str, Any]:
    plan = item.top_trade_plan
    return {
        "symbol": item.symbol,
        "sector": _sector_for(item.symbol),
        "rank": item.rank_label,
        "score": item.score,
        "action": item.action,
        "current_signal": item.current_signal,
        "current_signal_count": item.current_signal_count,
        "pattern": item.top_pattern_type,
        "pattern_state": item.top_pattern_state,
        "quality": item.top_pattern_quality,
        "edge": item.top_pattern_probability,
        "entry_grade": item.entry_grade,
        "entry_score": item.entry_score,
        "entry_summary": item.entry_summary,
        "daily_entry": item.daily_entry.summary if item.daily_entry else None,
        "weekly_entry": item.weekly_entry.summary if item.weekly_entry else None,
        "suggested_entry": plan.suggested_limit if plan else None,
        "stop_loss": plan.stop_loss if plan else None,
        "tp1": plan.target_1 if plan else None,
        "tp2": plan.target_2 if plan else None,
        "reason": item.deep_reason or item.summary,
    }


def _build_buy_markdown(*, items: list[RecommendationItem], errors: list[dict[str, str]], mode: str, universe: str, quality_min: float, scanned: int) -> str:
    title = "寄り前 日経225買い候補" if mode == "preopen" else "大引け後 日経225翌日買い候補"
    lines = [
        f"# {title}",
        "",
        f"- 作成時刻: {datetime.now(UTC).astimezone().strftime('%Y-%m-%d %H:%M')}",
        f"- 対象: {universe}",
        f"- スキャン銘柄数: {scanned}",
        f"- 条件: 買い候補 / 形の質 {quality_min:.0f}以上 / 日足・週足の入りが良好または監視",
        "- 注意: これは売買補助の機械スキャンであり、投資助言ではありません。",
        "",
    ]
    if not items:
        lines.append("条件に合う買い候補は見つかりませんでした。品質条件やスキャン数を緩めて確認してください。")
    for idx, item in enumerate(items, 1):
        plan = item.top_trade_plan
        lines.extend([
            f"## {idx}. {item.symbol}（{_sector_for(item.symbol)}） 評価{item.rank_label} / 総合{item.score:.1f}",
            "",
            f"- サイン: {item.top_pattern_type or '未検出'} / {item.top_pattern_state or '-'} / 現在サイン {'あり' if item.current_signal else 'なし'}",
            f"- 形の質: {item.top_pattern_quality if item.top_pattern_quality is not None else '-'}",
            f"- 推定優位度: {item.top_pattern_probability if item.top_pattern_probability is not None else '-'}%",
            f"- 上位足の入り: {item.entry_summary}",
            f"- 日足: {item.daily_entry.summary if item.daily_entry else '-'}",
            f"- 週足: {item.weekly_entry.summary if item.weekly_entry else '-'}",
            f"- 推奨エントリー価格: {plan.suggested_limit if plan else '未算出'}",
            f"- 損切り: {plan.stop_loss if plan else '未算出'}",
            f"- TP1 / TP2: {plan.target_1 if plan else '未算出'} / {plan.target_2 if plan else '未算出'}",
            f"- 理由: {item.deep_reason or item.summary}",
            "",
        ])
    if errors:
        lines.extend(["---", "", f"取得失敗: {len(errors)}件（上位10件のみ表示）"])
        for err in errors[:10]:
            lines.append(f"- {err.get('symbol')}: {err.get('detail')}")
    return "\n".join(lines)


def _sector_score_from_items(items: list[RecommendationItem], quality_min: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[RecommendationItem]] = defaultdict(list)
    for item in items:
        grouped[_sector_for(item.symbol)].append(item)

    rows: list[dict[str, Any]] = []
    for sector, sector_items in grouped.items():
        buy_items = [item for item in sector_items if _is_buy_candidate(item, quality_min)]
        avg_score = sum(item.score for item in sector_items) / max(1, len(sector_items))
        buy_avg = sum(item.score for item in buy_items) / max(1, len(buy_items)) if buy_items else 0.0
        current_count = sum(1 for item in sector_items if item.current_signal)
        best = _sort_buy_items(buy_items)[0] if buy_items else max(sector_items, key=lambda x: x.score)
        sector_score = min(100.0, avg_score * 0.35 + buy_avg * 0.45 + len(buy_items) * 4.0 + current_count * 3.0)
        rows.append({
            "sector": sector,
            "score": round(sector_score, 1),
            "scanned": len(sector_items),
            "buy_candidates": len(buy_items),
            "current_signals": current_count,
            "best_symbol": best.symbol,
            "best_score": best.score,
            "best_pattern": best.top_pattern_type,
            "best_quality": best.top_pattern_quality,
            "best_entry": best.entry_summary,
        })
    rows.sort(key=lambda row: (row["score"], row["buy_candidates"], row["current_signals"]), reverse=True)
    return rows


def _build_sector_markdown(*, rows: list[dict[str, Any]], errors: list[dict[str, str]], universe: str, quality_min: float, scanned: int) -> str:
    lines = [
        "# 日経225 セクター別スコア",
        "",
        f"- 作成時刻: {datetime.now(UTC).astimezone().strftime('%Y-%m-%d %H:%M')}",
        f"- 対象: {universe}",
        f"- スキャン銘柄数: {scanned}",
        f"- 買い候補条件: 形の質 {quality_min:.0f}以上 / 日足・週足の入りが良好または監視",
        "- 注意: これは売買補助の機械スキャンであり、投資助言ではありません。",
        "",
    ]
    if not rows:
        lines.append("セクター評価を作成できませんでした。")
    for idx, row in enumerate(rows, 1):
        lines.extend([
            f"## {idx}. {row['sector']}  スコア {row['score']}",
            "",
            f"- スキャン数: {row['scanned']}",
            f"- 買い候補数: {row['buy_candidates']}",
            f"- 現在サイン数: {row['current_signals']}",
            f"- 代表銘柄: {row['best_symbol']} / 総合 {row['best_score']}",
            f"- 代表サイン: {row['best_pattern']} / 形の質 {row['best_quality']}",
            f"- 上位足の入り: {row['best_entry']}",
            "",
        ])
    if errors:
        lines.extend(["---", "", f"取得失敗: {len(errors)}件（上位10件のみ表示）"])
        for err in errors[:10]:
            lines.append(f"- {err.get('symbol')}: {err.get('detail')}")
    return "\n".join(lines)


@router.get("/nikkei225-buy-candidates")
async def nikkei225_buy_candidates(
    mode: str = Query(default="preopen", pattern="^(preopen|afterclose)$"),
    universe: str = Query(default="daytrade"),
    sector: str | None = Query(default=None),
    symbols: str | None = Query(default=None),
    quality_min: float = Query(default=70, ge=0, le=100),
    limit: int = Query(default=8, ge=1, le=30),
    scan_limit: int = Query(default=50, ge=1, le=225),
    provider: ProviderName = Query(default=ProviderName.AUTO),
    preset_id: str = Query(default="jp_stock_day"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    raw_symbols = _unique(symbols.split(",")) if symbols else _universe_symbols(universe, sector=sector)
    scan_symbols = raw_symbols[:scan_limit]
    response = await build_recommendations(
        settings=settings,
        asset_class=AssetClass.STOCK,
        provider=provider,
        preset_id=preset_id,
        symbols=scan_symbols,
    )
    buy_items = _sort_buy_items([item for item in response.items if _is_buy_candidate(item, quality_min)])[:limit]
    errors = [{"symbol": f.symbol, "detail": f.detail} for f in response.failures]
    markdown = _build_buy_markdown(items=buy_items, errors=errors, mode=mode, universe=universe, quality_min=quality_min, scanned=len(scan_symbols))
    return {
        "mode": mode,
        "universe": universe,
        "sector": sector or "all",
        "quality_min": quality_min,
        "scanned": len(scan_symbols),
        "count": len(buy_items),
        "items": [_item_to_dict(item) for item in buy_items],
        "errors": errors[:20],
        "markdown": markdown,
        "generated_at": datetime.now(UTC),
    }


@router.get("/nikkei225-buy-candidates.md", response_class=PlainTextResponse)
async def nikkei225_buy_candidates_markdown(**kwargs: Any) -> str:
    data = await nikkei225_buy_candidates(**kwargs)
    return data["markdown"]


@router.get("/sector-scores")
async def sector_scores(
    universe: str = Query(default="nikkei225"),
    quality_min: float = Query(default=70, ge=0, le=100),
    scan_limit: int = Query(default=80, ge=1, le=225),
    provider: ProviderName = Query(default=ProviderName.AUTO),
    preset_id: str = Query(default="jp_stock_day"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    symbols = _universe_symbols(universe)[:scan_limit]
    response = await build_recommendations(
        settings=settings,
        asset_class=AssetClass.STOCK,
        provider=provider,
        preset_id=preset_id,
        symbols=symbols,
    )
    rows = _sector_score_from_items(response.items, quality_min=quality_min)
    errors = [{"symbol": f.symbol, "detail": f.detail} for f in response.failures]
    markdown = _build_sector_markdown(rows=rows, errors=errors, universe=universe, quality_min=quality_min, scanned=len(symbols))
    return {
        "universe": universe,
        "quality_min": quality_min,
        "scanned": len(symbols),
        "sectors": rows,
        "errors": errors[:20],
        "markdown": markdown,
        "generated_at": datetime.now(UTC),
    }


@router.get("/sector-scores.md", response_class=PlainTextResponse)
async def sector_scores_markdown(
    universe: str = Query(default="nikkei225"),
    quality_min: float = Query(default=70, ge=0, le=100),
    scan_limit: int = Query(default=80, ge=1, le=225),
    provider: ProviderName = Query(default=ProviderName.AUTO),
    preset_id: str = Query(default="jp_stock_day"),
    settings: Settings = Depends(get_settings),
) -> str:
    data = await sector_scores(
        universe=universe,
        quality_min=quality_min,
        scan_limit=scan_limit,
        provider=provider,
        preset_id=preset_id,
        settings=settings,
    )
    return data["markdown"]
