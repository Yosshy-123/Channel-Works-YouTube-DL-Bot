"""起動時の孤児一時ディレクトリ掃除。"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TMP_PREFIX = "yt-bot-"

# この時間より新しい一時ディレクトリは、並行稼働中の別プロセスのものかもしれないため
# 起動時の孤児掃除では触らない（誤って稼働中ジョブの作業ディレクトリを削除しない）。
_ORPHAN_MIN_AGE_SECONDS = 3600


def cleanup_orphan_tmpdirs() -> None:
    tmp_root = Path(tempfile.gettempdir())
    now = time.time()
    try:
        for path in tmp_root.glob(f"{TMP_PREFIX}*"):
            if not path.is_dir():
                continue
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age < _ORPHAN_MIN_AGE_SECONDS:
                continue
            shutil.rmtree(path, ignore_errors=True)
            logger.info("孤児一時ディレクトリを削除: %s", path)
    except OSError:
        logger.debug("孤児一時ディレクトリ掃除をスキップ", exc_info=True)
