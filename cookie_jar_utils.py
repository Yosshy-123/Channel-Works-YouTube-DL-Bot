"""requests.cookies.RequestsCookieJar 向けの安全なアクセスヘルパー。

RequestsCookieJar は Cookie を (name, domain, path) の組で区別する。
requests は応答を受け取るたびに Set-Cookie の内容を自動でセッションの
CookieJar へマージするため、こちらが手動で追加した Cookie（domain 未指定）
とサーバーが実際の domain 付きで設定した同名 Cookie が両方ジャーに残り、
同名で複数存在する状態になり得る。

その状態で `jar.pop(name)` や `jar.get(name)`（いずれも内部で
`_find_no_duplicates()` を呼ぶ）を使うと `CookieConflictError` を送出する。
本モジュールの関数はジャーを直接走査することでこれを回避する。
"""

from __future__ import annotations

from typing import Any


def first_cookie_value(jar: Any, name: str) -> str | None:
    """同名 Cookie が複数あっても衝突せず、最初に見つかった値を返す。"""
    if jar is None:
        return None
    try:
        for cookie in jar:
            if cookie.name == name and cookie.value:
                return cookie.value
    except TypeError:
        return None
    return None


def clear_cookie_all_domains(jar: Any, name: str) -> None:
    """同名 Cookie を domain/path を問わずすべて削除する。"""
    for cookie in list(jar):
        if cookie.name == name:
            jar.clear(cookie.domain, cookie.path, cookie.name)
