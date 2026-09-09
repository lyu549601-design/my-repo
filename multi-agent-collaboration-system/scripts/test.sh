#!/bin/bash
# 测试脚本

set -e

echo "=== 多Agent协作系统 - 测试 ==="

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 解析参数
TEST_TYPE=${1:-all}
COVERAGE=${2:-no}

case $TEST_TYPE in
  unit)
    echo "运行单元测试..."
    if [ "$COVERAGE" = "coverage" ]; then
        pytest tests/unit -v -m unit --cov=src --cov-report=html --cov-report=term-missing
    else
        pytest tests/unit -v -m unit
    fi
    ;;
    
  integration)
    echo "运行集成测试..."
    pytest tests/integration -v -m integration
    ;;
    
  all)
    echo "运行所有测试..."
    if [ "$COVERAGE" = "coverage" ]; then
        pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing
    else
        pytest tests/ -v
    fi
    ;;
    
  lint)
    echo "代码检查..."
    ruff check src/ tests/
    mypy src/
    ;;
    
  format)
    echo "代码格式化..."
    ruff format src/ tests/
    ruff check --fix src/ tests/
    ;;
    
  *)
    echo "用法: $0 [unit|integration|all|lint|format] [coverage]"
    exit 1
    ;;
esac

echo "=== 测试完成 ==="
