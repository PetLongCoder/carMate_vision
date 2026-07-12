import base64
import io
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.v1.auth import build_auth_response, fail, ok, require_current_user, user_to_out
from app.core.account_security import ensure_can_remove_method
from app.core.config import settings
from app.core.database import get_db
from app.core.network import detect_lan_ip
from app.core.security import hash_password
from app.models.auth_schemas import AuthResponse, UserOut, WechatConfirmRequest, WechatPollResponse
from app.models.db_models import User
from app.services.operation_log_service import log_operation
from app.services.user_privacy_service import (
    assign_wechat_openid,
    find_user_by_wechat_openid,
    get_wechat_openid_plain,
)
from app.utils.logger import logger

router = APIRouter(prefix="/auth/wechat", tags=["微信登录(Mock)"])

MOCK_AVATAR = "https://thirdwx.qlogo.cn/mmopen/mock/default/0"


@dataclass
class WechatPendingSession:
    state: str
    expires_at: datetime
    mode: str = "login"
    bind_user_id: int | None = None
    rebind_step: int = 0
    status: str = "waiting"
    auth_payload: dict | None = None
    user_payload: dict | None = None
    returned_openid: str | None = None


_pending_sessions: dict[str, WechatPendingSession] = {}


def _cleanup_expired_sessions() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expired = [state for state, item in _pending_sessions.items() if item.expires_at < now]
    for state in expired:
        session = _pending_sessions.pop(state, None)
        if session and session.status == "waiting":
            session.status = "expired"


def _get_session(state: str) -> WechatPendingSession | None:
    _cleanup_expired_sessions()
    session = _pending_sessions.get(state)
    if not session:
        return None
    if session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        session.status = "expired"
        return session
    return session


def _make_qrcode_base64(content: str) -> str:
    image = qrcode.make(content)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _generate_unique_username(db: Session, openid: str) -> str:
    suffix = openid.replace("mock_", "")[:8]
    candidate = f"wx_{suffix}"
    if not db.query(User).filter(User.username == candidate).first():
        return candidate

    for _ in range(5):
        candidate = f"wx_{secrets.token_hex(4)}"
        if not db.query(User).filter(User.username == candidate).first():
            return candidate

    return f"wx_{uuid.uuid4().hex[:10]}"


def _resolve_or_create_user(
    db: Session,
    mock_openid: str,
    nickname: str | None,
) -> User:
    user = find_user_by_wechat_openid(db, mock_openid)
    if user:
        if nickname and nickname.strip() and user.nickname != nickname.strip():
            user.nickname = nickname.strip()
            db.commit()
            db.refresh(user)
        return user

    display_name = (nickname or "").strip() or "微信用户"
    user = User(
        username=_generate_unique_username(db, mock_openid),
        password_hash=hash_password(secrets.token_urlsafe(24)),
        nickname=display_name,
        avatar_url=MOCK_AVATAR,
        role="user",
    )
    assign_wechat_openid(user, mock_openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Mock 微信用户创建: {user.username} (openid={mock_openid})")
    return user


def _ensure_enabled():
    if not settings.WECHAT_MOCK_ENABLED:
        raise HTTPException(status_code=404, detail="微信登录未启用")


def _bind_wechat_to_user(
    db: Session,
    user: User,
    mock_openid: str,
    nickname: str | None,
) -> User | str:
    if user.wechat_openid:
        return "您已绑定微信"

    owner = find_user_by_wechat_openid(db, mock_openid)
    if owner and owner.id != user.id:
        return "该微信已被其他账号绑定"

    assign_wechat_openid(user, mock_openid)
    if not user.avatar_url:
        user.avatar_url = MOCK_AVATAR
    if nickname and nickname.strip() and not user.nickname:
        user.nickname = nickname.strip()
    db.commit()
    db.refresh(user)
    logger.info(f"用户 {user.username} 绑定微信: {mock_openid}")
    return user


@router.get("/bind/qrcode")
def create_wechat_bind_qrcode(user: User = Depends(require_current_user)):
    _ensure_enabled()
    if user.wechat_openid:
        return fail("您已绑定微信")

    _cleanup_expired_sessions()
    state = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=settings.WECHAT_SESSION_TTL_SECONDS
    )
    confirm_url = f"{settings.wechat_confirm_base_url}/api/auth/wechat/confirm?state={state}"
    lan_ip = detect_lan_ip()

    _pending_sessions[state] = WechatPendingSession(
        state=state,
        expires_at=expires_at,
        mode="bind",
        bind_user_id=user.id,
    )

    return ok(
        {
            "state": state,
            "confirm_url": confirm_url,
            "qrcode_base64": _make_qrcode_base64(confirm_url),
            "expires_in": settings.WECHAT_SESSION_TTL_SECONDS,
            "lan_ip": lan_ip,
            "network_hint": "扫码确认后，将把微信绑定到当前登录账号。",
        }
    )


