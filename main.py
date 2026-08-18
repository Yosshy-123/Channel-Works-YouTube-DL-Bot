"""プロセスエントリポイント。

ログ設定・孤児一時ディレクトリ掃除・設定読み込みを行い、
YoutubeBot を起動する。
"""

from __future__ import annotations

import logging
import sys

from bot import YoutubeBot
from channel_client import ChannelClient
from config import Settings
from tmp_cleanup import cleanup_orphan_tmpdirs


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    cleanup_orphan_tmpdirs()
    try:
        settings = Settings.load()
    except RuntimeError as e:
        logging.error("%s", e)
        sys.exit(1)

    with ChannelClient(settings) as client:
        YoutubeBot(settings, client).run()


if __name__ == "__main__":
    main()
