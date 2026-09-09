#!/bin/bash
# 环境设置脚本

set -e

echo "=== 多Agent协作系统 - 环境设置 ==="

# 检查Python版本
echo "检查Python版本..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python版本: $python_version"

# 创建虚拟环境
echo "创建虚拟环境..."
python3 -m venv .venv
source .venv/bin/activate

# 升级pip
echo "升级pip..."
pip install --upgrade pip

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 复制环境变量
if [ ! -f .env ]; then
    echo "创建环境变量文件..."
    cp .env.example .env
    echo "请编辑 .env 文件填入实际配置"
fi

echo "=== 环境设置完成 ==="
echo ""
echo "下一步："
echo "1. 编辑 .env 文件填入实际配置"
echo "2. 启动Redis: redis-server"
echo "3. 启动PostgreSQL并创建数据库"
echo "4. 运行: make run"
