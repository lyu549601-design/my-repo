"""无 Docker 端到端演示：Excel 入库 -> 权限混合检索 -> DeepSeek 引用问答。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.config import get_settings
from src.rag.embedder import LocalEmbedder
from src.rag.memory_store import MemoryStore
from src.rag.models import Document, UserContext
from src.rag.parser import DocumentParser
from src.rag.qa_engine import DeepSeekClient, QAEngine
from src.rag.retriever import HybridRetriever


async def main() -> None:
    settings = get_settings()
    sample_dir = Path(__file__).resolve().parent.parent / "sample_data"
    sample_dir.mkdir(exist_ok=True)
    sample_file = sample_dir / "2026市场目标.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "市场目标"
    sheet.append(["指标", "2026年目标", "说明"])
    sheet.append(["市场份额", "25%", "新能源市场目标份额"])
    sheet.append(["营收", "1000亿元", "全年营收目标"])
    sheet.append(["海外占比", "30%", "海外市场收入占比"])
    workbook.save(sample_file)

    document = Document(
        id="doc_demo_001",
        title="2026市场目标.xlsx",
        file_path=str(sample_file),
        file_type="xlsx",
        page_count=1,
        project_folder_id="proj_market",
        visible_department_ids=["dept_strategy"],
    )

    parser = DocumentParser(max_chunk_tokens=settings.max_chunk_tokens)
    chunks = await parser.parse_file(
        path=str(sample_file),
        document_id=document.id,
        title=document.title,
    )

    embedder = LocalEmbedder(settings.embedding_model, settings.embedding_dim)
    texts = [chunk.content for chunk in chunks]
    embeddings = await embedder.embed_texts(texts)
    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding

    store = MemoryStore()
    await store.upsert_document(document)
    await store.insert_chunks(chunks)

    retriever = HybridRetriever(
        db=store,
        embedder=embedder,
        alpha=settings.bm25_weight,
        top_k=settings.retrieval_top_k,
        semantic_expansion=settings.semantic_expansion,
    )
    llm = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    engine = QAEngine(
        retriever=retriever,
        llm=llm,
        confidence_threshold=settings.confidence_threshold,
    )

    user = UserContext(
        user_id="u_1001",
        department_ids=["dept_strategy"],
        project_ids=["proj_market"],
    )
    question = "2026年新能源市场的目标市场份额是多少？"
    result = await engine.answer(user, question)

    print("=" * 60)
    print("问题：", question)
    print("答案：", result.answer)
    print("置信度：", round(result.confidence, 4))
    print("是否拒答：", result.rejected)
    print("引用：")
    for citation in result.citations:
        print(
            f"  [Ref-{citation.ref_id}] "
            f"{citation.document_name} 第{citation.page}页 "
            f"来源内容：{citation.content[:80]}"
        )
    print("=" * 60)


if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    asyncio.run(main())
