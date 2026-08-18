"""Channel Desk API への認証付き HTTP 実行層。

x-account (JWT) / セッション Cookie の同期、401 リカバリ、ネットワークリトライを
ここに集約する。token refresh の試行ロジック自体は token_refresher.TokenRefresher
に委譲する。Desk API のエンドポイント（メッセージ送受信など）は channel_client.py
が担う。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from account_auth import HEADER_NAME, AccountAuth
from channel_http import (
    API_BASE,
    BROWSER_HEADERS,
    is_auth_recoverable,
    response_error_type,
    safe_error_summary,
)
from config import Settings
from cookie_jar_utils import clear_cookie_all_domains
from exceptions import ChannelAPIError
from session_credentials import SessionCredentials
from token_refresher import TokenRefresher

logger = logging.getLogger(__name__)

_ACCOUNT_TOUCH_URL = f"{API_BASE}/account/touch"


class ChannelSession:
    """スレッドセーフな認証付き HTTP クライアント。"""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.http_timeout
        self._auth = AccountAuth(settings.x_account_token)
        self._creds = SessionCredentials(
            settings.session_cookie, settings.veil_id, settings.x_account_refresh
        )
        # フロント navigator.locks("ch-desk-session-operation") 相当
        self._op_lock = threading.RLock()
        self._session = requests.Session()
        self._session.headers.update(BROWSER_HEADERS)
        self._refresher = TokenRefresher(
            touch_url=_ACCOUNT_TOUCH_URL,
            session=self._session,
            auth=self._auth,
            sync_credentials=self._sync_credentials,
            ingest_response=self._ingest_response,
        )
        with self._op_lock:
            self._sync_credentials()

    def close(self) -> None:
        with self._op_lock:
            self._session.close()

    def __enter__(self) -> ChannelSession:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def http(self) -> requests.Session:
        """MediaUploader など、生の requests.Session が必要な呼び出し元向け。"""
        return self._session

    @property
    def default_timeout(self) -> float:
        return self._timeout

    def _sync_credentials(self) -> None:
        # x-account は Header と Cookie の両方に同じトークンを載せる。
        # headers は CaseInsensitiveDict なので大文字小文字を気にせず 1 回で消せる。
        account_header = self._auth.get_auth_header()  # {} または {HEADER_NAME: token}

        self._session.headers.pop(HEADER_NAME, None)
        self._session.headers.update(account_header)

        self._session.cookies.update(self._creds.cookie_dict())
        clear_cookie_all_domains(self._session.cookies, HEADER_NAME)
        self._session.cookies.update(account_header)

    def _ingest_response(self, resp: requests.Response) -> None:
        changed = self._auth.ingest_response_headers(resp.headers)
        if self._creds.ingest_response_cookies(resp.cookies):
            changed = True
        if changed:
            self._sync_credentials()

    def execute_with_auth(
        self,
        action: str,
        do_request: Callable[[], requests.Response],
        *,
        retry_on_auth: bool = True,
        max_network_retries: int = 0,
    ) -> dict[str, Any]:
        """token refresh・401 リカバリ・ネットワークリトライ付きでリクエストを実行する。"""
        with self._op_lock:
            self._refresher.refresh(force=False)
            self._sync_credentials()

        network_attempts = 0
        auth_retried = False

        while True:
            try:
                resp = do_request()
            except requests.RequestException as e:
                if network_attempts < max_network_retries:
                    network_attempts += 1
                    delay = 0.5 * (2 ** (network_attempts - 1))
                    logger.warning(
                        "%s ネットワーク例外、%.1fs 後リトライ (%d/%d): %s",
                        action,
                        delay,
                        network_attempts,
                        max_network_retries,
                        e,
                    )
                    time.sleep(delay)
                    with self._op_lock:
                        self._sync_credentials()
                    continue
                raise

            with self._op_lock:
                self._ingest_response(resp)

            if retry_on_auth and not auth_retried and is_auth_recoverable(resp):
                logger.warning(
                    "%s → 401 type=%s、force refresh 後に 1 回リプレイ",
                    action,
                    response_error_type(resp),
                )
                with self._op_lock:
                    self._refresher.refresh(force=True)
                    self._sync_credentials()
                auth_retried = True
                continue

            return self._parse(resp, action)

    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        action: str,
        retry_on_auth: bool = True,
        timeout: float | None = None,
        max_network_retries: int = 0,
    ) -> dict[str, Any]:
        to = self._timeout if timeout is None else timeout

        def do() -> requests.Response:
            return self._session.request(method, url, json=json_body, timeout=to)

        return self.execute_with_auth(
            action,
            do,
            retry_on_auth=retry_on_auth,
            max_network_retries=max_network_retries,
        )

    @staticmethod
    def _parse(resp: requests.Response, action: str) -> dict[str, Any]:
        try:
            body: Any = resp.json() if resp.content else {}
        except ValueError:
            body = {"raw": (resp.text or "")[:500]}
        if not resp.ok:
            logger.error(
                "%s failed status=%s %s",
                action,
                resp.status_code,
                safe_error_summary(body),
            )
            raise ChannelAPIError(
                f"{action} HTTP {resp.status_code}",
                status_code=resp.status_code,
                body=body,
            )
        if not isinstance(body, dict):
            raise ChannelAPIError(f"{action}: unexpected JSON type", body=body)
        return body
