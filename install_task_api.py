#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'app'/'main.py'
if not p.exists():
    raise SystemExit('app/main.py が見つかりません。プロジェクトルートで実行してください。')
text=p.read_text(encoding='utf-8')
imp='from app.services.daily_task_api import router as daily_task_router\n'
inc='app.include_router(daily_task_router)\n'
if imp not in text:
    lines=text.splitlines(keepends=True)
    at=0
    for i,line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            at=i+1
    lines.insert(at,imp)
    text=''.join(lines)
if inc not in text:
    lines=text.splitlines(keepends=True)
    inserted=False
    for i,line in enumerate(lines):
        if 'FastAPI(' in line and '=' in line:
            j=i
            while j<len(lines):
                if ')' in lines[j]:
                    lines.insert(j+1,inc)
                    inserted=True
                    break
                j+=1
            break
    if not inserted:
        lines.append('\n'+inc)
    text=''.join(lines)
p.write_text(text,encoding='utf-8')
print('OK: ChatGPTタスク用APIを登録しました。')
