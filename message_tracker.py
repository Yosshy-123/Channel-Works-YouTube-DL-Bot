"""処理済みメッセージの追跡（容量制限付き FIFO）。"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


def message_key(msg: dict[str, Any]) -> str:
    """メッセージを一意に識別するキーを返す。

    Channel Desk のメッセージ主キーは id。
    plainText 等の弱いフォールバックは使わない（誤同一視を防ぐ）。
    """
    value = msg.get("id")
    if value is not None and str(value).strip() != "":
        return str(value)
    raise ValueError("message has no usable id field")


class MessageTracker:
    """スレッドセーフな処理済みメッセージ集合。容量超過時は古いものから破棄。"""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._seen: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    def filter_unseen(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """未処理メッセージを返す。バッチ内の同一 ID は先頭のみ残す。"""
        with self._lock:
            result: list[dict[str, Any]] = []
            batch_keys: set[str] = set()
            for m in messages:
                try:
                    key = message_key(m)
                except ValueError:
                    logger.debug(
                        "ID を持たないメッセージをスキップ: keys=%s",
                        list(m.keys())[:10],
                    )
                    continue
                if key in self._seen or key in batch_keys:
                    continue
                batch_keys.add(key)
                result.append(m)
            return result

    def mark(self, msg: dict[str, Any]) -> None:
        try:
            key = message_key(msg)
        except ValueError:
            logger.debug("mark: ID 無しメッセージを無視")
            return
        self.mark_id(key)

    def mark_id(self, key: str) -> None:
        """id を処理済みとして直接登録する。

        bot 自身が送信したメッセージ（成功/失敗の返信）を、送信直後・ポーリングで
        受信するより前に処理済み登録するために使う。これを怠ると、bot の返信
        （特に失敗通知には URL 自体が含まれる）が次回ポーリングで新規メッセージ
        として検出され、ダウンロード再試行→失敗通知→再検出…という自己ループに
        陥る。
        """
        if not key:
            return
        with self._lock:
            if key in self._seen:
                return
            self._seen.add(key)
            self._order.append(key)
            while len(self._order) > self._capacity:
                old = self._order.popleft()
                self._seen.discard(old)
