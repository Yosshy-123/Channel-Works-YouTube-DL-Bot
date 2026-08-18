"""返信メッセージの整形（副作用なしの純粋関数群）。"""

from __future__ import annotations

import html

from models import StreamInfo


def format_success_caption(info: StreamInfo) -> str:
    """成功時の添付キャプションを生成する。"""
    return html.escape(info.title, quote=False)


def format_error_body(url: str, message: str) -> str:
    """失敗通知メッセージを組み立てる。"""
    return (
        f"<b>動画の取得に失敗しました</b>\n"
        f"{html.escape(url, quote=False)}\n"
        f"{html.escape(message, quote=False)}"
    )
