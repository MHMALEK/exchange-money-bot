#!/bin/sh
set -e
PORT="${PORT:-8000}"
uvicorn exchange_money_bot.api.main:app --host 0.0.0.0 --port "$PORT" &
exec python run_bot.py
