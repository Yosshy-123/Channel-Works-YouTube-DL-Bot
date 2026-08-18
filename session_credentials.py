"""ch-session-1 / ch-veil-id / x-account-refresh Cookie の保持。"""

from __future__ import annotations

import threading
from typing import Any

from cookie_jar_utils import first_cookie_value


class SessionCredentials:
    """スレッドセーフなセッション Cookie 保持クラス。"""

    def __init__(
        self, session_cookie: str, veil_id: str, account_refresh: str = ""
    ) -> None:
        self._lock = threading.RLock()
        self._session_cookie = session_cookie
        self._veil_id = veil_id
        self._account_refresh = (account_refresh or "").strip()

    def cookie_dict(self) -> dict[str, str]:
        with self._lock:
            cookies = {
                "ch-session-1": self._session_cookie,
                "ch-veil-id": self._veil_id,
            }
            if self._account_refresh:
                cookies["x-account-refresh"] = self._account_refresh
            return cookies

    def ingest_response_cookies(self, cookies: Any) -> bool:
        changed = False
        try:
            session = first_cookie_value(cookies, "ch-session-1")
            veil = first_cookie_value(cookies, "ch-veil-id")
            account_refresh = first_cookie_value(cookies, "x-account-refresh")
        except (AttributeError, TypeError):
            return False
        with self._lock:
            if session and session != self._session_cookie:
                self._session_cookie = session
                changed = True
            if veil and veil != self._veil_id:
                self._veil_id = veil
                changed = True
            if account_refresh and account_refresh != self._account_refresh:
                self._account_refresh = account_refresh
                changed = True
        return changed
