# RAG 企业知识问答系统

企业私有化内部文档知识问答系统，基于 FastAPI + PostgreSQL/pgvector + DeepSeek V4 Flash。

## 核心模块

- `src/rag/retriever.py`：权限前置过滤 + BM25/向量混合检索
- `src/rag/parser.py`：Word/PDF/PPT/Excel 解析与表格行级切片
- `src/rag/qa_engine.py`：引用注入、后验映射、拒答兜底
- `src/rag/mcp_server.py`：标准 MCP 工具端点，供多 Agent 系统调用

## 运行测试

```powershell
python -m pytest -q
```

## 启动 MCP 服务

```powershell
python -m src.main
```

默认端口 8090，Swagger：http://localhost:8090/docs
