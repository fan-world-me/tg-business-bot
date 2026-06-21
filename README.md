# tg-business-bot

Telegram business-bot з автовідповідями на AI, логами в Cloudflare D1, медіа в R2.

## Features
- Auto-replies via Groq → NVIDIA fallback
- Photo / video / voice / sticker / GIF / video note analysis
- Cloudflare D1 conversation logs
- Forwarded messages saved to D1 + media uploaded to R2
- `/on` `/off` `/status` `/muted` `/mute` `/unmute`
- 🔇 Mute button in every notification
- Missed call → auto-reply

## Setup

```bash
cp .env.example .env
# fill in all values

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

## Deploy (Fly.io)

```bash
fly launch --name tg-business-bot --no-deploy
fly secrets import < .env
fly deploy
```

## License

GPL-3.0 — see [LICENSE](LICENSE)
