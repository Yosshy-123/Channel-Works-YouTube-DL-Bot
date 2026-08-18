"""環境変数・実行設定。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

_MAX_MESSAGE_FETCH_LIMIT = 200
_MAX_YT_WORKERS = 16
_MAX_HTTP_TIMEOUT = 120.0
_MAX_POLL_IDLE_SLEEP = 60.0
_MAX_DOWNLOAD_FILESIZE_MB = 20_000
_MIN_SECRET_LEN = 8
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"必須の環境変数 {name} が未設定です。.env を確認してください。"
        )
    return value


def _require_secret(name: str) -> str:
    value = _require(name)
    if len(value) < _MIN_SECRET_LEN:
        raise RuntimeError(
            f"{name} が短すぎます（{_MIN_SECRET_LEN} 文字以上が必要）"
        )
    return value


def _require_id(name: str) -> str:
    value = _require(name)
    if not _ID_RE.fullmatch(value):
        raise RuntimeError(
            f"{name} の形式が不正です（英数字・ハイフン・アンダースコア、1〜128 文字）: "
            f"{value[:32]!r}"
        )
    return value


def _positive_int(name: str, default: int, *, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} は整数である必要があります: {raw!r}") from e
    if value < 1:
        raise RuntimeError(f"{name} は 1 以上である必要があります: {value}")
    if value > maximum:
        raise RuntimeError(f"{name} は {maximum} 以下である必要があります: {value}")
    return value


def _positive_float(name: str, default: float, *, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} は数値である必要があります: {raw!r}") from e
    if value <= 0:
        raise RuntimeError(f"{name} は 0 より大きい必要があります: {value}")
    if value > maximum:
        raise RuntimeError(f"{name} は {maximum} 以下である必要があります: {value}")
    return value


@dataclass(frozen=True)
class Settings:
    x_account_token: str
    session_cookie: str
    veil_id: str
    x_account_refresh: str
    channel_id: str
    group_id: str
    message_fetch_limit: int
    yt_workers: int
    http_timeout: float
    poll_idle_sleep: float
    max_download_filesize_mb: int

    @classmethod
    def load(cls) -> Settings:
        return cls(
            x_account_token=_require_secret("CH_X_ACCOUNT"),
            session_cookie=_require_secret("CH_SESSION_COOKIE"),
            veil_id=_require_secret("CH_VEIL_ID"),
            x_account_refresh=_require_secret("CH_X_ACCOUNT_REFRESH"),
            channel_id=_require_id("CH_CHANNEL_ID"),
            group_id=_require_id("CH_GROUP_YOUTUBE_DL"),
            message_fetch_limit=_positive_int(
                "MESSAGE_FETCH_LIMIT", 20, maximum=_MAX_MESSAGE_FETCH_LIMIT
            ),
            yt_workers=_positive_int("YT_WORKERS", 2, maximum=_MAX_YT_WORKERS),
            http_timeout=_positive_float(
                "HTTP_TIMEOUT", 15.0, maximum=_MAX_HTTP_TIMEOUT
            ),
            poll_idle_sleep=_positive_float(
                "POLL_IDLE_SLEEP", 0.5, maximum=_MAX_POLL_IDLE_SLEEP
            ),
            max_download_filesize_mb=_positive_int(
                "YT_MAX_FILESIZE_MB", 2_000, maximum=_MAX_DOWNLOAD_FILESIZE_MB
            ),
        )
