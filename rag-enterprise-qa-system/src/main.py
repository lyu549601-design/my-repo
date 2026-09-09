"""RAG 系统入口。"""

import uvicorn

from src.rag.config import get_settings


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.rag.mcp_server:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )
