# Render Deploy

## Build Command

pip install -r requirements.txt

## Start Command

uvicorn app.main:app --host 0.0.0.0 --port $PORT

## Health Check Path

/api/health
