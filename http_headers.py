"""HTTP ヘッダー取得の共通ヘルパー。

requests.Response.headers は大文字小文字を区別しない CaseInsensitiveDict
なので、呼び出し側は小文字のヘッダー名を渡せばよい。
"""

from __future__ import annotations

from typing import Any


def header_get(headers: Any, name: str) -> str | None:
    """headers から name を取得し、空文字を None に正規化して返す。"""
    if headers is None:
        return None
    try:
        value = headers.get(name)
    except (AttributeError, TypeError):
        return None
    if value is None:
        return None
    value = str(value).strip()
    return value or None
