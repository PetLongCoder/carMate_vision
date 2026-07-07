import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DB_HOST: str = os.getenv("DB_HOST", "bj-cdb-mcxp1yss.sql.tencentcdb.com")
    DB_PORT: int = int(os.getenv("DB_PORT", "23196"))
    DB_USER: str = os.getenv("DB_USER", "zbl")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "zbl123456")
    DB_NAME: str = os.getenv("DB_NAME", "carmate")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "carmate-dev-secret-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

    CODE_TTL_SECONDS: int = int(os.getenv("CODE_TTL_SECONDS", "300"))

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )


settings = Settings()