@router.get("/bind/poll")
def poll_wechat_bind(state: str):
    _ensure_enabled()
    session = _get_session(state)
    if not session or session.mode != "bind":
        return ok({"status": "expired", "user": None})

    if session.status == "confirmed" and session.user_payload:
        return ok({"status": "confirmed", "user": session.user_payload})

    if session.status == "expired":
        return ok({"status": "expired", "user": None})

    return ok({"status": "waiting", "user": None})


@router.get("/unbind/qrcode")
def create_wechat_unbind_qrcode(user: User = Depends(require_current_user)):
    _ensure_enabled()
    if not user.wechat_openid:
        return fail("您尚未绑定微信")
    guard = ensure_can_remove_method(user, "wechat")
    if guard:
        return fail(guard)

    _cleanup_expired_sessions()
    state = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=settings.WECHAT_SESSION_TTL_SECONDS
    )
    confirm_url = f"{settings.wechat_confirm_base_url}/api/auth/wechat/confirm?state={state}"
    _pending_sessions[state] = WechatPendingSession(
        state=state,
        expires_at=expires_at,
        mode="unbind",
        bind_user_id=user.id,
    )
    return ok(
        {
            "state": state,
            "confirm_url": confirm_url,
            "qrcode_base64": _make_qrcode_base64(confirm_url),
            "expires_in": settings.WECHAT_SESSION_TTL_SECONDS,
            "lan_ip": detect_lan_ip(),
            "network_hint": "请使用已绑定的微信扫码确认解绑。",
        }
    )


@router.get("/unbind/poll")
def poll_wechat_unbind(state: str):
    _ensure_enabled()
    session = _get_session(state)
    if not session or session.mode != "unbind":
        return ok({"status": "expired", "user": None})
    if session.status == "confirmed" and session.user_payload:
        return ok({"status": "confirmed", "user": session.user_payload})
    if session.status == "expired":
        return ok({"status": "expired", "user": None})
    return ok({"status": "waiting", "user": None})


@router.get("/rebind/qrcode")
def create_wechat_rebind_qrcode(user: User = Depends(require_current_user)):
    _ensure_enabled()
    if not user.wechat_openid:
        return fail("您尚未绑定微信，请使用绑定功能")

    _cleanup_expired_sessions()
    state = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=settings.WECHAT_SESSION_TTL_SECONDS
    )
    confirm_url = f"{settings.wechat_confirm_base_url}/api/auth/wechat/confirm?state={state}"
    _pending_sessions[state] = WechatPendingSession(
        state=state,
        expires_at=expires_at,
        mode="rebind",
        bind_user_id=user.id,
        rebind_step=1,
    )
    return ok(
        {
            "state": state,
            "confirm_url": confirm_url,
            "qrcode_base64": _make_qrcode_base64(confirm_url),
            "expires_in": settings.WECHAT_SESSION_TTL_SECONDS,
            "lan_ip": detect_lan_ip(),
            "network_hint": "第一步：请使用当前绑定的微信扫码确认。",
            "step": 1,
        }
    )


@router.get("/rebind/poll")
def poll_wechat_rebind(state: str):
    _ensure_enabled()
    session = _get_session(state)
    if not session or session.mode != "rebind":
        return ok({"status": "expired", "user": None, "step": 0})

    if session.status == "confirmed" and session.user_payload:
        return ok({"status": "confirmed", "user": session.user_payload, "step": 2})

    if session.rebind_step == 2 and session.status == "waiting":
        return ok({"status": "step1_done", "user": None, "step": 2})

    if session.status == "expired":
        return ok({"status": "expired", "user": None, "step": session.rebind_step})

    return ok({"status": "waiting", "user": None, "step": session.rebind_step or 1})


