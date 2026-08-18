"""Channel Desk 認証: x-account (JWT) トークンの状態管理。

フロント (channel-works) 準拠:
- 未所持・期限切れの x-account は送らない
- 応答ヘッダー x-account で更新
- 期限 5 分前から refresh (REFRESH_THRESHOLD_MS = 300000)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from http_headers import header_get
from jwt_token import expires_at_ms
from server_clock import get_clock

logger = logging.getLogger(__name__)

REFRESH_THRESHOLD_MS = 300_000
HEADER_NAME = "x-account"


class AccountAuth:
    """スレッドセーフな x-account 管理。"""

    def __init__(self, initial_token: str) -> None:
        self._lock = threading.RLock()
        self._token: str | None = (initial_token or "").strip() or None
        self._clock = get_clock()

    def get_token(self) -> str | None:
        with self._lock:
            return self._token

    def set_token(self, token: str | None) -> bool:
        cleaned = (token or "").strip() or None
        with self._lock:
            if cleaned == self._token:
                return False
            self._token = cleaned
        if cleaned:
            exp = expires_at_ms(cleaned)
            exp_s = (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp / 1000))
                if exp
                else "?"
            )
            logger.info("x-account 更新 exp=%s", exp_s)
        else:
            logger.warning("x-account をクリア")
        return True

    def get_auth_header(self) -> dict[str, str]:
        token = self.get_token()
        if not token or self.is_token_expired(token):
            return {}
        return {HEADER_NAME: token}

    def ingest_response_headers(self, headers: Any) -> bool:
        self._clock.ingest_date_header(headers)
        token = header_get(headers, HEADER_NAME)
        if not token:
            return False
        return self.set_token(token)

    def is_token_expired(self, token: str | None = None) -> bool:
        raw = token if token is not None else self.get_token()
        if not raw:
            return True
        exp = expires_at_ms(raw)
        if exp is None:
            return True
        return exp <= self._clock.now_ms()

    def should_refresh_token(self) -> bool:
        token = self.get_token()
        if not token:
            return True
        exp = expires_at_ms(token)
        if exp is None:
            return True
        return (exp - self._clock.now_ms()) <= REFRESH_THRESHOLD_MS
