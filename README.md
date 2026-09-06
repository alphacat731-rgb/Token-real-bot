# Token Real Bot 🐈

A hybrid Discord bot for a chaotic Token-style mascot.

## What it does

- Replies when Token is mentioned or receives a DM.
- Uses an OpenAI model for conversational replies when `OPENAI_API_KEY` is available.
- Falls back to the local `messages.py` pool if the AI API is unavailable.
- Keeps a small rolling conversation history per channel.
- Shows a short typing indicator before replies.
- Provides `/token`, `/token_mood`, and `/token_forget` slash commands.
- Occasionally sends a random local Token message as an idle event.

## Setup

### 1. Create the Discord application

Create a Discord application and add a bot user. Enable the **Message Content Intent** on the bot settings page, because Token needs access to message text when responding to mentions and DMs.

Invite the bot to your server with permissions to view channels, send messages, and read message history.

### 2. Install dependencies

```bash
python -m venv .venv
```

Activate the virtual environment, then run:

```bash
pip install -r requirements.txt
```

### 3. Configure secrets

Copy `.env.example` to `.env` and fill in your real values:

```env
DISCORD_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.6-luna
```

Do not commit `.env` to GitHub.

### 4. Start Token

```bash
python bot.py
```

You should see a startup message showing the bot account, guild count, and whether the AI backend is online.

## How the hybrid mode works

Normal conversation trigger:

```text
@Token what are you doing?
             ↓
       AI Token reply
```

AI unavailable:

```text
@Token what are you doing?
             ↓
     local random message
```

Idle event:

```text
no one talks to Token for a while
             ↓
     random Token message
```

## Message library

Put local fallback messages in `messages.py`. The bot imports the `messages` list and randomly selects from it when the AI backend is unavailable or when an idle event fires.

## Notes

The bot is designed to be run as a long-lived process on a machine or hosting service. GitHub itself stores the source code; it is not the runtime host for a continuously connected Discord Gateway bot.
