"""序列化工具"""

import json
import re
from datetime import datetime, date
from typing import Any
from pydantic import BaseModel


class DateTimeEncoder(json.JSONEncoder):
    """日期时间编码器"""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        return super().default(obj)


def json_serializer(obj: Any, **kwargs) -> str:
    """JSON序列化"""
    return json.dumps(obj, cls=DateTimeEncoder, ensure_ascii=False, **kwargs)


def json_deserializer(text: str) -> Any:
    """JSON反序列化"""
    return json.loads(text)


def extract_json_object(text: str) -> Any:
    """从LLM返回文本中提取JSON对象，兼容 ```json 围栏"""
    if not text:
        raise ValueError("空响应")
    cleaned = re.sub(r"```(?:json)?", "", text)
    cleaned = cleaned.replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("响应中未找到JSON对象")
    return json.loads(cleaned[start:end + 1])
