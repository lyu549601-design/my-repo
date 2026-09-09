"""向量生成器。"""

from __future__ import annotations

import hashlib
import asyncio
from typing import Protocol

import structlog

from src.config import Settings

logger = structlog.get_logger()


class Embedder(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    """基于 OpenAI Embeddings API 的向量生成器。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                model=self.settings.embedding_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )
        return self._client

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        return await client.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        client = self._get_client()
        return await client.aembed_query(text)


class LocalEmbedder:
    """本地轻量中文 Embedding，避免把向量请求发往 DeepSeek/OpenAI。"""

    def __init__(self, model_name: str, dim: int = 512):
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [vector[: self.dim].tolist() for vector in vectors]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


class HashingEmbedder:
    """确定性伪向量，用于开发、测试和离线检索。"""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def _hash_to_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [0.0] * self.dim
        for i in range(self.dim):
            vector[i] = (digest[i % len(digest)] / 255.0) * 2.0 - 1.0
        return vector

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._hash_to_vector(text)
