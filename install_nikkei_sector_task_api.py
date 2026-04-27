#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
main = ROOT / "app" / "main.py"
if not main.exists():
    raise SystemExit("app/main.py が見つかりません。プロジェクトルートで実行してください。")

text = main.read_text(encoding="utf-8")
imp = "from app.services.nikkei_sector_task_api import router as nikkei_sector_task_router\n"
inc = "app.include_router(nikkei_sector_task_router)\n"

if imp not in text:
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, imp)
    text = "".join(lines)

if inc not in text:
    lines = text.splitlines(keepends=True)
    inserted = False
    for i, line in enumerate(lines):
        if line.startswith("app = FastAPI("):
            j = i
            while j < len(lines):
                if lines[j].strip() == ")":
                    lines.insert(j + 1, inc)
                    inserted = True
                    break
                j += 1
            break
    if not inserted:
        lines.append("\n" + inc)
    text = "".join(lines)

main.write_text(text, encoding="utf-8")
print("OK: 日経225スキャン・セクター別スコアAPIを登録しました。")
