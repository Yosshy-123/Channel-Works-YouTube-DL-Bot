"""1 件の YouTube URL に対するダウンロード〜結果返信までを担当する。

ポーリング・ジョブ投入（orchestration）は bot.py が担い、
このモジュールは投入されたジョブの実行のみに責務を絞る。
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from channel_client import ChannelClient, extract_message_id
from exceptions import ChannelAPIError, StreamError
from models import StreamInfo
from reply_formatter import format_error_body, format_success_caption

logger = logging.getLogger(__name__)

_USER_ERR_STREAM = "動画を取得できませんでした。"
_USER_ERR_INTERNAL = "処理に失敗しました。"

DownloadFn = Callable[..., StreamInfo]
OnSentFn = Callable[[str], None]


class DownloadJobRunner:
    """ダウンロード実行・成功/失敗の返信を行う（ワーカースレッドから呼ばれる）。"""

    def __init__(
        self,
        *,
        client: ChannelClient,
        download_fn: DownloadFn,
        tmpdir: Path,
        max_filesize_mb: int,
        on_sent: OnSentFn,
    ) -> None:
        self._client = client
        self._download_fn = download_fn
        self._tmpdir = tmpdir
        self._max_filesize_mb = max_filesize_mb
        # bot 自身が送信したメッセージの id を登録するコールバック
        # (通常は MessageTracker.mark_id)。送信直後に登録することで、
        # 次回以降のポーリングでその返信自体が「新規メッセージ」として
        # 検出され、含まれる URL を再度ダウンロードしようとする自己ループを防ぐ。
        self._on_sent = on_sent

    def run(self, url: str) -> None:
        workdir: Path | None = None
        try:
            workdir = (
                self._tmpdir / f"{threading.get_ident()}_{int(time.time() * 1000)}"
            )
            workdir.mkdir(parents=True, exist_ok=True)
            info = self._download_fn(
                url, outdir=workdir, max_filesize_mb=self._max_filesize_mb
            )
            self._reply_ok(url, info)
        except StreamError as e:
            logger.warning("取得失敗 url=%s err=%s", url, e)
            self._reply_err(url, user_message=_USER_ERR_STREAM)
        except Exception:
            logger.exception("予期しない取得失敗 url=%s", url)
            self._reply_err(url, user_message=_USER_ERR_INTERNAL)
        finally:
            if workdir is not None:
                shutil.rmtree(workdir, ignore_errors=True)

    def _safe_send(self, action: str, fn: Callable[[], dict[str, Any]]) -> None:
        try:
            response_body = fn()
        except ChannelAPIError as e:
            logger.error("%s API エラー: %s", action, e)
            return
        except Exception:
            logger.exception("%s に失敗", action)
            return
        self._register_sent(action, response_body)

    def _register_sent(self, action: str, response_body: Any) -> None:
        message_id = extract_message_id(response_body)
        if message_id:
            self._on_sent(message_id)
        else:
            logger.debug("%s: 応答からメッセージ ID を取得できませんでした", action)

    def _reply_ok(self, url: str, info: StreamInfo) -> None:
        caption = format_success_caption(info)
        file_path = info.filepath.resolve()
        tmp_root = self._tmpdir.resolve()
        if file_path.is_file() and file_path.is_relative_to(tmp_root):
            sent = False

            def _do_file() -> dict[str, Any]:
                nonlocal sent
                body = self._client.send_file(
                    file_path,
                    text=caption,
                    filename=file_path.name,
                    allowed_root=self._tmpdir,
                )
                logger.info(
                    "添付送信 title=%r path=%s", info.title[:60], file_path
                )
                sent = True
                return body

            self._safe_send("ファイル添付", _do_file)
            if sent:
                return
        else:
            logger.error("添付ファイルが不正または作業ディレクトリ外: %s", file_path)
        self._reply_err(url, user_message=_USER_ERR_STREAM)

    def _reply_err(self, url: str, *, user_message: str) -> None:
        body_text = format_error_body(url, user_message)

        def _do() -> dict[str, Any]:
            return self._client.send_text(body_text)

        self._safe_send("失敗通知の送信", _do)
