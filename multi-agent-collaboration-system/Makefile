.PHONY: help install dev test lint format run docker-build docker-up docker-down clean

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖
	pip install -r requirements.txt

dev: ## 安装开发依赖
	pip install -e ".[dev]"
	pre-commit install

test: ## 运行测试
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-unit: ## 运行单元测试
	pytest tests/unit -v -m unit

test-integration: ## 运行集成测试
	pytest tests/integration -v -m integration

lint: ## 代码检查
	ruff check src/ tests/
	mypy src/

format: ## 代码格式化
	ruff format src/ tests/
	ruff check --fix src/ tests/

run: ## 启动应用
	uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

run-planner: ## 启动Planner服务
	python -m src.agents.planner

run-executor: ## 启动Executor服务
	python -m src.agents.executor

run-reviewer: ## 启动Reviewer服务
	python -m src.agents.reviewer

docker-build: ## 构建Docker镜像
	docker compose build

docker-up: ## 启动Docker服务
	docker compose up -d

docker-down: ## 停止Docker服务
	docker compose down

docker-logs: ## 查看Docker日志
	docker compose logs -f

clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage
	rm -rf build dist *.egg-info

setup-db: ## 初始化数据库
	PGPASSWORD=$(POSTGRES_PASSWORD) psql -h localhost -U postgres -d multiagent -f scripts/init_db.sql

benchmark: ## 运行性能测试
	python -m tests.performance.benchmark
