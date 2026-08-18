"""x-account (JWT) の refresh 実行ロジック（フロント AuthTokenRefreshManager 相当）。

排他制御（同時に 1 回しか refresh を走らせない）は呼び出し元 (channel_session)
が担う。このクラスは「1 回の refresh をどう試みるか」にのみ責務を絞る。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

from account_auth import AccountAuth
from channel_http import (
    TOUCH_RETRY_MULTIPLIERS,
    TOUCH_TIMEOUT_FULL,
    TOUCH_TIMEOUT_REFRESH,
    safe_error_summary,
    touch_retry_delay_ms,
)

logger = logging.getLogger(__name__)


class TokenRefresher:
    """account/touch を呼び出して x-account を更新する。"""

    def __init__(
        self,
        *,
        touch_url: str,
        session: requests.Session,
        auth: AccountAuth,
        sync_credentials: Callable[[], None],
        ingest_response: Callable[[requests.Response], None],
    ) -> None:
        self._touch_url = touch_url
        self._session = session
        self._auth = auth
        self._sync_credentials = sync_credentials
        self._ingest_response = ingest_response

    def _touch(self, *, refresh_only: bool, skip_session_extension: bool) -> bool:
        self._sync_credentials()
        timeout = TOUCH_TIMEOUT_REFRESH if refresh_only else TOUCH_TIMEOUT_FULL
        try:
            resp = self._session.post(
                self._touch_url,
                json={
                    "refreshOnly": refresh_only,
                    "skipSessionExtension": skip_session_extension,
                },
                timeout=timeout,
            )
        except requests.RequestException as e:
            logger.warning("account/touch 失敗: %s", e)
            return False
        self._ingest_response(resp)
        if not resp.ok:
            try:
                err_body: Any = resp.json() if resp.content else {}
            except ValueError:
                err_body = resp.text or ""
            logger.warning(
                "account/touch HTTP %s %s", resp.status_code, safe_error_summary(err_body)
            )
            return False
        return True

    def refresh(self, *, force: bool) -> None:
        """フロント AuthTokenRefreshManager.executeRefresh 相当。

        呼び出し元が排他ロックを保持している前提で呼ぶこと。
        """
        if not force and not self._auth.should_refresh_token():
            self._sync_credentials()
            return

        token_when_queued = self._auth.get_token()
        max_index = len(TOUCH_RETRY_MULTIPLIERS)

        for attempt in range(max_index + 1):
            if self._auth.get_token() != token_when_queued:
                self._sync_credentials()
                return
            if not force and not self._auth.should_refresh_token():
                self._sync_credentials()
                return

            # store なし = shouldSkipSessionExtension true
            if self._touch(refresh_only=True, skip_session_extension=True):
                return
            if attempt >= max_index:
                logger.warning("token refresh が上限まで失敗")
                return
            time.sleep(touch_retry_delay_ms(attempt) / 1000.0)
