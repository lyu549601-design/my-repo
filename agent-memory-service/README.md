# Agent 记忆管理系统（独立服务）

面向长任务 Agent 的任务内分层记忆服务，提供证据摘要、混合检索、Reviewer 上下文组装、重试反馈与任务清理能力。

## 启动

```powershell
docker compose up -d --build
```

访问：

- API 文档：http://localhost:8084/docs
- 健康检查：http://localhost:8084/health

## 主要接口

```text
POST   /tasks/{task_id}/evidence
POST   /tasks/{task_id}/feedback
POST   /tasks/{task_id}/reviewer-context
GET    /tasks/{task_id}/retry-feedback
GET    /tasks/{task_id}/evidence/{source_task}
DELETE /tasks/{task_id}
GET    /health
```

## 配置

对话模型由调用方负责；本服务使用本地 Embedding 模型，默认 `BAAI/bge-small-zh-v1.5`，向量维度 512。
