"""FastAPI应用入口"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.api.routes import router
from src.api.websocket import websocket_manager
from src.communication.event_bus import EventBus, Event

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# 全局EventBus
event_bus = EventBus()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    
    logger.info(
        "app.starting",
        env=settings.app_env,
        host=settings.app_host,
        port=settings.app_port,
    )

    # 注册EventBus事件处理器
    async def handle_event(event: Event):
        await websocket_manager.handle_event(event)

    event_bus.subscribe("plan_created", handle_event)
    event_bus.subscribe("level_executed", handle_event)
    event_bus.subscribe("level_reviewed", handle_event)
    event_bus.subscribe("report_completed", handle_event)

    yield

    logger.info("app.stopping")


app = FastAPI(
    title="多Agent协作系统 - 企业级自动化研报与竞品情报分析系统",
    description="基于LangGraph和MCP的多Agent协作系统，自动生成深度研报",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)


@app.websocket("/ws/reports/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket端点 - 实时推送任务进度"""
    await websocket_manager.connect(websocket, task_id)
    try:
        while True:
            # 保持连接，接收客户端消息
            data = await websocket.receive_text()
            
            # 处理客户端消息（如取消任务等）
            logger.info("ws.message_received", task_id=task_id, data=data)
            
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket, task_id)
    except Exception as e:
        logger.error("ws.error", task_id=task_id, error=str(e))
        await websocket_manager.disconnect(websocket, task_id)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "多Agent协作系统",
        "description": "企业级自动化研报与竞品情报分析系统",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
