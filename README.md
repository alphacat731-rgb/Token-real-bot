# Token Real Bot 🐈

A hybrid Discord bot for a chaotic Token-style mascot.

## What it does

- Replies when Token is mentioned or receives a DM.
- Uses the Gemini API for conversational replies when `GEMINI_API_KEY` is available.
- Falls back to the local `messages.py` pool if the AI API is unavailable.
- Keeps a small rolling conversation history per channel.
- Shows a short typing indicator before replies.
- Provides `/token`, `/token_mood`, and `/token_forget` slash commands.
- Occasionally sends a random local Token message as an idle event.

## Setup

### 1. Create the Discord application

Create a Discord application and add a bot user. Enable the **Message Content Intent** on the bot settings page, because Token needs access to message text when responding to mentions and DMs.

Invite the bot to your server with permissions to view channels, send messages, and read message history.

### 2. Get a Gemini API key

Create a Gemini API key in Google AI Studio and keep it private. The bot uses the official `google-genai` Python SDK.

The default model is `gemini-3.7-flash`. You can change it with `GEMINI_MODEL` without editing the code.

### 3. Install dependencies

```bash
python -m venv .venv
```

Activate the virtual environment, then run:

```bash
pip install -r requirements.txt
```

### 4. Configure secrets

Copy `.env.example` to `.env` and fill in your real values:

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.7-flash
```

Do not commit `.env` to GitHub.

### 5. Start Token

```bash
python bot.py
```

You should see a startup message showing the bot account, guild count, and whether the Gemini backend is online.

## How the hybrid mode works

Normal conversation trigger:

```text
@Token what are you doing?
             ↓
       Gemini Token reply
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

Put local fallback messages in `messages.py`. The bot imports the `messages` list and randomly selects from it when the Gemini backend is unavailable or when an idle event fires.

## Notes

The bot is designed to be run as a long-lived process on a machine or hosting service. GitHub itself stores the source code; it is not the runtime host for a continuously connected Discord Gateway bot.
