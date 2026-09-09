"""数据清洗MCP Server - 提供数据清洗、格式化、舆情分析等能力"""

import json
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
from datetime import datetime

app = FastAPI(title="Data Cleaner MCP Server", version="1.0.0")


class MCPRequest(BaseModel):
    tool: str
    params: dict[str, Any]
    request_id: str


@app.post("/execute")
async def execute_tool(request: MCPRequest):
    """执行数据处理工具"""
    try:
        tool = request.tool
        params = request.params

        if tool == "data_cleaner":
            result = await clean_data(params)
        elif tool == "sentiment_analyzer":
            result = await analyze_sentiment(params)
        elif tool == "chart_generator":
            result = await generate_chart(params)
        else:
            raise HTTPException(status_code=400, detail=f"未知工具: {tool}")

        return {
            "success": True,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def clean_data(params: dict[str, Any]) -> dict[str, Any]:
    """数据清洗与格式化"""
    data = params.get("data", {})
    rules = params.get("rules", {})

    # 简单的数据清洗逻辑
    cleaned = {}
    if isinstance(data, dict):
        for key, value in data.items():
            # 清理字符串
            if isinstance(value, str):
                cleaned[key] = value.strip()
            # 格式化数字
            elif isinstance(value, (int, float)):
                cleaned[key] = value
            # 递归清理
            elif isinstance(value, dict):
                cleaned[key] = (await clean_data({"data": value}))["cleaned_data"]
            else:
                cleaned[key] = value
    else:
        cleaned = data

    return {
        "cleaned_data": cleaned,
        "original_keys": len(data) if isinstance(data, dict) else 0,
        "cleaned_keys": len(cleaned) if isinstance(cleaned, dict) else 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def analyze_sentiment(params: dict[str, Any]) -> dict[str, Any]:
    """舆情分析"""
    text = params.get("text", "")
    language = params.get("language", "zh")

    # 简单的关键词匹配（生产环境应使用NLP模型）
    positive_keywords = ["增长", "提升", "突破", "创新", "领先", "优秀", "成功"]
    negative_keywords = ["下降", "亏损", "风险", "问题", "失败", "困难", "挑战"]

    text_lower = text.lower() if isinstance(text, str) else str(text)

    positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
    negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

    total = positive_count + negative_count
    if total == 0:
        sentiment_score = 0.5
    else:
        sentiment_score = positive_count / total

    if sentiment_score > 0.6:
        sentiment = "positive"
    elif sentiment_score < 0.4:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "text_length": len(text),
        "sentiment": sentiment,
        "sentiment_score": round(sentiment_score, 2),
        "positive_indicators": positive_count,
        "negative_indicators": negative_count,
        "language": language,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def generate_chart(params: dict[str, Any]) -> dict[str, Any]:
    """图表生成（返回图表配置，实际渲染由前端完成）"""
    data = params.get("data", {})
    chart_type = params.get("chart_type", "bar")
    options = params.get("options", {})

    # 返回ECharts配置
    chart_config = {
        "type": chart_type,
        "title": options.get("title", "数据图表"),
        "data": data,
        "options": {
            "responsive": True,
            "legend": True,
            **options,
        },
    }

    return {
        "chart_config": chart_config,
        "chart_type": chart_type,
        "format": "echarts",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cleaner-mcp"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
