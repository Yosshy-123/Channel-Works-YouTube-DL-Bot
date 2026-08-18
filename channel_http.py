"""Channel API 向け HTTP 共通定数・ヘルパ。

フロント (channel-works) のヘッダ・requestId・エラー型判定を集約する。
"""

from __future__ import annotations

import random
from typing import Any

import requests

from server_clock import get_clock

API_BASE = "https://api.channel.works/desk"
MEDIA_BASE = "https://media.channel.io/cht/v1"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# フロント touch タイムアウト
TOUCH_TIMEOUT_REFRESH = 5.0
TOUCH_TIMEOUT_FULL = 15.0

# AuthTokenRefreshManager: h=[1,2] → 最大 3 試行
TOUCH_RETRY_MULTIPLIERS = (1, 2)

# フロント bB でリカバリしない 401 type
TERMINAL_AUTH_ERROR_TYPES = frozenset(
    {
        "SessionJWTExpiredError",
        "SessionExpiredError",
        "SessionJWTInvalidError",
        "SignInFailureError",
    }
)

_SAFE_ERROR_KEYS = frozenset({"error", "code", "message", "status", "type", "name"})

BROWSER_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Origin": "https://channel.works",
    "Referer": "https://channel.works/",
    "User-Agent": USER_AGENT,
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


def safe_error_summary(body: Any) -> str:
    """ログ用: 機密混入リスクの低い要約。"""
    if body is None:
        return "None"
    if isinstance(body, dict):
        keys = sorted(str(k) for k in body)
        parts: list[str] = []
        for k in _SAFE_ERROR_KEYS:
            if k in body:
                v = body[k]
                if isinstance(v, (str, int, float, bool)) or v is None:
                    parts.append(f"{k}={str(v)[:80]!r}")
        key_list = ",".join(keys[:20])
        if len(keys) > 20:
            key_list += f",...(+{len(keys) - 20})"
        if parts:
            return f"keys=[{key_list}] " + " ".join(parts)
        return f"keys=[{key_list}]"
    if isinstance(body, str):
        return repr(body[:100]) + ("..." if len(body) > 100 else "")
    return f"<{type(body).__name__}>"


def response_error_type(resp: requests.Response) -> str | None:
    """応答 JSON からエラー type を取得（フロント body.type）。"""
    try:
        body = resp.json() if resp.content else None
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    for key in ("type", "name", "error", "code"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            inner = val.get("type") or val.get("name")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def is_auth_recoverable(resp: requests.Response) -> bool:
    """フロント bB: 401 かつ終端 type でない。"""
    if resp.status_code != 401:
        return False
    err_type = response_error_type(resp)
    if err_type is None:
        return True
    return err_type not in TERMINAL_AUTH_ERROR_TYPES


def random_base36(length: int) -> str:
    """フロント DU(n) 相当。"""
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choices(alphabet, k=length))


def new_request_id() -> str:
    """フロント generateRequestId: desk-web-{ms}{DU(4)}。"""
    return f"desk-web-{get_clock().now_ms()}{random_base36(4)}"


def touch_retry_delay_ms(attempt_index: int) -> float:
    """getRetryDelayMs: 500*h[e] + Math.floor(501*Math.random())。"""
    mults = TOUCH_RETRY_MULTIPLIERS
    mult = mults[attempt_index] if 0 <= attempt_index < len(mults) else mults[-1]
    return 500.0 * mult + float(random.randint(0, 500))


def message_body(
    *,
    request_id: str,
    text: str = "",
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """フロント Message.toRequestDTO 相当（options は送らない）。"""
    return {
        "requestId": request_id or "",
        "blocks": [{"type": "text", "value": text}] if text else None,
        "buttons": None,
        "form": None,
        "webPage": None,
        "files": files if files else None,
        "customPayload": None,
    }