@router.get("/qrcode")
def create_wechat_qrcode():
    _ensure_enabled()
    _cleanup_expired_sessions()

    state = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=settings.WECHAT_SESSION_TTL_SECONDS
    )
    confirm_url = f"{settings.wechat_confirm_base_url}/api/auth/wechat/confirm?state={state}"
    lan_ip = detect_lan_ip()

    _pending_sessions[state] = WechatPendingSession(state=state, expires_at=expires_at)

    return ok(
        {
            "state": state,
            "confirm_url": confirm_url,
            "qrcode_base64": _make_qrcode_base64(confirm_url),
            "expires_in": settings.WECHAT_SESSION_TTL_SECONDS,
            "lan_ip": lan_ip,
            "network_hint": (
                "已自动检测局域网 IP，无需手动改 .env。"
                "后端请使用 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 启动；"
                "手机与电脑需同一网络，校园网扫不开可改用手机热点。"
            ),
        }
    )


@router.get("/poll")
def poll_wechat_login(state: str):
    _ensure_enabled()
    session = _get_session(state)
    if not session:
        return ok(WechatPollResponse(status="expired").model_dump())

    if session.status == "confirmed" and session.auth_payload:
        auth = AuthResponse(**session.auth_payload)
        return ok(WechatPollResponse(status="confirmed", auth=auth).model_dump())

    if session.status == "expired":
        return ok(WechatPollResponse(status="expired").model_dump())

    return ok(WechatPollResponse(status="waiting").model_dump())


@router.get("/profile")
def get_wechat_profile(mock_openid: str, db: Session = Depends(get_db)):
    _ensure_enabled()
    openid = mock_openid.strip()
    if not openid:
        return ok({"exists": False})

    user = find_user_by_wechat_openid(db, openid)
    if not user:
        return ok({"exists": False})

    return ok(
        {
            "exists": True,
            "nickname": user.nickname or user.username,
            "username": user.username,
        }
    )


@router.get("/confirm", response_class=HTMLResponse)
def wechat_confirm_page(state: str):
    _ensure_enabled()
    session = _get_session(state)
    if not session or session.status == "expired":
        return HTMLResponse(
            content=_render_confirm_page(state, expired=True),
            status_code=400,
        )
    return HTMLResponse(content=_render_confirm_page(state, mode=session.mode, rebind_step=session.rebind_step))


@router.post("/confirm")
def confirm_wechat_login(body: WechatConfirmRequest, request: Request, db: Session = Depends(get_db)):
    _ensure_enabled()
    session = _get_session(body.state)
    if not session:
        return fail("二维码已过期，请重新获取")
    if session.status == "confirmed":
        return ok(
            {
                "message": "已确认",
                "mock_openid": session.returned_openid,
                "auth": session.auth_payload,
            }
        )
    if session.status == "expired":
        return fail("二维码已过期，请重新获取")

    mock_openid = (body.mock_openid or "").strip() or f"mock_{uuid.uuid4().hex}"

    if session.mode == "unbind" and session.bind_user_id:
        target = db.query(User).filter(User.id == session.bind_user_id).first()
        if not target:
            return fail("账号不存在")
        guard = ensure_can_remove_method(target, "wechat")
        if guard:
            return fail(guard)
        if get_wechat_openid_plain(target) != mock_openid:
            return fail("请使用已绑定的微信身份确认解绑")
        assign_wechat_openid(target, None)
        db.commit()
        db.refresh(target)
        user_payload = user_to_out(target).model_dump()
        session.status = "confirmed"
        session.user_payload = user_payload
        session.returned_openid = mock_openid
        logger.info(f"用户 {target.username} 解绑微信")
        log_operation(db, action="unbind_wechat", user=target, success=True, request=request)
        return ok({"message": "微信解绑成功", "mock_openid": mock_openid, "user": user_payload})

    if session.mode == "rebind" and session.bind_user_id:
        target = db.query(User).filter(User.id == session.bind_user_id).first()
        if not target or not target.wechat_openid:
            return fail("账号未绑定微信")

        if session.rebind_step == 1:
            if get_wechat_openid_plain(target) != mock_openid:
                return fail("请先使用当前绑定的微信扫码确认")
            session.rebind_step = 2
            session.status = "waiting"
            session.returned_openid = mock_openid
            return ok({"message": "旧微信验证成功，请再次扫码确认新微信", "step": 2})

        if mock_openid == get_wechat_openid_plain(target):
            return fail("新微信不能与当前微信相同")
        owner = find_user_by_wechat_openid(db, mock_openid)
        if owner and owner.id != target.id:
            return fail("该微信已被其他账号绑定")
        assign_wechat_openid(target, mock_openid)
        if not target.avatar_url:
            target.avatar_url = MOCK_AVATAR
        db.commit()
        db.refresh(target)
        user_payload = user_to_out(target).model_dump()
        session.status = "confirmed"
        session.user_payload = user_payload
        logger.info(f"用户 {target.username} 换绑微信: {mock_openid}")
        log_operation(db, action="rebind_wechat", user=target, success=True, request=request, detail={"mock_openid": mock_openid})
        return ok({"message": "微信换绑成功", "mock_openid": mock_openid, "user": user_payload})

    if session.mode == "bind" and session.bind_user_id:
        target = db.query(User).filter(User.id == session.bind_user_id).first()
        if not target:
            return fail("绑定账号不存在")
        result = _bind_wechat_to_user(db, target, mock_openid, body.nickname)
        if isinstance(result, str):
            return fail(result)
        user_payload = user_to_out(result).model_dump()
        session.status = "confirmed"
        session.user_payload = user_payload
        session.returned_openid = mock_openid
        log_operation(db, action="bind_wechat", user=result, success=True, request=request, detail={"mock_openid": mock_openid})
        return ok(
            {
                "message": "微信绑定成功",
                "mock_openid": mock_openid,
                "user": user_payload,
            }
        )

    user = _resolve_or_create_user(db, mock_openid, body.nickname)
    auth_payload = build_auth_response(user).model_dump()

    session.status = "confirmed"
    session.auth_payload = auth_payload
    session.returned_openid = mock_openid

    logger.info(f"Mock 微信扫码确认: {user.username} (state={body.state})")
    log_operation(db, action="login_wechat", user=user, success=True, request=request, detail={"mock_openid": mock_openid})
    return ok(
        {
            "message": "登录确认成功",
            "mock_openid": mock_openid,
            "auth": auth_payload,
        }
    )


