"""批量加密 users 表中仍为明文的隐私字段。"""
from app.core.database import SessionLocal
from app.services.user_privacy_service import migrate_user_privacy_fields


def main() -> None:
    db = SessionLocal()
    try:
        count = migrate_user_privacy_fields(db)
        print(f"Done. Encrypted privacy fields for {count} user(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
