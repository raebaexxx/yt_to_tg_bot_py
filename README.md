# YouTube to Telegram Bot

Telegram bot that downloads videos from YouTube and sends them directly to Telegram. Supports quality selection, automatic file splitting for videos larger than 2GB, and playlist downloads.

## Features

- **Quality Selection** — Choose from 1080p, 720p, 480p, 360p, or audio only via inline buttons
- **Auto-split** — Videos larger than 2GB are automatically split into parts
- **Video format** — All videos are sent as playable video (not as files) in MP4 H.264
- **Playlist support** — Download entire playlists or select individual videos
- **Download history** — Stored in SQLite

## Prerequisites

- Python 3.10+
- FFmpeg (required for video conversion and splitting)

## Installation

### Local

```bash
# Clone the repository
git clone https://github.com/raebaexxx/yt_to_tg_bot_py.git
cd yt_to_tg_bot_py

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and add your bot token

# Run
python bot/main.py
```

### Docker

```bash
# Build
docker build -t yt-tg-bot .

# Run
docker run --env-file .env yt-tg-bot
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather | Required |
| `MAX_FILE_SIZE_MB` | Maximum file size before splitting (MB) | 1900 |
| `DOWNLOAD_DIR` | Directory for temporary downloads | ./downloads |
| `LOG_LEVEL` | Logging level | INFO |

## Getting a Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the instructions
3. Copy the token and paste it into `.env`

## Project Structure

```
├── bot/
│   ├── main.py          # Entry point
│   ├── handlers.py      # Message & callback handlers
│   ├── keyboards.py     # Inline keyboards
│   └── states.py        # FSM states
├── services/
│   ├── youtube.py       # yt-dlp integration
│   ├── downloader.py    # Download & MP4 conversion
│   └── splitter.py      # FFmpeg file splitting (>2GB)
├── database/
│   └── models.py        # SQLite models (users, history)
├── utils/
│   ├── helpers.py       # URL validation, formatting
│   └── cleanup.py       # Temp file cleanup
├── config.py            # Environment configuration
├── requirements.txt
├── Dockerfile
└── .env.example
```

## License

MIT
