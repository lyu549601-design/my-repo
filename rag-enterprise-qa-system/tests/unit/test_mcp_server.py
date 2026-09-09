"""RAG MCP 适配器单元测试。"""

from fastapi.testclient import TestClient

from src.rag.mcp_server import app, get_retriever
from src.rag.models import RetrievedChunk


class FakeRetriever:
    async def retrieve(self, user, query):
        return [
            RetrievedChunk(
                chunk_id="c1",
                document_id="doc_001",
                document_name="测试.pdf",
                page=1,
                content="新能源汽车市场份额",
                score=0.9,
            )
        ]


class TestMCPAdapter:
    def test_execute_rag_search(self):
        fake = FakeRetriever()
        app.dependency_overrides[get_retriever] = lambda: fake
        client = TestClient(app)
        try:
            response = client.post(
                "/execute",
                json={
                    "tool": "rag_search",
                    "params": {
                        "query": "市场份额",
                        "user_id": "u1",
                        "department_ids": ["dept_1"],
                        "project_ids": ["proj_1"],
                    },
                    "request_id": "req_1",
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["result"]["total"] == 1
        assert data["result"]["chunks"][0]["document_name"] == "测试.pdf"

    def test_unknown_tool(self):
        client = TestClient(app)
        response = client.post(
            "/execute",
            json={"tool": "unknown", "params": {}, "request_id": "req_1"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_health(self):
        client = TestClient(app)
        response = client.get("/health")

        assert response.json()["status"] == "healthy"
