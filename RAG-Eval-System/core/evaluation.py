"""
RAG 评测模块
实现 RAGAS 评测机制，评估答案的忠实度和相关性
"""

import aiohttp
import json
import re
from typing import List, Dict, Any

from core.config import settings


async def evaluate_rag_response(query: str, contexts: List[str], generated_answer: str) -> Dict[str, Any]:
    """
    评估 RAG 生成的答案质量
    
    Args:
        query: 用户提出的问题
        contexts: 检索到的文档片段内容列表
        generated_answer: 大模型生成的答案
        
    Returns:
        Dict: 包含评估结果的字典
            - faithfulness_score: 忠实度评分 (1-5)
            - relevance_score: 相关性评分 (1-5)
            - reasoning: 评分理由
            
    Raises:
        Exception: API 调用失败或解析错误
    """
    # 组装评测 Prompt
    # 要求 LLM 作为无情的裁判，评估忠实度和相关性
    evaluation_prompt = """你是一个严格的答案质量评估专家。你的任务是评估生成的答案是否符合要求。

**评估维度**：

1. **忠实度 (Faithfulness)**：评估生成的答案是否完全忠实于提供的参考信息，有没有胡编乱造（幻觉）？
   - 1分：答案完全基于外部知识或猜测，与参考信息无关
   - 2分：答案大部分基于外部知识，只有少量来自参考信息
   - 3分：答案混合了参考信息和外部知识
   - 4分：答案主要基于参考信息，只有少量推测
   - 5分：答案完全基于参考信息，没有任何幻觉

2. **相关性 (Relevance)**：答案是否直接回答了用户的 query？
   - 1分：答案完全跑题，与问题无关
   - 2分：答案与问题相关，但没有直接回答
   - 3分：答案部分回答了问题
   - 4分：答案基本回答了问题，但不够完整
   - 5分：答案完整、准确地回答了问题

**参考信息**：
{contexts}

**用户问题**：{query}

**生成的答案**：{generated_answer}

请严格评估上述答案，输出严格的 JSON 格式，包含以下字段：
- faithfulness: 忠实度评分 (1-5 的整数)
- relevance: 相关性评分 (1-5 的整数)
- reasoning: 详细的评分理由，解释为什么给出这样的分数

**输出格式**（严格 JSON，不要有其他内容）：
```json
{{
    "faithfulness": <分数>,
    "relevance": <分数>,
    "reasoning": "<评分理由>"
}}
```"""

    # 将 contexts 列表格式化为带编号的文本
    contexts_text = "\n\n".join([f"[{i+1}] {ctx}" for i, ctx in enumerate(contexts)])
    
    # 填充 Prompt
    formatted_prompt = evaluation_prompt.format(
        contexts=contexts_text,
        query=query,
        generated_answer=generated_answer
    )
    
    # 构建请求 payload
    payload = {
        "model": settings.MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一个严格的答案质量评估专家，只输出 JSON 格式的评估结果。"},
            {"role": "user", "content": formatted_prompt}
        ],
        "temperature": 0.0,  # 零温度，确保输出稳定
        "max_tokens": 512,
        "stream": False
    }
    
    # 设置请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}"
    }
    
    # API 端点
    url = f"{settings.BASE_URL}/chat/completions"
    
    try:
        # 使用 aiohttp 异步调用 API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                # 检查响应状态
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API 调用失败，状态码: {response.status}, 错误: {error_text}")
                
                # 解析响应
                result = await response.json()
                
                # 提取生成的评估结果
                if "choices" in result and len(result["choices"]) > 0:
                    evaluation_text = result["choices"][0]["message"]["content"].strip()
                    
                    # 解析 JSON 格式的评估结果
                    return _parse_evaluation_json(evaluation_text)
                else:
                    raise Exception("API 响应格式错误，缺少 choices 字段")
                    
    except aiohttp.ClientError as e:
        raise Exception(f"网络请求失败: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON 解析失败: {str(e)}")
    except Exception as e:
        raise Exception(f"评估失败: {str(e)}")


def _parse_evaluation_json(evaluation_text: str) -> Dict[str, Any]:
    """
    解析评估结果的 JSON 文本
    
    Args:
        evaluation_text: 大模型返回的评估文本
        
    Returns:
        Dict: 解析后的评估结果
        
    Raises:
        ValueError: JSON 解析失败
    """
    try:
        # 尝试直接解析 JSON
        # 先尝试提取 JSON 块（可能被包裹在 ```json ... ``` 中）
        json_match = re.search(r'```json\s*(.*?)\s*```', evaluation_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析整个文本
            json_str = evaluation_text
        
        # 解析 JSON
        evaluation_data = json.loads(json_str)
        
        # 验证必需字段
        required_fields = ["faithfulness", "relevance", "reasoning"]
        for field in required_fields:
            if field not in evaluation_data:
                raise ValueError(f"评估结果缺少必需字段: {field}")
        
        # 验证分数范围
        faithfulness = int(evaluation_data["faithfulness"])
        relevance = int(evaluation_data["relevance"])
        
        if not (1 <= faithfulness <= 5):
            raise ValueError(f"忠实度分数超出范围 (1-5): {faithfulness}")
        if not (1 <= relevance <= 5):
            raise ValueError(f"相关性分数超出范围 (1-5): {relevance}")
        
        # 返回标准化的结果
        return {
            "faithfulness_score": faithfulness,
            "relevance_score": relevance,
            "reasoning": str(evaluation_data["reasoning"])
        }
        
    except json.JSONDecodeError as e:
        raise ValueError(f"评估结果 JSON 解析失败: {str(e)}, 原始文本: {evaluation_text}")
    except ValueError as e:
        raise e
    except Exception as e:
        raise ValueError(f"评估结果解析失败: {str(e)}")