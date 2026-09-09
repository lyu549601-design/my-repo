# 部署指南

## 1. 环境要求

### 1.1 本地开发

- Python 3.11+
- Redis 7.0+
- PostgreSQL 15+
- Git

### 1.2 Docker部署

- Docker 20.10+
- Docker Compose 2.0+

### 1.3 Kubernetes部署

- Kubernetes 1.24+
- kubectl
- Helm 3.0+ (可选)

## 2. 本地开发部署

### 2.1 克隆项目

```bash
git clone <repo-url>
cd multi-agent-collaboration-system
```

### 2.2 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
```

### 2.3 安装依赖

```bash
pip install -r requirements.txt
```

### 2.4 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入实际配置
```

关键配置项：

```env
# LLM
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o

# Redis
REDIS_URL=redis://localhost:6379/0

# PostgreSQL
POSTGRES_URL=postgresql://postgres:password@localhost:5432/multiagent

# MCP Server API Keys
SERPAPI_KEY=your-serpapi-key
TUSHARE_TOKEN=your-tushare-token
```

### 2.5 启动服务

```bash
# 启动Redis
redis-server

# 启动PostgreSQL
# 创建数据库 multiagent

# 启动应用
make run
# 或
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.6 启动MCP Servers

```bash
# 终端1：启动搜索服务
cd mcp-servers/search-server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8081

# 终端2：启动金融服务
cd mcp-servers/financial-server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8082

# 终端3：启动清洗服务
cd mcp-servers/cleaner-server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8083
```

## 3. Docker部署

### 3.1 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件
```

### 3.2 构建镜像

```bash
make docker-build
# 或
docker compose build
```

### 3.3 启动服务

```bash
make docker-up
# 或
docker compose up -d
```

### 3.4 查看日志

```bash
make docker-logs
# 或
docker compose logs -f
```

### 3.5 停止服务

```bash
make docker-down
# 或
docker compose down
```

### 3.6 服务访问

- API: http://localhost:8000
- Swagger文档: http://localhost:8000/docs
- ReDoc文档: http://localhost:8000/redoc

## 4. Kubernetes部署

### 4.1 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
```

### 4.2 创建配置

```bash
# 创建ConfigMap
kubectl apply -f k8s/configmap.yaml

# 创建Secret（需要先创建）
kubectl create secret generic api-keys \
  --from-literal=openai-api-key=sk-your-key \
  --from-literal=serpapi-key=your-key \
  --from-literal=tushare-token=your-token \
  -n multi-agent

kubectl create secret generic db-credentials \
  --from-literal=password=your-password \
  -n multi-agent
```

### 4.3 部署服务

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### 4.4 检查状态

```bash
# 查看Pod状态
kubectl get pods -n multi-agent

# 查看服务状态
kubectl get svc -n multi-agent

# 查看日志
kubectl logs -f deployment/api-gateway -n multi-agent
```

### 4.5 访问服务

```bash
# 端口转发
kubectl port-forward svc/api-gateway 8000:8000 -n multi-agent

# 或通过Ingress访问
# http://report.local
```

## 5. 生产环境配置

### 5.1 LLM配置

```env
# OpenAI
OPENAI_API_KEY=sk-your-production-key
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

# 或使用其他LLM
# ANTHROPIC_API_KEY=your-key
# AZURE_OPENAI_API_KEY=your-key
```

### 5.2 数据库配置

```env
# Redis
REDIS_URL=redis://your-redis-host:6379/0
REDIS_PASSWORD=your-redis-password

# PostgreSQL
POSTGRES_URL=postgresql://user:password@your-pg-host:5432/multiagent
```

### 5.3 监控配置

```env
# Langfuse
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com

# Prometheus
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090
```

### 5.4 日志配置

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## 6. 扩展配置

### 6.1 水平扩展

```bash
# Kubernetes HPA
kubectl autoscale deployment api-gateway \
  --cpu-percent=70 \
  --min=2 \
  --max=10 \
  -n multi-agent
```

### 6.2 负载均衡

使用Nginx Ingress或云厂商负载均衡器。

### 6.3 持久化存储

配置PVC用于Redis和PostgreSQL数据持久化。

## 7. 故障排查

### 7.1 常见问题

1. **Redis连接失败**
   - 检查Redis服务是否启动
   - 检查REDIS_URL配置

2. **PostgreSQL连接失败**
   - 检查PostgreSQL服务是否启动
   - 检查数据库是否创建
   - 检查POSTGRES_URL配置

3. **LLM调用失败**
   - 检查OPENAI_API_KEY配置
   - 检查API配额

4. **MCP Server调用失败**
   - 检查MCP Server是否启动
   - 检查网络连接

### 7.2 日志查看

```bash
# Docker
docker compose logs -f api-gateway

# Kubernetes
kubectl logs -f deployment/api-gateway -n multi-agent
```

### 7.3 健康检查

```bash
curl http://localhost:8000/health
```
