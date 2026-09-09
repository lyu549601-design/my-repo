"""Embedding 生成器。"""

from __future__ import annotations

import asyncio
import hashlib


class LocalEmbedder:
    """本地轻量中文 Embedding。"""

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
    """确定性伪向量，用于离线测试。"""

    def __init__(self, dim: int = 16):
        self.dim = dim

    def _hash_to_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [
            (digest[i % len(digest)] / 255.0) * 2.0 - 1.0
            for i in range(self.dim)
        ]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._hash_to_vector(text)
