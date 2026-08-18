"""Channel.works Desk API クライアント（メッセージ送受信）。

認証・トークン refresh・リトライは channel_session.ChannelSession に委譲する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from channel_http import API_BASE, message_body, new_request_id
from channel_media import MediaUploader, guess_content_type
from channel_session import ChannelSession
from config import Settings
from exceptions import ChannelAPIError


def extract_message_id(body: dict[str, Any] | None) -> str | None:
    """メッセージ送信 API の応答から、作成されたメッセージの id を取り出す。

    Desk API のメッセージ作成レスポンスの正確な形は未公開のため、想定される
    複数の形（{"message": {...}}／トップレベルに直接 id／{"messages": [...]})
    を順に試す防御的な実装。取得できなくても致命的ではない
    （呼び出し元は best-effort のループ防止に使うのみ）。
    """
    if not isinstance(body, dict):
        return None

    message = body.get("message")
    if isinstance(message, dict):
        mid = message.get("id")
        if mid is not None and str(mid).strip():
            return str(mid)

    mid = body.get("id")
    if mid is not None and str(mid).strip():
        return str(mid)

    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            mid = first.get("id")
            if mid is not None and str(mid).strip():
                return str(mid)

    return None


class ChannelClient:
    def __init__(self, settings: Settings) -> None:
        self._channel_id = settings.channel_id
        self._group_id = settings.group_id
        self._session = ChannelSession(settings)
        self._media = MediaUploader(
            channel_id=self._channel_id,
            timeout=self._session.default_timeout,
            session=self._session.http,
            execute_with_auth=self._session.execute_with_auth,
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> ChannelClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _messages_url(self, *, query: str = "") -> str:
        base = (
            f"{API_BASE}/channels/{self._channel_id}"
            f"/groups/{self._group_id}/messages"
        )
        return f"{base}?{query}" if query else base

    def send_text(self, text: str, *, request_id: str | None = None) -> dict[str, Any]:
        rid = request_id or new_request_id()
        return self._session.request(
            "POST",
            self._messages_url(),
            json_body=message_body(request_id=rid, text=text, files=None),
            action="send_text",
            timeout=5.0,
        )

    def send_file(
        self,
        filepath: str | Path,
        *,
        text: str = "",
        filename: str | None = None,
        request_id: str | None = None,
        allowed_root: Path | None = None,
    ) -> dict[str, Any]:
        raw = Path(filepath)
        if raw.is_symlink():
            raise ChannelAPIError(f"send_file: シンボリックリンクは許可しません: {raw}")
        path = raw.resolve()
        if not path.is_file():
            raise ChannelAPIError(f"send_file: ファイルが存在しません: {path}")
        if allowed_root is not None:
            root = allowed_root.resolve()
            if not path.is_relative_to(root):
                raise ChannelAPIError(
                    f"send_file: 許可ディレクトリ外のファイルです: {path}"
                )

        fname = filename or path.name
        content_type = guess_content_type(fname)
        file_dto = self._media.upload_public_message_file(
            path, filename=fname, content_type=content_type
        )
        rid = request_id or new_request_id()
        return self._session.request(
            "POST",
            self._messages_url(),
            json_body=message_body(request_id=rid, text=text, files=[file_dto]),
            action="send_file",
            timeout=5.0,
        )

    def get_recent_messages(self, limit: int) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        data = self._session.request(
            "GET",
            self._messages_url(
                query=f"sortOrder=desc&limit={int(limit)}&logFolded=false"
            ),
            action="get_recent_messages",
            max_network_retries=1,
        )
        messages = data.get("messages") or []
        return messages if isinstance(messages, list) else []
