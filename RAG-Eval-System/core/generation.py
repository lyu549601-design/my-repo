"""
答案生成模块
基于检索到的上下文，使用大模型生成答案
"""

import aiohttp
import json
from typing import List

from core.config import settings


async def generate_answer(query: str, contexts: List[str]) -> str:
    """
    基于检索到的上下文生成答案
    
    Args:
        query: 用户提出的问题
        contexts: 检索到的文档片段内容列表
        
    Returns:
        str: 大模型生成的答案
        
    Raises:
        Exception: API 调用失败或解析错误
    """
    # 组装严格的 System Prompt
    # 要求模型只能基于提供的 contexts 回答，如果 contexts 中没有答案，必须回答“根据已知信息无法回答”
    system_prompt = """你是一个严谨的问答助手。你的任务是基于提供的参考信息回答用户问题。

**严格规则**：
1. **只能**使用提供的参考信息来回答问题，**绝对不能**使用任何外部知识或猜测。
2. 如果参考信息中没有足够的信息来回答问题，**必须**回答：“根据已知信息无法回答”。
3. 回答要简洁、准确、完整，直接回答问题，不要添加多余的解释。
4. 如果参考信息中有矛盾，以最新或最相关的信息为准。

**参考信息**：
{contexts}

**用户问题**：{query}

请基于上述参考信息回答问题。"""

    # 将 contexts 列表格式化为带编号的文本
    contexts_text = "\n\n".join([f"[{i+1}] {ctx}" for i, ctx in enumerate(contexts)])
    
    # 填充 Prompt
    formatted_prompt = system_prompt.format(
        contexts=contexts_text,
        query=query
    )
    
    # 构建请求 payload
    payload = {
        "model": settings.MODEL_NAME,
        "messages": [
            {"role": "system", "content": formatted_prompt},
            {"role": "user", "content": query}
        ],
        "temperature": 0.1,  # 低温度，确保回答稳定
        "max_tokens": 1024,
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
                
                # 提取生成的答案
                if "choices" in result and len(result["choices"]) > 0:
                    answer = result["choices"][0]["message"]["content"].strip()
                    return answer
                else:
                    raise Exception("API 响应格式错误，缺少 choices 字段")
                    
    except aiohttp.ClientError as e:
        raise Exception(f"网络请求失败: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON 解析失败: {str(e)}")
    except Exception as e:
        raise Exception(f"答案生成失败: {str(e)}")