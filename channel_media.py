"""公開メッセージ用メディアアップロード。"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from channel_http import MEDIA_BASE
from exceptions import ChannelAPIError

logger = logging.getLogger(__name__)

_JS_ENCODE_URI_COMPONENT_SAFE = "!'()*"

_BROWSER_MIME_BY_EXT: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".m4v": "video/x-m4v",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".json": "application/json",
    ".zip": "application/zip",
}


def encode_uri_component(value: str) -> str:
    return quote(value, safe=_JS_ENCODE_URI_COMPONENT_SAFE)


def guess_content_type(filename: str) -> str:
    """File.type ?? application/octet-stream 相当。"""
    suffix = Path(filename).suffix.lower()
    if suffix in _BROWSER_MIME_BY_EXT:
        return _BROWSER_MIME_BY_EXT[suffix]
    guessed, _ = mimetypes.guess_type(filename)
    return (guessed or "").strip() or "application/octet-stream"


class MediaUploader:
    def __init__(
        self,
        *,
        channel_id: str,
        timeout: float,
        session: requests.Session,
        execute_with_auth: Callable[..., dict[str, Any]],
    ) -> None:
        self._channel_id = channel_id
        self._timeout = timeout
        self._session = session
        self._execute_with_auth = execute_with_auth

    def upload_public_message_file(
        self,
        path: Path,
        *,
        filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        size = path.stat().st_size
        if size <= 0:
            raise ChannelAPIError(f"upload_file: 空ファイルです: {path}")

        url = (
            f"{MEDIA_BASE}/pub-file/{self._channel_id}/message/"
            f"{encode_uri_component(filename)}"
        )
        timeout = max(self._timeout, 120.0)
        ct = (content_type or "").strip() or "application/octet-stream"

        def do() -> requests.Response:
            headers = {
                k: v
                for k, v in self._session.headers.items()
                if k.lower() not in ("content-type", "content-length", "accept")
            }
            headers["Content-Type"] = ct
            headers["Accept"] = "application/json"
            # channel.works → media.channel.io は cross-site
            headers["sec-fetch-site"] = "cross-site"
            with path.open("rb") as f:
                return self._session.post(
                    url, data=f, headers=headers, timeout=timeout
                )

        body = self._execute_with_auth("upload_file", do)
        file_dto: dict[str, Any] = {
            "id": body.get("id"),
            "key": body.get("key"),
            "name": body.get("name") or filename,
            "size": body.get("size") or size,
            "contentType": body.get("contentType") or ct,
            "bucket": body.get("bucket"),
        }
        if not file_dto.get("key") or not file_dto.get("bucket"):
            raise ChannelAPIError(
                "upload_file: 応答に key/bucket がありません", body=body
            )
        return file_dto