def _render_confirm_page(state: str, expired: bool = False, mode: str = "login", rebind_step: int = 0) -> str:
    is_bind = mode == "bind"
    is_unbind = mode == "unbind"
    is_rebind = mode == "rebind"
    if expired:
        title = "二维码已过期"
        action_text = "请返回电脑重新扫码"
        desc_default = "当前确认链接已失效，请回到电脑端刷新二维码。"
    elif is_unbind:
        title = "CarMate 微信解绑确认"
        action_text = "确认解绑"
        desc_default = "确认后将解除当前账号的微信绑定（演示模式）。"
    elif is_rebind and rebind_step >= 2:
        title = "CarMate 微信换绑确认"
        action_text = "确认新微信"
        desc_default = "第二步：请确认新的微信身份，完成换绑。"
    elif is_rebind:
        title = "CarMate 微信换绑确认"
        action_text = "确认当前微信"
        desc_default = "第一步：请使用当前绑定的微信确认身份。"
    elif is_bind:
        title = "CarMate 微信绑定确认"
        action_text = "确认绑定"
        desc_default = "确认后将把微信绑定到您的 CarMate 账号（演示模式）。"
    else:
        title = "CarMate 微信登录确认"
        action_text = "确认登录"
        desc_default = "确认后将登录 CarMate 智能车载视觉系统（演示模式）。"
    welcome_login_hint = "点击下方按钮即可登录 CarMate"
    welcome_bind_hint = "点击下方按钮即可完成微信绑定"
    disabled = "disabled" if expired else ""
    button_style = "background:#ccc;cursor:not-allowed;" if expired else "background:#07c160;cursor:pointer;"
    hide_nickname = is_bind or is_unbind or is_rebind or expired

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: linear-gradient(160deg, #001529 0%, #1677ff 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      box-sizing: border-box;
    }}
    .card {{
      width: 100%;
      max-width: 360px;
      background: #fff;
      border-radius: 16px;
      padding: 28px 24px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
      text-align: center;
    }}
    .logo {{
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #e6f4ff;
      color: #1677ff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 20px;
      color: #1f2937;
    }}
    p {{
      margin: 0 0 20px;
      color: #6b7280;
      font-size: 14px;
      line-height: 1.6;
    }}
    .welcome {{
      display: none;
      margin: 0 0 20px;
      padding: 14px;
      background: #f6ffed;
      border: 1px solid #b7eb8f;
      border-radius: 10px;
      color: #389e0d;
      font-size: 15px;
      font-weight: 600;
      line-height: 1.6;
    }}
    input {{
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #d9d9d9;
      border-radius: 8px;
      padding: 12px;
      font-size: 14px;
      margin-bottom: 16px;
    }}
    button {{
      width: 100%;
      border: none;
      border-radius: 8px;
      color: #fff;
      font-size: 16px;
      padding: 12px;
      {button_style}
    }}
    .tip {{
      margin-top: 16px;
      font-size: 12px;
      color: #9ca3af;
      line-height: 1.6;
    }}
    .status {{
      margin-top: 12px;
      font-size: 14px;
      color: #1677ff;
      min-height: 20px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">C</div>
    <h1>{title}</h1>
    <p id="descText">{desc_default}</p>
    <div id="welcomeBox" class="welcome"></div>
    <input id="nickname" type="text" maxlength="20" placeholder="昵称（可选，默认：微信用户）" {disabled} />
    <button id="confirmBtn" {disabled}>{action_text}</button>
    <div id="status" class="status"></div>
    <div class="tip">演示说明：此为 Mock 微信扫码，不获取真实微信账号信息。下次扫码会记住本机模拟身份。</div>
  </div>
  <script>
    const state = {state!r};
    const expired = {str(expired).lower()};
    const isBind = {str(is_bind).lower()};
    const isUnbind = {str(is_unbind).lower()};
    const isRebind = {str(is_rebind).lower()};
    const storageKey = 'carmate_mock_wechat_openid';
    const statusEl = document.getElementById('status');
    const nicknameEl = document.getElementById('nickname');
    const confirmBtn = document.getElementById('confirmBtn');
    const welcomeBox = document.getElementById('welcomeBox');
    const descText = document.getElementById('descText');
    let isReturningUser = false;

    async function initPage() {{
      if (expired || isBind || isUnbind || isRebind) {{
        nicknameEl.style.display = 'none';
        if (expired) return;
      }}

      if (isUnbind || (isRebind && {rebind_step} >= 2)) {{
        return;
      }}

      if (isRebind) {{
        return;
      }}

      if (isBind) {{
        nicknameEl.style.display = 'none';
        return;
      }}

      const savedOpenid = localStorage.getItem(storageKey);
      if (!savedOpenid) {{
        return;
      }}

      try {{
        const response = await fetch('/api/auth/wechat/profile?mock_openid=' + encodeURIComponent(savedOpenid));
        const result = await response.json();
        if (result.code === 0 && result.data?.exists) {{
          isReturningUser = true;
          const displayName = result.data.nickname || '微信用户';
          welcomeBox.textContent = '欢迎回来，' + displayName;
          welcomeBox.style.display = 'block';
          nicknameEl.style.display = 'none';
          descText.textContent = isBind ? '{welcome_bind_hint}' : '{welcome_login_hint}';
        }}
      }} catch (error) {{
        console.warn('读取用户信息失败', error);
      }}
    }}

    if (!expired) {{
      initPage();
      confirmBtn.addEventListener('click', async () => {{
        confirmBtn.disabled = true;
        statusEl.textContent = '正在确认...';
        try {{
          const response = await fetch('/api/auth/wechat/confirm', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
              state,
              mock_openid: localStorage.getItem(storageKey) || undefined,
              nickname: (isBind || isUnbind || isRebind || isReturningUser) ? undefined : (nicknameEl.value.trim() || undefined),
            }}),
          }});
          const result = await response.json();
          if (result.code !== 0) {{
            throw new Error(result.message || '确认失败');
          }}
          if (result.data?.mock_openid) {{
            localStorage.setItem(storageKey, result.data.mock_openid);
          }}
          const doneText = isUnbind ? '解绑成功，请回到电脑查看' : (isRebind ? '确认成功，请回到电脑查看' : (isBind ? '绑定成功，请回到电脑查看' : '确认成功，请回到电脑查看'));
          statusEl.textContent = doneText;
          confirmBtn.textContent = '已完成';
        }} catch (error) {{
          statusEl.textContent = error.message || '确认失败，请重试';
          confirmBtn.disabled = false;
        }}
      }});
    }}
  </script>
</body>
</html>"""
