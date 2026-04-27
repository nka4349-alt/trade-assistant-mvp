# ChatGPTタスク完全連携API 追加パック

## 反映手順

```bash
cd ~/projects/trade_assistant_mvp/trade_assistant_mvp
unzip -o /mnt/c/Users/opu13/Downloads/trade_assistant_mvp_task_api_update.zip
python install_task_api.py
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

## ローカル確認

```bash
curl "http://127.0.0.1:8000/api/task/buy-candidates.md?mode=preopen&universe=daytrade&quality_min=70&limit=5&scan_limit=10&provider=auto"
```

## Renderへ反映

```bash
git add .
git commit -m "Add ChatGPT task daily buy candidate API"
git push
```
