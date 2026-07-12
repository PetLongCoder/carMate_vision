"""密码强度校验（注册、修改密码）。"""

from __future__ import annotations

import re

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)\S{8,128}$")
PASSWORD_HINT = "密码须为 8-128 位，同时包含字母和数字，且不能含空格"


def validate_password_strength(password: str) -> str:
    if not PASSWORD_PATTERN.match(password):
        raise ValueError(PASSWORD_HINT)
    return password
