# Clyde Discord Helper

Clyde is a female Discord-native helper built from the Token bot project, but designed as a separate assistant rather than a Token character bot.

## What Clyde does

- Replies when mentioned or when she receives a DM.
- Uses Groq GPT-OSS for normal conversation.
- Uses Groq Qwen 3.6 27B for image understanding.
- Falls back to Gemini when the primary provider is unavailable.
- Keeps persistent SQLite conversation/user memory.
- Understands basic server, channel, member, and role context.
- Provides Discord-native slash commands for utilities, polls, moderation, announcements, avatars, server info, user info, and memory management.
- Performs moderation actions only through Discord permission checks and role hierarchy.

## Environment

Copy `.env.example` to `.env` and set:

```env
DISCORD_TOKEN=your_clyde_discord_bot_token
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_VISION_MODEL=qwen/qwen3.6-27b
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.7-flash
CLYDE_MEMORY_DB=clyde_memory.db
```

Never commit `.env`.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Run:

```bash
python3 clyde.py
```

## Discord permissions

Clyde needs the Message Content Intent for mention/DM conversation. Give her the normal permissions needed for the tools you intend to use. Moderation commands additionally require the corresponding Discord permission and respect Discord role hierarchy.

## Vision

Image requests use `qwen/qwen3.6-27b` through Groq first. GIFs are converted to a PNG first frame with Pillow so they can be handled consistently. Gemini is kept as the secondary vision provider.

## Suggested 24/7 systemd service

Use the virtual-environment Python directly from systemd instead of relying on an interactive `source .venv/bin/activate` shell.

```ini
[Unit]
Description=Clyde Discord Helper
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/home/YOUR_LINUX_USER/Clyde-bot
ExecStart=/home/YOUR_LINUX_USER/Clyde-bot/.venv/bin/python /home/YOUR_LINUX_USER/Clyde-bot/clyde.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Notes

GitHub stores the source; the Discord Gateway connection runs on your Raspberry Pi or another host. Clyde is intentionally separate from Token so the Token project can keep its own personality and runtime.
