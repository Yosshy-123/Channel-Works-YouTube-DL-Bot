"""YouTube 動画ダウンロード bot 本体。

指定グループのメッセージから YouTube URL を検出し、動画を添付返信する。
ダウンロード実行・返信そのものは job_runner.DownloadJobRunner に委譲し、
ここではポーリングループとプロセスライフサイクルの管理に専念する。
起動時の孤児一時ディレクトリ掃除は tmp_cleanup に、プロセス起動そのものは
main.py に分離してある。
"""

from __future__ import annotations

import logging
import shutil
import signal
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from channel_client import ChannelClient
from config import Settings
from exceptions import ChannelAPIError
from job_runner import DownloadFn, DownloadJobRunner
from message_tracker import MessageTracker
from stream import download as download_stream
from tmp_cleanup import TMP_PREFIX
from youtube_url import extract_video_id, find_youtube_urls

logger = logging.getLogger(__name__)

_POLL_ERROR_BACKOFF_BASE = 1.0
_POLL_ERROR_BACKOFF_MAX = 30.0


class YoutubeBot:
    def __init__(
        self,
        settings: Settings,
        client: ChannelClient,
        *,
        download_fn: DownloadFn | None = None,
    ) -> None:
        self._settings = settings
        self._tracker = MessageTracker(
            capacity=max(settings.message_fetch_limit * 5, 100)
        )
        self._pool = ThreadPoolExecutor(
            max_workers=settings.yt_workers,
            thread_name_prefix="yt",
        )
        self._running = True
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()
        self._tmpdir = Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
        self._poll_errors = 0
        self._client = client
        self._job_runner = DownloadJobRunner(
            client=client,
            download_fn=download_fn or download_stream,
            tmpdir=self._tmpdir,
            max_filesize_mb=settings.max_download_filesize_mb,
            on_sent=self._tracker.mark_id,
        )

    def stop(self, *_args: object) -> None:
        logger.info("停止シグナルを受信")
        self._running = False

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        s = self._settings
        logger.info(
            "開始 channel=%s group=%s limit=%d workers=%d tmp=%s",
            s.channel_id,
            s.group_id,
            s.message_fetch_limit,
            s.yt_workers,
            self._tmpdir,
        )
        try:
            while self._running:
                try:
                    had_work = self._poll()
                    self._poll_errors = 0
                except ChannelAPIError as e:
                    self._poll_errors += 1
                    logger.error("API エラー (連続 %d 回): %s", self._poll_errors, e)
                    had_work = False
                except Exception:
                    self._poll_errors += 1
                    logger.exception("ポーリングエラー (連続 %d 回)", self._poll_errors)
                    had_work = False

                if not self._running:
                    break
                if self._poll_errors > 0:
                    delay = min(
                        _POLL_ERROR_BACKOFF_BASE * (2 ** (self._poll_errors - 1)),
                        _POLL_ERROR_BACKOFF_MAX,
                    )
                    time.sleep(delay)
                elif not had_work:
                    time.sleep(s.poll_idle_sleep)
        finally:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._cleanup_tmpdir()
            logger.info("終了")

    def _cleanup_tmpdir(self) -> None:
        try:
            if self._tmpdir.exists():
                shutil.rmtree(self._tmpdir, ignore_errors=True)
        except OSError:
            logger.exception("一時ディレクトリ削除失敗")

    def _poll(self) -> bool:
        messages = self._client.get_recent_messages(self._settings.message_fetch_limit)
        pending = self._tracker.filter_unseen(messages)
        if not pending:
            return False

        for msg in reversed(pending):
            self._tracker.mark(msg)
            plain = (msg.get("plainText") or "").strip()
            if not plain:
                continue
            urls = find_youtube_urls(plain)
            if not urls:
                continue
            logger.info("検出 urls=%s text=%r", urls, plain[:80])
            for url in urls:
                self._submit(url)
        return True

    def _inflight_key(self, url: str) -> str:
        return extract_video_id(url) or url

    def _submit(self, url: str) -> None:
        key = self._inflight_key(url)
        with self._inflight_lock:
            if key in self._inflight:
                return
            self._inflight.add(key)
        self._pool.submit(self._run_job, url, key)

    def _run_job(self, url: str, key: str) -> None:
        try:
            self._job_runner.run(url)
        finally:
            with self._inflight_lock:
                self._inflight.discard(key)
