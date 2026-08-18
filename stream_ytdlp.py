"""yt-dlp による単一動画のダウンロード。

オプションの組み立ては ytdlp_options に分離してある。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from exceptions import YtdlpError
from models import StreamInfo
from ytdlp_options import build_options, ffmpeg_available

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^\w\s\-\.\(\)\[\]]+", re.UNICODE)
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 未完了・中間生成物として yt-dlp が残しうる拡張子（最終成果物として扱わない）
_INCOMPLETE_SUFFIXES = frozenset({".part", ".ytdl", ".temp", ".part-frag"})

_DEFAULT_MAX_FILESIZE_MB = 2_000

# yt-dlp が単一動画ではなくプレイリスト/複数動画として解決した場合の _type 値。
# 呼び出し元 (stream.py) の videoId チェックに加えた多層防御。
_COLLECTION_TYPES = frozenset({"playlist", "multi_video"})


def _safe_filename(title: str, max_len: int = 80) -> str:
    name = _SAFE_NAME_RE.sub("_", title).strip() or "video"
    name = re.sub(r"\s+", " ", name)
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name


def _is_complete_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() not in _INCOMPLETE_SUFFIXES


def _resolve_downloaded_path(info: dict[str, Any], outdir: Path, video_id: str) -> Path:
    # video_id は glob パターンだけでなく、呼び出し元で最終ファイル名の組み立てにも
    # 使われる。パストラバーサル文字（"/" や ".."）が無いことを、どの経路でも
    # 使われる前に必ず確認する。
    if not _VIDEO_ID_RE.fullmatch(video_id):
        raise YtdlpError("yt-dlp: video id が不正です")

    outdir_resolved = outdir.resolve()
    requested = info.get("requested_downloads") or []
    if isinstance(requested, list):
        for item in requested:
            if isinstance(item, dict) and item.get("filepath"):
                p = Path(item["filepath"]).resolve()
                if _is_complete_file(p) and p.is_relative_to(outdir_resolved):
                    return p

    candidates = sorted(c for c in outdir.glob(f"{video_id}.*") if _is_complete_file(c))
    for c in candidates:
        if c.suffix.lower() == ".mp4":
            return c
    if candidates:
        return candidates[0]
    raise YtdlpError("yt-dlp: ダウンロードファイルが見つかりません")


def download(
    url: str,
    *,
    outdir: str | Path,
    max_filesize_mb: int | None = None,
) -> StreamInfo:
    outdir = Path(outdir)
    outtmpl = str(outdir / "%(id)s.%(ext)s")
    has_ffmpeg = ffmpeg_available()
    if has_ffmpeg:
        logger.info("ffmpeg 利用可能: 分離トラック結合モード")
    else:
        logger.warning("ffmpeg 未検出: progressive ストリームのみ")

    filesize_limit_mb = _DEFAULT_MAX_FILESIZE_MB if max_filesize_mb is None else max_filesize_mb
    opts = build_options(outtmpl=outtmpl, max_filesize_mb=filesize_limit_mb, has_ffmpeg=has_ffmpeg)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except (DownloadError, ExtractorError, OSError) as e:
        raise YtdlpError(f"yt-dlp download failed: {e}") from e

    if not isinstance(info, dict):
        raise YtdlpError("yt-dlp: メタデータが不正です")

    if info.get("is_live"):
        raise YtdlpError("yt-dlp: ライブ配信中の動画は取得できません")

    if info.get("_type") in _COLLECTION_TYPES or info.get("entries") is not None:
        raise YtdlpError(
            "yt-dlp: 単一動画以外の URL（プレイリスト/チャンネル等）は取得できません"
        )

    title = str(info.get("title") or "Unknown")
    video_id = str(info.get("id") or "video")
    filepath = _resolve_downloaded_path(info, outdir, video_id)

    if filepath.stat().st_size == 0:
        filepath.unlink(missing_ok=True)
        raise YtdlpError("ダウンロードファイルが空です")

    safe = _safe_filename(title)
    ext = filepath.suffix.lower() or ".mp4"
    final = outdir / f"{safe}_{video_id}{ext}"
    if final != filepath:
        try:
            filepath.rename(final)
            filepath = final
        except OSError as e:
            logger.debug("リネーム失敗、元パスを使用: %s", e)

    return StreamInfo(title=title, filepath=filepath)
