"""yt-dlp 実行オプションの構築（リソース上限・抽出器制限）。"""

from __future__ import annotations

import shutil
from typing import Any

_PROGRESSIVE_FORMAT = "best[vcodec!=none][acodec!=none]/best"
_MERGE_FORMAT = "bestvideo*+bestaudio/best"

# 安全性・リソース制限
_SOCKET_TIMEOUT = 30
_RETRIES = 3
_FRAGMENT_RETRIES = 3

# 対象を YouTube 抽出器のみに固定する（許可ホスト以外の URL が紛れ込んでも
# 汎用抽出器 (generic) が任意サイトへアクセスするのを防ぐ多層防御）。
# yt-dlp は allowed_extractors を IE_NAME に対する正規表現の fullmatch（大小文字
# 無視）で評価するため、"youtube" から始まる名前をすべて拾うには ".*" が必要。
_ALLOWED_EXTRACTORS = ("youtube.*",)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def reject_live_filter(info_dict: dict[str, Any], *, incomplete: bool = False) -> str | None:
    """yt-dlp の match_filter: 配信中のライブは実ダウンロード開始前に弾く。

    サイズが際限なく増え続けるライブ配信を、実際のダウンロードが始まる前に
    yt-dlp 内部でスキップさせる（メタデータ取得とダウンロードを別々に
    2 回実行する無駄を避けつつ、無制限ダウンロードを防止する）。
    """
    if info_dict.get("is_live"):
        return "live broadcast in progress"
    return None


def build_options(*, outtmpl: str, max_filesize_mb: int, has_ffmpeg: bool) -> dict[str, Any]:
    """download() から呼ばれる yt-dlp オプション辞書を組み立てる。"""
    opts: dict[str, Any] = {
        "format": _MERGE_FORMAT if has_ffmpeg else _PROGRESSIVE_FORMAT,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        # noplaylist は「動画IDとプレイリストIDが同時に含まれる URL」の曖昧さ解消に
        # しか効かないため、プレイリスト/チャンネル URL 単体には無力。
        # playlist_items で仮に解決された場合でも先頭 1 件までに強制的に制限する
        # （呼び出し元の videoId チェックと合わせた多層防御）。
        "noplaylist": True,
        "playlist_items": "1",
        "extract_flat": False,
        "overwrites": True,
        "prefer_ffmpeg": has_ffmpeg,
        "socket_timeout": _SOCKET_TIMEOUT,
        "retries": _RETRIES,
        "fragment_retries": _FRAGMENT_RETRIES,
        "max_filesize": max_filesize_mb * 1024 * 1024,
        "allowed_extractors": list(_ALLOWED_EXTRACTORS),
        "match_filter": reject_live_filter,
        # 外部ダウンローダーや危険なポストプロセッサを避ける
        "external_downloader": None,
        "hls_prefer_native": True,
    }
    if has_ffmpeg:
        opts["merge_output_format"] = "mp4"
    return opts
