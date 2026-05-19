# YouTube to Telegram Bot

Telegram bot that downloads videos from YouTube and sends them directly to Telegram. Supports quality selection, automatic file splitting for videos larger than 2GB, and playlist downloads.

## Features

- **Quality Selection** -- Choose from 4K, 1080p, 720p, 480p, 360p, or audio only via inline buttons
- **Auto-split** -- Videos larger than 2GB are automatically split into parts
- **Streaming** -- All videos sent with `supports_streaming` and correct aspect ratio
- **Playlist support** -- Download entire playlists or select individual videos
- **Download history** -- Stored in SQLite
- **Fast downloads** -- Uses aria2c with 16 parallel connections
- **Cancellation** -- Cancel downloads mid-process with the Cancel button

## Prerequisites

- Python 3.12+
- FFmpeg (required for video conversion and splitting)
- aria2c (recommended for faster downloads)
- **Local Bot API Server** (required for videos >50MB)

## Local Bot API Server

Telegram Bot API has a **50MB upload limit** by default. To send videos up to 2GB, you must run a [local Bot API Server](https://core.telegram.org/bots/api#using-a-local-bot-api-server).

### Run via Docker (recommended)

```bash
docker pull aiogram/telegram-bot-api:latest

docker run -p 8081:8081 -e TELEGRAM_API_ID=YOUR_API_ID -e TELEGRAM_API_HASH=YOUR_API_HASH aiogram/telegram-bot-api:latest --timeout 3600
```

Get `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` at https://my.telegram.org

Then set in `.env`:
```
BOT_API_SERVER_URL=http://localhost:8081
```

## Installation

### Local

```bash
git clone https://github.com/raebaexxx/yt_to_tg_bot_py.git
cd yt_to_tg_bot_py

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your bot token

python bot/main.py
```

### Docker

```bash
docker build -t yt-tg-bot .

docker run --env-file .env yt-tg-bot
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather | Required |
| `BOT_API_SERVER_URL` | Local Bot API Server URL | `http://localhost:8081` |
| `MAX_FILE_SIZE_MB` | Max file size before splitting | `1900` |
| `DOWNLOAD_DIR` | Directory for temporary downloads | `./downloads` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Project Structure

```
├── bot/
│   ├── main.py          # Entry point, bot lifecycle
│   ├── handlers.py      # Message/callback handlers
│   ├── keyboards.py     # Inline keyboards
│   └── states.py        # FSM states
├── services/
│   ├── youtube.py       # yt-dlp wrappers
│   ├── downloader.py    # Download, codec detection, ffmpeg
│   └── splitter.py      # Video splitting for large files
├── database/
│   └── models.py        # SQLite models (users, history)
├── utils/
│   ├── helpers.py       # URL validation, formatting
│   ├── cleanup.py       # File/directory cleanup
│   └── progress.py      # Safe message editing
├── config.py            # Environment configuration
├── requirements.txt
├── Dockerfile
└── .env.example
```
