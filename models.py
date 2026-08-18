"""ドメイン共有モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StreamInfo:
    """ダウンロード結果。"""

    title: str
    filepath: Path
