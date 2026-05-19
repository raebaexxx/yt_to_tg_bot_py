import requests
import logging
from typing import Optional
from config import TMDB_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

HEADERS = {
    "Authorization": f"Bearer {TMDB_API_KEY}",
    "Content-Type": "application/json",
}


def search(query: str, page: int = 1) -> list:
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY not set")
        return []

    url = f"{BASE_URL}/search/multi"
    params = {
        "query": query,
        "page": page,
        "include_adult": False,
    }

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            if item.get("media_type") not in ("movie", "tv"):
                continue
            results.append({
                "id": item["id"],
                "title": item.get("title") or item.get("name"),
                "year": _extract_year(item),
                "type": item["media_type"],
                "poster": f"{IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
                "overview": item.get("overview", ""),
                "vote": item.get("vote_average", 0),
                "tmdb_id": item["id"],
            })

        return results
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return []


def get_details(tmdb_id: int, media_type: str = "movie") -> Optional[dict]:
    if not TMDB_API_KEY:
        return None

    url = f"{BASE_URL}/{media_type}/{tmdb_id}"
    params = {"append_to_response": "external_ids"}

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        return {
            "tmdb_id": data["id"],
            "title": data.get("title") or data.get("name"),
            "year": _extract_year(data),
            "type": media_type,
            "overview": data.get("overview", ""),
            "poster": f"{IMAGE_BASE}{data['poster_path']}" if data.get("poster_path") else None,
            "imdb_id": data.get("external_ids", {}).get("imdb_id"),
            "runtime": data.get("runtime") or _get_episode_runtime(data),
            "seasons": data.get("number_of_seasons", 0) if media_type == "tv" else 0,
            "episodes": data.get("number_of_episodes", 0) if media_type == "tv" else 0,
            "vote": data.get("vote_average", 0),
            "genres": [g["name"] for g in data.get("genres", [])],
        }
    except Exception as e:
        logger.error(f"TMDB get_details failed: {e}")
        return None


def get_season_episodes(tmdb_id: int, season_number: int) -> list:
    if not TMDB_API_KEY:
        return []

    url = f"{BASE_URL}/tv/{tmdb_id}/season/{season_number}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        episodes = []
        for ep in data.get("episodes", []):
            episodes.append({
                "episode_number": ep["episode_number"],
                "title": ep.get("name", f"Episode {ep['episode_number']}"),
                "runtime": ep.get("runtime", 0),
                "overview": ep.get("overview", ""),
            })
        return episodes
    except Exception as e:
        logger.error(f"TMDB get_season_episodes failed: {e}")
        return []


def _extract_year(data: dict) -> int:
    date_str = data.get("release_date") or data.get("first_air_date", "")
    if date_str:
        try:
            return int(date_str.split("-")[0])
        except (ValueError, IndexError):
            pass
    return 0


def _get_episode_runtime(data: dict) -> int:
    episodes = data.get("episodes", [])
    if episodes:
        return episodes[0].get("runtime", 0)
    return 0
