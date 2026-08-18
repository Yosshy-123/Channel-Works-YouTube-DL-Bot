"""アプリケーション全体で共有する例外クラス。"""

from __future__ import annotations


class StreamError(Exception):
    """動画ストリーム取得全般のエラー。"""


class YtdlpError(StreamError):
    """yt-dlp による想定内の取得失敗。"""


class ChannelAPIError(Exception):
    """Channel Desk API 呼び出しのエラー。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: object = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
