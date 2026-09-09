"""金融数据MCP Server - 提供股票、财报等金融数据查询"""

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
from datetime import datetime

app = FastAPI(title="Financial MCP Server", version="1.0.0")


class MCPRequest(BaseModel):
    tool: str
    params: dict[str, Any]
    request_id: str


@app.post("/execute")
async def execute_financial(request: MCPRequest):
    """执行金融数据查询"""
    try:
        symbol = request.params.get("symbol", "")
        data_type = request.params.get("data_type", "overview")
        period = request.params.get("period", "annual")

        # 获取金融数据
        data = await get_financial_data(symbol, data_type, period)

        return {
            "success": True,
            "result": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_financial_data(symbol: str, data_type: str, period: str) -> dict[str, Any]:
    """获取金融数据"""
    tushare_token = os.getenv("TUSHARE_TOKEN", "")

    if not tushare_token:
        # 返回模拟数据（开发环境）
        return _get_mock_data(symbol, data_type)

    # 实际调用Tushare API
    # 注：需要安装 tushare 库
    # import tushare as ts
    # pro = ts.pro_api(tushare_token)
    # ...

    return _get_mock_data(symbol, data_type)


def _get_mock_data(symbol: str, data_type: str) -> dict[str, Any]:
    """模拟数据"""
    mock_companies = {
        "BYD": {
            "name": "比亚迪",
            "revenue": 602315000000,
            "net_profit": 30041000000,
            "total_assets": 624466000000,
            "market_cap": 780000000000,
            "pe_ratio": 25.6,
            "stock_price": 268.50,
        },
        "NIO": {
            "name": "蔚来汽车",
            "revenue": 55617900000,
            "net_profit": -20719800000,
            "total_assets": 87824000000,
            "market_cap": 98000000000,
            "pe_ratio": -4.7,
            "stock_price": 56.80,
        },
        "LI": {
            "name": "理想汽车",
            "revenue": 123851000000,
            "net_profit": 11809000000,
            "total_assets": 145263000000,
            "market_cap": 280000000000,
            "pe_ratio": 23.7,
            "stock_price": 132.40,
        },
    }

    company = mock_companies.get(symbol.upper(), {
        "name": symbol,
        "revenue": 100000000000,
        "net_profit": 10000000000,
        "total_assets": 200000000000,
        "market_cap": 300000000000,
        "pe_ratio": 30.0,
        "stock_price": 100.00,
    })

    return {
        "symbol": symbol,
        "data_type": data_type,
        "period": "2025",
        "data": company,
        "source": "mock",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "financial-mcp"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
