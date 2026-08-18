"""サーバー応答の Date ヘッダーから時刻ズレを補正するクロック。

フロント (channel-works) の computeTimeAdjuster / now() 相当。
トークン有効期限判定をクライアントのローカル時刻に依存させないために使う。
"""

from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime
from typing import Any

from http_headers import header_get


class ServerClock:
    """スレッドセーフなサーバー時刻推定クロック。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._adjuster_ms: float = 0.0

    def ingest_date_header(self, headers: Any) -> None:
        """cache-control 付き応答の Date ヘッダーからズレを更新する。

        cache-control の有無を見るのは、CDN/プロキシがキャッシュ応答を
        返した場合の Date は「応答生成時刻」ではなくなるため、フロント同様
        キャッシュ制御ヘッダーが明示された応答のみを時刻補正の根拠にする。
        """
        if not header_get(headers, "cache-control"):
            return
        date_raw = header_get(headers, "date")
        if not date_raw:
            return
        try:
            server_ms = parsedate_to_datetime(date_raw).timestamp() * 1000.0
        except (TypeError, ValueError, OSError, OverflowError):
            return
        with self._lock:
            self._adjuster_ms = server_ms - time.time() * 1000.0

    def now_ms(self) -> int:
        with self._lock:
            adjuster = self._adjuster_ms
        return int(time.time() * 1000.0 + adjuster)


_CLOCK = ServerClock()


def get_clock() -> ServerClock:
    return _CLOCK
