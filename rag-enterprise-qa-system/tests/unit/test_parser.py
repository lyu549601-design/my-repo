"""文档解析与切片单元测试。"""

from src.rag.parser import (
    DocumentParser,
    estimate_tokens,
    split_text_into_chunks,
    table_to_markdown_rows,
)


class TestParser:
    def test_estimate_tokens(self):
        assert estimate_tokens("新能源汽车") >= 5
        assert estimate_tokens("hello world") == 2

    def test_split_text_into_chunks_respects_budget(self):
        text = "市场增长。" * 200
        chunks = split_text_into_chunks(text, max_tokens=50)

        assert len(chunks) > 1
        assert all(estimate_tokens(chunk) <= 50 for chunk in chunks)

    def test_table_to_markdown_rows(self):
        lines = table_to_markdown_rows(
            ["指标", "数值"],
            [["收入", "100"], ["利润", "20"]],
        )

        assert "指标" in lines[0]
        assert "100" in lines[0]
        assert "利润" in lines[1]

    def test_make_chunk_keeps_document_and_page(self):
        parser = DocumentParser(max_chunk_tokens=500)
        chunk = parser._make_chunk(
            document_id="doc_001",
            title="测试.pdf",
            page=12,
            content="目标市场份额为25%",
        )

        assert chunk.document_id == "doc_001"
        assert chunk.page == 12
        assert chunk.metadata["document_title"] == "测试.pdf"
