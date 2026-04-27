# 日経225スキャン・セクター別スコアAPI

追加されるAPI:

- `/api/task/nikkei225-buy-candidates`
- `/api/task/nikkei225-buy-candidates.md`
- `/api/task/sector-scores`
- `/api/task/sector-scores.md`

ChatGPT TASK には `.md` のURLを使うのがおすすめです。

## 寄り前

```text
https://trade-assistant-mvp.onrender.com/api/task/nikkei225-buy-candidates.md?mode=preopen&universe=daytrade&quality_min=70&limit=8&scan_limit=50&provider=auto
```

## 大引け後

```text
https://trade-assistant-mvp.onrender.com/api/task/nikkei225-buy-candidates.md?mode=afterclose&universe=nikkei225&quality_min=70&limit=8&scan_limit=80&provider=auto
```

## セクター別スコア

```text
https://trade-assistant-mvp.onrender.com/api/task/sector-scores.md?universe=nikkei225&quality_min=70&scan_limit=80&provider=auto
```
