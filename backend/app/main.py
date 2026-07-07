from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import (
    auth,
    driver_gesture,
    plate,
    police_gesture,
    alerts,
    history,
    stats
)
from app.core.database import SessionLocal, init_db
from app.api.v1.auth import seed_default_users
from app.utils.logger import logger

app = FastAPI(
    title="CarMate 车载视觉系统",
    version="1.0.0",
    docs_url="/docs",
    description="智能车载视觉感知系统后端 API"
)

# 配置 CORS（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有，生产环境请限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由（统一前缀 /api）
app.include_router(auth.router, prefix="/api", tags=["用户认证"])
app.include_router(driver_gesture.router, prefix="/api", tags=["车主手势控车"])
app.include_router(plate.router, prefix="/api", tags=["车牌识别"])
app.include_router(police_gesture.router, prefix="/api", tags=["交警手势识别"])
app.include_router(alerts.router, prefix="/api", tags=["告警管理"])
app.include_router(history.router, prefix="/api", tags=["历史记录"])
app.include_router(stats.router, prefix="/api", tags=["仪表盘统计"])


@app.get("/")
async def root():
    return {"message": "CarMate 后端服务已启动，访问 /docs 查看接口文档"}


@app.on_event("startup")
async def startup_event():
    init_db()
    db = SessionLocal()
    try:
        seed_default_users(db)
    finally:
        db.close()
    logger.info("🚀 CarMate 服务启动成功，访问 http://127.0.0.1:8000/docs")