"""YouTube URL の検出・正規化・videoId 抽出。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# テキスト検索の上限（DoS 対策）
_MAX_TEXT_LEN = 100_000
_MAX_URLS = 50

_URL_IN_TEXT = re.compile(
    r"(https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtube-nocookie\.com)/[^\s<>\"']+"
    r"|https?://youtu\.be/[^\s<>\"']+)",
    re.IGNORECASE,
)
_VIDEO_ID_IN_URL = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|live/|shorts/|embed/|v/)"
    r"|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)
_VIDEO_ID_BODY = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "youtu.be",
        "youtube-nocookie.com",
        "music.youtube.com",
    }
)


def _normalize_host(host: str) -> str:
    """www. / m. プレフィックスのみ除去。music. は誤って削らない。"""
    h = (host or "").strip().lower().rstrip(".")
    parts = h.split(".")
    if len(parts) > 2 and parts[0] in ("www", "m"):
        return ".".join(parts[1:])
    return h


def is_youtube_url(url: str) -> bool:
    """許可ホスト・スキームの YouTube URL かどうか。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    return _normalize_host(hostname) in _YOUTUBE_HOSTS


def _extract_video_id_unchecked(url: str) -> str | None:
    """ホスト検証済みを前提に videoId を抽出する（内部専用）。"""
    match = _VIDEO_ID_IN_URL.search(url)
    if match:
        return match.group(1)

    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    values = parse_qs(parsed.query).get("v")
    if values and _VIDEO_ID_BODY.fullmatch(values[0]):
        return values[0]
    return None


def extract_video_id(url: str) -> str | None:
    """許可ホストの URL から 11 文字の videoId を抽出する。"""
    if not is_youtube_url(url):
        return None
    return _extract_video_id_unchecked(url)


def find_youtube_urls(text: str) -> list[str]:
    """テキスト中の、単一動画を指す YouTube URL を重複なく返す（出現順）。

    同一 videoId の別 URL 形式は最初の 1 件のみ残す。

    videoId を抽出できない URL（プレイリスト・チャンネルページ等）は対象外とする。
    is_youtube_url はホスト名のみで判定しパスまでは見ないため、これらを許してしまうと
    yt-dlp 側の noplaylist（動画ID・プレイリストIDが同時に含まれる URL の曖昧さ解消に
    しか効かず、プレイリスト/チャンネル単体の URL には効かない）をすり抜け、
    チャンネル全体を無制限にダウンロードしようとする経路になる。videoId を必須にする
    ことで、そのような URL を検出の時点で除外する。
    """
    if not text:
        return []
    if len(text) > _MAX_TEXT_LEN:
        text = text[:_MAX_TEXT_LEN]

    found: list[str] = []
    seen_urls: set[str] = set()
    seen_ids: set[str] = set()

    for match in _URL_IN_TEXT.finditer(text):
        url = match.group(1).rstrip(".,;:!?)>\"'")
        if url in seen_urls:
            continue
        if not is_youtube_url(url):
            continue

        vid = _extract_video_id_unchecked(url)
        if not vid or vid in seen_ids:
            continue
        seen_ids.add(vid)

        seen_urls.add(url)
        found.append(url)
        if len(found) >= _MAX_URLS:
            break
    return found
