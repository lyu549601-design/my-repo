#!/bin/bash
# 部署脚本

set -e

echo "=== 多Agent协作系统 - 部署 ==="

# 检查环境
ENV=${1:-development}
echo "部署环境: $ENV"

case $ENV in
  development)
    echo "本地开发部署..."
    
    # 检查依赖
    if ! command -v python3 &> /dev/null; then
        echo "错误: Python3未安装"
        exit 1
    fi
    
    if ! command -v redis-cli &> /dev/null; then
        echo "警告: Redis未安装，请先安装Redis"
    fi
    
    # 启动服务
    echo "启动应用..."
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
    ;;
    
  docker)
    echo "Docker部署..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        echo "错误: Docker未安装"
        exit 1
    fi
    
    # 构建镜像
    echo "构建镜像..."
    docker compose build
    
    # 启动服务
    echo "启动服务..."
    docker compose up -d
    
    echo "服务已启动"
    echo "API: http://localhost:8000"
    echo "Swagger: http://localhost:8000/docs"
    ;;
    
  kubernetes|k8s)
    echo "Kubernetes部署..."
    
    # 检查kubectl
    if ! command -v kubectl &> /dev/null; then
        echo "错误: kubectl未安装"
        exit 1
    fi
    
    # 创建命名空间
    echo "创建命名空间..."
    kubectl apply -f k8s/namespace.yaml
    
    # 创建配置
    echo "创建配置..."
    kubectl apply -f k8s/configmap.yaml
    
    # 部署服务
    echo "部署服务..."
    kubectl apply -f k8s/deployment.yaml
    kubectl apply -f k8s/service.yaml
    
    echo "部署完成"
    echo "查看状态: kubectl get pods -n multi-agent"
    ;;
    
  *)
    echo "用法: $0 [development|docker|kubernetes]"
    exit 1
    ;;
esac
