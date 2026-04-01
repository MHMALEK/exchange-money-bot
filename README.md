# Exchange money bot

A **personal**, **non‑commercial** Telegram bot. The goal is modest: make it a bit simpler for **people in Iran** to find each other for **ریال ↔ euro / US dollar** deals—posting offers, browsing a small catalog, and seeing rough **ریالی equivalents** from public rate snapshots.

It does **not** move money, hold funds, or vet counterparties. You’re always responsible for who you trust and how you settle.

---

### What it does (high level)

- **Sign‑up / consent** flow in Persian  
- **Sell flow**: post an amount in EUR or USD; optional publish to a **listings channel** (bot must be admin there)  
- **Buy / browse** helpers and optional **auth** (Telegram channel and/or group) when configured  
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

The repo includes a **Dockerfile** and a **GitHub Actions** workflow (`.github/workflows/deploy.yml`) that builds, pushes to **GHCR**, and **SSH‑deploys** to a VPS. The workflow runs `docker run` with `-e` so values are not interpolated into the shell script (safe for passwords and URLs).

#### Required (Secrets)

| Name | Purpose |
|------|---------|
| `VM_HOST`, `VM_USER`, `VM_SSH_KEY` | SSH into the deployment server |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `DATABASE_URL` | Async SQLAlchemy URL (e.g. Postgres); includes credentials |
| `TELEGRAM_LISTINGS_CHANNEL_ID` | **Required.** Channel where listings are posted; bot must be admin. Also used for the «open channel» / listings CTA. |

**Auth (optional)** — unrelated to where listings are posted:

- **`TELEGRAM_MEMBERSHIP_CHANNEL_ID`** — If set, users must be members of this channel when the gate is on.
- **`TELEGRAM_MEMBERSHIP_GROUP_ID`** — If set, users must be members of this group when the gate is on.
- **Both set** → user must satisfy **both** (channel **and** group).
- **Neither set** → no membership gate. In dev you can also set variable `TELEGRAM_DISABLE_MEMBERSHIP_GATE=true` to skip auth even when ids are set.

#### Optional (Secrets)

Passed into the container only when non‑empty (see `deploy.yml`).

| Name | Purpose |
|------|---------|
| `TELEGRAM_MEMBERSHIP_CHANNEL_ID` | Auth channel (optional) |
| `TELEGRAM_MEMBERSHIP_GROUP_ID` | Auth group/supergroup (optional) |
| `TELEGRAM_CHANNEL_INVITE_URL` | Listings channel join/open link (helps when the channel is private) |
| `TELEGRAM_MEMBERSHIP_GROUP_INVITE_URL` | Invite link for the auth group button |

#### Optional (Variables)

| Name | Purpose |
|------|---------|
| `TELEGRAM_DISABLE_MEMBERSHIP_GATE` | `true` only for dev‑style deploys |
| `API_BASE_URL` | If the bot should call the HTTP API after upsert |
| `IRR_RATES_TTL_SECONDS`, `IRR_USD_JSON_URL`, `IRR_EUR_JSON_URL` | Spot‑rate cache / JSON sources |

#### Secrets vs variables

Use **Secrets** for tokens, `DATABASE_URL`, and invite links. Use **Variables** for non‑sensitive toggles and URLs. Local parity: `.env.example` / `.env` use the same names.

---

### Disclaimer

**Not** financial, legal, or tax advice. Rates shown are indicative only. This project is a hobby; use it at your own risk.
