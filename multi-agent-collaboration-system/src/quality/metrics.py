"""质量指标"""

import structlog
from typing import Any
from datetime import datetime

logger = structlog.get_logger()


class QualityMetrics:
    """质量指标收集和分析"""

    def __init__(self):
        self.metrics: dict[str, list[dict[str, Any]]] = {
            "review_scores": [],
            "retry_counts": [],
            "degraded_tasks": [],
            "execution_times": [],
        }

    def record_review_score(self, task_id: str, score: float, passed: bool):
        """记录审核分数"""
        self.metrics["review_scores"].append({
            "task_id": task_id,
            "score": score,
            "passed": passed,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def record_retry_count(self, task_id: str, retry_count: int):
        """记录重试次数"""
        self.metrics["retry_counts"].append({
            "task_id": task_id,
            "retry_count": retry_count,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def record_degraded_task(self, task_id: str, reason: str):
        """记录降级任务"""
        self.metrics["degraded_tasks"].append({
            "task_id": task_id,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def record_execution_time(self, task_id: str, execution_time: float):
        """记录执行时间"""
        self.metrics["execution_times"].append({
            "task_id": task_id,
            "execution_time": execution_time,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_average_score(self) -> float:
        """获取平均审核分数"""
        scores = [m["score"] for m in self.metrics["review_scores"]]
        return sum(scores) / len(scores) if scores else 0.0

    def get_pass_rate(self) -> float:
        """获取通过率"""
        if not self.metrics["review_scores"]:
            return 0.0
        passed = sum(1 for m in self.metrics["review_scores"] if m["passed"])
        return passed / len(self.metrics["review_scores"])

    def get_average_retry_count(self) -> float:
        """获取平均重试次数"""
        counts = [m["retry_count"] for m in self.metrics["retry_counts"]]
        return sum(counts) / len(counts) if counts else 0.0

    def get_degraded_rate(self) -> float:
        """获取降级率"""
        total = len(self.metrics["review_scores"])
        if total == 0:
            return 0.0
        degraded = len(self.metrics["degraded_tasks"])
        return degraded / total

    def get_average_execution_time(self) -> float:
        """获取平均执行时间"""
        times = [m["execution_time"] for m in self.metrics["execution_times"]]
        return sum(times) / len(times) if times else 0.0

    def get_summary(self) -> dict[str, Any]:
        """获取指标摘要"""
        return {
            "average_score": self.get_average_score(),
            "pass_rate": self.get_pass_rate(),
            "average_retry_count": self.get_average_retry_count(),
            "degraded_rate": self.get_degraded_rate(),
            "average_execution_time": self.get_average_execution_time(),
            "total_tasks": len(self.metrics["review_scores"]),
            "timestamp": datetime.utcnow().isoformat(),
        }
