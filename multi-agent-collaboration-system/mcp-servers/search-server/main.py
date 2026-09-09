"""搜索MCP Server - 提供网页实时搜索能力"""

import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any

app = FastAPI(title="Search MCP Server", version="1.0.0")


class MCPRequest(BaseModel):
    tool: str
    params: dict[str, Any]
    request_id: str


class SearchResult(BaseModel):
    title: str
    snippet: str
    url: str
    source: str


@app.post("/execute")
async def execute_search(request: MCPRequest):
    """执行搜索工具"""
    try:
        query = request.params.get("query") or request.params.get("task_description")
        if not query:
            raise HTTPException(status_code=400, detail="缺少搜索关键词")

        num_results = request.params.get("num_results", 10)

        # 调用搜索API
        results = await search_via_serpapi(query, num_results)

        return {
            "success": True,
            "result": {
                "query": query,
                "results": [r.model_dump() for r in results],
                "total": len(results),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def search_via_serpapi(query: str, num_results: int = 10) -> list[SearchResult]:
    """通过SerpAPI执行搜索"""
    api_key = os.getenv("SERPAPI_KEY", "")
    
    if not api_key:
        # 返回模拟数据（开发环境）
        return [
            SearchResult(
                title=f"搜索结果 {i}: {query}",
                snippet=f"这是关于{query}的搜索结果摘要...",
                url=f"https://example.com/result{i}",
                source="mock",
            )
            for i in range(1, min(num_results + 1, 6))
        ]

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": api_key,
                "num": num_results,
            },
        )
        data = response.json()

        results = []
        for item in data.get("organic_results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    url=item.get("link", ""),
                    source="serpapi",
                )
            )
        return results


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "search-mcp"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
