from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import db_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_wechat_columns()
    ensure_alert_columns()


def ensure_wechat_columns():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("users")}
    migrations = [
        ("wechat_openid", "ALTER TABLE users ADD COLUMN wechat_openid VARCHAR(64) UNIQUE"),
        ("wechat_unionid", "ALTER TABLE users ADD COLUMN wechat_unionid VARCHAR(64) UNIQUE"),
        ("nickname", "ALTER TABLE users ADD COLUMN nickname VARCHAR(64)"),
        ("avatar_url", "ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255)"),
    ]

    with engine.begin() as conn:
        for column_name, ddl in migrations:
            if column_name not in existing:
                conn.execute(text(ddl))

    # history_records.session_id — 追踪会话历史记录的关联键
    if "history_records" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("history_records")}
        if "session_id" not in existing:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE history_records ADD COLUMN session_id VARCHAR(36) NULL"
                ))
                conn.execute(text(
                    "CREATE INDEX ix_history_records_session_id "
                    "ON history_records(session_id)"
                ))


def ensure_alert_columns():
    """迁移：为 alert_records 表添加告警智能体所需的新字段"""
    inspector = inspect(engine)
    if "alert_records" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("alert_records")}
    alert_migrations = [
        ("acknowledged_by", "ALTER TABLE alert_records ADD COLUMN acknowledged_by VARCHAR(50) NULL"),
        ("acknowledged_at", "ALTER TABLE alert_records ADD COLUMN acknowledged_at DATETIME NULL"),
        ("anomaly_type", "ALTER TABLE alert_records ADD COLUMN anomaly_type VARCHAR(50) NULL"),
        ("impact_scope", "ALTER TABLE alert_records ADD COLUMN impact_scope VARCHAR(200) NULL"),
        ("suggested_actions", "ALTER TABLE alert_records ADD COLUMN suggested_actions TEXT NULL"),
        ("raw_event", "ALTER TABLE alert_records ADD COLUMN raw_event TEXT NULL"),
        ("notified_channels", "ALTER TABLE alert_records ADD COLUMN notified_channels VARCHAR(200) NULL"),
    ]

    with engine.begin() as conn:
        for column_name, ddl in alert_migrations:
            if column_name not in existing:
                conn.execute(text(ddl))

    # 创建 anomaly_type 索引
    if "anomaly_type" not in existing:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX ix_alert_records_anomaly_type "
                    "ON alert_records(anomaly_type)"
                ))
        except Exception:
            pass  # 索引可能已存在
