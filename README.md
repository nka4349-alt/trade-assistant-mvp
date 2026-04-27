# Trade Assistant MVP

FX と株デイトレ向けの **個人用** 補佐ツールの MVP です。

今回の実装範囲:

- Phase 1: ローソク足 + ダブル / トリプル + ヘッドアンドショルダー + トライアングル + フラッグの検出と可視化
- UI改善: 現在サイン表示、最新順サイドバー、カード連動のチャート強調、単独表示、時間足ヒント
- Phase 2: ヒューリスティックな成功確率、推奨指値、損切り、TP1 / TP2 の提案
- Phase 3: ニュースの簡易要約とアラート土台（Alpaca 接続またはデモ）
- 保存機能: 監視銘柄リスト、足セット、フィルタをブラウザに保存して次回起動時に復元


## 現在対応しているチャートパターン

現時点で検出ロジックが入っているのは次の 18 種です。

- ダブルボトム
- ダブルトップ
- トリプルボトム
- トリプルトップ
- ヘッドアンドショルダー・トップ
- ヘッドアンドショルダー・ボトム
- 上昇トライアングル
- 下降トライアングル
- 上昇フラッグ
- 下降フラッグ
- 上昇チャネル
- 下降チャネル
- 上昇ウェッジ
- 下降ウェッジ
- 上昇ペナント
- 下降ペナント
- ソーサー・トップ
- ソーサー・ボトム

## 構成

```text
trade_assistant_mvp/
├─ app/
│  ├─ main.py                # FastAPI エントリポイント
│  ├─ config.py              # 環境変数
│  ├─ schemas.py             # API スキーマ
│  ├─ services/
│  │  ├─ data_providers.py   # demo / OANDA / Alpaca
│  │  ├─ patterns.py         # パターン検出
│  │  ├─ scoring.py          # 成功確率とトレードプラン
│  │  ├─ news.py             # ニュース要約
│  │  └─ recommendations.py  # 注目銘柄スキャンと深掘り理由
│  └─ static/
│     ├─ index.html
│     ├─ styles.css
│     ├─ app.js
│     └─ vendor/plotly.min.js
├─ tests/
├─ requirements.txt
└─ .env.example
```

## セットアップ

```bash
cd trade_assistant_mvp
python -m venv .venv
source .venv/bin/activate   # Windows は .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

起動後: `http://127.0.0.1:8000`

## まず試す方法

### デモで確認

- FX ダブルボトム: `BOT_USDJPY`
- FX トリプルトップ寄り: `TOP_EURUSD`
- 株ダブルボトム: `BOT_AAPL`
- 株トリプルトップ寄り: `TOP_TSLA`

### 実データで確認

- FX: `provider=oanda`
- 株: `provider=alpaca`
- `provider=auto` にすると、キーがあれば実データ、なければ demo を使います。

## 環境変数

`.env.example` を参照してください。

- `OANDA_TOKEN`
- `OANDA_ACCOUNT_ID`（現状は将来拡張用）
- `OANDA_BASE_URL`
- `ALPACA_KEY_ID`
- `ALPACA_SECRET_KEY`
- `ALPACA_DATA_URL`
- `ALPACA_FEED`

## 実装上のポイント

### Phase 1

- ピボット高安を抽出
- その並びから反転型と継続型を判定
- 水平線だけでなく、ネックライン / 支持線 / 抵抗線 / フラッグ上辺下辺などのガイド線を API で返却
- フロントは Plotly で単独表示・ガイド線描画・現在サイン強調に対応

### Phase 2

現時点では**ヒューリスティック**です。表示している probability は ML 学習済みの確率ではありません。

置き換え口は `app/services/scoring.py` にあります。将来やること:

1. ジャーナルを蓄積
2. パターンごとに feature を保存
3. XGBoost を学習
4. `CalibratedClassifierCV` などで確率校正
5. `score_pattern()` を学習済みモデル呼び出しに差し替え

### Phase 3

- Alpaca の news endpoint を使う土台を実装
- デモモードではキーワードベースの疑似センチメント
- 本番では FinBERT や LLM 要約に差し替え可能

## 注目銘柄スキャン

- おすすめ足セットから FXデイトレ / 日本株デイトレ / スイング を選択できます。
- 注目銘柄は 日足の前日高値安値 / 重要ライン、上位足の方向、現在サイン、ニュース をまとめて点数化します。
- 各カードから 上位足 / パターン足 / 実行足 をワンクリックで開けます。

## 監視銘柄リストの保存

- 「監視銘柄を保存」を押すと、現在の監視銘柄、足セット、表示中の時間足、品質フィルタ、現在サインのみ、確定のみがブラウザに保存されます。
- 次回 `http://127.0.0.1:8000` を開いたときに、保存内容が自動復元されます。
- 保存先はブラウザの `localStorage` です。別ブラウザや別PCには自動共有されません。
- 「保存リストを復元」は現在の足セットに対応する保存銘柄を入力欄へ戻します。
- 「保存削除」はブラウザ内の保存データだけを削除します。


## API

### `GET /api/health`

疎通確認。

### `GET /api/snapshot`

クエリ例:

```text
/api/snapshot?asset_class=fx&symbol=BOT_USDJPY&timeframe=5m&provider=demo&limit=240
```

レスポンス:

- candles
- patterns
- news
- provider
- generated_at

## 次にやるとよい拡張

1. ジャーナル保存（SQLite）
2. パターン feature 永続化
3. バックテスト
4. XGBoost + 確率校正
5. OANDA / Alpaca の発注連携
6. Discord / LINE 通知

## 注意

- この MVP は個人用の補佐ツール前提です。
- Probability は学習済みモデルではなく、ルールベースに近い初期実装です。
- FX のスプレッドやニュース反応まで厳密に見たい場合は、実データ連携とログ保存を先に追加してください。

## 日本株の使い方

- `provider=auto` なら、日本株コード `7203` や `6758.T` を入れたときは `yfinance` を優先して使います。
- 米国株は Alpaca のキーがあれば Alpaca、なければ `yfinance` を使います。
- 日本株の例: `7203`, `6758`, `9984`, `7203.T`
- 米国株の例: `AAPL`, `NVDA`, `TSLA`

> 補足: `yfinance` は個人の研究・検証向けに使いやすい反面、イントラデイは直近データ中心です。

### `GET /api/recommendations`

クエリ例:

```text
/api/recommendations?asset_class=stock&provider=auto&preset_id=jp_stock_day&watchlist=7203,6758,9984
```

レスポンス:

- items: 注目銘柄カード
- failures: 取得失敗した銘柄
- daily_timeframe / upper_timeframe / pattern_timeframe / entry_timeframe
- generated_at
