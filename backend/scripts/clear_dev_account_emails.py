"""清空默认测试账号（admin/user）的邮箱，恢复为未绑定状态。"""
from app.core.database import SessionLocal
from app.models.db_models import User
from app.services.user_privacy_service import assign_email, get_email_plain

DEV_USERNAMES = ("admin", "user")


def main() -> None:
    db = SessionLocal()
    try:
        cleared = 0
        for username in DEV_USERNAMES:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                print(f"[skip] {username}: 账号不存在")
                continue
            old_email = get_email_plain(user)
            if not old_email:
                print(f"[skip] {username}: 邮箱已是未绑定")
                continue
            assign_email(user, None)
            cleared += 1
            print(f"[ok] {username}: 已清空邮箱 ({old_email})")
        if cleared:
            db.commit()
        print(f"Done. Cleared email for {cleared} account(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
