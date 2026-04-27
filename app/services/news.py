from __future__ import annotations

import statistics

from app.schemas import NewsArticle, NewsSummary


def summarize_news(articles: list[NewsArticle]) -> NewsSummary:
    if not articles:
        return NewsSummary(
            overall_bias="neutral",
            alert_level="none",
            one_line_summary="ニュースはまだ取得できていません。",
            why=["デモモードまたは未接続のためニュースなし"],
            articles=[],
        )

    avg_score = statistics.mean(article.sentiment_score for article in articles)
    if avg_score > 0.12:
        bias = "bullish"
    elif avg_score < -0.12:
        bias = "bearish"
    else:
        bias = "neutral"

    latest = articles[0]
    headlines = " / ".join(article.headline for article in articles[:2])
    if bias == "bearish":
        level = "warning"
        one_line = f"下落警戒: {headlines}"
        why = [
            f"直近ニュースの平均スコアが弱い ({avg_score:.2f})",
            f"最新ヘッドライン: {latest.headline}",
        ]
    elif bias == "bullish":
        level = "watch"
        one_line = f"上昇寄り: {headlines}"
        why = [
            f"直近ニュースの平均スコアが強め ({avg_score:.2f})",
            f"最新ヘッドライン: {latest.headline}",
        ]
    else:
        level = "watch"
        one_line = f"中立監視: {headlines}"
        why = [
            f"ニュースバイアスは中立圏 ({avg_score:.2f})",
            f"最新ヘッドライン: {latest.headline}",
        ]

    return NewsSummary(
        overall_bias=bias,
        alert_level=level,
        one_line_summary=one_line,
        why=why,
        articles=articles,
    )
