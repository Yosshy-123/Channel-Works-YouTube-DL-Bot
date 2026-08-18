"""JWT (x-account トークン) のデコードと有効期限抽出。

署名検証は行わない（サーバーが発行したトークンの exp クレームを
読み取るだけの用途であり、リクエスト送信要否の判断にのみ使う）。
"""

from __future__ import annotations

import base64
import json
import math
from typing import Any


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """JWT の payload 部分（第 2 セグメント）を dict として返す。"""
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("JWT の形式が不正です")
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    raw = base64.urlsafe_b64decode(payload_b64 + padding)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JWT payload がオブジェクトではありません")
    return data


def expires_at_ms(token: str) -> int | None:
    """exp をミリ秒 epoch で返す。不正・欠落時は None。"""
    try:
        exp = decode_jwt_payload(token).get("exp")
        if exp is None:
            return None
        exp_f = float(exp)
        if math.isnan(exp_f) or math.isinf(exp_f):
            return None
        return int(exp_f * 1000)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
