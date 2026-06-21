# tgbot — Telegram Business Bot

Telegram business-bot with AI auto-replies, Cloudflare AI Gateway, D1 logging, and media analysis.

## Features
- Auto-replies in business chats via Groq → NVIDIA fallback
- Cloudflare AI Gateway proxies all AI requests (keys stored in BYOK)
- Conversations logged to Cloudflare D1
- Media support: photos, voice, video notes, videos (frame + speech)
- `/on` `/off` `/status` commands for the owner

## Setup

### 1. Copy env
```bash
cp .env.example .env
# fill in all values
```

### 2. Create D1 table
```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query" \
  -H "Authorization: Bearer {D1_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"sql": "CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, conn_id TEXT NOT NULL, user_id INTEGER NOT NULL, user_name TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, ts TEXT NOT NULL);"}'
```

### 3. Run locally
```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
python src/main.py
```

### 4. Deploy to Fly.io
```bash
fly launch --name tgbot --no-deploy
fly secrets import < .env
fly deploy
```

## Commands
| Command | Description |
|---------|-------------|
| `/on`   | Enable auto-replies |
| `/off`  | Disable auto-replies |
| `/status` | Show current state |
