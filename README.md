# Quran Malayalam Bot 🌙

A Telegram bot that serves Quranic verse meanings in Malayalam.

## Features

- Look up any verse by sending `surah:verse` — example: `1:1` or `2:255`
- Inline mode — use in any chat by typing `@YourBotUsername 2:255`
- Language toggle — choose Malayalam only, Arabic only, or both (Arabic coming soon)

## Commands

| Command | Description |
|---|---|
| /start | Welcome message and instructions |
| /help | How to use the bot |
| /settings | Choose your language preference |

## Setup

### Environment Variables

| Variable | Description |
|---|---|
| BOT_TOKEN | Your Telegram bot token from BotFather |

### Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your BOT_TOKEN
python main.py
```

### Deploying to Railway

1. Push this repo to GitHub
2. Create a new project on Railway and connect the GitHub repo
3. Add BOT_TOKEN as an environment variable in Railway dashboard
4. Railway will deploy automatically

## Data Files

- `quran.json` — Malayalam translation of the Quran (114 Surahs, 6236 verses)
- Arabic JSON will be added in a future update

## Adding Arabic Support Later

When the Arabic JSON file is ready, it will be loaded alongside `quran.json`
and the language toggle will become fully functional for Arabic and both modes.
