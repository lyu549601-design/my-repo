"""引用注入与后验映射问答引擎。"""

from __future__ import annotations

import re
from typing import Protocol

import httpx

from .models import Citation, QAResult, RetrievedChunk, UserContext
from .retriever import HybridRetriever


class LLMClient(Protocol):
    async def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class DeepSeekClient:
    """DeepSeek V4 Flash（OpenAI 兼容接口）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-v4-flash",
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class QAEngine:
    """RAG 问答：检索 -> Ref 注入 -> 生成 -> 后验引用映射。"""

    SYSTEM_PROMPT = """你是企业知识库问答助手。
规则：
1. 只能使用给定的参考资料回答。
2. 每个关键结论必须使用 [Ref-N] 标注来源。
3. 若参考资料无法回答，必须回答“知识库中未找到可靠依据”，禁止编造。"""

    def __init__(
        self,
        retriever: HybridRetriever,
        llm: LLMClient,
        confidence_threshold: float = 0.65,
    ):
        self.retriever = retriever
        self.llm = llm
        self.confidence_threshold = confidence_threshold

    async def answer(self, user: UserContext, question: str) -> QAResult:
        chunks = await self.retriever.retrieve(user, question)
        if not chunks:
            return QAResult(
                question=question,
                answer="知识库中未找到可靠依据",
                rejected=True,
                rejection_reason="无可用检索结果",
            )

        confidence = max(chunk.score for chunk in chunks)
        if confidence < self.confidence_threshold:
            return QAResult(
                question=question,
                answer="知识库中未找到可靠依据",
                confidence=confidence,
                rejected=True,
                rejection_reason=f"检索置信度 {confidence:.3f} 低于阈值 {self.confidence_threshold}",
            )

        refs = self._build_refs(chunks)
        user_prompt = f"{refs}\n\n用户问题：{question}"
        raw_answer = await self.llm.complete(self.SYSTEM_PROMPT, user_prompt)
        citations = self._map_citations(raw_answer, chunks)

        if not citations:
            return QAResult(
                question=question,
                answer=raw_answer,
                confidence=confidence,
                rejected=True,
                rejection_reason="答案未包含可验证引用",
            )

        return QAResult(
            question=question,
            answer=raw_answer,
            citations=citations,
            confidence=confidence,
            rejected=False,
        )

    @staticmethod
    def _build_refs(chunks: list[RetrievedChunk]) -> str:
        lines = ["参考资料："]
        for index, chunk in enumerate(chunks, start=1):
            lines.append(
                f"[Ref-{index}] 《{chunk.document_name}》第 {chunk.page} 页：{chunk.content}"
            )
        return "\n".join(lines)

    @staticmethod
    def _map_citations(
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> list[Citation]:
        citations: list[Citation] = []
        ref_ids = sorted(
            {
                int(ref_id)
                for ref_id in re.findall(r"\[Ref-(\d+)\]", answer)
            }
        )
        for ref_id in ref_ids:
            if not 1 <= ref_id <= len(chunks):
                continue
            chunk = chunks[ref_id - 1]
            citations.append(
                Citation(
                    ref_id=ref_id,
                    document_id=chunk.document_id,
                    document_name=chunk.document_name,
                    page=chunk.page,
                    content=chunk.content[:300],
                )
            )
        return citations
