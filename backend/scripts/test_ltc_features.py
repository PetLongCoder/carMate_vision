"""Smoke test for LTC auth & related features (罗天赐)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api"


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.skipped: list[str] = []

    def ok(self, name: str) -> None:
        self.passed.append(name)

    def fail(self, name: str, detail: str) -> None:
        self.failed.append(f"{name}: {detail}")

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append(f"{name}: {reason}")


def request(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw or str(e)}
        return e.code, payload


def main() -> int:
    r = Result()

    # ── 基础 ──
    code, data = request("GET", "/health")
    if code == 200 and data.get("status") == "ok":
        r.ok("后端健康检查")
    else:
        r.fail("后端健康检查", f"code={code} {data}")

    # ── 密码登录 ──
    code, data = request("POST", "/auth/login", {"username": "admin", "password": "123456", "portal": "admin"})
    admin_token = None
    if code == 200 and data.get("code") == 0 and data.get("data", {}).get("token"):
        admin_token = data["data"]["token"]
        r.ok("管理员密码登录")
    else:
        r.fail("管理员密码登录", str(data))

    code, data = request("POST", "/auth/login", {"username": "user", "password": "123456", "portal": "user"})
    user_token = None
    if code == 200 and data.get("code") == 0 and data.get("data", {}).get("token"):
        user_token = data["data"]["token"]
        r.ok("普通用户密码登录")
    else:
        r.fail("普通用户密码登录", str(data))

    # 错误密码
    code, data = request("POST", "/auth/login", {"username": "user", "password": "wrong", "portal": "user"})
    if code == 200 and data.get("code") != 0:
        r.ok("错误密码被拒绝")
    else:
        r.fail("错误密码被拒绝", str(data))

    # 门户校验
    code, data = request("POST", "/auth/login", {"username": "user", "password": "123456", "portal": "admin"})
    if code == 200 and data.get("code") != 0:
        r.ok("普通用户不能走管理员入口")
    else:
        r.fail("普通用户不能走管理员入口", str(data))

    # ── 密码格式（注册） ──
    code, data = request(
        "POST",
        "/auth/register",
        {
            "username": "test_weak_pwd",
            "password": "123456",
            "phone": "13900001111",
            "code": "000000",
        },
    )
    if data.get("code") != 0 or "密码" in str(data.get("message", "")):
        r.ok("弱密码注册被拒绝")
    else:
        r.fail("弱密码注册被拒绝", str(data))

    # ── SMS mock ──
    code, data = request("POST", "/auth/sms/send", {"phone": "13800138000", "scene": "login"})
    if code == 200 and data.get("code") == 0:
        r.ok("短信验证码发送（mock）")
    else:
        r.fail("短信验证码发送（mock）", str(data))

    # ── 邮箱验证码 ──
    code, data = request("POST", "/auth/email/send", {"email": "test@qq.com", "scene": "login"})
    if code == 200:
        if data.get("code") == 0:
            r.ok("邮箱验证码发送")
        elif "未注册" in str(data.get("message", "")):
            r.ok("邮箱验证码发送（未注册邮箱正确提示）")
        else:
            r.fail("邮箱验证码发送", str(data))
    else:
        r.fail("邮箱验证码发送", f"HTTP {code}")

    # ── 当前用户 / 登录方式 ──
    if user_token:
        code, data = request("GET", "/auth/me", token=user_token)
        user = data.get("data") or {}
        methods = user.get("login_methods") or []
        if code == 200 and data.get("code") == 0 and "password" in methods:
            r.ok("获取当前用户与 login_methods")
        else:
            r.fail("获取当前用户与 login_methods", str(data))

    # ── 微信 Mock ──
    code, data = request("GET", "/auth/wechat/qrcode")
    if code == 200 and data.get("code") == 0 and data.get("data", {}).get("qrcode_base64"):
        r.ok("微信登录二维码")
    else:
        r.fail("微信登录二维码", str(data))

    if user_token:
        code, data = request("GET", "/auth/wechat/bind/qrcode", token=user_token)
        if code == 200 and data.get("code") == 0 and data.get("data", {}).get("state"):
            r.ok("微信绑定二维码")
        elif "已绑定" in str(data.get("message", "")):
            r.skip("微信绑定二维码", "用户已绑定微信")
        else:
            r.fail("微信绑定二维码", str(data))

        code, data = request("GET", "/auth/wechat/delete/qrcode", token=user_token)
        if code == 200 and data.get("code") == 0:
            r.ok("微信注销二维码接口")
        elif "尚未绑定微信" in str(data.get("message", "")):
            r.skip("微信注销二维码接口", "当前用户未绑定微信")
        else:
            r.fail("微信注销二维码接口", str(data))

    # ── 改密密码格式 ──
    if user_token:
        code, data = request(
            "POST",
            "/auth/account/change-password",
            {
                "verify_method": "password",
                "old_password": "123456",
                "new_password": "weak",
            },
            token=user_token,
        )
        if data.get("code") != 0:
            r.ok("改密弱密码被拒绝")
        else:
            r.fail("改密弱密码被拒绝", str(data))

    # ── 告警智能体（合并 main 后） ──
    if user_token:
        code, data = request("GET", "/alerts/stats", token=user_token)
        if code == 200 and data.get("code") == 0:
            r.ok("告警统计 API")
        else:
            r.fail("告警统计 API", str(data))

    if admin_token:
        code, data = request("GET", "/alerts?page=1&pageSize=10", token=admin_token)
        if code == 200 and data.get("code") == 0:
            r.ok("告警中心列表（管理员）")
        else:
            r.fail("告警中心列表（管理员）", str(data))

        code, data = request("GET", "/admin/operation-logs?page=1&pageSize=10", token=admin_token)
        if code == 200 and data.get("code") == 0:
            r.ok("用户操作日志（管理员）")
        else:
            r.fail("用户操作日志（管理员）", str(data))

        code, data = request("GET", "/admin/recognition-records?page=1&pageSize=10", token=admin_token)
        if code == 200 and data.get("code") == 0:
            r.ok("识别记录管理（管理员）")
        else:
            r.fail("识别记录管理（管理员）", str(data))

    # ── 零配置 .env ──
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    example_path = env_path.with_name(".env.example")
    if env_path.exists() and example_path.exists():
        r.ok("backend/.env 存在（零配置）")
    else:
        r.fail("backend/.env 存在（零配置）", f"env={env_path.exists()} example={example_path.exists()}")

    # ── 输出 ──
    print("\n=== CarMate LTC 功能冒烟测试 ===\n")
    for name in r.passed:
        print(f"  [PASS] {name}")
    for name in r.skipped:
        print(f"  [SKIP] {name}")
    for name in r.failed:
        print(f"  [FAIL] {name}")

    print(f"\n合计: {len(r.passed)} 通过, {len(r.failed)} 失败, {len(r.skipped)} 跳过")
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
