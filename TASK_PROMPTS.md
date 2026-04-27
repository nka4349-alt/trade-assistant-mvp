# ChatGPTタスク完全連携用プロンプト

## 寄り前 8:30 用

次のURLを開いて、日本株の買い候補をMarkdownとして読み取り、日本語で上位候補を要約してください。これは投資助言ではなく売買補助スキャンとして扱ってください。

https://trade-assistant-mvp.onrender.com/api/task/buy-candidates.md?mode=preopen&universe=daytrade&quality_min=70&limit=5&scan_limit=30&provider=auto

## 大引け後 15:40 用

次のURLを開いて、翌日向けの日本株買い候補をMarkdownとして読み取り、日本語で上位候補を要約してください。これは投資助言ではなく売買補助スキャンとして扱ってください。

https://trade-assistant-mvp.onrender.com/api/task/buy-candidates.md?mode=afterclose&universe=swing&quality_min=70&limit=5&scan_limit=30&provider=auto
