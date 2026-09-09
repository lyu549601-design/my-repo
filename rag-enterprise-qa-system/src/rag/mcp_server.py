"""RAG MCP 适配器：将知识检索封装为标准工具端点。"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from .config import get_settings
from .db import RAGDatabase
from .embedder import LocalEmbedder
from .models import RetrievedChunk, UserContext
from .retriever import HybridRetriever

app = FastAPI(
    title="RAG 企业知识问答 MCP Server",
    description="通过 MCP 工具端点提供企业知识检索",
    version="1.0.0",
)


class MCPRequest(BaseModel):
    tool: str
    params: dict[str, Any]
    request_id: str = Field(default="")


def get_retriever() -> HybridRetriever:
    settings = get_settings()
    db = RAGDatabase(settings.postgres_url)
    embedder = LocalEmbedder(settings.embedding_model, settings.embedding_dim)
    return HybridRetriever(
        db=db,
        embedder=embedder,
        alpha=settings.bm25_weight,
        top_k=settings.retrieval_top_k,
        semantic_expansion=settings.semantic_expansion,
    )


@app.post("/execute")
async def execute(
    request: MCPRequest,
    retriever: HybridRetriever = Depends(get_retriever),
):
    if request.tool not in {"rag_search", "knowledge_search"}:
        return {
            "success": False,
            "error_code": "TOOL_NOT_FOUND",
            "error_message": f"未知工具: {request.tool}",
        }

    params = request.params
    query = params.get("query") or params.get("question") or ""
    user = UserContext(
        user_id=params.get("user_id", "unknown"),
        department_ids=params.get("department_ids", []),
        role_ids=params.get("role_ids", []),
        project_ids=params.get("project_ids", []),
    )
    chunks: list[RetrievedChunk] = await retriever.retrieve(user, query)
    return {
        "success": True,
        "result": {
            "query": query,
            "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
            "total": len(chunks),
        },
        "request_id": request.request_id,
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "rag-mcp"}
