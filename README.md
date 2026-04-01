# Exchange money bot

A **personal**, **non‑commercial** Telegram bot. The goal is modest: make it a bit simpler for **people in Iran** to find each other for **ریال ↔ euro / US dollar** deals—posting offers, browsing a small catalog, and seeing rough **ریالی equivalents** from public rate snapshots.

It does **not** move money, hold funds, or vet counterparties. You’re always responsible for who you trust and how you settle.

---

### What it does (high level)

- **Sign‑up / consent** flow in Persian  
- **Sell flow**: post an amount in EUR or USD; optional publish to a **listings channel** (bot must be admin there)  
- **Buy / browse** helpers and **channel membership** gate when configured  
- Small **FastAPI** app alongside the bot (e.g. for integrations); **SQLite** or **Postgres** via `DATABASE_URL`

---

### Run locally

Requires **Python 3.9+**.

```bash
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN and the rest
pip install -e ".[dev]"
python run_bot.py      # Telegram bot
# optional: python run_api.py   # FastAPI on :8000
```

Docker starts **both** the API and the bot (see `scripts/docker-entrypoint.sh`).

Tests: `pytest`

---

### Deploy

The repo includes a **Dockerfile** and a **GitHub Actions** workflow (`.github/workflows/deploy.yml`) that builds, pushes to **GHCR**, and **SSH‑deploys** to a VPS. The workflow runs `docker run` with `-e` so values are not interpolated into the shell script

#### Required (Secrets)

| Name | Purpose |
|------|---------|
| `VM_HOST`, `VM_USER`, `VM_SSH_KEY` | SSH into the deployment server |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `DATABASE_URL` | Async SQLAlchemy URL (e.g. Postgres); includes credentials |
| `TELEGRAM_LISTINGS_CHANNEL_ID` | Channel where listings are posted (`@username` or `-100…`); bot must be admin |

#### Optional (Secrets)

Omit any you do not use; they are only passed into the container when non‑empty.

| Name | Purpose |
|------|---------|
| `TELEGRAM_MEMBERSHIP_CHANNEL_ID` | Different channel for membership checks only (rare); defaults to listings channel when unset |
| `TELEGRAM_MEMBERSHIP_GROUP_ID` | Optional group/supergroup; with a channel id, user passes if member of **either** (OR) |


---

### Disclaimer

**Not** financial, legal, or tax advice. Rates shown are indicative only. This project is a hobby; use it at your own risk.
