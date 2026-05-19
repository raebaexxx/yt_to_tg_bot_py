# Movie & Series Bot

Telegram bot for downloading movies and series from Rutracker with voiceover selection and burned-in subtitles.

## Features

- **Search** — Movies & series via TMDB API
- **Releases** — Search Rutracker, grouped by voiceover and quality
- **Voiceover** — LostFilm, Кубик в Кубе, HDRezka, NewStudio, Original, etc.
- **Subtitles** — Auto-download from OpenSubtitles, burn into video via ffmpeg
- **Auto-split** — Files >2GB split into parts
- **Streaming** — Videos sent with `supports_streaming` and correct aspect ratio
- **Progress** — Real-time download/upload/burn-in progress with ETA

## Prerequisites

- Python 3.12+
- FFmpeg (required for subtitle burn-in and splitting)
- aria2c (recommended for faster downloads)
- **Local Bot API Server** (required for videos >50MB)

## API Keys (Free)

| Service | URL | Purpose |
|---------|-----|---------|
| TMDB | https://www.themoviedb.org/settings/api | Search movies/series, metadata |
| OpenSubtitles | https://www.opensubtitles.com/en/api | Download subtitles |
| Rutracker | Your account credentials | Download torrents |

## Installation

```bash
git clone https://github.com/raebaexxx/yt_to_tg_bot_py.git
cd movie_bot

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys and credentials

python bot/main.py
```

## Docker

```bash
docker build -t movie-bot .
docker run --env-file .env movie-bot
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token | Required |
| `TMDB_API_KEY` | TMDB API key | Required |
| `RUTRACKER_USERNAME` | Rutracker login | Required |
| `RUTRACKER_PASSWORD` | Rutracker password | Required |
| `OPENSUBTITLES_API_KEY` | OpenSubtitles API key | Required |
| `BOT_API_SERVER_URL` | Local Bot API Server | `http://localhost:8081` |
| `MAX_FILE_SIZE_MB` | Max file size before split | `1900` |
| `SUBTITLE_FONT_SIZE` | Burned subtitle font size | `24` |

## Project Structure

```
movie_bot/
├── bot/
│   ├── main.py          # Entry point
│   ├── handlers.py      # FSM handlers
│   ├── keyboards.py     # Inline keyboards
│   └── states.py        # FSM states
├── services/
│   ├── tmdb.py          # TMDB API
│   ├── torrent.py       # Rutracker + libtorrent
│   ├── subtitles.py     # OpenSubtitles API
│   ├── burner.py        # ffmpeg subtitle burn-in
│   ├── splitter.py      # File splitting
│   └── metadata.py      # Video probing
├── utils/
│   ├── helpers.py       # Formatting utilities
│   ├── cleanup.py       # File cleanup
│   └── progress.py      # Safe message editing
├── database/
│   └── models.py        # SQLite models
├── config.py            # Environment config
├── requirements.txt
├── Dockerfile
└── .env.example
```

## User Flow

```
1. /start → Welcome message
2. User: "Interstellar" → TMDB search → results with posters
3. Select movie → Rutracker search → releases grouped by voiceover
4. Select release → Choose quality
5. "Add subtitles?" → Select language → OpenSubtitles download
6. Download torrent → Progress with ETA
7. Burn-in subtitles (if selected) → Progress with ETA
8. Split if >2GB → Send to Telegram
```

## Local Bot API Server

```bash
docker run -p 8081:8081 \
  -e TELEGRAM_API_ID=YOUR_API_ID \
  -e TELEGRAM_API_HASH=YOUR_API_HASH \
  aiogram/telegram-bot-api:latest --timeout 3600
```

Get API ID/Hash at https://my.telegram.org
