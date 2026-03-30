FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY exchange_money_bot ./exchange_money_bot
COPY run_bot.py run_api.py ./

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
