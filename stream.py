"""ストリーム取得の公開入口。"""

from __future__ import annotations

from pathlib import Path

from exceptions import StreamError
from models import StreamInfo
from stream_ytdlp import download as _download_ytdlp
from youtube_url import extract_video_id, is_youtube_url


def download(url: str, *, outdir: str | Path, max_filesize_mb: int | None = None) -> StreamInfo:
    """動画ファイルを取得する。outdir の作成を保証する。

    呼び出し元での検証状況に関わらず、ここでも以下を検証する（多層防御）:
    - YouTube の許可ホストであること（yt-dlp に任意 URL を渡す SSRF 類似の経路を防ぐ）
    - 単一動画の videoId を抽出できる URL であること（プレイリスト/チャンネル URL に
      よる無制限ダウンロードを防ぐ）
    """
    if not is_youtube_url(url):
        raise StreamError("YouTube の URL ではありません")
    if extract_video_id(url) is None:
        raise StreamError("単一動画の URL ではありません（プレイリスト/チャンネルは非対応）")
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return _download_ytdlp(url, outdir=outdir, max_filesize_mb=max_filesize_mb)
