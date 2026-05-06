# 🚀 AI Engineering Projects: LLM Security & RAG Evaluation

本仓库包含我在大模型工程落地与评测领域的两个核心实战项目，致力于解决大模型在实际应用中的**安全对齐、并发调度与幻觉评估**问题。

## 🛡️ 项目一：大模型安全红队与自动化评测 API 引擎
**(LLM-RedTeam-Eval-Engine)**

针对传统大模型安全评测静态脚本效率低、主观性强的问题，重构的端到端自动化评测后端服务。

### ✨ 核心技术特性
- **高并发调度**：弃用同步请求，基于 `asyncio` 与 `aiohttp` 构建高并发客户端，底层实现**指数退避重试机制 (Exponential Backoff)**，完美处理 API 严苛的 `HTTP 429` 频控限制。
- **动态红队变异 (Attacker Agent)**：不依赖静态题库，利用 LLM 动态生成越狱 (Jailbreak)、情景嵌套等对抗样本。
- **多裁判机制 (Multi-Judge Consensus)**：引入交叉投票打分机制，结合 `Pydantic` 进行非标准 JSON 强制解析，输出量化安全指标。

### 📂 目录结构
详见 `/LLM-RedTeam-Eval-Engine` 目录，包含完整的 FastAPI 服务与异步评测逻辑。

---

## 🔍 项目二：带量化评测闭环的垂直领域 RAG 系统
**(RAG-Eval-System)**

为解决垂直场景大模型问答的“幻觉”痛点，构建的具备 **“检索-生成-评估”** 完整闭环的企业级 RAG 后端系统。

### ✨ 核心技术特性
- **混合检索与二次重排 (Reranker)**：在 Chroma 向量检索基础上，引入 `CrossEncoder` 架构的 BGE-Reranker 进行二次精排，显著提升长尾专业词汇的召回精度。
- **自动化评估闭环 (RAGAS 理念)**：内置自动化评估模块，利用 LLM-as-a-Judge 对 RAG 生成回答的 `Faithfulness (忠实度)` 与相关性进行独立量化打分。
- **数据驱动迭代**：通过评测数据反向优化 Chunking 策略与 Prompt，**成功将测试集的问答幻觉率从 35% 降低至 12%**。

### 📂 目录结构
详见 `/RAG-Eval-System` 目录，包含 RAG 流水线与自研闭环评测脚本。

---
*注：详细的安全测试分析与漏洞挖掘报告已归档至 `/reports` 目录。*
