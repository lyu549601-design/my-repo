"""
FastAPI 入口模块
整合 RAG 问答系统的核心功能，提供 RESTful API
"""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from typing import List

from models.schemas import AskRequest, AskResponse, SourceNode, EvalScore
from core.retrieval import AdvancedRetriever
from core.generation import generate_answer
from core.evaluation import evaluate_rag_response


# 全局变量：高级检索器实例
advanced_retriever = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    在应用启动时加载必要的资源（如 Reranker 模型）
    """
    global advanced_retriever
    
    # 启动时：初始化高级检索器（加载 Reranker 模型等）
    print("正在初始化高级检索器...")
    advanced_retriever = AdvancedRetriever()
    print("高级检索器初始化完成")
    
    yield  # 应用运行期间
    
    # 关闭时：清理资源（如果需要）
    print("应用关闭，清理资源")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="RAG 问答系统",
    description="带评测闭环的垂直领域 RAG 问答系统",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """根路径，返回系统状态"""
    return {
        "message": "RAG 问答系统运行中",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.post("/api/v1/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    问答接口
    
    接收用户问题，返回答案、参考来源和评估结果
    
    Args:
        request: 问答请求，包含用户问题
        
    Returns:
        AskResponse: 包含答案、参考来源和评估结果的响应
        
    Raises:
        HTTPException: 处理过程中出现错误
    """
    global advanced_retriever
    
    # 检查检索器是否已初始化
    if advanced_retriever is None:
        raise HTTPException(
            status_code=503,
            detail="服务未就绪，高级检索器尚未初始化"
        )
    
    try:
        # 第一步：检索与重排
        # 调用 retrieve_and_rerank 获取重排后的高质量上下文
        retrieval_results = advanced_retriever.retrieve_and_rerank(request.query)
        
        if not retrieval_results:
            # 如果没有检索到相关内容，返回默认响应
            return AskResponse(
                answer="根据已知信息无法回答",
                sources=[],
                evaluation=EvalScore(
                    faithfulness_score=5,
                    relevance_score=1,
                    reasoning="未检索到相关文档，无法提供答案"
                )
            )
        
        # 提取上下文内容列表
        contexts = [result["content"] for result in retrieval_results]
        
        # 第二步：生成答案
        # 调用 generate_answer 结合 contexts 生成答案
        generated_answer = await generate_answer(request.query, contexts)
        
        # 第三步：评估答案质量
        # 调用 evaluate_rag_response 进行幻觉和质量检测
        evaluation_result = await evaluate_rag_response(
            query=request.query,
            contexts=contexts,
            generated_answer=generated_answer
        )
        
        # 第四步：构建响应
        # 将检索结果转换为 SourceNode 列表
        sources = [
            SourceNode(
                content=result["content"],
                score=result["score"]
            )
            for result in retrieval_results
        ]
        
        # 构建评估结果
        evaluation = EvalScore(
            faithfulness_score=evaluation_result["faithfulness_score"],
            relevance_score=evaluation_result["relevance_score"],
            reasoning=evaluation_result["reasoning"]
        )
        
        # 返回最终响应
        return AskResponse(
            answer=generated_answer,
            sources=sources,
            evaluation=evaluation
        )
        
    except Exception as e:
        # 捕获所有异常，返回 HTTP 500 错误
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生错误: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    # 启动 FastAPI 应用
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )